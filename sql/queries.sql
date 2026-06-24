-- 1. Top 5 funds by latest AUM
SELECT f.amfi_code, f.scheme_name, f.fund_house, p.aum_crore
FROM fact_performance p
JOIN dim_fund f ON f.amfi_code = p.amfi_code
ORDER BY p.aum_crore DESC
LIMIT 5;

-- 2. Average NAV per month
SELECT f.amfi_code, f.scheme_name, d.year, d.month, ROUND(AVG(n.nav), 4) AS avg_nav
FROM fact_nav n
JOIN dim_date d ON d.date_key = n.date_key
JOIN dim_fund f ON f.amfi_code = n.amfi_code
GROUP BY f.amfi_code, f.scheme_name, d.year, d.month
ORDER BY f.amfi_code, d.year, d.month;

-- 3. SIP year-over-year growth from monthly SIP industry data
SELECT strftime('%Y', month) AS year,
       ROUND(SUM(sip_inflow_crore), 2) AS sip_inflow_crore,
       ROUND(
           100.0 * (SUM(sip_inflow_crore) - LAG(SUM(sip_inflow_crore)) OVER (ORDER BY strftime('%Y', month)))
           / NULLIF(LAG(SUM(sip_inflow_crore)) OVER (ORDER BY strftime('%Y', month)), 0),
           2
       ) AS yoy_growth_pct
FROM monthly_sip_inflows
GROUP BY strftime('%Y', month)
ORDER BY year;

-- 4. Transactions by state
SELECT state, COUNT(*) AS transaction_count, ROUND(SUM(amount_inr), 2) AS total_amount_inr
FROM fact_transactions
GROUP BY state
ORDER BY transaction_count DESC, total_amount_inr DESC;

-- 5. Funds with expense ratio below 1%
SELECT f.amfi_code, f.scheme_name, f.fund_house, f.expense_ratio_pct
FROM dim_fund f
WHERE f.expense_ratio_pct < 1
ORDER BY f.expense_ratio_pct, f.scheme_name;

-- 6. Net inflow by category and year
SELECT category, strftime('%Y', month) AS year, ROUND(SUM(net_inflow_crore), 2) AS net_inflow_crore
FROM category_inflows
GROUP BY category, strftime('%Y', month)
ORDER BY year, net_inflow_crore DESC;

-- 7. Best 3-year risk-adjusted performers
SELECT f.scheme_name, p.return_3yr_pct, p.sharpe_ratio, p.std_dev_ann_pct
FROM fact_performance p
JOIN dim_fund f ON f.amfi_code = p.amfi_code
ORDER BY p.sharpe_ratio DESC, p.return_3yr_pct DESC
LIMIT 10;

-- 8. Monthly redemption share of transaction value
SELECT strftime('%Y-%m', transaction_date) AS month,
       ROUND(SUM(CASE WHEN transaction_type = 'Redemption' THEN amount_inr ELSE 0 END), 2) AS redemption_amount,
       ROUND(SUM(amount_inr), 2) AS total_amount,
       ROUND(100.0 * SUM(CASE WHEN transaction_type = 'Redemption' THEN amount_inr ELSE 0 END) / SUM(amount_inr), 2) AS redemption_share_pct
FROM fact_transactions
GROUP BY strftime('%Y-%m', transaction_date)
ORDER BY month;

-- 9. Latest top holdings by scheme
WITH latest_holdings AS (
    SELECT *, MAX(portfolio_date) OVER (PARTITION BY amfi_code) AS latest_date
    FROM portfolio_holdings
)
SELECT f.scheme_name, h.stock_symbol, h.stock_name, h.sector, h.weight_pct
FROM latest_holdings h
JOIN dim_fund f ON f.amfi_code = h.amfi_code
WHERE h.portfolio_date = h.latest_date
ORDER BY f.scheme_name, h.weight_pct DESC;

-- 10. Benchmark monthly returns
WITH monthly_close AS (
    SELECT index_name,
           strftime('%Y-%m', date) AS month,
           FIRST_VALUE(close_value) OVER (PARTITION BY index_name, strftime('%Y-%m', date) ORDER BY date) AS first_close,
           FIRST_VALUE(close_value) OVER (PARTITION BY index_name, strftime('%Y-%m', date) ORDER BY date DESC) AS last_close
    FROM benchmark_indices
)
SELECT DISTINCT index_name,
       month,
       ROUND(100.0 * (last_close - first_close) / NULLIF(first_close, 0), 2) AS monthly_return_pct
FROM monthly_close
ORDER BY index_name, month;
