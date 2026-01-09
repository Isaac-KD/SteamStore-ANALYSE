# 🎮 SteamStore Analysis: The Ultimate Indie Game Success Predictor

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![CatBoost](https://img.shields.io/badge/Model-CatBoost-green?style=for-the-badge&logo=pandas&logoColor=white)
![NLP](https://img.shields.io/badge/NLP-Transformers_%26_BERTopic-orange?style=for-the-badge)
![Scraping](https://img.shields.io/badge/Architecture-AsyncIO_%2F_AIMD-red?style=for-the-badge)

> **Master 1 MIND Project - Sorbonne University**
> *A comprehensive Data Science approach to decipher the "Indiepocalypse" market and predict commercial success on Steam.*

---

## 📑 Table of Contents
1. [Scientific Context](#-scientific-context)
2. [Project Architecture](#-project-architecture)
3. [💾 Dataset & Data Dictionary](#-dataset--data-dictionary)
4. [📈 Visualization (Plots)](#-visualization-plots)
5. [🧠 Modeling (NLP & ML)](#-modeling-nlp--ml)
6. [Installation & Reproduction](#-installation--reproduction)

---

## 📖 Scientific Context

The indie game market is oversaturated (power-law effect). This project goes beyond simple sales prediction: it identifies the **structural factors of success** by combining:
* **Tabular Data**: Price, technical features (Co-op, Controller), release dates.
* **Textual Data (NLP)**: Deep semantic analysis of narrative descriptions via Transformers.

**Objectives:**
* **Regression**: Estimate the number of reviews (`log(1+reviews)`) as a proxy for sales.
* **Classification**: Detect "Hits" (>500 reviews, >85% positive).

---

## 🏗️ Project Architecture

The repository is modularly organized to separate collection, processing, and analysis:

```bash
├── 📂 SCRAPPING/          # ⚙️ Ingestion Engine (ETL)
│   ├── SteamScraper.py        # Async core (AsyncIO/Aiohttp) with AIMD rate control.
│   ├── schema.json            # Data Contract: Strict type validation at ingestion.
│   └── launcher.bash          # Robust orchestration script.
│
├── 📂 data/               # 💾 Data & Processing
│   ├── (parquet files)         # Raw and cleaned datasets.
│   ├── cleaning.ipynb          # Data cleaning and train/test split code.
│   └── valide_data.jsonl       # JSON schema.
│
├── 📂 plot/               # 📉 Results Gallery
│   └── (png files)            # Experimentation plots (EDA, SHAP, Confusion matrices).
│
├── 📂 EDA/                # 📊 Exploratory Analysis
│   ├── EDA.ipynb              # Visualization "Lab".
│   └── visualisation.py       # Internal plotting library.
│
├── 📂 embedding/          # 🗣️ NLP & Vectorization
│   ├── embedding.ipynb        # Embedding generation (e5-base-v2 model).
│
└── 📂 Model/              # 🤖 Machine Learning
    ├── 📂 NLP/                # Advanced clustering (BERTopic, K-Means).
    ├── 📂 Validation/         # Cross-validation & model tuning.
    └── 📂 Test/               # Final evaluation on the Test Set.
```

---

## 💾 Dataset & Data Dictionary

The pipeline generates a rich dataset (`.jsonl`) validated by `schema.json`. Key variables include:

### Identifiers & Metadata

| Variable | Type | Description |
| --- | --- | --- |
| `game_id` | `int` | Unique Steam identifier (AppID). |
| `name` | `str` | Official game title. |
| `developers` | `list` | List of development studios. |
| `release_date` | `date` | Release date (transformed for seasonality). |

### Text & Semantics (NLP)

| Variable | Type | Description |
| --- | --- | --- |
| `detailed_description` | `str` | Full description, source for **BERTopic**. |
| `emb_i` | `float` | Dense vector (768 dimensions) from the `e5-base-v2` Transformer. |
| `cluster_BERTopic` | `int` | Identified semantic "Micro-Genre" (e.g., *Roguelike Deckbuilder*). |

### Commercial Metrics & Gameplay

| Variable | Type | Description |
| --- | --- | --- |
| `price` | `float` | Launch price (in Euros). |
| `reviews_count` | `int` | **TARGET**: Total user reviews (proxy for sales). |
| `genres` | `list` | Broad declared genres (e.g., Action, Indie). |
| `categories` | `list` | Technical features (e.g., *Co-op*, *Controller support*). |

---

## 📈 Visualization (Plots)

The `plot/` folder contains visual results from our research:

1. **Market Analysis (EDA)**:
   * "Power Law" distribution showing extreme market inequality.
   * Price vs Popularity curve revealing the "Double-A" quality signal.

2. **Semantic Clustering**:
   * Genre mapping (Mean vs Median) to distinguish "safe" niches from "lottery" genres.

3. **Model Performance**:
   * **Feature Importance (SHAP)**: Ranking of success factors (Tech > Art).
   * **Confusion Matrices**: Model's ability to filter commercial failures.

---

## 🧠 Modeling (NLP & ML)

### Processing Pipeline (see `data/`)

The cleaning and split code ensures:

1. Data is clean and typed (`schema.json`).
2. Train/Test split is rigorous to prevent data leakage.
3. Categorical features are handled natively or via OHE.

### Results (Test Set)

| Task | Metric | Score | Interpretation |
| --- | --- | --- | --- |
| **Regression** | (Log-Space) | **0.746** | Excellent prediction of success order of magnitude. |
| **Classification** | F1-Score (Hit) | **0.46** | Optimal Precision/Recall tradeoff for investment decisions. |

---

## 🛠️ Installation

```bash
git clone https://github.com/Isaac-KD/SteamStore-ANALYSE.git
cd SteamStore-ANALYSE
```

*Note: To start a new data collection, refer to the `SCRAPPING/` folder.*

---

## 👥 Credits

* **Author**: Isaac Kinane
