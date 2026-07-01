"""
Generate advanced analytics and risk metric deliverables.

Outputs:
    notebooks/Advanced_Analytics.ipynb
    data/processed/var_cvar_report.csv
    data/processed/investor_cohort_analysis.csv
    data/processed/sip_continuity_analysis.csv
    data/processed/sector_hhi_concentration.csv
    reports/figures/rolling_sharpe_chart.png
    recommender.py
"""

from __future__ import annotations

from pathlib import Path
import textwrap

import nbformat as nbf
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt


BASE_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
REPORTS_FIG_DIR = BASE_DIR / "reports" / "figures"
NOTEBOOK_PATH = BASE_DIR / "notebooks" / "Advanced_Analytics.ipynb"
VAR_CVAR_PATH = PROCESSED_DIR / "var_cvar_report.csv"
COHORT_PATH = PROCESSED_DIR / "investor_cohort_analysis.csv"
SIP_CONTINUITY_PATH = PROCESSED_DIR / "sip_continuity_analysis.csv"
SECTOR_HHI_PATH = PROCESSED_DIR / "sector_hhi_concentration.csv"
ROLLING_SHARPE_PATH = REPORTS_FIG_DIR / "rolling_sharpe_chart.png"
RECOMMENDER_PATH = BASE_DIR / "recommender.py"

TRADING_DAYS = 252
VAR_CONFIDENCE = 0.95

sns.set_theme(style="whitegrid", context="notebook")
plt.rcParams.update(
    {
        "figure.dpi": 140,
        "savefig.dpi": 180,
        "axes.titlesize": 13,
        "axes.labelsize": 10,
        "font.size": 10,
    }
)


def load_data() -> dict[str, pd.DataFrame]:
    data = {
        "nav": pd.read_csv(PROCESSED_DIR / "nav_history_clean.csv", parse_dates=["date"]),
        "fund": pd.read_csv(PROCESSED_DIR / "fund_master_clean.csv"),
        "scorecard": pd.read_csv(PROCESSED_DIR / "fund_scorecard.csv"),
        "transactions": pd.read_csv(PROCESSED_DIR / "investor_transactions_clean.csv", parse_dates=["transaction_date"]),
        "holdings": pd.read_csv(PROCESSED_DIR / "portfolio_holdings_clean.csv", parse_dates=["portfolio_date"]),
    }
    return data


def compute_daily_returns(nav: pd.DataFrame) -> pd.DataFrame:
    nav_wide = nav.pivot_table(index="date", columns="amfi_code", values="nav").sort_index()
    return nav_wide.pct_change(fill_method=None).dropna(how="all")


def compute_var_cvar(data: dict[str, pd.DataFrame], returns: pd.DataFrame) -> pd.DataFrame:
    fund_cols = [
        "amfi_code",
        "scheme_name",
        "fund_house",
        "category",
        "sub_category",
        "plan",
        "risk_category",
        "expense_ratio_pct",
    ]
    fund = data["fund"][fund_cols].set_index("amfi_code")
    score = data["scorecard"][
        ["amfi_code", "sharpe_ratio", "sortino_ratio", "fund_score", "overall_rank", "annualized_volatility_pct", "max_drawdown_pct"]
    ].set_index("amfi_code")

    rows: list[dict[str, object]] = []
    for amfi_code in returns.columns:
        series = returns[amfi_code].dropna()
        var_threshold = series.quantile(1 - VAR_CONFIDENCE)
        cvar = series[series <= var_threshold].mean()
        rows.append(
            {
                "amfi_code": int(amfi_code),
                "var_95_daily_pct": var_threshold * 100,
                "cvar_95_daily_pct": cvar * 100,
                "annualized_volatility_pct_from_daily": series.std() * np.sqrt(TRADING_DAYS) * 100,
                "average_daily_return_pct": series.mean() * 100,
                "worst_daily_return_pct": series.min() * 100,
                "best_daily_return_pct": series.max() * 100,
                "observations": int(series.count()),
            }
        )
    report = pd.DataFrame(rows).set_index("amfi_code").join(fund).join(score).reset_index()
    report["var_rank"] = report["var_95_daily_pct"].rank(method="dense", ascending=True).astype(int)
    report["cvar_rank"] = report["cvar_95_daily_pct"].rank(method="dense", ascending=True).astype(int)
    report = report.sort_values(["var_rank", "cvar_rank", "scheme_name"]).reset_index(drop=True)
    report.to_csv(VAR_CVAR_PATH, index=False)
    return report


def compute_rolling_sharpe_chart(data: dict[str, pd.DataFrame], returns: pd.DataFrame) -> pd.DataFrame:
    top_codes = data["scorecard"].sort_values("overall_rank").head(5)["amfi_code"].tolist()
    name_map = data["fund"].set_index("amfi_code")["scheme_name"].to_dict()
    rolling = returns[top_codes].rolling(90).mean() / returns[top_codes].rolling(90).std() * np.sqrt(TRADING_DAYS)
    rolling_long = rolling.reset_index().melt(id_vars="date", var_name="amfi_code", value_name="rolling_90d_sharpe")
    rolling_long["scheme_name"] = rolling_long["amfi_code"].map(name_map)

    REPORTS_FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 6))
    sns.lineplot(data=rolling_long.dropna(), x="date", y="rolling_90d_sharpe", hue="scheme_name", linewidth=1.8, ax=ax)
    ax.axhline(0, color="#333333", linewidth=1, linestyle="--")
    ax.set_title("Rolling 90-Day Sharpe Ratio - Top 5 Scorecard Funds")
    ax.set_xlabel("Date")
    ax.set_ylabel("Rolling Sharpe")
    ax.legend(title="Fund", fontsize=7, title_fontsize=8, bbox_to_anchor=(1.02, 1), loc="upper left", frameon=False)
    fig.tight_layout()
    fig.savefig(ROLLING_SHARPE_PATH, bbox_inches="tight")
    plt.close(fig)
    return rolling_long


def compute_investor_cohorts(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    transactions = data["transactions"].copy()
    fund_names = data["fund"].set_index("amfi_code")["scheme_name"].to_dict()
    first_txn = transactions.groupby("investor_id")["transaction_date"].min().rename("first_transaction_date")
    transactions = transactions.merge(first_txn, on="investor_id")
    transactions["first_transaction_year"] = transactions["first_transaction_date"].dt.year

    sip = transactions[transactions["transaction_type"].eq("SIP")]
    top_pref = (
        transactions.groupby(["first_transaction_year", "amfi_code"])["amount_inr"]
        .sum()
        .reset_index()
        .sort_values(["first_transaction_year", "amount_inr"], ascending=[True, False])
        .drop_duplicates("first_transaction_year")
    )
    top_pref["top_fund_preference"] = top_pref["amfi_code"].map(fund_names)

    cohort = transactions.groupby("first_transaction_year").agg(
        investors=("investor_id", "nunique"),
        total_invested_inr=("amount_inr", "sum"),
        total_transactions=("transaction_id", "count"),
    )
    sip_avg = sip.groupby("first_transaction_year")["amount_inr"].mean().rename("avg_sip_amount_inr")
    cohort = cohort.join(sip_avg).reset_index()
    cohort = cohort.merge(
        top_pref[["first_transaction_year", "amfi_code", "top_fund_preference"]],
        on="first_transaction_year",
        how="left",
    )
    cohort = cohort.rename(columns={"amfi_code": "top_fund_amfi_code"})
    cohort["avg_total_invested_per_investor_inr"] = cohort["total_invested_inr"] / cohort["investors"]
    cohort = cohort[
        [
            "first_transaction_year",
            "investors",
            "avg_sip_amount_inr",
            "total_invested_inr",
            "avg_total_invested_per_investor_inr",
            "total_transactions",
            "top_fund_amfi_code",
            "top_fund_preference",
        ]
    ].sort_values("first_transaction_year")
    cohort.to_csv(COHORT_PATH, index=False)
    return cohort


def compute_sip_continuity(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    sip = data["transactions"][data["transactions"]["transaction_type"].eq("SIP")].copy()
    rows: list[dict[str, object]] = []
    for investor_id, group in sip.sort_values("transaction_date").groupby("investor_id"):
        dates = group["transaction_date"].sort_values()
        if len(dates) < 6:
            continue
        gaps = dates.diff().dt.days.dropna()
        rows.append(
            {
                "investor_id": investor_id,
                "sip_transactions": int(len(dates)),
                "first_sip_date": dates.iloc[0].date().isoformat(),
                "last_sip_date": dates.iloc[-1].date().isoformat(),
                "avg_gap_days": gaps.mean(),
                "max_gap_days": gaps.max(),
                "at_risk": bool((gaps > 35).any()),
            }
        )
    continuity = pd.DataFrame(rows).sort_values(["at_risk", "avg_gap_days"], ascending=[False, False])
    continuity.to_csv(SIP_CONTINUITY_PATH, index=False)
    return continuity


def compute_sector_hhi(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    holdings = data["holdings"].copy()
    fund = data["fund"][["amfi_code", "scheme_name", "fund_house", "category", "sub_category"]]
    equity_codes = fund[fund["category"].eq("Equity")]["amfi_code"]
    equity_holdings = holdings[holdings["amfi_code"].isin(equity_codes)].copy()
    sector_weights = equity_holdings.groupby(["amfi_code", "sector"], as_index=False)["weight_pct"].sum()
    rows: list[dict[str, object]] = []
    for amfi_code, group in sector_weights.groupby("amfi_code"):
        weights = group["weight_pct"] / 100
        hhi = float((weights**2).sum())
        top_sector = group.sort_values("weight_pct", ascending=False).iloc[0]
        rows.append(
            {
                "amfi_code": int(amfi_code),
                "sector_hhi": hhi,
                "sector_hhi_10000": hhi * 10000,
                "top_sector": top_sector["sector"],
                "top_sector_weight_pct": top_sector["weight_pct"],
                "sector_count": int(group["sector"].nunique()),
                "concentration_flag": "High" if hhi >= 0.25 else "Moderate" if hhi >= 0.15 else "Low",
            }
        )
    hhi_report = pd.DataFrame(rows).merge(fund, on="amfi_code", how="left")
    hhi_report = hhi_report.sort_values("sector_hhi", ascending=False).reset_index(drop=True)
    hhi_report.to_csv(SECTOR_HHI_PATH, index=False)
    return hhi_report


def write_recommender() -> None:
    RECOMMENDER_PATH.write_text(
        '''"""Simple mutual fund recommender by risk appetite.

Usage:
    python recommender.py Low
    python recommender.py Moderate
    python recommender.py High
"""

from __future__ import annotations

from pathlib import Path
import argparse

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"

RISK_MAP = {
    "low": ["Low"],
    "moderate": ["Moderate", "Moderately High"],
    "high": ["High", "Very High"],
}


def recommend(risk_appetite: str, top_n: int = 3) -> pd.DataFrame:
    key = risk_appetite.strip().lower()
    if key not in RISK_MAP:
        valid = ", ".join(sorted(name.title() for name in RISK_MAP))
        raise ValueError(f"Unsupported risk appetite: {risk_appetite!r}. Use one of: {valid}.")

    scorecard = pd.read_csv(PROCESSED_DIR / "fund_scorecard.csv")
    fund = pd.read_csv(PROCESSED_DIR / "fund_master_clean.csv")[["amfi_code", "risk_category"]]
    candidates = scorecard.merge(fund, on="amfi_code", how="left")
    candidates = candidates[candidates["risk_category"].isin(RISK_MAP[key])].copy()
    if candidates.empty:
        return candidates
    columns = [
        "overall_rank",
        "amfi_code",
        "scheme_name",
        "fund_house",
        "category",
        "risk_category",
        "sharpe_ratio",
        "cagr_3yr_pct",
        "fund_score",
        "expense_ratio_pct",
        "max_drawdown_pct",
    ]
    return candidates.sort_values(["sharpe_ratio", "fund_score"], ascending=False)[columns].head(top_n)


def main() -> None:
    parser = argparse.ArgumentParser(description="Recommend top mutual funds by risk appetite.")
    parser.add_argument("risk_appetite", choices=["Low", "Moderate", "High", "low", "moderate", "high"])
    parser.add_argument("--top-n", type=int, default=3)
    args = parser.parse_args()

    recommendations = recommend(args.risk_appetite, args.top_n)
    if recommendations.empty:
        print("No matching funds found.")
    else:
        print(recommendations.to_string(index=False, float_format=lambda value: f"{value:.2f}"))


if __name__ == "__main__":
    main()
''',
        encoding="utf-8",
    )


def write_notebook(
    var_cvar: pd.DataFrame,
    cohort: pd.DataFrame,
    continuity: pd.DataFrame,
    hhi: pd.DataFrame,
) -> None:
    NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)

    worst_var = var_cvar.iloc[0]
    best_var = var_cvar.sort_values("var_95_daily_pct", ascending=False).iloc[0]
    highest_cohort = cohort.sort_values("total_invested_inr", ascending=False).iloc[0]
    continuity_rate = 100 * (1 - continuity["at_risk"].mean()) if not continuity.empty else np.nan
    riskiest_hhi = hhi.iloc[0]

    nb = nbf.v4.new_notebook()
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "pygments_lexer": "ipython3"},
    }
    nb["cells"] = [
        nbf.v4.new_markdown_cell(
            "# Advanced Analytics + Risk Metrics\n\n"
            "This notebook summarizes VaR/CVaR, rolling Sharpe, investor cohorts, SIP continuity, risk-appetite recommendations, and sector HHI concentration."
        ),
        nbf.v4.new_code_cell(
            "from pathlib import Path\n"
            "import pandas as pd\n\n"
            "BASE_DIR = Path('..').resolve()\n"
            "PROCESSED_DIR = BASE_DIR / 'data' / 'processed'\n"
            "var_cvar = pd.read_csv(PROCESSED_DIR / 'var_cvar_report.csv')\n"
            "cohort = pd.read_csv(PROCESSED_DIR / 'investor_cohort_analysis.csv')\n"
            "sip_continuity = pd.read_csv(PROCESSED_DIR / 'sip_continuity_analysis.csv')\n"
            "sector_hhi = pd.read_csv(PROCESSED_DIR / 'sector_hhi_concentration.csv')\n"
            "var_cvar.head()"
        ),
        nbf.v4.new_markdown_cell(
            "## Methodology\n\n"
            "- Historical VaR 95%: 5th percentile of each fund's daily return distribution.\n"
            "- CVaR 95%: average return for observations at or below the VaR threshold.\n"
            "- Rolling Sharpe: `returns.rolling(90).mean() / returns.rolling(90).std() * sqrt(252)`.\n"
            "- Investor cohorts: grouped by first transaction year.\n"
            "- SIP continuity: investors with 6+ SIP transactions are at risk if any transaction gap exceeds 35 days.\n"
            "- Sector HHI: sum of squared sector weights per equity fund."
        ),
        nbf.v4.new_markdown_cell(
            "## Rolling 90-Day Sharpe\n\n"
            "![Rolling Sharpe](../reports/figures/rolling_sharpe_chart.png)"
        ),
        nbf.v4.new_markdown_cell(
            f"**Insight 1.** The weakest 95% historical VaR is **{worst_var['scheme_name']}** at **{worst_var['var_95_daily_pct']:.2f}%** daily VaR; see `var_cvar_report.csv`."
        ),
        nbf.v4.new_markdown_cell(
            f"**Insight 2.** The most stable VaR profile is **{best_var['scheme_name']}** at **{best_var['var_95_daily_pct']:.2f}%** daily VaR."
        ),
        nbf.v4.new_markdown_cell(
            f"**Insight 3.** The **{int(highest_cohort['first_transaction_year'])}** investor cohort has the highest total invested amount at **Rs. {highest_cohort['total_invested_inr']:,.0f}**."
        ),
        nbf.v4.new_markdown_cell(
            f"**Insight 4.** SIP continuity among investors with 6+ SIPs is **{continuity_rate:.1f}%** by the 35-day gap rule."
        ),
        nbf.v4.new_markdown_cell(
            f"**Insight 5.** The highest sector concentration is **{riskiest_hhi['scheme_name']}** with HHI **{riskiest_hhi['sector_hhi_10000']:.0f}**, led by **{riskiest_hhi['top_sector']}**."
        ),
        nbf.v4.new_code_cell("var_cvar[['var_rank', 'scheme_name', 'risk_category', 'var_95_daily_pct', 'cvar_95_daily_pct', 'sharpe_ratio']].head(10)"),
        nbf.v4.new_code_cell("cohort"),
        nbf.v4.new_code_cell("sip_continuity.head(10)"),
        nbf.v4.new_code_cell("sector_hhi.head(10)"),
        nbf.v4.new_markdown_cell(
            "## Recommender\n\n"
            "Run `python recommender.py Low`, `python recommender.py Moderate`, or `python recommender.py High` from the repository root."
        ),
    ]
    NOTEBOOK_PATH.write_text(nbf.writes(nb), encoding="utf-8")


def main() -> None:
    data = load_data()
    returns = compute_daily_returns(data["nav"])
    var_cvar = compute_var_cvar(data, returns)
    compute_rolling_sharpe_chart(data, returns)
    cohort = compute_investor_cohorts(data)
    continuity = compute_sip_continuity(data)
    hhi = compute_sector_hhi(data)
    write_recommender()
    write_notebook(var_cvar, cohort, continuity, hhi)

    print(f"Wrote {VAR_CVAR_PATH}")
    print(f"Wrote {ROLLING_SHARPE_PATH}")
    print(f"Wrote {NOTEBOOK_PATH}")
    print(f"Wrote {RECOMMENDER_PATH}")


if __name__ == "__main__":
    main()
