"""Simple mutual fund recommender by risk appetite.

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
