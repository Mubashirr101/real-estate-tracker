# 🏠 Mumbai Real Estate Price Analysis

[![Live](https://img.shields.io/badge/demo-sqft.mubashirshaikh.com-orange)](https://sqft.mubashirshaikh.com)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B)](https://streamlit.io/)

Scrapes MagicBricks → cleans it properly → figures out what drives price → ships a live estimator.

**[🔗 sqft.mubashirshaikh.com](https://sqft.mubashirshaikh.com)**

## ⚡ Highlights

- 🐛 Found & fixed a scrape bug that priced listings both at ₹0 and ₹1 quadrillion
- 🚩 Sketchy prices flagged, not silently dropped or trusted
- 📍 Locality-aware model, small-sample areas don't get overconfident estimates
- ✅ Cross-validated (5-fold), not a lucky single split
- 📊 R² ≈ 0.88 on log(price)

## 🔧 Pipeline

```
scraper.py  →  eda + cleaning notebook  →  model notebook  →  export script  →  streamlit app
```

## 🛠️ Stack

`pandas` · `scikit-learn` · `Streamlit` · Jupyter

## 🚀 Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 🔁 Retrain

```bash
python train_and_export.py
```

## ⚠️ Limitations

- Median 1 listing/locality, thin areas get flagged in-app
- Directional estimate, not a valuation

