"""
Generate fund performance analytics deliverables.

Outputs:
    notebooks/Performance_Analytics.ipynb
    data/processed/fund_scorecard.csv
    data/processed/alpha_beta.csv
    reports/figures/benchmark_comparison_top5.png
    reports/figures/daily_return_distribution.png
"""

from __future__ import annotations

from pathlib import Path
import warnings

import nbformat as nbf
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt
from matplotlib.ticker import FuncFormatter
from scipy.stats import linregress


BASE_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
NOTEBOOK_PATH = BASE_DIR / "notebooks" / "Performance_Analytics.ipynb"
FIG_DIR = BASE_DIR / "reports" / "figures"
SCORECARD_PATH = PROCESSED_DIR / "fund_scorecard.csv"
ALPHA_BETA_PATH = PROCESSED_DIR / "alpha_beta.csv"

RISK_FREE_RATE = 0.065
TRADING_DAYS = 252

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


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    nav = pd.read_csv(PROCESSED_DIR / "nav_history_clean.csv", parse_dates=["date"])
    fund = pd.read_csv(PROCESSED_DIR / "fund_master_clean.csv", parse_dates=["launch_date"])
    performance = pd.read_csv(PROCESSED_DIR / "scheme_performance_clean.csv")
    benchmarks = pd.read_csv(PROCESSED_DIR / "benchmark_indices_clean.csv", parse_dates=["date"])
    return nav, fund, performance, benchmarks


def cagr_for_period(series: pd.Series, end_date: pd.Timestamp, years: int) -> tuple[float, float]:
    series = series.dropna().sort_index()
    if series.empty:
        return np.nan, np.nan
    target_start = end_date - pd.DateOffset(years=years)
    eligible = series.loc[series.index >= target_start]
    if eligible.empty:
        start_date = series.index[0]
        start_nav = series.iloc[0]
    else:
        start_date = eligible.index[0]
        start_nav = eligible.iloc[0]
    end_nav = series.loc[:end_date].iloc[-1]
    observed_years = (end_date - start_date).days / 365.25
    if start_nav <= 0 or observed_years <= 0:
        return np.nan, observed_years
    return ((end_nav / start_nav) ** (1 / observed_years) - 1) * 100, observed_years


def max_drawdown(series: pd.Series) -> tuple[float, pd.Timestamp, pd.Timestamp]:
    series = series.dropna().sort_index()
    running_max = series.cummax()
    drawdown = series / running_max - 1
    trough_date = drawdown.idxmin()
    peak_date = series.loc[:trough_date].idxmax()
    return drawdown.loc[trough_date] * 100, peak_date, trough_date


def percentile_score(values: pd.Series, higher_is_better: bool = True) -> pd.Series:
    ranks = values.rank(method="average", ascending=not higher_is_better, na_option="bottom")
    count = values.notna().sum()
    if count <= 1:
        return pd.Series(100.0, index=values.index)
    return (count - ranks + 1) / count * 100


def compute_metrics(
    nav: pd.DataFrame,
    fund: pd.DataFrame,
    performance: pd.DataFrame,
    benchmarks: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    nav_wide = nav.pivot_table(index="date", columns="amfi_code", values="nav").sort_index()
    daily_returns = nav_wide.pct_change(fill_method=None).dropna(how="all")

    benchmark_wide = benchmarks.pivot_table(index="date", columns="index_name", values="close_value").sort_index()
    benchmark_returns = benchmark_wide.pct_change(fill_method=None).dropna(how="all")
    nifty100_returns = benchmark_returns["NIFTY100"].dropna()
    nifty50_returns = benchmark_returns["NIFTY50"].dropna()

    metrics: list[dict[str, object]] = []
    alpha_beta_rows: list[dict[str, object]] = []
    end_date = nav_wide.index.max()
    daily_rf = RISK_FREE_RATE / TRADING_DAYS

    fund_lookup = fund.set_index("amfi_code")
    expense_lookup = performance.set_index("amfi_code")["expense_ratio_pct"]
    aum_lookup = performance.set_index("amfi_code")["aum_crore"]

    for amfi_code in nav_wide.columns:
        nav_series = nav_wide[amfi_code].dropna()
        returns = daily_returns[amfi_code].dropna()
        excess = returns - daily_rf

        std_daily = returns.std()
        downside_std = returns[returns < 0].std()
        sharpe = ((returns.mean() - daily_rf) / std_daily * np.sqrt(TRADING_DAYS)) if std_daily and not np.isnan(std_daily) else np.nan
        sortino = ((returns.mean() - daily_rf) / downside_std * np.sqrt(TRADING_DAYS)) if downside_std and not np.isnan(downside_std) else np.nan

        cagr_1yr, obs_1yr = cagr_for_period(nav_series, end_date, 1)
        cagr_3yr, obs_3yr = cagr_for_period(nav_series, end_date, 3)
        cagr_5yr, obs_5yr = cagr_for_period(nav_series, end_date, 5)

        max_dd, dd_start, dd_end = max_drawdown(nav_series)

        aligned = pd.concat(
            [returns.rename("fund_return"), nifty100_returns.rename("nifty100_return")],
            axis=1,
            join="inner",
        ).dropna()
        if len(aligned) >= 30:
            regression = linregress(aligned["nifty100_return"], aligned["fund_return"])
            beta = regression.slope
            alpha = regression.intercept * TRADING_DAYS * 100
            r_squared = regression.rvalue**2
        else:
            beta = alpha = r_squared = np.nan
        tracking_error_nifty100 = (aligned["fund_return"] - aligned["nifty100_return"]).std() * np.sqrt(TRADING_DAYS) * 100

        aligned_nifty50 = pd.concat(
            [returns.rename("fund_return"), nifty50_returns.rename("nifty50_return")],
            axis=1,
            join="inner",
        ).dropna()
        tracking_error_nifty50 = (aligned_nifty50["fund_return"] - aligned_nifty50["nifty50_return"]).std() * np.sqrt(TRADING_DAYS) * 100

        info = fund_lookup.loc[amfi_code]
        metrics.append(
            {
                "amfi_code": int(amfi_code),
                "scheme_name": info["scheme_name"],
                "fund_house": info["fund_house"],
                "category": info["category"],
                "sub_category": info["sub_category"],
                "plan": info["plan"],
                "expense_ratio_pct": expense_lookup.get(amfi_code, np.nan),
                "aum_crore": aum_lookup.get(amfi_code, np.nan),
                "cagr_1yr_pct": cagr_1yr,
                "cagr_1yr_observed_years": obs_1yr,
                "cagr_3yr_pct": cagr_3yr,
                "cagr_3yr_observed_years": obs_3yr,
                "cagr_5yr_pct": cagr_5yr,
                "cagr_5yr_observed_years": obs_5yr,
                "annualized_return_pct": returns.mean() * TRADING_DAYS * 100,
                "annualized_volatility_pct": std_daily * np.sqrt(TRADING_DAYS) * 100,
                "sharpe_ratio": sharpe,
                "sortino_ratio": sortino,
                "alpha_pct": alpha,
                "beta": beta,
                "r_squared_vs_nifty100": r_squared,
                "tracking_error_vs_nifty100_pct": tracking_error_nifty100,
                "tracking_error_vs_nifty50_pct": tracking_error_nifty50,
                "max_drawdown_pct": max_dd,
                "drawdown_start_date": dd_start.date().isoformat(),
                "drawdown_end_date": dd_end.date().isoformat(),
                "daily_return_mean_pct": returns.mean() * 100,
                "daily_return_std_pct": returns.std() * 100,
                "negative_return_days": int((returns < 0).sum()),
                "observations": int(returns.count()),
            }
        )
        alpha_beta_rows.append(
            {
                "amfi_code": int(amfi_code),
                "scheme_name": info["scheme_name"],
                "alpha_pct": alpha,
                "beta": beta,
                "r_squared_vs_nifty100": r_squared,
                "regression_observations": int(len(aligned)),
                "benchmark": "NIFTY100",
            }
        )

    scorecard = pd.DataFrame(metrics)
    scorecard["return_3yr_score"] = percentile_score(scorecard["cagr_3yr_pct"], higher_is_better=True)
    scorecard["sharpe_score"] = percentile_score(scorecard["sharpe_ratio"], higher_is_better=True)
    scorecard["alpha_score"] = percentile_score(scorecard["alpha_pct"], higher_is_better=True)
    scorecard["expense_ratio_score"] = percentile_score(scorecard["expense_ratio_pct"], higher_is_better=False)
    scorecard["max_drawdown_score"] = percentile_score(scorecard["max_drawdown_pct"], higher_is_better=True)
    scorecard["fund_score"] = (
        0.30 * scorecard["return_3yr_score"]
        + 0.25 * scorecard["sharpe_score"]
        + 0.20 * scorecard["alpha_score"]
        + 0.15 * scorecard["expense_ratio_score"]
        + 0.10 * scorecard["max_drawdown_score"]
    ).round(2)
    scorecard["overall_rank"] = scorecard["fund_score"].rank(method="dense", ascending=False).astype(int)
    scorecard = scorecard.sort_values(["overall_rank", "fund_score", "scheme_name"], ascending=[True, False, True]).reset_index(drop=True)

    alpha_beta = pd.DataFrame(alpha_beta_rows).sort_values("alpha_pct", ascending=False).reset_index(drop=True)
    return scorecard, alpha_beta, daily_returns, benchmark_returns


def save_outputs(scorecard: pd.DataFrame, alpha_beta: pd.DataFrame) -> None:
    scorecard.to_csv(SCORECARD_PATH, index=False)
    alpha_beta.to_csv(ALPHA_BETA_PATH, index=False)


def make_charts(
    scorecard: pd.DataFrame,
    daily_returns: pd.DataFrame,
    benchmark_returns: pd.DataFrame,
    nav: pd.DataFrame,
    benchmarks: pd.DataFrame,
) -> tuple[str, str, pd.DataFrame]:
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    # Return-distribution validation chart.
    distribution = daily_returns.stack().mul(100).rename("daily_return_pct").reset_index()
    distribution.columns = ["date", "amfi_code", "daily_return_pct"]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    sns.histplot(distribution["daily_return_pct"], bins=120, kde=True, ax=ax, color="#4c78a8")
    ax.axvline(0, color="#333333", linewidth=1)
    ax.set_xlim(-8, 8)
    ax.set_title("Daily Return Distribution Across 40 Schemes")
    ax.set_xlabel("Daily return, %")
    ax.set_ylabel("Observation count")
    distribution_path = FIG_DIR / "daily_return_distribution.png"
    fig.tight_layout()
    fig.savefig(distribution_path, bbox_inches="tight")
    plt.close(fig)

    # Benchmark comparison chart for top 5 funds by score over last 3 years.
    top5_codes = scorecard.head(5)["amfi_code"].tolist()
    top5_names = scorecard.set_index("amfi_code").loc[top5_codes, "scheme_name"].to_dict()
    nav_wide = nav[nav["amfi_code"].isin(top5_codes)].pivot_table(index="date", columns="amfi_code", values="nav").sort_index()
    end_date = nav_wide.index.max()
    start_date = end_date - pd.DateOffset(years=3)
    nav_three_year = nav_wide.loc[nav_wide.index >= start_date]
    indexed_funds = nav_three_year.div(nav_three_year.iloc[0]).mul(100)

    benchmark_wide = benchmarks.pivot_table(index="date", columns="index_name", values="close_value").sort_index()
    benchmark_three_year = benchmark_wide.loc[benchmark_wide.index >= start_date, ["NIFTY50", "NIFTY100"]]
    indexed_benchmarks = benchmark_three_year.div(benchmark_three_year.iloc[0]).mul(100)

    fig, ax = plt.subplots(figsize=(12, 6))
    for code in indexed_funds.columns:
        label = top5_names[code].replace(" Fund", "").replace(" - Growth", "")[:42]
        ax.plot(indexed_funds.index, indexed_funds[code], linewidth=1.8, label=label)
    ax.plot(indexed_benchmarks.index, indexed_benchmarks["NIFTY50"], color="#222222", linestyle="--", linewidth=2.0, label="NIFTY50")
    ax.plot(indexed_benchmarks.index, indexed_benchmarks["NIFTY100"], color="#666666", linestyle=":", linewidth=2.4, label="NIFTY100")
    ax.set_title("Top 5 Fund Scorecard Funds vs NIFTY50 and NIFTY100, Last 3 Years")
    ax.set_xlabel("Date")
    ax.set_ylabel("Indexed value, start = 100")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
    benchmark_path = FIG_DIR / "benchmark_comparison_top5.png"
    fig.tight_layout()
    fig.savefig(benchmark_path, bbox_inches="tight")
    plt.close(fig)

    # Tracking error vs NIFTY100 for the same top 5 funds.
    tracking_rows: list[dict[str, object]] = []
    nifty100 = benchmark_returns["NIFTY100"].dropna()
    for code in top5_codes:
        aligned = pd.concat([daily_returns[code].rename("fund"), nifty100.rename("benchmark")], axis=1, join="inner").dropna()
        tracking_error = (aligned["fund"] - aligned["benchmark"]).std() * np.sqrt(TRADING_DAYS) * 100
        tracking_rows.append(
            {
                "amfi_code": code,
                "scheme_name": top5_names[code],
                "tracking_error_vs_nifty100_pct": tracking_error,
            }
        )
    tracking_error = pd.DataFrame(tracking_rows)
    return str(distribution_path), str(benchmark_path), tracking_error


def write_notebook(scorecard: pd.DataFrame, alpha_beta: pd.DataFrame, tracking_error: pd.DataFrame) -> None:
    NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    top_fund = scorecard.iloc[0]
    worst_dd = scorecard.sort_values("max_drawdown_pct").iloc[0]
    best_alpha = alpha_beta.iloc[0]
    best_tracking = tracking_error.sort_values("tracking_error_vs_nifty100_pct").iloc[0]

    nb = nbf.v4.new_notebook()
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "pygments_lexer": "ipython3"},
    }
    nb["cells"] = [
        nbf.v4.new_markdown_cell(
            "# Fund Performance Analytics\n\n"
            "This notebook documents the Day 4 performance analytics workflow: daily returns, trailing CAGR, Sharpe, Sortino, alpha/beta, drawdown, scorecard ranking, and benchmark comparison."
        ),
        nbf.v4.new_code_cell(
            "from pathlib import Path\n"
            "import pandas as pd\n"
            "import numpy as np\n"
            "from scipy.stats import linregress\n\n"
            "BASE_DIR = Path('..').resolve()\n"
            "PROCESSED_DIR = BASE_DIR / 'data' / 'processed'\n"
            "scorecard = pd.read_csv(PROCESSED_DIR / 'fund_scorecard.csv')\n"
            "alpha_beta = pd.read_csv(PROCESSED_DIR / 'alpha_beta.csv')\n"
            "scorecard.head()"
        ),
        nbf.v4.new_markdown_cell(
            "## Methodology\n\n"
            "- Daily return: `NAV_t / NAV_t-1 - 1` for each scheme.\n"
            "- CAGR: `(NAV_end / NAV_start) ** (1 / observed_years) - 1` for 1-year, 3-year, and available-history 5-year windows.\n"
            "- Sharpe: `(Rp - Rf) / Std(Rp) * sqrt(252)` with `Rf = 6.5%`.\n"
            "- Sortino: same excess-return numerator, downside standard deviation denominator.\n"
            "- Alpha/Beta: `scipy.stats.linregress` of fund returns on NIFTY100 returns; annualized alpha is `intercept * 252`.\n"
            "- Scorecard: 30% 3-year return rank, 25% Sharpe rank, 20% alpha rank, 15% inverse expense-ratio rank, 10% inverse max-drawdown rank."
        ),
        nbf.v4.new_markdown_cell(
            "## Daily Return Distribution Validation\n\n"
            "![Daily return distribution](../reports/figures/daily_return_distribution.png)"
        ),
        nbf.v4.new_markdown_cell(
            "## Top Fund Scorecard\n\n"
            f"The highest composite score is **{top_fund['scheme_name']}** with a score of **{top_fund['fund_score']:.2f}**."
        ),
        nbf.v4.new_code_cell("scorecard[['overall_rank', 'scheme_name', 'fund_score', 'cagr_3yr_pct', 'sharpe_ratio', 'alpha_pct', 'expense_ratio_pct', 'max_drawdown_pct']].head(10)"),
        nbf.v4.new_markdown_cell(
            "## Alpha and Beta\n\n"
            f"The highest annualized NIFTY100 regression alpha is **{best_alpha['scheme_name']}** at **{best_alpha['alpha_pct']:.2f}%**."
        ),
        nbf.v4.new_code_cell("alpha_beta.head(10)"),
        nbf.v4.new_markdown_cell(
            "## Maximum Drawdown\n\n"
            f"The worst max drawdown is **{worst_dd['scheme_name']}** at **{worst_dd['max_drawdown_pct']:.2f}%**, from {worst_dd['drawdown_start_date']} to {worst_dd['drawdown_end_date']}."
        ),
        nbf.v4.new_markdown_cell(
            "## Benchmark Comparison\n\n"
            "![Benchmark comparison](../reports/figures/benchmark_comparison_top5.png)"
        ),
        nbf.v4.new_markdown_cell(
            "## Tracking Error\n\n"
            f"Among the scorecard top 5, **{best_tracking['scheme_name']}** has the lowest tracking error versus NIFTY100 at **{best_tracking['tracking_error_vs_nifty100_pct']:.2f}%**."
        ),
        nbf.v4.new_code_cell("pd.read_csv(PROCESSED_DIR / 'fund_scorecard.csv').describe(include='all')"),
        nbf.v4.new_markdown_cell(
            "## Deliverables\n\n"
            "- `data/processed/fund_scorecard.csv`\n"
            "- `data/processed/alpha_beta.csv`\n"
            "- `reports/figures/benchmark_comparison_top5.png`\n"
            "- `reports/figures/daily_return_distribution.png`\n"
        ),
    ]
    NOTEBOOK_PATH.write_text(nbf.writes(nb), encoding="utf-8")


def main() -> None:
    warnings.filterwarnings("ignore", category=FutureWarning)
    nav, fund, performance, benchmarks = load_inputs()
    scorecard, alpha_beta, daily_returns, benchmark_returns = compute_metrics(nav, fund, performance, benchmarks)
    save_outputs(scorecard, alpha_beta)
    _, _, tracking_error = make_charts(scorecard, daily_returns, benchmark_returns, nav, benchmarks)
    write_notebook(scorecard, alpha_beta, tracking_error)

    print(f"Wrote {SCORECARD_PATH}")
    print(f"Wrote {ALPHA_BETA_PATH}")
    print(f"Wrote {NOTEBOOK_PATH}")
    print(f"Top fund: {scorecard.iloc[0]['scheme_name']} ({scorecard.iloc[0]['fund_score']:.2f})")


if __name__ == "__main__":
    main()
