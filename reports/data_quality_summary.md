# Day 1 — Data Quality Summary

_Generated (UTC): 2026-06-22T11:04:59+00:00_

## 1. Source data

- **Primary:** the 10 provided CSV datasets in `data/raw/` — fund master, NAV history, AUM by fund house, monthly SIP inflows, category inflows, industry folio counts, scheme performance, investor transactions, portfolio holdings and benchmark indices.

- **Supplementary:** live AMFI NAV pulls in `data/raw/live_api/` (via `live_nav_fetch.py`, 6 scheme codes). Known anomaly: 5 of those 6 codes resolve to a *different* fund on the live feed than the assignment brief states — see the table below and `data/raw/live_api/fetch_manifest.csv`.

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
| 01_fund_master.csv | 40 | 15 | constant/empty column(s): ['min_sip_amount'] |
| 02_nav_history.csv | 46000 | 3 | 'date' is not chronologically sorted |
| 03_aum_by_fund_house.csv | 90 | 5 | none |
| 04_monthly_sip_inflows.csv | 48 | 6 | null values present: {'yoy_growth_pct': 12} |
| 05_category_inflows.csv | 144 | 3 | none |
| 06_industry_folio_count.csv | 21 | 6 | none |
| 07_scheme_performance.csv | 40 | 19 | none |
| 08_investor_transactions.csv | 32778 | 13 | none |
| 09_portfolio_holdings.csv | 322 | 8 | constant/empty column(s): ['portfolio_date'] |
| 10_benchmark_indices.csv | 8050 | 3 | 'date' is not chronologically sorted |

## 3. Fund master

- **fund_house** (10): Aditya Birla Sun Life MF, Axis Mutual Fund, DSP Mutual Fund, HDFC Mutual Fund, ICICI Prudential MF, Kotak Mahindra MF, Mirae Asset MF, Nippon India MF, SBI Mutual Fund, UTI Mutual Fund
- **category** (2): Debt, Equity
- **sub_category** (12): ELSS, Flexi Cap, Gilt, Index, Index/ETF, Large & Mid Cap, Large Cap, Liquid, Mid Cap, Short Duration, Small Cap, Value
- **risk_grade** (5): High, Low, Moderate, Moderately High, Very High

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

- fund_master codes: **40**
- nav_history codes: **40**
- Codes in fund_master **missing** from nav_history: **none**
- Codes in nav_history not in fund_master: none
- **Result: ✅ PASS — every fund_master code has NAV history.**

### NAV quality

- NAV rows (raw): 46000
- Null NAVs: 0
- Non-positive NAVs (<= 0): 0
- Unparseable dates: 0
- Duplicate (scheme_code, date) pairs: 0
- Date range: 2022-01-03 → 2026-05-29
- Rows dropped while building `data/processed/nav_history_clean.csv`: 0 (null/unparseable + non-positive + duplicate).

### Per-scheme NAV coverage

| scheme_code | rows | from | to |
|------------:|-----:|------|----|
| 100016 | 1150 | 2022-01-03 | 2026-05-29 |
| 100025 | 1150 | 2022-01-03 | 2026-05-29 |
| 100033 | 1150 | 2022-01-03 | 2026-05-29 |
| 101206 | 1150 | 2022-01-03 | 2026-05-29 |
| 101207 | 1150 | 2022-01-03 | 2026-05-29 |
| 101208 | 1150 | 2022-01-03 | 2026-05-29 |
| 102885 | 1150 | 2022-01-03 | 2026-05-29 |
| 102886 | 1150 | 2022-01-03 | 2026-05-29 |
| 102887 | 1150 | 2022-01-03 | 2026-05-29 |
| 118632 | 1150 | 2022-01-03 | 2026-05-29 |
| 118633 | 1150 | 2022-01-03 | 2026-05-29 |
| 118634 | 1150 | 2022-01-03 | 2026-05-29 |
| 118635 | 1150 | 2022-01-03 | 2026-05-29 |
| 118636 | 1150 | 2022-01-03 | 2026-05-29 |
| 119092 | 1150 | 2022-01-03 | 2026-05-29 |
| 119093 | 1150 | 2022-01-03 | 2026-05-29 |
| 119094 | 1150 | 2022-01-03 | 2026-05-29 |
| 119095 | 1150 | 2022-01-03 | 2026-05-29 |
| 119120 | 1150 | 2022-01-03 | 2026-05-29 |
| 119551 | 1150 | 2022-01-03 | 2026-05-29 |
| 119552 | 1150 | 2022-01-03 | 2026-05-29 |
| 119598 | 1150 | 2022-01-03 | 2026-05-29 |
| 119599 | 1150 | 2022-01-03 | 2026-05-29 |
| 120503 | 1150 | 2022-01-03 | 2026-05-29 |
| 120504 | 1150 | 2022-01-03 | 2026-05-29 |
| 120505 | 1150 | 2022-01-03 | 2026-05-29 |
| 120506 | 1150 | 2022-01-03 | 2026-05-29 |
| 120507 | 1150 | 2022-01-03 | 2026-05-29 |
| 120841 | 1150 | 2022-01-03 | 2026-05-29 |
| 120842 | 1150 | 2022-01-03 | 2026-05-29 |
| 120843 | 1150 | 2022-01-03 | 2026-05-29 |
| 120844 | 1150 | 2022-01-03 | 2026-05-29 |
| 125497 | 1150 | 2022-01-03 | 2026-05-29 |
| 125498 | 1150 | 2022-01-03 | 2026-05-29 |
| 148567 | 1150 | 2022-01-03 | 2026-05-29 |
| 148568 | 1150 | 2022-01-03 | 2026-05-29 |
| 148569 | 1150 | 2022-01-03 | 2026-05-29 |
| 149322 | 1150 | 2022-01-03 | 2026-05-29 |
| 149323 | 1150 | 2022-01-03 | 2026-05-29 |
| 149324 | 1150 | 2022-01-03 | 2026-05-29 |

## 5. Cross-dataset code integrity

Every `amfi_code` in another dataset should exist in `fund_master`:

| File | code col | distinct codes | not in fund_master | examples |
|------|----------|---------------:|-------------------:|----------|
| 01_fund_master.csv | amfi_code | 40 | 0 |  |
| 02_nav_history.csv | amfi_code | 40 | 0 |  |
| 07_scheme_performance.csv | amfi_code | 40 | 0 |  |
| 08_investor_transactions.csv | amfi_code | 40 | 0 |  |
| 09_portfolio_holdings.csv | amfi_code | 34 | 0 |  |
