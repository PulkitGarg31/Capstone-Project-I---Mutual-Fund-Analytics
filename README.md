# Mutual Fund Analytics — Capstone Project I

Analytics on Indian mutual-fund data. The project is built around **10 provided
datasets** (fund master, NAV history, AUM, flows, performance, holdings,
transactions, benchmarks) and supplemented with **live NAV pulls** from the
public AMFI mirror at [mfapi.in](https://www.mfapi.in/). This repository tracks
the work day by day; **Day 1** covers environment setup and data ingestion.

---

## Project structure

```
.
├── data/
│   ├── raw/                # 10 provided datasets (01_*.csv ... 10_*.csv)
│   │   └── live_api/       # supplementary live NAV pulls from mfapi.in
│   └── processed/          # cleaned, analysis-ready data
├── notebooks/              # exploratory Jupyter notebooks
├── sql/                    # SQL schema / queries (later days)
├── dashboard/              # dashboard app (later days)
├── reports/                # generated reports (e.g. data_quality_summary.md)
├── data_ingestion.py       # load + profile + explore + validate the datasets
├── live_nav_fetch.py       # fetch live NAV history -> data/raw/live_api/
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
# 1) (optional) refresh the supplementary live NAV pulls -> data/raw/live_api/
python live_nav_fetch.py

# 2) Load + profile all 10 provided CSVs, explore fund_master, validate AMFI
#    codes (incl. cross-dataset integrity), write the data-quality report and
#    a cleaned data/processed/nav_history_clean.csv
python data_ingestion.py
```

`data_ingestion.py` is schema-tolerant: it profiles **every** CSV in `data/raw/`
and locates `fund_master` / `nav_history` by filename or columns, so additional
datasets can be dropped in and re-run.

## The 10 provided datasets (`data/raw/`)

| # | File | Grain | Rows | Key |
|---|------|-------|-----:|-----|
| 01 | `fund_master.csv` | one row per scheme | 40 | `amfi_code` |
| 02 | `nav_history.csv` | daily NAV per scheme | 46,000 | `amfi_code` + `date` |
| 03 | `aum_by_fund_house.csv` | quarterly AUM per fund house | 90 | `fund_house` + `date` |
| 04 | `monthly_sip_inflows.csv` | monthly industry SIP | 48 | `month` |
| 05 | `category_inflows.csv` | monthly net inflow per category | 144 | `month` + `category` |
| 06 | `industry_folio_count.csv` | quarterly folio counts | 21 | `month` |
| 07 | `scheme_performance.csv` | returns / risk metrics per scheme | 40 | `amfi_code` |
| 08 | `investor_transactions.csv` | individual investor transactions | 32,778 | `investor_id` |
| 09 | `portfolio_holdings.csv` | top holdings per scheme | 322 | `amfi_code` + `stock_symbol` |
| 10 | `benchmark_indices.csv` | daily index close | 8,050 | `index_name` + `date` |

## Data dictionary (key tables)

**`01_fund_master.csv`** — `amfi_code` (PK), `fund_house`, `scheme_name`,
`category`, `sub_category`, `plan`, `launch_date`, `benchmark`,
`expense_ratio_pct`, `exit_load_pct`, `min_sip_amount`, `min_lumpsum_amount`,
`fund_manager`, `risk_category`, `sebi_category_code`.

**`02_nav_history.csv`** — `amfi_code`, `date` (ISO `YYYY-MM-DD`), `nav`.

**`data/processed/nav_history_clean.csv`** — `02_nav_history` with parsed dates,
numeric NAV, non-positive/duplicate rows removed, sorted ascending per scheme.

## Day 1 — key findings

See [`reports/data_quality_summary.md`](reports/data_quality_summary.md) for the
full report. Headlines:

- **AMFI-code validation passes:** all 40 `fund_master` codes have NAV history,
  no orphans; every `amfi_code` in performance / transactions / holdings also
  exists in `fund_master`.
- The provided NAV history is clean: 46,000 rows, 0 nulls, 0 non-positive NAVs,
  0 duplicate `(amfi_code, date)` pairs, spanning 2022-01-03 → 2026-05-29.
- **Date-parsing pitfall (handled):** the provided data is ISO `YYYY-MM-DD`,
  while the live API is `DD-MM-YYYY`. A naive `dayfirst=True` silently rewrites
  ISO dates (e.g. `2022-01-03` → `2022-03-01`) and drops any day > 12; the loader
  uses a format-robust parser instead.
- **Supplementary live-API note:** 5 of the 6 scheme codes named in the brief
  resolve to a *different* fund on the live AMFI feed (only `118632` = Nippon
  Large Cap matches). The live pulls live under `data/raw/live_api/` and are
  kept separate from the canonical provided data.

## Deliverables (Day 1)

- `data_ingestion.py`, `live_nav_fetch.py`, `requirements.txt`
- 10 provided datasets in `data/raw/`, live pulls in `data/raw/live_api/`,
  cleaned data in `data/processed/`
- `reports/data_quality_summary.md`
- Git repo with the Day 1 commits
