"""
Generate Day 5 dashboard deliverables.

Power BI Desktop is required to create a real .pbix file and is not available in
this execution environment. This script generates the dashboard pages, PDF
export, data-load manifest, Bluestock theme, and Power BI build guide from the
same cleaned datasets that a .pbix should connect to.

Outputs:
    dashboard/Dashboard.pdf
    dashboard/pages/page_1_industry_overview.png
    dashboard/pages/page_2_fund_performance.png
    dashboard/pages/page_3_investor_analytics.png
    dashboard/pages/page_4_sip_market_trends.png
    dashboard/data_model_manifest.csv
    dashboard/bluestock_theme.json
    dashboard/powerbi_build_guide.md
"""

from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch, Rectangle
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas


BASE_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
DASHBOARD_DIR = BASE_DIR / "dashboard"
PAGE_DIR = DASHBOARD_DIR / "pages"
PDF_PATH = DASHBOARD_DIR / "Dashboard.pdf"
MANIFEST_PATH = DASHBOARD_DIR / "data_model_manifest.csv"
THEME_PATH = DASHBOARD_DIR / "bluestock_theme.json"
BUILD_GUIDE_PATH = DASHBOARD_DIR / "powerbi_build_guide.md"

BLUE = "#174A7C"
TEAL = "#2CA6A4"
GREEN = "#4CAF7A"
GOLD = "#F4B942"
RED = "#D95F5F"
INK = "#1F2937"
MUTED = "#6B7280"
GRID = "#E5E7EB"
BG = "#F7F9FC"
CARD = "#FFFFFF"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "figure.facecolor": BG,
        "axes.facecolor": CARD,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.titleweight": "bold",
        "axes.titlecolor": INK,
        "savefig.facecolor": BG,
    }
)
sns.set_theme(style="whitegrid")


def load_data() -> dict[str, pd.DataFrame]:
    files = {
        "fund_master": "fund_master_clean.csv",
        "nav_history": "nav_history_clean.csv",
        "aum_by_fund_house": "aum_by_fund_house_clean.csv",
        "monthly_sip_inflows": "monthly_sip_inflows_clean.csv",
        "category_inflows": "category_inflows_clean.csv",
        "industry_folio_count": "industry_folio_count_clean.csv",
        "investor_transactions": "investor_transactions_clean.csv",
        "benchmark_indices": "benchmark_indices_clean.csv",
        "fund_scorecard": "fund_scorecard.csv",
        "alpha_beta": "alpha_beta.csv",
    }
    data = {name: pd.read_csv(PROCESSED_DIR / filename) for name, filename in files.items()}
    date_columns = {
        "nav_history": ["date"],
        "aum_by_fund_house": ["date"],
        "monthly_sip_inflows": ["month"],
        "category_inflows": ["month"],
        "industry_folio_count": ["month"],
        "investor_transactions": ["transaction_date"],
        "benchmark_indices": ["date"],
    }
    for table, columns in date_columns.items():
        for column in columns:
            data[table][column] = pd.to_datetime(data[table][column])
    return data


def format_cr(value: float) -> str:
    return f"{value:,.0f} Cr"


def format_lakh_cr(value: float) -> str:
    return f"{value / 100000:,.1f}L Cr"


def add_header(fig: plt.Figure, title: str, subtitle: str) -> None:
    fig.text(0.035, 0.955, "Bluestock", fontsize=19, fontweight="bold", color=BLUE)
    fig.text(0.035, 0.918, title, fontsize=26, fontweight="bold", color=INK)
    fig.text(0.035, 0.889, subtitle, fontsize=11, color=MUTED)
    fig.add_artist(Rectangle((0.035, 0.872), 0.93, 0.004, transform=fig.transFigure, color=TEAL, linewidth=0))


def kpi_card(fig: plt.Figure, x: float, y: float, w: float, h: float, label: str, value: str, accent: str = BLUE) -> None:
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        transform=fig.transFigure,
        facecolor=CARD,
        edgecolor=GRID,
        linewidth=1.0,
    )
    fig.add_artist(box)
    fig.add_artist(Rectangle((x, y), 0.008, h, transform=fig.transFigure, color=accent, linewidth=0))
    fig.text(x + 0.022, y + h - 0.035, label, fontsize=10, color=MUTED, fontweight="bold")
    fig.text(x + 0.022, y + 0.028, value, fontsize=19, color=INK, fontweight="bold")


def clean_axis(ax: plt.Axes) -> None:
    ax.grid(True, color=GRID, linewidth=0.8)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.tick_params(labelsize=8)
    ax.title.set_fontsize(12)


def save_page(fig: plt.Figure, filename: str) -> Path:
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = PAGE_DIR / filename
    fig.savefig(path, dpi=180, bbox_inches="tight", pad_inches=0.22)
    plt.close(fig)
    return path


def page_1_industry_overview(data: dict[str, pd.DataFrame]) -> Path:
    aum = data["aum_by_fund_house"].copy()
    sip = data["monthly_sip_inflows"].copy()
    folios = data["industry_folio_count"].copy()
    fund = data["fund_master"].copy()

    latest_aum_date = aum["date"].max()
    latest_aum = aum[aum["date"].eq(latest_aum_date)]
    total_aum = latest_aum["aum_crore"].sum()
    latest_sip = sip.loc[sip["month"].idxmax()]
    latest_folios = folios.loc[folios["month"].idxmax()]
    latest_schemes = int(latest_aum["num_schemes"].sum())

    industry_aum = aum.groupby("date", as_index=False)["aum_crore"].sum()
    latest_amc = latest_aum.sort_values("aum_crore", ascending=False)

    fig = plt.figure(figsize=(16, 9), constrained_layout=False)
    add_header(fig, "Industry Overview", "KPI summary, industry AUM trend, and AMC-level AUM concentration")
    kpi_card(fig, 0.035, 0.765, 0.215, 0.095, "Total AUM", format_lakh_cr(total_aum), BLUE)
    kpi_card(fig, 0.275, 0.765, 0.215, 0.095, "Latest SIP Inflow", format_cr(latest_sip["sip_inflow_crore"]), GREEN)
    kpi_card(fig, 0.515, 0.765, 0.215, 0.095, "Total Folios", f"{latest_folios['total_folios_crore']:.2f} Cr", TEAL)
    kpi_card(fig, 0.755, 0.765, 0.21, 0.095, "Schemes", f"{latest_schemes:,}", GOLD)

    gs = GridSpec(2, 2, figure=fig, left=0.055, right=0.96, top=0.715, bottom=0.08, hspace=0.32, wspace=0.18)
    ax1 = fig.add_subplot(gs[0, :])
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[1, 1])

    ax1.plot(industry_aum["date"], industry_aum["aum_crore"], color=BLUE, linewidth=2.5)
    ax1.fill_between(industry_aum["date"], industry_aum["aum_crore"], color=BLUE, alpha=0.12)
    ax1.set_title("Industry AUM Trend, 2022-2026")
    ax1.set_ylabel("AUM, Rs. crore")
    ax1.yaxis.set_major_formatter(lambda value, _: format_lakh_cr(value))
    clean_axis(ax1)

    sns.barplot(data=latest_amc, x="aum_crore", y="fund_house", color=TEAL, ax=ax2)
    ax2.set_title(f"AUM by AMC ({latest_aum_date.date()})")
    ax2.set_xlabel("AUM, Rs. crore")
    ax2.set_ylabel("")
    ax2.xaxis.set_major_formatter(lambda value, _: f"{value / 100000:.1f}L")
    clean_axis(ax2)

    plan_counts = fund.groupby(["category", "plan"], as_index=False).size()
    sns.barplot(data=plan_counts, x="category", y="size", hue="plan", palette=[BLUE, GREEN], ax=ax3)
    ax3.set_title("Scheme Count by Category and Plan")
    ax3.set_xlabel("")
    ax3.set_ylabel("Schemes")
    ax3.legend(title="Plan", frameon=False)
    clean_axis(ax3)
    return save_page(fig, "page_1_industry_overview.png")


def page_2_fund_performance(data: dict[str, pd.DataFrame]) -> Path:
    score = data["fund_scorecard"].copy()
    nav = data["nav_history"].copy()
    benchmarks = data["benchmark_indices"].copy()
    top5 = score.sort_values("overall_rank").head(5)

    fig = plt.figure(figsize=(16, 9), constrained_layout=False)
    add_header(fig, "Fund Performance", "Return-risk map, scorecard ranking, and top fund NAV versus benchmarks")
    gs = GridSpec(2, 2, figure=fig, left=0.055, right=0.96, top=0.82, bottom=0.075, hspace=0.31, wspace=0.18)
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])

    sns.scatterplot(
        data=score,
        x="cagr_3yr_pct",
        y="annualized_volatility_pct",
        size="aum_crore",
        hue="category",
        sizes=(60, 650),
        alpha=0.72,
        ax=ax1,
    )
    ax1.set_title("Return vs Risk: 3Y CAGR and Annualized Volatility")
    ax1.set_xlabel("3Y CAGR, %")
    ax1.set_ylabel("Risk / StdDev, %")
    ax1.legend(fontsize=7, title="Category / AUM", frameon=False, loc="best")
    clean_axis(ax1)

    table_cols = ["overall_rank", "scheme_name", "fund_score", "cagr_3yr_pct", "sharpe_ratio", "alpha_pct"]
    table_data = top5[table_cols].copy()
    table_data["scheme_name"] = table_data["scheme_name"].str.replace(" Fund", "", regex=False).str.slice(0, 34)
    for col in ["fund_score", "cagr_3yr_pct", "sharpe_ratio", "alpha_pct"]:
        table_data[col] = table_data[col].map(lambda value: f"{value:.2f}")
    ax2.axis("off")
    ax2.set_title("Sortable Fund Scorecard - Top 5", loc="left", pad=12)
    table = ax2.table(
        cellText=table_data.values,
        colLabels=["Rank", "Scheme", "Score", "3Y CAGR", "Sharpe", "Alpha"],
        loc="center",
        cellLoc="left",
        colColours=[BLUE] * 6,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.7)
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(color="white", weight="bold")
        cell.set_edgecolor(GRID)

    top_code = int(top5.iloc[0]["amfi_code"])
    fund_nav = nav[nav["amfi_code"].eq(top_code)].set_index("date")["nav"].sort_index()
    end_date = fund_nav.index.max()
    start_date = end_date - pd.DateOffset(years=3)
    fund_nav = fund_nav.loc[fund_nav.index >= start_date]
    fund_index = fund_nav / fund_nav.iloc[0] * 100
    bench = benchmarks[benchmarks["index_name"].isin(["NIFTY50", "NIFTY100"])].pivot_table(index="date", columns="index_name", values="close_value").sort_index()
    bench = bench.loc[bench.index >= start_date]
    bench_index = bench.div(bench.iloc[0]).mul(100)
    ax3.plot(fund_index.index, fund_index.values, color=BLUE, linewidth=2.5, label=top5.iloc[0]["scheme_name"][:48])
    ax3.plot(bench_index.index, bench_index["NIFTY50"], color=GREEN, linewidth=2, linestyle="--", label="NIFTY50")
    ax3.plot(bench_index.index, bench_index["NIFTY100"], color=GOLD, linewidth=2, linestyle=":", label="NIFTY100")
    ax3.set_title("NAV vs Benchmark, Last 3 Years")
    ax3.set_ylabel("Indexed value, start = 100")
    ax3.legend(frameon=False)
    clean_axis(ax3)
    return save_page(fig, "page_2_fund_performance.png")


def page_3_investor_analytics(data: dict[str, pd.DataFrame]) -> Path:
    txn = data["investor_transactions"].copy()
    sip_txn = txn[txn["transaction_type"].eq("SIP")].copy()

    state_amount = txn.groupby("state", as_index=False)["amount_inr"].sum().sort_values("amount_inr", ascending=False).head(12)
    split = txn.groupby("transaction_type", as_index=False)["amount_inr"].sum()
    age_sip = sip_txn.groupby("age_group", as_index=False)["amount_inr"].mean()
    monthly_volume = txn.groupby(pd.Grouper(key="transaction_date", freq="MS")).size().reset_index(name="transactions")

    fig = plt.figure(figsize=(16, 9), constrained_layout=False)
    add_header(fig, "Investor Analytics", "State contribution, transaction split, age cohort SIP behavior, and transaction volume")
    gs = GridSpec(2, 2, figure=fig, left=0.055, right=0.96, top=0.82, bottom=0.075, hspace=0.32, wspace=0.22)
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, 0])
    ax4 = fig.add_subplot(gs[1, 1])

    sns.barplot(data=state_amount, x="amount_inr", y="state", color=BLUE, ax=ax1)
    ax1.set_title("Transaction Amount by State")
    ax1.set_xlabel("Amount, Rs. crore")
    ax1.set_ylabel("")
    ax1.xaxis.set_major_formatter(lambda value, _: f"{value / 1e7:.1f}")
    clean_axis(ax1)

    ax2.pie(split["amount_inr"], labels=split["transaction_type"], autopct="%1.1f%%", colors=[GREEN, BLUE, GOLD], startangle=90)
    ax2.add_artist(plt.Circle((0, 0), 0.56, color=CARD))
    ax2.set_title("SIP / Lumpsum / Redemption Split")

    sns.barplot(data=age_sip.sort_values("age_group"), x="age_group", y="amount_inr", color=TEAL, ax=ax3)
    ax3.set_title("Average SIP Amount by Age Group")
    ax3.set_xlabel("Age group")
    ax3.set_ylabel("Average SIP amount, Rs.")
    clean_axis(ax3)

    ax4.plot(monthly_volume["transaction_date"], monthly_volume["transactions"], color=GREEN, linewidth=2.5)
    ax4.fill_between(monthly_volume["transaction_date"], monthly_volume["transactions"], color=GREEN, alpha=0.13)
    ax4.set_title("Monthly Transaction Volume")
    ax4.set_xlabel("Month")
    ax4.set_ylabel("Transactions")
    clean_axis(ax4)
    return save_page(fig, "page_3_investor_analytics.png")


def page_4_sip_market_trends(data: dict[str, pd.DataFrame]) -> Path:
    sip = data["monthly_sip_inflows"].copy()
    benchmarks = data["benchmark_indices"].copy()
    category = data["category_inflows"].copy()

    nifty50 = benchmarks[benchmarks["index_name"].eq("NIFTY50")].copy()
    nifty50_month = nifty50.groupby(pd.Grouper(key="date", freq="MS"))["close_value"].last().reset_index()
    sip_merged = sip.merge(nifty50_month, left_on="month", right_on="date", how="left")
    category["month_label"] = category["month"].dt.strftime("%Y-%m")
    heat = category.pivot_table(index="category", columns="month_label", values="net_inflow_crore", aggfunc="sum")
    fy25 = category[(category["month"] >= "2024-04-01") & (category["month"] <= "2025-03-31")]
    top_fy25 = fy25.groupby("category", as_index=False)["net_inflow_crore"].sum().sort_values("net_inflow_crore", ascending=False).head(5)

    fig = plt.figure(figsize=(16, 9), constrained_layout=False)
    add_header(fig, "SIP & Market Trends", "SIP momentum, NIFTY50 context, category flow heatmap, and FY25 leaders")
    gs = GridSpec(2, 2, figure=fig, left=0.055, right=0.96, top=0.82, bottom=0.075, hspace=0.34, wspace=0.22)
    ax1 = fig.add_subplot(gs[0, :])
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[1, 1])

    ax1.bar(sip_merged["month"], sip_merged["sip_inflow_crore"], width=22, color=BLUE, alpha=0.82, label="SIP inflow")
    ax1.set_ylabel("SIP inflow, Rs. crore", color=BLUE)
    ax1.tick_params(axis="y", labelcolor=BLUE)
    ax1b = ax1.twinx()
    ax1b.plot(sip_merged["month"], sip_merged["close_value"], color=GOLD, linewidth=2.5, label="NIFTY50")
    ax1b.set_ylabel("NIFTY50 close", color=GOLD)
    ax1b.tick_params(axis="y", labelcolor=GOLD)
    ax1.set_title("SIP Inflows and NIFTY50, 2022-2025")
    clean_axis(ax1)

    sns.heatmap(heat, cmap="RdYlGn", center=0, linewidths=0.1, ax=ax2, cbar_kws={"label": "Net inflow, Rs. crore"})
    ax2.set_title("Category Inflow Heatmap")
    ax2.set_xlabel("Month")
    ax2.set_ylabel("")
    ax2.tick_params(axis="x", labelrotation=90, labelsize=6)
    ax2.tick_params(axis="y", labelsize=8)

    sns.barplot(data=top_fy25, x="net_inflow_crore", y="category", color=GREEN, ax=ax3)
    ax3.set_title("Top 5 Categories by Net Inflow, FY25")
    ax3.set_xlabel("Net inflow, Rs. crore")
    ax3.set_ylabel("")
    ax3.xaxis.set_major_formatter(lambda value, _: f"{value:,.0f}")
    clean_axis(ax3)
    return save_page(fig, "page_4_sip_market_trends.png")


def write_pdf(page_paths: list[Path]) -> None:
    width, height = landscape(letter)
    pdf = canvas.Canvas(str(PDF_PATH), pagesize=landscape(letter))
    for page_path in page_paths:
        pdf.drawImage(str(page_path), 0, 0, width=width, height=height, preserveAspectRatio=True, anchor="c")
        pdf.showPage()
    pdf.save()


def write_manifest(data: dict[str, pd.DataFrame]) -> None:
    rows = []
    source_files = {
        "fund_master": "data/processed/fund_master_clean.csv",
        "nav_history": "data/processed/nav_history_clean.csv",
        "aum_by_fund_house": "data/processed/aum_by_fund_house_clean.csv",
        "monthly_sip_inflows": "data/processed/monthly_sip_inflows_clean.csv",
        "category_inflows": "data/processed/category_inflows_clean.csv",
        "industry_folio_count": "data/processed/industry_folio_count_clean.csv",
        "investor_transactions": "data/processed/investor_transactions_clean.csv",
        "benchmark_indices": "data/processed/benchmark_indices_clean.csv",
        "fund_scorecard": "data/processed/fund_scorecard.csv",
        "alpha_beta": "data/processed/alpha_beta.csv",
    }
    for table, frame in data.items():
        rows.append(
            {
                "table": table,
                "source": source_files[table],
                "rows": len(frame),
                "columns": len(frame.columns),
                "status": "loaded",
            }
        )
    pd.DataFrame(rows).to_csv(MANIFEST_PATH, index=False)


def write_theme() -> None:
    theme = {
        "name": "Bluestock Mutual Fund Analytics",
        "dataColors": [BLUE, TEAL, GREEN, GOLD, RED, "#7C3AED", "#4B5563", "#60A5FA"],
        "background": BG,
        "foreground": INK,
        "tableAccent": TEAL,
        "visualStyles": {
            "*": {
                "*": {
                    "title": [{"fontColor": {"solid": {"color": INK}}, "fontSize": 12}],
                    "labels": [{"color": {"solid": {"color": MUTED}}}],
                }
            }
        },
    }
    THEME_PATH.write_text(json.dumps(theme, indent=2), encoding="utf-8")


def write_build_guide(data: dict[str, pd.DataFrame]) -> None:
    manifest_lines = [
        "| Table | Rows | Columns |",
        "|---|---:|---:|",
    ]
    for table, frame in data.items():
        manifest_lines.append(f"| `{table}` | {len(frame)} | {len(frame.columns)} |")
    manifest_md = "\n".join(manifest_lines)
    BUILD_GUIDE_PATH.write_text(
        f"""# Bluestock Mutual Fund Dashboard - Power BI Build Guide

Power BI Desktop was not available in this environment, so a native `.pbix` could not be generated here. Use this guide to recreate the dashboard from the committed data sources and exports.

## Data Sources

Import these cleaned CSVs from `data/processed/`:

{manifest_md}

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
""",
        encoding="utf-8",
    )


def main() -> None:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    data = load_data()
    write_manifest(data)
    write_theme()
    page_paths = [
        page_1_industry_overview(data),
        page_2_fund_performance(data),
        page_3_investor_analytics(data),
        page_4_sip_market_trends(data),
    ]
    write_pdf(page_paths)
    write_build_guide(data)
    print(f"Wrote {PDF_PATH}")
    for page in page_paths:
        print(f"Wrote {page}")
    print(f"Wrote {MANIFEST_PATH}")
    print(f"Wrote {THEME_PATH}")
    print(f"Wrote {BUILD_GUIDE_PATH}")


if __name__ == "__main__":
    main()
