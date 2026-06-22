# Day 1 — Data Quality Summary

_Generated (UTC): 2026-06-22T07:53:10+00:00_

## 1. Source note / known anomaly

- The 10 provided CSV datasets were **not present** in `data/raw/` at run time. The pipeline was bootstrapped from **live AMFI NAV data** (mfapi.in) for the 6 assignment scheme codes so that load → explore → validate runs end-to-end. `data_ingestion.py` auto-loads any additional CSVs later dropped into `data/raw/`.

- **The brief's scheme-code labels are largely wrong.** Each code was checked against the live AMFI feed; the API scheme name is treated as the source of truth. See the mapping below and `data/raw/fetch_manifest.csv`.

### Brief label vs live AMFI scheme name

| Code | Brief label (assignment) | Live API scheme name | Matches? |
|-----:|--------------------------|----------------------|:--------:|
| 125497 | HDFC Top 100 Direct | SBI Small Cap Fund - Direct Plan - Growth | ❌ |
| 119551 | SBI Bluechip | Aditya Birla Sun Life Banking & PSU Debt Fund  - DIRECT - IDCW | ❌ |
| 120503 | ICICI Bluechip | Axis ELSS Tax Saver Fund - Direct Plan - Growth Option | ❌ |
| 118632 | Nippon Large Cap | Nippon India Large Cap Fund - Direct Plan Growth Plan - Growth Option | ✅ |
| 119092 | Axis Bluechip | HDFC Money Market Fund - Growth Option - Direct Plan | ❌ |
| 120841 | Kotak Bluechip | quant Mid Cap Fund - Growth Option - Direct Plan | ❌ |

**5 of 6 codes resolve to a different fund than the brief states.** Downstream analysis must key on the live AMFI scheme name / code, not the brief label.


## 2. File inventory

| File | Rows | Cols | Anomalies |
|------|-----:|-----:|-----------|
| fetch_manifest.csv | 6 | 11 | null values present: {'error': 6}; constant/empty column(s): ['status', 'latest_date', 'error', 'fetched_at_utc'] |
| fund_master.csv | 6 | 12 | null values present: {'isin_div_reinvestment': 5}; constant/empty column(s): ['scheme_type', 'plan_type'] |
| nav_118632.csv | 3312 | 2 | 'date' is sorted NEWEST-first (descending) |
| nav_119092.csv | 3579 | 2 | 'date' is sorted NEWEST-first (descending) |
| nav_119551.csv | 3250 | 2 | 'date' is sorted NEWEST-first (descending) |
| nav_120503.csv | 3321 | 2 | 'date' is sorted NEWEST-first (descending) |
| nav_120841.csv | 3315 | 2 | 'date' is sorted NEWEST-first (descending) |
| nav_125497.csv | 3105 | 2 | 'date' is sorted NEWEST-first (descending) |
| nav_history.csv | 19882 | 4 | 'date' is not chronologically sorted |

## 3. Fund master

- **fund_house** (6): Aditya Birla Sun Life Mutual Fund, Axis Mutual Fund, HDFC Mutual Fund, Nippon India Mutual Fund, SBI Mutual Fund, quant Mutual Fund
- **category** (2): Debt Scheme, Equity Scheme
- **sub_category** (6): Banking and PSU Fund, ELSS, Large Cap Fund, Mid Cap Fund, Money Market Fund, Small Cap Fund
- **risk_grade** (3): High, Low to Moderate, Very High

### AMFI scheme-code structure

> AMFI scheme codes are unique numeric identifiers assigned by the Association of
> Mutual Funds in India (AMFI). Key properties relevant to this project:
> 
>   * They are (currently) 6-digit integers, e.g. 119551, 125497.
>   * One code maps to exactly ONE (scheme x plan x option) combination. The same
>     fund therefore has DIFFERENT codes for its Direct vs Regular plans and for
>     its Growth vs IDCW/Dividend options.
>   * Codes are not contiguous per fund house; they are allocated over time as
>     schemes launch, so adjacent codes are unrelated.
>   * mfapi.in keys its NAV history endpoint (/mf/<code>) on this exact code, so
>     the AMFI code is the natural primary/foreign key linking fund_master
>     (one row per scheme) to nav_history (many NAV observations per scheme).

## 4. AMFI code validation

- fund_master codes: **6**
- nav_history codes: **6**
- Codes in fund_master **missing** from nav_history: **none**
- Codes in nav_history not in fund_master: none
- **Result: ✅ PASS — every fund_master code has NAV history.**

### NAV quality

- NAV rows (raw): 19882
- Null NAVs: 0
- Non-positive NAVs (<= 0): 1
  - offending row: {'scheme_code': 120503, 'date': '07-04-2013', 'nav': 0.0}
- Unparseable dates: 0
- Duplicate (scheme_code, date) pairs: 0
- Date range: 2012-12-31 → 2026-06-19
- Rows dropped while building `data/processed/nav_history_clean.csv`: 1 (null/unparseable + non-positive + duplicate).

### Per-scheme NAV coverage

| scheme_code | rows | from | to |
|------------:|-----:|------|----|
| 118632 | 3312 | 2013-01-02 | 2026-06-19 |
| 119092 | 3579 | 2012-12-31 | 2026-06-19 |
| 119551 | 3250 | 2013-01-02 | 2026-06-19 |
| 120503 | 3321 | 2013-01-02 | 2026-06-19 |
| 120841 | 3315 | 2013-01-07 | 2026-06-19 |
| 125497 | 3105 | 2013-11-18 | 2026-06-19 |
