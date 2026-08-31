# Mumbai Real Estate Price Estimator

Streamlit app wrapping the Random Forest model from `price-prediction-model.ipynb`.

## Files

- `train_and_export.py` reproduces the notebook's cleaning/feature pipeline, refits the model on the full usable dataset (987 rows, all of it rather than just the 80% CV split, since evaluation already happened in the notebook), and saves everything the app needs into `price_model_artifact.pkl`.
- `app.py` the Streamlit UI. Loads the artifact, nothing in it depends on pandas/sklearn version quirks from training, it just builds a feature row and calls `.predict()`.
- `price_model_artifact.pkl` the trained model plus all lookup tables (locality stats, category options, medians, ranges) bundled together, this is what actually ships.
- `requirements.txt`

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`.

## Retraining

If `cleaned_dataset_final.csv` gets updated (more scraped listings, further cleaning), rerun:

```bash
python train_and_export.py
```

This regenerates `price_model_artifact.pkl` in place, `app.py` doesn't need any changes, it reads whatever dropdown options and ranges the new artifact contains.

## Two fixes made during export that weren't in the notebook

1. **`possStatusD` consolidated.** The raw data had "Ready to Move" and "Ready To Move" as separate categories (casing bug) plus 23 specific possession dates ("Dec '27", "Jun '30", etc.) with 1-7 listings each. Collapsed into `Ready to Move` / `Under Construction`, cut the feature count from 44 to 22 and made the dropdown usable instead of a 25-option date picker most of which had almost no training data behind them.
2. **`transactionTypeD` restricted to Resale/New Property.** One `Rent` row existed in the raw data (already excluded, it had no price), explicitly dropped from the dropdown too since the model has zero training signal for it.

## Design choice: why carpet area is a slider, not a dropdown

Every categorical feature (locality, property type, transaction type, possession status, furnishing, bedroom/bathroom count, floor, age) is a `selectbox`, a fixed list, no free text, no way to enter something the model wasn't trained on. Carpet area is continuous, so it's a slider bounded to a practical range (150 to 6000 sqft) rather than either free-text entry (the thing being avoided) or an unusably long list of every possible sqft value.

## Known limitation, carried over from the notebook

Median of 1 listing per locality, only 54 of 265 original localities had 5+. The app shows a warning when the selected locality has under 5 comparable listings in training, telling the user the estimate is leaning on the citywide average rather than local data. This is a data coverage problem, not something the app can fix, more scraped listings per locality is the actual lever.
