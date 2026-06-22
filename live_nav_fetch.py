"""
live_nav_fetch.py
=================
Day 1 — Mutual Fund Analytics Capstone.

Fetches live Net Asset Value (NAV) history from the public AMFI mirror API
at https://api.mfapi.in for a set of scheme codes, parses the JSON response,
and persists it as RAW CSV files under ``data/raw/``.

Outputs (all written to ``data/raw/live_api/``):
    * nav_<code>.csv ........ raw NAV history for one scheme (date, nav).
    * nav_history.csv ....... combined long-format NAV history for all schemes.
    * fund_master.csv ....... one row per scheme describing the fund
                              (fund house, category, sub-category, risk grade, ISINs).
    * fetch_manifest.csv .... audit log of what was fetched and when.

Run:
    python live_nav_fetch.py

The script is defensive: a single failed scheme does not abort the run, the
HTTP layer retries transient errors, and a clear summary is printed at the end.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

BASE_DIR = Path(__file__).resolve().parent
# Live API pulls live in their own subfolder so they never collide with the
# 10 provided datasets (01_fund_master.csv / 02_nav_history.csv ...) in data/raw.
RAW_DIR = BASE_DIR / "data" / "raw" / "live_api"

API_TEMPLATE = "https://api.mfapi.in/mf/{code}"
REQUEST_TIMEOUT = 30          # seconds
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0           # seconds, multiplied by attempt number

# Scheme codes to fetch, with the NAME EACH CODE IS LABELLED WITH IN THE BRIEF.
# The script records whatever the live API reports as the source of truth and
# flags every code whose live scheme name disagrees with the brief. (At the time
# of writing, 5 of these 6 codes resolve to a completely different fund than the
# brief claims — e.g. 125497 is "SBI Small Cap", not "HDFC Top 100".)
SCHEMES = [
    {"code": 125497, "brief_name": "HDFC Top 100 Direct"},
    {"code": 119551, "brief_name": "SBI Bluechip"},
    {"code": 120503, "brief_name": "ICICI Bluechip"},
    {"code": 118632, "brief_name": "Nippon Large Cap"},
    {"code": 119092, "brief_name": "Axis Bluechip"},
    {"code": 120841, "brief_name": "Kotak Bluechip"},
]


def matches_brief(brief_name: str, api_scheme_name: str) -> bool:
    """The brief's fund-house token (first word) should appear in the live
    scheme name. e.g. brief 'Nippon Large Cap' matches API 'Nippon India
    Large Cap Fund ...'; brief 'HDFC Top 100' does NOT match 'SBI Small Cap'."""
    if not brief_name or not api_scheme_name:
        return False
    house_token = brief_name.split()[0].lower()
    return house_token in api_scheme_name.lower()


# --------------------------------------------------------------------------- #
# Derivation helpers (category / sub-category / risk grade / plan)
# --------------------------------------------------------------------------- #

def split_category(scheme_category: str) -> tuple[str, str]:
    """Split an AMFI scheme_category like 'Equity Scheme - Large Cap Fund'
    into (category, sub_category). Falls back gracefully when the dash is
    absent."""
    if not scheme_category:
        return ("Unknown", "Unknown")
    parts = [p.strip() for p in scheme_category.split(" - ", 1)]
    if len(parts) == 2:
        return (parts[0], parts[1])
    return (parts[0], parts[0])


def derive_risk_grade(sub_category: str, scheme_name: str) -> str:
    """Heuristic SEBI-riskometer-style grade derived from the fund's
    sub-category. This is DERIVED (the mfapi.in feed carries no riskometer
    field) and documented as such in the data-quality summary."""
    text = f"{sub_category} {scheme_name}".lower()
    if any(k in text for k in ("small cap",)):
        return "Very High"
    if any(k in text for k in ("mid cap", "sectoral", "thematic")):
        return "Very High"
    if any(k in text for k in ("large & mid", "multi cap", "flexi cap", "elss")):
        return "High"
    if any(k in text for k in ("large cap", "bluechip", "blue chip", "top 100", "index")):
        return "High"
    if any(k in text for k in ("hybrid", "balanced")):
        return "Moderately High"
    if any(k in text for k in ("debt", "bond", "gilt", "liquid", "money market")):
        return "Low to Moderate"
    return "Moderate"


def derive_plan_type(scheme_name: str) -> str:
    return "Direct" if "direct" in (scheme_name or "").lower() else "Regular"


def derive_option(scheme_name: str) -> str:
    name = (scheme_name or "").lower()
    if "idcw" in name or "dividend" in name:
        return "IDCW/Dividend"
    if "growth" in name:
        return "Growth"
    return "Unknown"


# --------------------------------------------------------------------------- #
# HTTP layer
# --------------------------------------------------------------------------- #

def fetch_scheme(session: requests.Session, code: int) -> dict:
    """GET one scheme from the API, with retries on transient failures.
    Returns the parsed JSON dict. Raises on permanent failure."""
    url = API_TEMPLATE.format(code=code)
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict) or "data" not in payload:
                raise ValueError("unexpected JSON shape (no 'data' key)")
            return payload
        except Exception as err:  # noqa: BLE001 - we want to retry broadly
            last_err = err
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"    attempt {attempt} failed ({err}); retrying in {wait:.0f}s...")
                time.sleep(wait)
    raise RuntimeError(f"failed to fetch scheme {code} after {MAX_RETRIES} attempts: {last_err}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    session = requests.Session()
    session.headers.update({"User-Agent": "mf-analytics-capstone/1.0 (+day1 ingestion)"})

    master_rows: list[dict] = []
    nav_frames: list[pd.DataFrame] = []
    manifest_rows: list[dict] = []

    print("=" * 78)
    print("LIVE NAV FETCH — mfapi.in")
    print(f"Fetched at (UTC): {fetched_at}")
    print("=" * 78)

    for spec in SCHEMES:
        code = spec["code"]
        print(f"\n[{code}] brief: {spec['brief_name']}")
        try:
            payload = fetch_scheme(session, code)
        except Exception as err:  # noqa: BLE001
            print(f"    ERROR: {err}")
            manifest_rows.append({
                "scheme_code": code, "brief_name": spec["brief_name"],
                "api_scheme_name": "", "api_scheme_code": "",
                "matches_brief": False, "status": "FAILED", "rows": 0,
                "latest_date": None, "oldest_date": None,
                "error": str(err), "fetched_at_utc": fetched_at,
            })
            continue

        meta = payload.get("meta", {}) or {}
        data = payload.get("data", []) or []

        scheme_name = meta.get("scheme_name", "") or ""
        fund_house = meta.get("fund_house", "") or ""
        scheme_type = meta.get("scheme_type", "") or ""
        scheme_category = meta.get("scheme_category", "") or ""
        api_code = meta.get("scheme_code", code)
        category, sub_category = split_category(scheme_category)

        # ---- per-scheme RAW nav file (faithful to the API: DD-MM-YYYY + string nav)
        nav_df = pd.DataFrame(data, columns=["date", "nav"])
        per_scheme_path = RAW_DIR / f"nav_{code}.csv"
        nav_df.to_csv(per_scheme_path, index=False, encoding="utf-8")

        # ---- contribution to the combined long-format nav_history
        combined = nav_df.copy()
        combined.insert(0, "scheme_code", code)
        combined.insert(1, "scheme_name", scheme_name)
        nav_frames.append(combined)

        # ---- fund_master row
        master_rows.append({
            "scheme_code": code,
            "scheme_name": scheme_name,
            "fund_house": fund_house,
            "scheme_type": scheme_type,
            "scheme_category": scheme_category,
            "category": category,
            "sub_category": sub_category,
            "risk_grade": derive_risk_grade(sub_category, scheme_name),
            "plan_type": derive_plan_type(scheme_name),
            "option": derive_option(scheme_name),
            "isin_growth": meta.get("isin_growth"),
            "isin_div_reinvestment": meta.get("isin_div_reinvestment"),
        })

        # ---- manifest / anomaly flag
        ok_match = matches_brief(spec["brief_name"], scheme_name)
        manifest_rows.append({
            "scheme_code": code,
            "brief_name": spec["brief_name"],
            "api_scheme_name": scheme_name,
            "api_scheme_code": api_code,
            "matches_brief": bool(ok_match),
            "status": "OK",
            "rows": len(nav_df),
            "latest_date": nav_df["date"].iloc[0] if len(nav_df) else None,
            "oldest_date": nav_df["date"].iloc[-1] if len(nav_df) else None,
            "error": "",
            "fetched_at_utc": fetched_at,
        })

        flag = "" if ok_match else "   <-- DOES NOT MATCH BRIEF"
        print(f"    name : {scheme_name}{flag}")
        print(f"    house: {fund_house}  |  category: {scheme_category}")
        print(f"    rows : {len(nav_df)}  ->  {per_scheme_path.name}")

    # ----------------------------------------------------------------------- #
    # Persist combined artefacts
    # ----------------------------------------------------------------------- #
    if not master_rows:
        print("\nNo schemes fetched successfully — nothing to write.")
        return 1

    fund_master = pd.DataFrame(master_rows)
    fund_master.to_csv(RAW_DIR / "fund_master.csv", index=False, encoding="utf-8")

    nav_history = pd.concat(nav_frames, ignore_index=True)
    nav_history.to_csv(RAW_DIR / "nav_history.csv", index=False, encoding="utf-8")

    manifest = pd.DataFrame(manifest_rows)
    manifest.to_csv(RAW_DIR / "fetch_manifest.csv", index=False, encoding="utf-8")

    print("\n" + "=" * 78)
    print("WROTE RAW ARTEFACTS")
    print("=" * 78)
    print(f"  fund_master.csv ... {len(fund_master)} schemes")
    print(f"  nav_history.csv ... {len(nav_history)} NAV rows")
    print(f"  fetch_manifest.csv  {len(manifest)} log rows")
    ok = (manifest["status"] == "OK").sum()
    print(f"\n  {ok}/{len(SCHEMES)} schemes fetched successfully.")
    mismatches = int((~manifest["matches_brief"] & (manifest["status"] == "OK")).sum())
    if mismatches:
        print(f"  NOTE: {mismatches}/{ok} fetched scheme name(s) DISAGREE with the brief "
              f"— see data/raw/live_api/fetch_manifest.csv (matches_brief column).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
