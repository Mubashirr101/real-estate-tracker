"""
Reproduces the cleaning/feature pipeline from price-prediction-model.ipynb
and refits the final model (Random Forest, feature set C) on the full usable
dataset, then exports everything a Streamlit app needs to make predictions
without re-running any notebook.

Two small fixes applied here that weren't in the notebook, since this is
now a production artifact rather than an analysis pass:
1. possStatusD had two casings of the same value ("Ready to Move" / "Ready
   To Move") plus 23 near-singleton specific possession dates (1-7 rows
   each). Consolidated into 3 categories: Ready to Move, Under Construction,
   and folded "Immediately" into Ready to Move (same meaning). The granular
   dates weren't carrying enough data per bucket to mean anything, and made
   for an unusable 25-option dropdown.
2. transactionTypeD had one 'Rent' row, already dropped since it had no
   price, but excluded explicitly from the dropdown options too, since
   the model has zero training signal for that category.
"""
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

RANDOM_STATE = 42

# ---------------- Load ----------------
df = pd.read_csv(r"model_training\cleaned_dataset_final.csv")
df = df.dropna(subset=['price']).copy()

unverified = df['review_high_psf'] | df['review_low_psf']
pool = df[~unverified].copy()
print(f"modeling pool: {pool.shape}")

# ---------------- possStatusD consolidation ----------------
def consolidate_poss_status(val):
    if pd.isna(val):
        return 'Unknown'
    v = str(val).strip()
    if v.lower() in ('ready to move', 'immediately'):
        return 'Ready to Move'
    if v == 'Under Construction':
        return 'Under Construction'
    return 'Under Construction'  # any specific future date is still "under construction"

pool['possStatusD'] = pool['possStatusD'].apply(consolidate_poss_status)

# ---------------- transactionTypeD: drop categories with no real signal ----------------
pool = pool[pool['transactionTypeD'].isin(['Resale', 'New Property'])].copy()
print(f"after restricting transaction type to Resale/New Property: {pool.shape}")

# ---------------- carpetArea recovery ----------------
both_present = pool.dropna(subset=['carpetArea', 'coveredArea'])
both_present = both_present[both_present['coveredArea'] > 0]
loading_ratio = (both_present['carpetArea'] / both_present['coveredArea']).median()
recoverable = pool['carpetArea'].isna() & pool['coveredArea'].notna()
pool.loc[recoverable, 'carpetArea'] = pool.loc[recoverable, 'coveredArea'] * loading_ratio
pool['log_carpetArea'] = np.log(pool['carpetArea'])

# ---------------- imputation ----------------
impute_cols = ['bathD', 'floorNo', 'property_age_yrs', 'furnished_ord', 'latitude', 'longitude']
medians = {}
for col in impute_cols:
    med = pool[col].median()
    medians[col] = med
    pool[f"{col}_was_missing"] = pool[col].isna().astype(int)
    pool[col] = pool[col].fillna(med)

pool['locSeoName'] = pool['locSeoName'].fillna('Unknown')
pool = pool.dropna(subset=['log_carpetArea', 'bedroomD', 'log_price']).copy()
print(f"final modeling pool: {pool.shape}")

# ---------------- categorical encoding ----------------
categorical_cols = ['propTypeD', 'transactionTypeD', 'possStatusD']
for col in categorical_cols:
    pool[col] = pool[col].fillna('Unknown')

encoded = pd.get_dummies(pool[categorical_cols], drop_first=True)
category_options = {col: sorted(pool[col].unique().tolist()) for col in categorical_cols}

# ---------------- smoothed locality encoding ----------------
def smoothed_target_encode(series, target, smoothing=10, global_mean=None):
    if global_mean is None:
        global_mean = target.mean()
    stats = target.groupby(series).agg(['mean', 'count'])
    smoothed = (stats['count'] * stats['mean'] + smoothing * global_mean) / (stats['count'] + smoothing)
    return series.map(smoothed).fillna(global_mean), stats, global_mean

pool['locality_smoothed'], locality_stats, global_mean_log_price = smoothed_target_encode(
    pool['locSeoName'], pool['log_price'], smoothing=10
)

# per-locality lookup for the UI: smoothed price, avg coordinates, listing count
locality_stats_dict = locality_stats.to_dict('index')
locality_lookup = {}
for loc in pool['locSeoName'].unique():
    rows = pool[pool['locSeoName'] == loc]
    stats_row = locality_stats_dict.get(loc, {})
    locality_lookup[loc] = {
        'smoothed_log_price': float(stats_row.get('mean', global_mean_log_price)),
        'count': int(stats_row.get('count', 0)),
        'avg_lat': float(rows['latitude'].mean()),
        'avg_lon': float(rows['longitude'].mean()),
    }

# ---------------- feature set C (physical + coordinates + smoothed locality) ----------------
physical_features = ['log_carpetArea', 'bedroomD', 'bathD', 'floorNo', 'property_age_yrs', 'furnished_ord']
missing_flags = [f"{c}_was_missing" for c in impute_cols]

X = pd.concat([
    pool[physical_features + missing_flags],
    encoded,
    pool[['latitude', 'longitude', 'locality_smoothed']]
], axis=1)
y = pool['log_price']

feature_columns = X.columns.tolist()
print(f"feature count: {len(feature_columns)}")

# ---------------- refit on full usable data for deployment ----------------
# CV during analysis already validated ~0.88 R2 (see price-prediction-model.ipynb).
# For the deployed artifact, refitting on 100% of the clean pool rather than
# the 80% train split used for evaluation, more data in, better real-world fit.
model = RandomForestRegressor(n_estimators=300, random_state=RANDOM_STATE)
model.fit(X, y)
print(f"refit on {len(X)} rows, {len(feature_columns)} features")

# age bucket labels (from acD) -> numeric midpoint, needed for the age dropdown
age_options = {
    'New Construction': 0,
    '0 to 1 years': 0.5,
    'Less than 5 years': 3,
    '5 to 10 years': 7.5,
    '10 to 15 years': 12.5,
    '15 to 20 years': 17.5,
    'Above 20 years': 25,
}

furnished_options = {'Unfurnished': 0, 'Semi-Furnished': 1, 'Furnished': 2}

artifact = {
    'model': model,
    'feature_columns': feature_columns,
    'physical_features': physical_features,
    'missing_flags': missing_flags,
    'impute_cols': impute_cols,
    'medians': medians,
    'categorical_cols': categorical_cols,
    'category_options': category_options,
    'age_options': age_options,
    'furnished_options': furnished_options,
    'locality_lookup': locality_lookup,
    'global_mean_log_price': global_mean_log_price,
    'carpet_area_range': (float(pool['carpetArea'].min()), float(pool['carpetArea'].max())),
    'bedroom_range': (int(pool['bedroomD'].min()), int(pool['bedroomD'].max())),
    'bathroom_range': (int(pool['bathD'].min()), int(pool['bathD'].max())),
    'floor_range': (int(pool['floorNo'].min()), int(pool['floorNo'].max())),
}

joblib.dump(artifact, r'model_training\price_model_artifact.pkl')
print("saved price_model_artifact.pkl")
print(f"localities available: {len(locality_lookup)}")
print(f"propTypeD options: {category_options['propTypeD']}")
print(f"transactionTypeD options: {category_options['transactionTypeD']}")
print(f"possStatusD options: {category_options['possStatusD']}")
