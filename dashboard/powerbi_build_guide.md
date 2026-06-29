# Bluestock Mutual Fund Dashboard - Power BI Build Guide

Power BI Desktop was not available in this environment, so a native `.pbix` could not be generated here. Use this guide to recreate the dashboard from the committed data sources and exports.

## Data Sources

Import these cleaned CSVs from `data/processed/`:

| Table | Rows | Columns |
|---|---:|---:|
| `fund_master` | 40 | 15 |
| `nav_history` | 64320 | 3 |
| `aum_by_fund_house` | 90 | 5 |
| `monthly_sip_inflows` | 48 | 6 |
| `category_inflows` | 144 | 3 |
| `industry_folio_count` | 21 | 6 |
| `investor_transactions` | 32778 | 15 |
| `benchmark_indices` | 8050 | 3 |
| `fund_scorecard` | 40 | 37 |
| `alpha_beta` | 40 | 7 |

All dashboard source files were loaded and verified by `generate_dashboard.py`; see `dashboard/data_model_manifest.csv`.

## Relationships

- `fund_master.amfi_code` one-to-many `nav_history.amfi_code`
- `fund_master.amfi_code` one-to-many `investor_transactions.amfi_code`
- `fund_master.amfi_code` one-to-one `fund_scorecard.amfi_code`
- `fund_master.amfi_code` one-to-one `alpha_beta.amfi_code`
- Use a calendar table with `date` relationships to `nav_history.date`, `aum_by_fund_house.date`, `monthly_sip_inflows.month`, `category_inflows.month`, `industry_folio_count.month`, `investor_transactions.transaction_date`, and `benchmark_indices.date`.

## Theme

Import `dashboard/bluestock_theme.json` through View > Themes > Browse for themes.

## Pages

### Page 1 - Industry Overview

- KPI cards: Total AUM, latest SIP inflow, total folios, schemes.
- Line chart: industry AUM trend.
- Bar chart: AUM by AMC.
- Supporting bar: scheme count by category and plan.

### Page 2 - Fund Performance

- Scatter: `cagr_3yr_pct` on X, `annualized_volatility_pct` on Y, bubble size `aum_crore`.
- Table: sortable `fund_scorecard`.
- Line: selected top fund NAV indexed against NIFTY50 and NIFTY100.
- Slicers: fund house, category, plan.
- Drill-through target: NAV detail page filtered by `amfi_code`.

### Page 3 - Investor Analytics

- Bar: transaction amount by state.
- Donut: SIP, Lumpsum, Redemption amount split.
- Bar: age group vs average SIP amount.
- Line: monthly transaction volume.
- Slicers: state, age group, city tier.

### Page 4 - SIP & Market Trends

- Dual-axis chart: SIP inflow bars and NIFTY50 line.
- Heatmap: monthly category net inflows.
- Bar: top 5 categories by net inflow in FY25.

## Exported Deliverables

- `dashboard/Dashboard.pdf`
- `dashboard/pages/page_1_industry_overview.png`
- `dashboard/pages/page_2_fund_performance.png`
- `dashboard/pages/page_3_investor_analytics.png`
- `dashboard/pages/page_4_sip_market_trends.png`

## Native PBIX Note

Creating `bluestock_mf_dashboard.pbix` requires Power BI Desktop. Once Desktop is available, import the CSVs above, apply the theme and relationships, recreate the visuals using the page specs, then save as `dashboard/bluestock_mf_dashboard.pbix`.
