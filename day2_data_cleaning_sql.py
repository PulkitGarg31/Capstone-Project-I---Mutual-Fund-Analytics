"""
Day 2 - Data cleaning + SQLite star-schema load.

Run:
    python day2_data_cleaning_sql.py

Outputs:
    * data/processed/*_clean.csv for all 10 source datasets
    * bluestock_mf.db
    * sql/schema.sql
    * sql/queries.sql
    * data_dictionary.md
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import warnings

import pandas as pd
from sqlalchemy import create_engine, text


BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
SQL_DIR = BASE_DIR / "sql"
DB_PATH = BASE_DIR / "bluestock_mf.db"
DATA_DICTIONARY_PATH = BASE_DIR / "data_dictionary.md"
SCHEMA_PATH = SQL_DIR / "schema.sql"
QUERIES_PATH = SQL_DIR / "queries.sql"


RAW_FILES = {
    "fund_master": "01_fund_master.csv",
    "nav_history": "02_nav_history.csv",
    "aum_by_fund_house": "03_aum_by_fund_house.csv",
    "monthly_sip_inflows": "04_monthly_sip_inflows.csv",
    "category_inflows": "05_category_inflows.csv",
    "industry_folio_count": "06_industry_folio_count.csv",
    "scheme_performance": "07_scheme_performance.csv",
    "investor_transactions": "08_investor_transactions.csv",
    "portfolio_holdings": "09_portfolio_holdings.csv",
    "benchmark_indices": "10_benchmark_indices.csv",
}

KYC_STATUSES = {"Verified", "Pending", "Rejected"}
TRANSACTION_TYPE_MAP = {
    "sip": "SIP",
    "systematic investment plan": "SIP",
    "lumpsum": "Lumpsum",
    "lump sum": "Lumpsum",
    "one time": "Lumpsum",
    "redemption": "Redemption",
    "redeem": "Redemption",
}


@dataclass
class CleanResult:
    name: str
    raw_rows: int
    clean_rows: int
    duplicate_rows_removed: int
    invalid_rows_removed: int
    notes: list[str]


def parse_date(series: pd.Series) -> pd.Series:
    """Parse ISO, Indian, or month-level dates deterministically."""
    values = series.astype("string").str.strip()
    attempts = [
        {"format": "%Y-%m-%d"},
        {"format": "%d-%m-%Y"},
        {"format": "%Y-%m"},
        {"dayfirst": False},
        {"dayfirst": True},
    ]
    best = None
    best_valid = -1
    for kwargs in attempts:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            parsed = pd.to_datetime(values, errors="coerce", **kwargs)
        valid = int(parsed.notna().sum())
        if valid > best_valid:
            best = parsed
            best_valid = valid
    return best


def to_number(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def normalize_strings(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].astype("string").str.strip()
    return df


def read_raw(name: str) -> pd.DataFrame:
    return pd.read_csv(RAW_DIR / RAW_FILES[name])


def write_clean(name: str, df: pd.DataFrame) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_DIR / f"{name}_clean.csv", index=False)


def clean_fund_master() -> tuple[pd.DataFrame, CleanResult]:
    name = "fund_master"
    raw = read_raw(name)
    df = normalize_strings(raw.copy())
    df["amfi_code"] = pd.to_numeric(df["amfi_code"], errors="coerce").astype("Int64")
    df["launch_date"] = parse_date(df["launch_date"]).dt.date
    df = to_number(
        df,
        [
            "expense_ratio_pct",
            "exit_load_pct",
            "min_sip_amount",
            "min_lumpsum_amount",
        ],
    )
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["amfi_code"], keep="first")
    valid = df["amfi_code"].notna() & df["scheme_name"].notna()
    invalid = int((~valid).sum())
    df = df.loc[valid].sort_values("amfi_code").reset_index(drop=True)
    return df, CleanResult(name, len(raw), len(df), before_dedup - len(df), invalid, [])


def clean_nav_history() -> tuple[pd.DataFrame, CleanResult]:
    name = "nav_history"
    raw = read_raw(name)
    df = raw.copy()
    df["amfi_code"] = pd.to_numeric(df["amfi_code"], errors="coerce").astype("Int64")
    df["date"] = parse_date(df["date"])
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")

    valid = df["amfi_code"].notna() & df["date"].notna() & (df["nav"] > 0)
    invalid = int((~valid).sum())
    df = df.loc[valid].drop_duplicates(subset=["amfi_code", "date"], keep="last")
    deduped_rows = int(valid.sum()) - len(df)
    df = df.sort_values(["amfi_code", "date"])

    filled_parts = []
    filled_rows = 0
    for amfi_code, group in df.groupby("amfi_code", sort=True):
        group = group.set_index("date").sort_index()
        full_index = pd.date_range(group.index.min(), group.index.max(), freq="D")
        expanded = group.reindex(full_index)
        expanded["amfi_code"] = amfi_code
        expanded["nav"] = expanded["nav"].ffill()
        filled_rows += int(expanded["nav"].isna().sum() == 0) * (len(expanded) - len(group))
        expanded = expanded.reset_index(names="date")
        filled_parts.append(expanded[["amfi_code", "date", "nav"]])
    cleaned = pd.concat(filled_parts, ignore_index=True)
    cleaned["date"] = cleaned["date"].dt.date
    notes = [f"Forward-filled {filled_rows} holiday/weekend NAV rows across scheme date ranges."]
    return cleaned, CleanResult(name, len(raw), len(cleaned), deduped_rows, invalid, notes)


def clean_aum_by_fund_house() -> tuple[pd.DataFrame, CleanResult]:
    name = "aum_by_fund_house"
    raw = read_raw(name)
    df = normalize_strings(raw.copy())
    df["date"] = parse_date(df["date"]).dt.date
    df = to_number(df, ["aum_lakh_crore", "aum_crore", "num_schemes"])
    valid = df["date"].notna() & df["fund_house"].notna() & (df["aum_crore"] > 0)
    invalid = int((~valid).sum())
    before = int(valid.sum())
    df = df.loc[valid].drop_duplicates(subset=["date", "fund_house"], keep="last")
    return df.sort_values(["date", "fund_house"]).reset_index(drop=True), CleanResult(
        name, len(raw), len(df), before - len(df), invalid, []
    )


def clean_monthly_sip_inflows() -> tuple[pd.DataFrame, CleanResult]:
    name = "monthly_sip_inflows"
    raw = read_raw(name)
    df = raw.copy()
    df["month"] = parse_date(df["month"]).dt.to_period("M").dt.to_timestamp().dt.date
    df = to_number(
        df,
        [
            "sip_inflow_crore",
            "active_sip_accounts_crore",
            "new_sip_accounts_lakh",
            "sip_aum_lakh_crore",
            "yoy_growth_pct",
        ],
    )
    valid = df["month"].notna() & (df["sip_inflow_crore"] > 0)
    invalid = int((~valid).sum())
    before = int(valid.sum())
    df = df.loc[valid].drop_duplicates(subset=["month"], keep="last")
    return df.sort_values("month").reset_index(drop=True), CleanResult(
        name, len(raw), len(df), before - len(df), invalid, []
    )


def clean_category_inflows() -> tuple[pd.DataFrame, CleanResult]:
    name = "category_inflows"
    raw = read_raw(name)
    df = normalize_strings(raw.copy())
    df["month"] = parse_date(df["month"]).dt.to_period("M").dt.to_timestamp().dt.date
    df = to_number(df, ["net_inflow_crore"])
    valid = df["month"].notna() & df["category"].notna() & df["net_inflow_crore"].notna()
    invalid = int((~valid).sum())
    before = int(valid.sum())
    df = df.loc[valid].drop_duplicates(subset=["month", "category"], keep="last")
    return df.sort_values(["month", "category"]).reset_index(drop=True), CleanResult(
        name, len(raw), len(df), before - len(df), invalid, []
    )


def clean_industry_folio_count() -> tuple[pd.DataFrame, CleanResult]:
    name = "industry_folio_count"
    raw = read_raw(name)
    df = raw.copy()
    df["month"] = parse_date(df["month"]).dt.to_period("M").dt.to_timestamp().dt.date
    numeric_cols = [c for c in df.columns if c != "month"]
    df = to_number(df, numeric_cols)
    valid = df["month"].notna() & df[numeric_cols].notna().all(axis=1)
    invalid = int((~valid).sum())
    before = int(valid.sum())
    df = df.loc[valid].drop_duplicates(subset=["month"], keep="last")
    return df.sort_values("month").reset_index(drop=True), CleanResult(
        name, len(raw), len(df), before - len(df), invalid, []
    )


def clean_scheme_performance() -> tuple[pd.DataFrame, CleanResult]:
    name = "scheme_performance"
    raw = read_raw(name)
    df = normalize_strings(raw.copy())
    df["amfi_code"] = pd.to_numeric(df["amfi_code"], errors="coerce").astype("Int64")
    numeric_cols = [
        "return_1yr_pct",
        "return_3yr_pct",
        "return_5yr_pct",
        "benchmark_3yr_pct",
        "alpha",
        "beta",
        "sharpe_ratio",
        "sortino_ratio",
        "std_dev_ann_pct",
        "max_drawdown_pct",
        "aum_crore",
        "expense_ratio_pct",
        "morningstar_rating",
    ]
    df = to_number(df, numeric_cols)
    return_cols = ["return_1yr_pct", "return_3yr_pct", "return_5yr_pct", "benchmark_3yr_pct"]
    df["return_anomaly_flag"] = df[return_cols].lt(-100).any(axis=1) | df[return_cols].gt(200).any(axis=1)
    df["expense_ratio_out_of_range"] = ~df["expense_ratio_pct"].between(0.1, 2.5, inclusive="both")
    valid = df["amfi_code"].notna() & df[numeric_cols].notna().all(axis=1)
    invalid = int((~valid).sum())
    before = int(valid.sum())
    df = df.loc[valid].drop_duplicates(subset=["amfi_code"], keep="last")
    notes = [
        f"Return anomalies flagged: {int(df['return_anomaly_flag'].sum())}.",
        f"Expense-ratio range anomalies flagged: {int(df['expense_ratio_out_of_range'].sum())}.",
    ]
    return df.sort_values("amfi_code").reset_index(drop=True), CleanResult(
        name, len(raw), len(df), before - len(df), invalid, notes
    )


def clean_investor_transactions() -> tuple[pd.DataFrame, CleanResult]:
    name = "investor_transactions"
    raw = read_raw(name)
    df = normalize_strings(raw.copy())
    df["transaction_date"] = parse_date(df["transaction_date"]).dt.date
    df["amfi_code"] = pd.to_numeric(df["amfi_code"], errors="coerce").astype("Int64")
    df = to_number(df, ["amount_inr", "annual_income_lakh"])
    normalized_types = df["transaction_type"].astype("string").str.lower().str.strip()
    df["transaction_type"] = normalized_types.map(TRANSACTION_TYPE_MAP).fillna(df["transaction_type"])
    df["kyc_status_valid"] = df["kyc_status"].isin(KYC_STATUSES)
    valid = (
        df["investor_id"].notna()
        & df["transaction_date"].notna()
        & df["amfi_code"].notna()
        & df["transaction_type"].isin(["SIP", "Lumpsum", "Redemption"])
        & (df["amount_inr"] > 0)
        & df["kyc_status_valid"]
    )
    invalid = int((~valid).sum())
    before = int(valid.sum())
    df = df.loc[valid].drop_duplicates().reset_index(drop=True)
    df.insert(0, "transaction_id", range(1, len(df) + 1))
    notes = [f"KYC statuses observed: {', '.join(sorted(df['kyc_status'].dropna().unique()))}."]
    return df.sort_values(["transaction_date", "transaction_id"]).reset_index(drop=True), CleanResult(
        name, len(raw), len(df), before - len(df), invalid, notes
    )


def clean_portfolio_holdings() -> tuple[pd.DataFrame, CleanResult]:
    name = "portfolio_holdings"
    raw = read_raw(name)
    df = normalize_strings(raw.copy())
    df["amfi_code"] = pd.to_numeric(df["amfi_code"], errors="coerce").astype("Int64")
    df["portfolio_date"] = parse_date(df["portfolio_date"]).dt.date
    df = to_number(df, ["weight_pct", "market_value_cr", "current_price_inr"])
    valid = (
        df["amfi_code"].notna()
        & df["portfolio_date"].notna()
        & df["stock_symbol"].notna()
        & df["weight_pct"].between(0, 100, inclusive="both")
        & (df["market_value_cr"] >= 0)
        & (df["current_price_inr"] > 0)
    )
    invalid = int((~valid).sum())
    before = int(valid.sum())
    df = df.loc[valid].drop_duplicates(subset=["amfi_code", "stock_symbol", "portfolio_date"], keep="last")
    return df.sort_values(["amfi_code", "portfolio_date", "weight_pct"], ascending=[True, True, False]).reset_index(drop=True), CleanResult(
        name, len(raw), len(df), before - len(df), invalid, []
    )


def clean_benchmark_indices() -> tuple[pd.DataFrame, CleanResult]:
    name = "benchmark_indices"
    raw = read_raw(name)
    df = normalize_strings(raw.copy())
    df["date"] = parse_date(df["date"]).dt.date
    df = to_number(df, ["close_value"])
    valid = df["date"].notna() & df["index_name"].notna() & (df["close_value"] > 0)
    invalid = int((~valid).sum())
    before = int(valid.sum())
    df = df.loc[valid].drop_duplicates(subset=["date", "index_name"], keep="last")
    return df.sort_values(["index_name", "date"]).reset_index(drop=True), CleanResult(
        name, len(raw), len(df), before - len(df), invalid, []
    )


def build_dim_date(cleaned: dict[str, pd.DataFrame]) -> pd.DataFrame:
    date_values = []
    date_sources = [
        ("nav_history", "date"),
        ("aum_by_fund_house", "date"),
        ("monthly_sip_inflows", "month"),
        ("category_inflows", "month"),
        ("industry_folio_count", "month"),
        ("investor_transactions", "transaction_date"),
        ("portfolio_holdings", "portfolio_date"),
        ("benchmark_indices", "date"),
    ]
    for table, column in date_sources:
        date_values.extend(pd.to_datetime(cleaned[table][column], errors="coerce").dropna().tolist())
    dates = pd.Series(sorted(set(date_values)), name="date")
    dim_date = pd.DataFrame({"date": dates})
    dim_date["date_key"] = dim_date["date"].dt.strftime("%Y%m%d").astype(int)
    dim_date["year"] = dim_date["date"].dt.year
    dim_date["quarter"] = dim_date["date"].dt.quarter
    dim_date["month"] = dim_date["date"].dt.month
    dim_date["month_name"] = dim_date["date"].dt.month_name()
    dim_date["day"] = dim_date["date"].dt.day
    dim_date["day_of_week"] = dim_date["date"].dt.day_name()
    dim_date["is_weekend"] = dim_date["date"].dt.dayofweek >= 5
    dim_date["date"] = dim_date["date"].dt.date
    return dim_date[["date_key", "date", "year", "quarter", "month", "month_name", "day", "day_of_week", "is_weekend"]]


def add_date_key(df: pd.DataFrame, source_col: str, dim_date: pd.DataFrame) -> pd.Series:
    mapping = pd.Series(dim_date.date_key.values, index=pd.to_datetime(dim_date.date).dt.date).to_dict()
    return pd.to_datetime(df[source_col]).dt.date.map(mapping).astype("Int64")


def write_schema_sql() -> None:
    SQL_DIR.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(
        """PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS fact_aum;
DROP TABLE IF EXISTS fact_performance;
DROP TABLE IF EXISTS fact_transactions;
DROP TABLE IF EXISTS fact_nav;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_fund;

CREATE TABLE dim_fund (
    amfi_code INTEGER PRIMARY KEY,
    fund_house TEXT NOT NULL,
    scheme_name TEXT NOT NULL,
    category TEXT,
    sub_category TEXT,
    plan TEXT,
    launch_date TEXT,
    benchmark TEXT,
    expense_ratio_pct REAL,
    exit_load_pct REAL,
    min_sip_amount REAL,
    min_lumpsum_amount REAL,
    fund_manager TEXT,
    risk_category TEXT,
    sebi_category_code TEXT
);

CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    date TEXT NOT NULL UNIQUE,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    month INTEGER NOT NULL,
    month_name TEXT NOT NULL,
    day INTEGER NOT NULL,
    day_of_week TEXT NOT NULL,
    is_weekend INTEGER NOT NULL
);

CREATE TABLE fact_nav (
    amfi_code INTEGER NOT NULL,
    date_key INTEGER NOT NULL,
    date TEXT NOT NULL,
    nav REAL NOT NULL CHECK (nav > 0),
    PRIMARY KEY (amfi_code, date_key),
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code),
    FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
);

CREATE TABLE fact_transactions (
    transaction_id INTEGER PRIMARY KEY,
    investor_id TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    date_key INTEGER NOT NULL,
    amfi_code INTEGER NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('SIP', 'Lumpsum', 'Redemption')),
    amount_inr REAL NOT NULL CHECK (amount_inr > 0),
    state TEXT,
    city TEXT,
    city_tier TEXT,
    age_group TEXT,
    gender TEXT,
    annual_income_lakh REAL,
    payment_mode TEXT,
    kyc_status TEXT NOT NULL CHECK (kyc_status IN ('Verified', 'Pending', 'Rejected')),
    kyc_status_valid INTEGER NOT NULL,
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code),
    FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
);

CREATE TABLE fact_performance (
    amfi_code INTEGER PRIMARY KEY,
    scheme_name TEXT,
    fund_house TEXT,
    category TEXT,
    plan TEXT,
    return_1yr_pct REAL,
    return_3yr_pct REAL,
    return_5yr_pct REAL,
    benchmark_3yr_pct REAL,
    alpha REAL,
    beta REAL,
    sharpe_ratio REAL,
    sortino_ratio REAL,
    std_dev_ann_pct REAL,
    max_drawdown_pct REAL,
    aum_crore REAL,
    expense_ratio_pct REAL CHECK (expense_ratio_pct > 0),
    morningstar_rating REAL,
    risk_grade TEXT,
    return_anomaly_flag INTEGER NOT NULL,
    expense_ratio_out_of_range INTEGER NOT NULL,
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code)
);

CREATE TABLE fact_aum (
    date_key INTEGER NOT NULL,
    date TEXT NOT NULL,
    fund_house TEXT NOT NULL,
    aum_lakh_crore REAL,
    aum_crore REAL NOT NULL CHECK (aum_crore > 0),
    num_schemes REAL,
    PRIMARY KEY (date_key, fund_house),
    FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
);
""",
        encoding="utf-8",
    )


def write_queries_sql() -> None:
    QUERIES_PATH.write_text(
        """-- 1. Top 5 funds by latest AUM
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
""",
        encoding="utf-8",
    )


def load_sqlite(cleaned: dict[str, pd.DataFrame], dim_date: pd.DataFrame) -> dict[str, int]:
    if DB_PATH.exists():
        DB_PATH.unlink()
    write_schema_sql()
    engine = create_engine(f"sqlite:///{DB_PATH}")

    with engine.begin() as conn:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        for statement in schema_sql.split(";"):
            if statement.strip():
                conn.execute(text(statement))

    sql_tables: dict[str, pd.DataFrame] = {}
    sql_tables["dim_fund"] = cleaned["fund_master"].copy()
    sql_tables["dim_date"] = dim_date.copy()

    fact_nav = cleaned["nav_history"].copy()
    fact_nav["date_key"] = add_date_key(fact_nav, "date", dim_date)
    sql_tables["fact_nav"] = fact_nav[["amfi_code", "date_key", "date", "nav"]]

    fact_txn = cleaned["investor_transactions"].copy()
    fact_txn["date_key"] = add_date_key(fact_txn, "transaction_date", dim_date)
    sql_tables["fact_transactions"] = fact_txn[
        [
            "transaction_id",
            "investor_id",
            "transaction_date",
            "date_key",
            "amfi_code",
            "transaction_type",
            "amount_inr",
            "state",
            "city",
            "city_tier",
            "age_group",
            "gender",
            "annual_income_lakh",
            "payment_mode",
            "kyc_status",
            "kyc_status_valid",
        ]
    ]

    sql_tables["fact_performance"] = cleaned["scheme_performance"].copy()

    fact_aum = cleaned["aum_by_fund_house"].copy()
    fact_aum["date_key"] = add_date_key(fact_aum, "date", dim_date)
    sql_tables["fact_aum"] = fact_aum[["date_key", "date", "fund_house", "aum_lakh_crore", "aum_crore", "num_schemes"]]

    auxiliary_tables = [
        "monthly_sip_inflows",
        "category_inflows",
        "industry_folio_count",
        "portfolio_holdings",
        "benchmark_indices",
    ]
    for name in auxiliary_tables:
        sql_tables[name] = cleaned[name].copy()

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        for table_name, frame in sql_tables.items():
            frame.to_sql(table_name, conn, if_exists="append", index=False)

    with engine.connect() as conn:
        loaded_counts = {}
        for table_name in sql_tables:
            loaded_counts[table_name] = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
        foreign_key_violations = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
        if foreign_key_violations:
            raise RuntimeError(f"Foreign-key violations found: {foreign_key_violations}")
    return loaded_counts


def write_data_dictionary(cleaned: dict[str, pd.DataFrame], results: list[CleanResult], loaded_counts: dict[str, int]) -> None:
    business_definitions = {
        "amfi_code": "AMFI scheme identifier used to join scheme-level facts to the fund dimension.",
        "fund_house": "Asset management company or fund-house name.",
        "scheme_name": "Mutual fund scheme name and plan/option.",
        "category": "High-level scheme or flow category.",
        "sub_category": "More granular scheme category.",
        "plan": "Scheme plan, typically Regular or Direct.",
        "launch_date": "Scheme launch date.",
        "benchmark": "Benchmark index assigned to the scheme.",
        "expense_ratio_pct": "Annual expense ratio percentage.",
        "exit_load_pct": "Exit load percentage where applicable.",
        "min_sip_amount": "Minimum allowed SIP investment amount in INR.",
        "min_lumpsum_amount": "Minimum allowed lumpsum investment amount in INR.",
        "fund_manager": "Named fund manager.",
        "risk_category": "Scheme risk bucket from fund metadata.",
        "sebi_category_code": "SEBI category code from the master dataset.",
        "date": "Calendar date of the observation.",
        "month": "Month represented as the first calendar day of the month.",
        "nav": "Net asset value, validated as positive.",
        "transaction_id": "Generated surrogate key for investor transaction rows.",
        "investor_id": "Masked investor identifier from the source data.",
        "transaction_date": "Date on which the investor transaction occurred.",
        "transaction_type": "Standardized transaction class: SIP, Lumpsum, or Redemption.",
        "amount_inr": "Transaction value in INR, validated as positive.",
        "kyc_status": "Investor KYC status constrained to Verified, Pending, or Rejected.",
        "kyc_status_valid": "Boolean flag confirming KYC status is in the accepted enum.",
        "return_anomaly_flag": "Boolean flag for return values outside conservative sanity bounds.",
        "expense_ratio_out_of_range": "Boolean flag for expense ratio outside the 0.1% to 2.5% task range.",
        "date_key": "Integer YYYYMMDD key linking facts to dim_date.",
    }

    lines = [
        "# Data Dictionary",
        "",
        "Generated by `day2_data_cleaning_sql.py`.",
        "",
        "## Cleaning Summary",
        "",
        "| Dataset | Raw rows | Clean rows | Duplicate rows removed | Invalid rows removed | Notes |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for result in results:
        notes = " ".join(result.notes) if result.notes else "None"
        lines.append(
            f"| {result.name} | {result.raw_rows} | {result.clean_rows} | "
            f"{result.duplicate_rows_removed} | {result.invalid_rows_removed} | {notes} |"
        )

    lines.extend(
        [
            "",
            "## SQLite Row-Count Verification",
            "",
            "| SQLite table | Loaded rows |",
            "|---|---:|",
        ]
    )
    for table_name, count in sorted(loaded_counts.items()):
        lines.append(f"| {table_name} | {count} |")

    lines.extend(["", "## Tables and Columns", ""])
    for table_name, frame in cleaned.items():
        source_file = RAW_FILES[table_name]
        lines.extend(
            [
                f"### `{table_name}_clean.csv`",
                "",
                f"Source: `data/raw/{source_file}`",
                "",
                "| Column | Data type | Business definition |",
                "|---|---|---|",
            ]
        )
        for column, dtype in frame.dtypes.items():
            definition = business_definitions.get(column, f"Cleaned source field `{column}`.")
            lines.append(f"| `{column}` | `{dtype}` | {definition} |")
        lines.append("")

    DATA_DICTIONARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    cleaners = [
        clean_fund_master,
        clean_nav_history,
        clean_aum_by_fund_house,
        clean_monthly_sip_inflows,
        clean_category_inflows,
        clean_industry_folio_count,
        clean_scheme_performance,
        clean_investor_transactions,
        clean_portfolio_holdings,
        clean_benchmark_indices,
    ]
    cleaned: dict[str, pd.DataFrame] = {}
    results: list[CleanResult] = []
    for cleaner in cleaners:
        frame, result = cleaner()
        cleaned[result.name] = frame
        results.append(result)
        write_clean(result.name, frame)

    dim_date = build_dim_date(cleaned)
    write_queries_sql()
    loaded_counts = load_sqlite(cleaned, dim_date)
    write_data_dictionary(cleaned, results, loaded_counts)

    print("Day 2 pipeline complete.")
    for result in results:
        print(f"{result.name}: raw={result.raw_rows:,} clean={result.clean_rows:,}")
    print(f"SQLite DB: {DB_PATH}")
    print(f"Schema SQL: {SCHEMA_PATH}")
    print(f"Queries SQL: {QUERIES_PATH}")
    print(f"Data dictionary: {DATA_DICTIONARY_PATH}")


if __name__ == "__main__":
    main()
