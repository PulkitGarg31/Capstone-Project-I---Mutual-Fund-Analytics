# Mutual Fund Analytics — Capstone Project I

An analytics project on Indian mutual-fund NAV data, sourced from the public
AMFI mirror API at [mfapi.in](https://www.mfapi.in/). This repository tracks the
project day by day; **Day 1** covers environment setup and data ingestion.

---

## Project structure

```
.
├── data/
│   ├── raw/            # immutable source data (live API pulls, provided CSVs)
│   └── processed/      # cleaned, analysis-ready data
├── notebooks/          # exploratory Jupyter notebooks
├── sql/                # SQL schema / queries (later days)
├── dashboard/          # dashboard app (later days)
├── reports/            # generated reports (e.g. data_quality_summary.md)
├── data_ingestion.py   # load + profile + explore + validate raw CSVs
├── live_nav_fetch.py   # fetch live NAV history from mfapi.in -> data/raw
├── requirements.txt
└── README.md
```

## Setup

```bash
python -m venv .venv          # optional but recommended
.\.venv\Scripts\activate      # Windows PowerShell
pip install -r requirements.txt
```

Dependencies: pandas, numpy, matplotlib, seaborn, plotly, sqlalchemy, requests,
scipy, jupyter.

## Usage (Day 1 pipeline)

```bash
# 1) Fetch live NAV history for the 6 assignment scheme codes -> data/raw/
python live_nav_fetch.py

# 2) Load + profile every CSV in data/raw, explore fund_master,
#    validate AMFI codes, and write reports/data_quality_summary.md
python data_ingestion.py
```

`data_ingestion.py` is schema-tolerant: drop any additional CSVs (e.g. the 10
provided datasets) into `data/raw/` and re-run — they are profiled
automatically, and `fund_master` / `nav_history` are located by filename or by
their columns.

## Data dictionary

**`data/raw/fund_master.csv`** — one row per scheme.

| column | meaning |
|--------|---------|
| `scheme_code` | AMFI scheme code (primary key) |
| `scheme_name` | full scheme name from AMFI |
| `fund_house` | AMC / fund house |
| `scheme_type`, `scheme_category` | AMFI classification (raw) |
| `category`, `sub_category` | `scheme_category` split on `-` |
| `risk_grade` | **derived** riskometer grade (heuristic from sub-category) |
| `plan_type`, `option` | Direct/Regular and Growth/IDCW (parsed from name) |
| `isin_growth`, `isin_div_reinvestment` | ISINs |

**`data/raw/nav_history.csv`** — long format, many rows per scheme:
`scheme_code, scheme_name, date (DD-MM-YYYY, raw), nav (raw)`.

**`data/processed/nav_history_clean.csv`** — parsed `date` (datetime), numeric
`nav`, de-duplicated, non-positive NAVs removed, sorted ascending per scheme.

## Day 1 — key findings

See [`reports/data_quality_summary.md`](reports/data_quality_summary.md) for the
full report. Headlines:

- **The brief's scheme-code labels are mostly wrong.** 5 of the 6 codes resolve
  to a different fund on the live AMFI feed (e.g. `125497` is *SBI Small Cap*,
  not *HDFC Top 100*; only `118632` = Nippon Large Cap matches). All downstream
  work keys on the live AMFI scheme code / name, not the brief label.
- The 10 "provided" CSV datasets were not supplied, so the pipeline was
  bootstrapped from live AMFI data for the 6 codes (≈19.9k NAV rows, 2012–2026).
- AMFI-code validation **passes**: every `fund_master` code has NAV history;
  no orphan codes.
- Raw quirks handled: NAV dates are strings sorted newest-first; one bad
  `0.0` NAV (scheme `120503`, 2013-04-07) is dropped during cleaning.

## Deliverables (Day 1)

- `data_ingestion.py`, `live_nav_fetch.py`, `requirements.txt`
- Raw data in `data/raw/`, cleaned data in `data/processed/`
- `reports/data_quality_summary.md`
- Git repo with commit **"Day 1: Data ingestion complete"**
