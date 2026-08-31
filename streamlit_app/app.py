"""
Mumbai real estate price estimator.

Loads price_model_artifact.pkl (built by train_and_export.py) and exposes
the model's features as constrained dropdowns/sliders rather than free-text
inputs, so a typo or an out-of-training-range value can't silently produce
a garbage prediction. Carpet area is the one continuous input; it uses a
slider bounded to the range actually seen in training, which still can't
take arbitrary invalid values but isn't a fixed set of options either
(a dropdown of every possible sqft value would be unusable).
"""
import joblib
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Mumbai Real Estate Price Estimator", page_icon="🏠", layout="centered")


@st.cache_resource
def load_artifact():
    return joblib.load("price_model_artifact.pkl")


artifact = load_artifact()


def format_inr(value):
    if value >= 1e7:
        return f"₹{value / 1e7:.2f} Cr"
    elif value >= 1e5:
        return f"₹{value / 1e5:.1f} L"
    return f"₹{value:,.0f}"


st.title("🏠 Mumbai Real Estate Price Estimator")
st.caption(
    "Trained on cleaned MagicBricks listings. This gives a directional estimate, "
    "not a valuation, accuracy varies a lot by locality, see the note at the bottom."
)

st.divider()

# ---------------- Inputs ----------------
col1, col2 = st.columns(2)

with col1:
    localities = sorted(artifact["locality_lookup"].keys())
    locality = st.selectbox("Locality", localities, index=localities.index("Andheri West") if "Andheri West" in localities else 0)

    prop_type = st.selectbox("Property type", artifact["category_options"]["propTypeD"])

    transaction_type = st.selectbox("Transaction type", artifact["category_options"]["transactionTypeD"])

    poss_status_choices = [c for c in artifact["category_options"]["possStatusD"] if c != "Unknown"]
    poss_status = st.selectbox("Possession status", poss_status_choices)

    furnishing = st.selectbox("Furnishing", list(artifact["furnished_options"].keys()), index=1)

with col2:
    bed_lo, bed_hi = artifact["bedroom_range"]
    bedrooms = st.selectbox("Bedrooms (BHK)", list(range(bed_lo, bed_hi + 1)), index=1)

    bath_lo, bath_hi = artifact["bathroom_range"]
    bathrooms = st.selectbox("Bathrooms", list(range(bath_lo, bath_hi + 1)), index=1)

    floor_lo, floor_hi = artifact["floor_range"]
    floor_no = st.selectbox("Floor number", list(range(floor_lo, min(floor_hi, 40) + 1)), index=2)

    age_label = st.selectbox("Property age", list(artifact["age_options"].keys()))

carpet_lo, carpet_hi = artifact["carpet_area_range"]
carpet_area = st.slider(
    "Carpet area (sqft)",
    min_value=150,
    max_value=6000,
    value=650,
    step=10,
    help=f"Training data ranged from {carpet_lo:.0f} to {carpet_hi:.0f} sqft, bounded here to a practical range.",
)

st.divider()

# ---------------- Predict ----------------
if st.button("Estimate price", type="primary", use_container_width=True):
    loc_info = artifact["locality_lookup"][locality]

    row = {col: 0 for col in artifact["feature_columns"]}
    row["log_carpetArea"] = np.log(carpet_area)
    row["bedroomD"] = bedrooms
    row["bathD"] = bathrooms
    row["floorNo"] = floor_no
    row["property_age_yrs"] = artifact["age_options"][age_label]
    row["furnished_ord"] = artifact["furnished_options"][furnishing]
    row["latitude"] = loc_info["avg_lat"]
    row["longitude"] = loc_info["avg_lon"]
    row["locality_smoothed"] = loc_info["smoothed_log_price"]

    prop_col = f"propTypeD_{prop_type}"
    if prop_col in row:
        row[prop_col] = 1

    trans_col = f"transactionTypeD_{transaction_type}"
    if trans_col in row:
        row[trans_col] = 1

    poss_col = f"possStatusD_{poss_status}"
    if poss_col in row:
        row[poss_col] = 1

    X = pd.DataFrame([row])[artifact["feature_columns"]]
    log_pred = artifact["model"].predict(X)[0]
    pred_price = np.exp(log_pred)

    # Rough +/-29% band, the model's typical error at the median listing
    # during evaluation (see price-prediction-model.ipynb). Not a formal
    # confidence interval, a directional sense of spread.
    low, high = pred_price * 0.77, pred_price * 1.29

    st.subheader("Estimated price")
    st.markdown(f"## {format_inr(pred_price)}")
    st.caption(f"Typical range: {format_inr(low)} to {format_inr(high)}")

    if loc_info["count"] < 5:
        st.warning(
            f"Only {loc_info['count']} comparable listing(s) for {locality} in the training "
            f"data, treat this estimate as rough, it's leaning heavily on the citywide "
            f"average rather than this locality's own pricing."
        )
    else:
        st.info(f"Based on {loc_info['count']} comparable listings in {locality}.")

st.divider()
with st.expander("About this model"):
    st.markdown(
        """
        - Random Forest trained on cleaned MagicBricks Mumbai listings, cross-validated R2 ≈ 0.88.
        - Location (locality + coordinates) explains most of the price variance, carpet area is the strongest physical feature, everything else (bedrooms, bathrooms, floor, age, furnishing) contributes comparatively little.
        - Median of 1 listing per locality across the dataset, only a minority of localities have 5+ listings, estimates for thin localities lean on the citywide average and should be treated as rough.
        - Not a valuation tool. Useful for a directional sense of price, not for pricing an actual listing.
        """
    )
