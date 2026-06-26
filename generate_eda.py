"""
Generate Day 3 EDA notebook and report-ready PNG charts.

Outputs:
    notebooks/EDA_Analysis.ipynb
    reports/figures/*.png
"""

from __future__ import annotations

from pathlib import Path
import warnings

import nbformat as nbf
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import seaborn as sns
from matplotlib import pyplot as plt
from matplotlib.ticker import FuncFormatter
from plotly.subplots import make_subplots


BASE_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
NOTEBOOK_PATH = BASE_DIR / "notebooks" / "EDA_Analysis.ipynb"
FIG_DIR = BASE_DIR / "reports" / "figures"

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
    tables = {
        "fund_master": "fund_master_clean.csv",
        "nav": "nav_history_clean.csv",
        "aum": "aum_by_fund_house_clean.csv",
        "sip": "monthly_sip_inflows_clean.csv",
        "category": "category_inflows_clean.csv",
        "folios": "industry_folio_count_clean.csv",
        "performance": "scheme_performance_clean.csv",
        "transactions": "investor_transactions_clean.csv",
        "holdings": "portfolio_holdings_clean.csv",
        "benchmarks": "benchmark_indices_clean.csv",
    }
    data = {name: pd.read_csv(PROCESSED_DIR / filename) for name, filename in tables.items()}
    for frame, columns in [
        (data["nav"], ["date"]),
        (data["aum"], ["date"]),
        (data["sip"], ["month"]),
        (data["category"], ["month"]),
        (data["folios"], ["month"]),
        (data["transactions"], ["transaction_date"]),
        (data["holdings"], ["portfolio_date"]),
        (data["benchmarks"], ["date"]),
    ]:
        for col in columns:
            frame[col] = pd.to_datetime(frame[col])
    return data


def save_matplotlib(fig: plt.Figure, filename: str) -> str:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / filename
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return str(path.relative_to(BASE_DIR)).replace("\\", "/")


def save_plotly(fig: go.Figure, filename: str) -> str:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / filename
    fig.write_image(str(path), width=1400, height=760, scale=2)
    return str(path.relative_to(BASE_DIR)).replace("\\", "/")


def crore_formatter(x: float, _: int) -> str:
    return f"{x:,.0f}"


def make_charts(data: dict[str, pd.DataFrame]) -> tuple[list[dict[str, str]], list[str]]:
    fund = data["fund_master"]
    nav = data["nav"].merge(fund[["amfi_code", "scheme_name", "category", "fund_house"]], on="amfi_code", how="left")
    aum = data["aum"].copy()
    sip = data["sip"].copy()
    category = data["category"].copy()
    folios = data["folios"].copy()
    perf = data["performance"].copy()
    txn = data["transactions"].copy()
    holdings = data["holdings"].merge(
        fund[["amfi_code", "category", "sub_category"]],
        on="amfi_code",
        how="left",
        suffixes=("", "_fund"),
    )
    charts: list[dict[str, str]] = []

    def add(title: str, filename: str, kind: str) -> None:
        charts.append({"title": title, "path": f"../reports/figures/{filename}", "kind": kind})

    # 1. Plotly daily NAV for all schemes, with market-period highlights.
    fig = go.Figure()
    for _, group in nav.sort_values("date").groupby("scheme_name"):
        fig.add_trace(
            go.Scatter(
                x=group["date"],
                y=group["nav"],
                mode="lines",
                name=str(group["scheme_name"].iloc[0])[:44],
                line={"width": 1},
                opacity=0.55,
            )
        )
    fig.add_vrect(x0="2023-01-01", x1="2023-12-31", fillcolor="#2ca25f", opacity=0.12, line_width=0)
    fig.add_vrect(x0="2024-01-01", x1="2024-12-31", fillcolor="#de2d26", opacity=0.10, line_width=0)
    fig.update_layout(
        title="Daily NAV Trend for All 40 Schemes, 2022-2026",
        xaxis_title="Date",
        yaxis_title="NAV",
        legend_title="Scheme",
        template="plotly_white",
        showlegend=False,
        annotations=[
            dict(x="2023-07-01", y=1.06, yref="paper", text="2023 bull run", showarrow=False, font=dict(color="#1b7837")),
            dict(x="2024-07-01", y=1.00, yref="paper", text="2024 corrections", showarrow=False, font=dict(color="#b2182b")),
        ],
    )
    save_plotly(fig, "01_nav_daily_all_schemes_plotly.png")
    add("Daily NAV trend for all 40 schemes", "01_nav_daily_all_schemes_plotly.png", "Plotly")

    # 2. Indexed NAV view to make all schemes comparable.
    indexed = nav.sort_values("date").copy()
    indexed["base_nav"] = indexed.groupby("amfi_code")["nav"].transform("first")
    indexed["indexed_nav"] = indexed["nav"] / indexed["base_nav"] * 100
    fig = go.Figure()
    for _, group in indexed.groupby("scheme_name"):
        fig.add_trace(go.Scatter(x=group["date"], y=group["indexed_nav"], mode="lines", line={"width": 1}, opacity=0.45))
    fig.add_vrect(x0="2023-01-01", x1="2023-12-31", fillcolor="#2ca25f", opacity=0.12, line_width=0)
    fig.add_vrect(x0="2024-01-01", x1="2024-12-31", fillcolor="#de2d26", opacity=0.10, line_width=0)
    fig.update_layout(
        title="Indexed NAV Performance, Base = 100",
        xaxis_title="Date",
        yaxis_title="Indexed NAV",
        template="plotly_white",
        showlegend=False,
    )
    save_plotly(fig, "02_nav_indexed_performance_plotly.png")
    add("Indexed NAV performance, base 100", "02_nav_indexed_performance_plotly.png", "Plotly")

    # 3. Mean NAV by category.
    category_nav = nav.groupby(["date", "category"], as_index=False)["nav"].mean()
    fig, ax = plt.subplots(figsize=(11, 5.5))
    sns.lineplot(data=category_nav, x="date", y="nav", hue="category", ax=ax)
    ax.set_title("Average NAV by Fund Category")
    ax.set_xlabel("Date")
    ax.set_ylabel("Average NAV")
    ax.legend(title="Category", ncol=2)
    save_matplotlib(fig, "03_average_nav_by_category.png")
    add("Average NAV by fund category", "03_average_nav_by_category.png", "Seaborn")

    # 4. AUM grouped bar by fund house by year, 2022-2025.
    aum["year"] = aum["date"].dt.year
    aum_year = aum[aum["year"].between(2022, 2025)].groupby(["year", "fund_house"], as_index=False)["aum_crore"].mean()
    fig, ax = plt.subplots(figsize=(12, 6))
    sns.barplot(data=aum_year, x="year", y="aum_crore", hue="fund_house", ax=ax)
    ax.set_title("AUM Growth by Fund House, 2022-2025")
    ax.set_xlabel("Year")
    ax.set_ylabel("Average AUM, Rs. crore")
    ax.yaxis.set_major_formatter(FuncFormatter(crore_formatter))
    sbi = aum_year[aum_year["fund_house"].str.contains("SBI", case=False, na=False)]
    if not sbi.empty:
        top_row = sbi.sort_values("aum_crore", ascending=False).iloc[0]
        ax.annotate(
            "SBI dominance\n~Rs. 12.5L Cr",
            xy=(top_row["year"] - 2022, top_row["aum_crore"]),
            xytext=(0.5, top_row["aum_crore"] * 1.08),
            textcoords="data",
            arrowprops={"arrowstyle": "->", "color": "#333333"},
            fontsize=9,
        )
    ax.legend(title="Fund house", bbox_to_anchor=(1.02, 1), loc="upper left")
    save_matplotlib(fig, "04_aum_growth_grouped_bar.png")
    add("AUM growth grouped bar by fund house", "04_aum_growth_grouped_bar.png", "Seaborn")

    # 5. Latest fund-house AUM ranking.
    latest_aum_date = aum["date"].max()
    latest_aum = aum[aum["date"].eq(latest_aum_date)].sort_values("aum_crore", ascending=False)
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=latest_aum, y="fund_house", x="aum_crore", color="#4c78a8", ax=ax)
    ax.set_title(f"Latest Fund-House AUM Ranking ({latest_aum_date.date()})")
    ax.set_xlabel("AUM, Rs. crore")
    ax.set_ylabel("")
    ax.xaxis.set_major_formatter(FuncFormatter(crore_formatter))
    save_matplotlib(fig, "05_latest_fund_house_aum_ranking.png")
    add("Latest fund-house AUM ranking", "05_latest_fund_house_aum_ranking.png", "Seaborn")

    # 6. SIP inflow trend, Plotly, annotated high.
    high = sip.loc[sip["sip_inflow_crore"].idxmax()]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sip["month"], y=sip["sip_inflow_crore"], mode="lines+markers", name="SIP inflow"))
    fig.add_annotation(
        x=high["month"].strftime("%Y-%m-%d"),
        y=high["sip_inflow_crore"],
        text=f"All-time high<br>Rs. {high['sip_inflow_crore']:,.0f} Cr",
        showarrow=True,
        arrowhead=2,
        ax=30,
        ay=-65,
    )
    fig.update_layout(
        title="Monthly SIP Inflow Trend, Jan 2022-Dec 2025",
        xaxis_title="Month",
        yaxis_title="SIP inflow, Rs. crore",
        template="plotly_white",
    )
    save_plotly(fig, "06_monthly_sip_inflow_plotly.png")
    add("Monthly SIP inflow trend", "06_monthly_sip_inflow_plotly.png", "Plotly")

    # 7. SIP inflow and active accounts.
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=sip["month"], y=sip["sip_inflow_crore"], name="SIP inflow"), secondary_y=False)
    fig.add_trace(go.Scatter(x=sip["month"], y=sip["active_sip_accounts_crore"], name="Active SIP accounts"), secondary_y=True)
    fig.update_yaxes(title_text="SIP inflow, Rs. crore", secondary_y=False)
    fig.update_yaxes(title_text="Active SIP accounts, crore", secondary_y=True)
    fig.update_layout(title="SIP Inflows vs Active SIP Accounts", template="plotly_white")
    save_plotly(fig, "07_sip_inflow_vs_active_accounts.png")
    add("SIP inflows vs active accounts", "07_sip_inflow_vs_active_accounts.png", "Plotly")

    # 8. Category inflow heatmap.
    category["month_label"] = category["month"].dt.strftime("%Y-%m")
    heat = category.pivot_table(index="category", columns="month_label", values="net_inflow_crore", aggfunc="sum")
    fig, ax = plt.subplots(figsize=(14, 5.5))
    sns.heatmap(heat, cmap="RdYlGn", center=0, linewidths=0.1, ax=ax, cbar_kws={"label": "Net inflow, Rs. crore"})
    ax.set_title("Category Net Inflow Heatmap")
    ax.set_xlabel("Month")
    ax.set_ylabel("Fund category")
    ax.tick_params(axis="x", labelrotation=90)
    save_matplotlib(fig, "08_category_inflow_heatmap.png")
    add("Category inflow heatmap", "08_category_inflow_heatmap.png", "Seaborn")

    # 9. Annual category inflows.
    category["year"] = category["month"].dt.year
    cat_year = category.groupby(["year", "category"], as_index=False)["net_inflow_crore"].sum()
    fig, ax = plt.subplots(figsize=(11, 5))
    sns.barplot(data=cat_year, x="year", y="net_inflow_crore", hue="category", ax=ax)
    ax.set_title("Annual Net Inflows by Category")
    ax.set_xlabel("Year")
    ax.set_ylabel("Net inflow, Rs. crore")
    ax.legend(title="Category", ncol=2)
    save_matplotlib(fig, "09_annual_category_inflows.png")
    add("Annual net inflows by category", "09_annual_category_inflows.png", "Seaborn")

    # 10. Investor age distribution.
    age_counts = txn["age_group"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.pie(age_counts, labels=age_counts.index, autopct="%1.1f%%", startangle=90, counterclock=False)
    ax.set_title("Investor Age Group Distribution")
    save_matplotlib(fig, "10_investor_age_group_pie.png")
    add("Investor age group distribution pie", "10_investor_age_group_pie.png", "Matplotlib")

    # 11. SIP amount box plot by age group.
    sip_txn = txn[txn["transaction_type"].eq("SIP")].copy()
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.boxplot(data=sip_txn, x="age_group", y="amount_inr", order=sorted(sip_txn["age_group"].dropna().unique()), ax=ax)
    ax.set_title("SIP Transaction Amount by Age Group")
    ax.set_xlabel("Age group")
    ax.set_ylabel("SIP amount, Rs.")
    save_matplotlib(fig, "11_sip_amount_box_by_age.png")
    add("SIP amount box plot by age group", "11_sip_amount_box_by_age.png", "Seaborn")

    # 12. Gender split.
    gender_counts = txn["gender"].value_counts()
    fig, ax = plt.subplots(figsize=(7, 6))
    sns.barplot(x=gender_counts.index, y=gender_counts.values, palette="Set2", hue=gender_counts.index, legend=False, ax=ax)
    ax.set_title("Investor Gender Split")
    ax.set_xlabel("Gender")
    ax.set_ylabel("Transactions")
    save_matplotlib(fig, "12_gender_split.png")
    add("Investor gender split", "12_gender_split.png", "Seaborn")

    # 13. SIP amount by state.
    sip_state = sip_txn.groupby("state", as_index=False)["amount_inr"].sum().sort_values("amount_inr", ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=sip_state, y="state", x="amount_inr", color="#59a14f", ax=ax)
    ax.set_title("Top States by SIP Transaction Amount")
    ax.set_xlabel("SIP amount, Rs.")
    ax.set_ylabel("")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x / 1e7:.1f} Cr"))
    save_matplotlib(fig, "13_sip_amount_by_state.png")
    add("Horizontal bar chart of SIP amount by state", "13_sip_amount_by_state.png", "Seaborn")

    # 14. T30 vs B30 city-tier split.
    tier_counts = txn["city_tier"].value_counts()
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.pie(tier_counts, labels=tier_counts.index, autopct="%1.1f%%", startangle=90, counterclock=False)
    ax.set_title("T30 vs B30 City-Tier Distribution")
    save_matplotlib(fig, "14_city_tier_pie.png")
    add("T30 vs B30 city-tier pie", "14_city_tier_pie.png", "Matplotlib")

    # 15. Folio count growth.
    fig, ax = plt.subplots(figsize=(11, 5))
    sns.lineplot(data=folios, x="month", y="total_folios_crore", marker="o", ax=ax)
    first, last = folios.iloc[0], folios.iloc[-1]
    for row, label in [(first, "Start"), (last, "Latest")]:
        ax.annotate(
            f"{label}: {row['total_folios_crore']:.2f} Cr",
            xy=(row["month"], row["total_folios_crore"]),
            xytext=(10, 15 if label == "Start" else -28),
            textcoords="offset points",
            arrowprops={"arrowstyle": "->", "color": "#333333"},
        )
    ax.set_title("Industry Folio Count Growth")
    ax.set_xlabel("Month")
    ax.set_ylabel("Total folios, crore")
    save_matplotlib(fig, "15_folio_count_growth.png")
    add("Folio count growth line chart", "15_folio_count_growth.png", "Seaborn")

    # 16. NAV return correlation matrix for 10 selected funds.
    selected_codes = perf.sort_values("aum_crore", ascending=False)["amfi_code"].head(10).tolist()
    selected_names = fund.set_index("amfi_code").loc[selected_codes, "scheme_name"].str.replace(" Fund", "", regex=False)
    nav_wide = nav[nav["amfi_code"].isin(selected_codes)].pivot_table(index="date", columns="amfi_code", values="nav")
    returns = nav_wide.pct_change(fill_method=None).dropna(how="all")
    corr = returns.corr()
    corr.index = selected_names.reindex(corr.index).str.slice(0, 22)
    corr.columns = selected_names.reindex(corr.columns).str.slice(0, 22)
    fig, ax = plt.subplots(figsize=(9, 7))
    sns.heatmap(corr, cmap="vlag", vmin=-1, vmax=1, center=0, annot=True, fmt=".2f", square=True, ax=ax)
    ax.set_title("Daily NAV Return Correlation: Top 10 AUM Funds")
    save_matplotlib(fig, "16_nav_return_correlation_heatmap.png")
    add("NAV daily return correlation matrix", "16_nav_return_correlation_heatmap.png", "Seaborn")

    # 17. Sector allocation donut across equity funds.
    equity_codes = fund[fund["category"].eq("Equity")]["amfi_code"]
    sector_alloc = holdings[holdings["amfi_code"].isin(equity_codes)].groupby("sector", as_index=False)["weight_pct"].sum()
    sector_alloc = sector_alloc.sort_values("weight_pct", ascending=False)
    fig, ax = plt.subplots(figsize=(8, 8))
    wedges, texts = ax.pie(sector_alloc["weight_pct"], labels=sector_alloc["sector"], startangle=90, counterclock=False)
    centre = plt.Circle((0, 0), 0.58, fc="white")
    ax.add_artist(centre)
    ax.set_title("Aggregate Sector Allocation Across Equity Funds")
    ax.legend(wedges, sector_alloc["sector"], title="Sector", loc="center left", bbox_to_anchor=(1, 0.5))
    save_matplotlib(fig, "17_sector_allocation_donut.png")
    add("Sector allocation donut", "17_sector_allocation_donut.png", "Matplotlib")

    # 18. Expense ratio vs returns.
    fig, ax = plt.subplots(figsize=(9, 5.5))
    sns.scatterplot(data=perf, x="expense_ratio_pct", y="return_3yr_pct", hue="category", size="aum_crore", sizes=(40, 450), alpha=0.75, ax=ax)
    ax.axvline(1, color="#555555", linestyle="--", linewidth=1)
    ax.set_title("Expense Ratio vs 3-Year Return")
    ax.set_xlabel("Expense ratio, %")
    ax.set_ylabel("3-year return, %")
    ax.legend(title="Category / AUM", bbox_to_anchor=(1.02, 1), loc="upper left")
    save_matplotlib(fig, "18_expense_ratio_vs_return.png")
    add("Expense ratio vs 3-year return", "18_expense_ratio_vs_return.png", "Seaborn")

    findings = build_findings(data, indexed, aum_year, high, category, sip_txn, tier_counts, folios, corr, sector_alloc)
    return charts, findings


def build_findings(
    data: dict[str, pd.DataFrame],
    indexed_nav: pd.DataFrame,
    aum_year: pd.DataFrame,
    sip_high: pd.Series,
    category: pd.DataFrame,
    sip_txn: pd.DataFrame,
    tier_counts: pd.Series,
    folios: pd.DataFrame,
    corr: pd.DataFrame,
    sector_alloc: pd.DataFrame,
) -> list[str]:
    nav_gain = indexed_nav.groupby("amfi_code")["indexed_nav"].last().sub(100)
    best_code = int(nav_gain.idxmax())
    best_name = data["fund_master"].set_index("amfi_code").loc[best_code, "scheme_name"]
    best_gain = nav_gain.max()

    latest_aum = data["aum"][data["aum"]["date"].eq(data["aum"]["date"].max())].sort_values("aum_crore", ascending=False).iloc[0]
    top_cat = category.groupby("category")["net_inflow_crore"].sum().sort_values(ascending=False).index[0]
    top_state = sip_txn.groupby("state")["amount_inr"].sum().sort_values(ascending=False).index[0]
    tier_share = (tier_counts / tier_counts.sum() * 100).round(1)
    folio_growth = (folios["total_folios_crore"].iloc[-1] / folios["total_folios_crore"].iloc[0] - 1) * 100
    corr_mean = corr.where(~np.eye(corr.shape[0], dtype=bool)).stack().mean()
    top_sector = sector_alloc.iloc[0]
    low_expense_count = int((data["performance"]["expense_ratio_pct"] < 1).sum())

    return [
        f"NAV compounding was broad-based, with {best_name} ending the period about {best_gain:.1f}% above its 2022 base; see Chart 2.",
        f"The latest fund-house AUM snapshot is led by {latest_aum['fund_house']} at Rs. {latest_aum['aum_crore']:,.0f} crore; see Chart 5.",
        f"SIP inflows reached their observed high of Rs. {sip_high['sip_inflow_crore']:,.0f} crore in {sip_high['month'].strftime('%b %Y')}; see Chart 6.",
        f"{top_cat} attracted the highest cumulative net category inflow over the period; see Charts 8 and 9.",
        f"SIP ticket sizes vary meaningfully by age group, with visible upper-tail outliers across cohorts; see Chart 11.",
        f"{top_state} contributes the largest aggregate SIP transaction amount among states; see Chart 13.",
        f"City-tier participation is split {', '.join(f'{idx}: {val:.1f}%' for idx, val in tier_share.items())}; see Chart 14.",
        f"Total folios grew by {folio_growth:.1f}% across the available series; see Chart 15.",
        f"The selected top-AUM funds have an average pairwise daily-return correlation of {corr_mean:.2f}; see Chart 16.",
        f"{top_sector['sector']} is the largest aggregate equity-holding sector, while {low_expense_count} schemes have expense ratios below 1%; see Charts 17 and 18.",
    ]


def write_notebook(charts: list[dict[str, str]], findings: list[str]) -> None:
    NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    nb = nbf.v4.new_notebook()
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "pygments_lexer": "ipython3"},
    }

    cells = [
        nbf.v4.new_markdown_cell(
            "# Exploratory Data Analysis (EDA)\n\n"
            "Day 3 analysis for the Mutual Fund Analytics capstone. "
            "The notebook uses Day 2 cleaned CSVs and exports report-ready PNG charts to `reports/figures/`."
        ),
        nbf.v4.new_code_cell(
            "from pathlib import Path\n"
            "import pandas as pd\n"
            "import numpy as np\n"
            "import matplotlib.pyplot as plt\n"
            "import seaborn as sns\n"
            "import plotly.graph_objects as go\n\n"
            "BASE_DIR = Path('..').resolve()\n"
            "PROCESSED_DIR = BASE_DIR / 'data' / 'processed'\n"
            "FIG_DIR = BASE_DIR / 'reports' / 'figures'\n"
            "sns.set_theme(style='whitegrid')"
        ),
        nbf.v4.new_code_cell(
            "# Load cleaned Day 2 datasets\n"
            "fund_master = pd.read_csv(PROCESSED_DIR / 'fund_master_clean.csv')\n"
            "nav = pd.read_csv(PROCESSED_DIR / 'nav_history_clean.csv', parse_dates=['date'])\n"
            "aum = pd.read_csv(PROCESSED_DIR / 'aum_by_fund_house_clean.csv', parse_dates=['date'])\n"
            "sip = pd.read_csv(PROCESSED_DIR / 'monthly_sip_inflows_clean.csv', parse_dates=['month'])\n"
            "category = pd.read_csv(PROCESSED_DIR / 'category_inflows_clean.csv', parse_dates=['month'])\n"
            "folios = pd.read_csv(PROCESSED_DIR / 'industry_folio_count_clean.csv', parse_dates=['month'])\n"
            "transactions = pd.read_csv(PROCESSED_DIR / 'investor_transactions_clean.csv', parse_dates=['transaction_date'])\n"
            "holdings = pd.read_csv(PROCESSED_DIR / 'portfolio_holdings_clean.csv', parse_dates=['portfolio_date'])\n"
            "performance = pd.read_csv(PROCESSED_DIR / 'scheme_performance_clean.csv')\n"
            "nav.shape, transactions.shape"
        ),
        nbf.v4.new_markdown_cell(
            "## Reproducibility\n\n"
            "Run `python generate_eda.py` from the repository root to regenerate this notebook and every PNG below."
        ),
    ]

    cells.append(nbf.v4.new_markdown_cell("## Chart Gallery\n"))
    for index, chart in enumerate(charts, start=1):
        cells.append(
            nbf.v4.new_markdown_cell(
                f"### Chart {index}: {chart['title']}\n\n"
                f"Tool: {chart['kind']}\n\n"
                f"![{chart['title']}]({chart['path']})"
            )
        )

    cells.append(nbf.v4.new_markdown_cell("## 10 Key EDA Findings\n"))
    for index, finding in enumerate(findings, start=1):
        cells.append(nbf.v4.new_markdown_cell(f"**Insight {index}.** {finding}"))

    nb["cells"] = cells
    NOTEBOOK_PATH.write_text(nbf.writes(nb), encoding="utf-8")


def main() -> None:
    warnings.filterwarnings("ignore", category=FutureWarning)
    data = load_data()
    charts, findings = make_charts(data)
    write_notebook(charts, findings)
    print(f"Created {len(charts)} PNG charts in {FIG_DIR}")
    print(f"Wrote notebook: {NOTEBOOK_PATH}")


if __name__ == "__main__":
    main()
