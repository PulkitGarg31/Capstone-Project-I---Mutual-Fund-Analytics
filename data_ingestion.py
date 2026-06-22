"""
data_ingestion.py
=================
Day 1 — Mutual Fund Analytics Capstone.

End-to-end Day-1 ingestion + exploratory data-quality pass:

    1. Load EVERY CSV found in ``data/raw/`` and profile it
       (.shape, .dtypes, .head(), plus automatic anomaly detection).
    2. Explore ``fund_master`` — unique fund houses, categories,
       sub-categories and risk grades; explain the AMFI scheme-code structure.
    3. Validate AMFI codes — confirm every code in ``fund_master`` exists in
       ``nav_history`` (and report the reverse), plus NAV-level quality checks.
    4. Emit a cleaned ``data/processed/nav_history_clean.csv`` and a written
       ``reports/data_quality_summary.md``.

This script is schema-tolerant: if you later drop the 10 provided CSV datasets
into ``data/raw/``, they are profiled automatically, and ``fund_master`` /
``nav_history`` are located by filename or by their columns.

Run (after ``python live_nav_fetch.py``):
    python data_ingestion.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
REPORTS_DIR = BASE_DIR / "reports"

# Column-name aliases used to locate key columns across arbitrary schemas.
CODE_ALIASES = ["scheme_code", "schemecode", "amfi_code", "amficode", "code"]
DATE_ALIASES = ["date", "nav_date", "navdate", "asofdate", "as_of_date"]
NAV_ALIASES = ["nav", "net_asset_value", "netassetvalue", "nav_value"]

AMFI_CODE_STRUCTURE = """\
AMFI scheme codes are unique numeric identifiers assigned by the Association of
Mutual Funds in India (AMFI). Key properties relevant to this project:

  * They are (currently) 6-digit integers, e.g. 119551, 125497.
  * One code maps to exactly ONE (scheme x plan x option) combination. The same
    fund therefore has DIFFERENT codes for its Direct vs Regular plans and for
    its Growth vs IDCW/Dividend options.
  * Codes are not contiguous per fund house; they are allocated over time as
    schemes launch, so adjacent codes are unrelated.
  * mfapi.in keys its NAV history endpoint (/mf/<code>) on this exact code, so
    the AMFI code is the natural primary/foreign key linking fund_master
    (one row per scheme) to nav_history (many NAV observations per scheme)."""


# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #

def find_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    """Return the first column whose lower-cased name matches an alias."""
    lower = {c.lower().strip(): c for c in df.columns}
    for alias in aliases:
        if alias in lower:
            return lower[alias]
    return None


def parse_dates(series: pd.Series) -> pd.Series:
    """Robustly parse a date column that may be ISO ``YYYY-MM-DD``, Indian
    ``DD-MM-YYYY``, or ``YYYY-MM``. Tries explicit formats first (deterministic)
    and returns the parse with the fewest NaT.

    This deliberately avoids a blanket ``dayfirst=True``: that silently reads an
    ISO ``2022-01-03`` as ``YYYY-DD-MM`` (-> 2022-03-01) and coerces any day > 12
    to NaT. The provided datasets are ISO, the live API is DD-MM-YYYY, so we let
    the data pick the format rather than assuming one."""
    s = series.astype(str).str.strip()
    attempts = [{"format": "%Y-%m-%d"}, {"format": "%d-%m-%Y"},
                {"format": "%Y-%m"}, {"dayfirst": False}, {"dayfirst": True}]
    best, best_score = None, -1.0
    for kw in attempts:
        try:
            parsed = pd.to_datetime(s, errors="coerce", **kw)
        except (ValueError, TypeError):
            continue
        score = float(parsed.notna().mean())
        if score > best_score:
            best, best_score = parsed, score
        if best_score == 1.0:
            break
    return best if best is not None else pd.to_datetime(s, errors="coerce")


def looks_like_date(series: pd.Series, sample: int = 50) -> bool:
    s = series.dropna().astype(str).head(sample)
    if s.empty:
        return False
    return parse_dates(s).notna().mean() > 0.8


def looks_numeric(series: pd.Series, sample: int = 50) -> bool:
    s = series.dropna().astype(str).head(sample)
    if s.empty:
        return False
    parsed = pd.to_numeric(s, errors="coerce")
    return parsed.notna().mean() > 0.8


# --------------------------------------------------------------------------- #
# 1. Load + profile every raw CSV
# --------------------------------------------------------------------------- #

def profile_csv(path: Path) -> dict:
    """Load one CSV, print its profile, and return a record of findings."""
    print("\n" + "-" * 78)
    print(f"FILE: {path.name}")
    print("-" * 78)
    try:
        df = pd.read_csv(path)
    except Exception as err:  # noqa: BLE001
        print(f"  !! could not read: {err}")
        return {"file": path.name, "loaded": False, "error": str(err)}

    print(f"  .shape   : {df.shape[0]} rows x {df.shape[1]} cols")
    print("  .dtypes  :")
    for col, dt in df.dtypes.items():
        print(f"             {col:<28} {dt}")
    print("  .head()  :")
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(df.head().to_string().replace("\n", "\n             "))

    # ---- anomaly detection -------------------------------------------------
    anomalies: list[str] = []

    null_cols = {c: int(n) for c, n in df.isna().sum().items() if n > 0}
    if null_cols:
        anomalies.append(f"null values present: {null_cols}")

    dup = int(df.duplicated().sum())
    if dup:
        anomalies.append(f"{dup} fully-duplicated row(s)")

    for col in df.columns:
        if df[col].dtype == object:
            if looks_like_date(df[col]):
                anomalies.append(f"column '{col}' holds date-like strings (object) — parse to datetime")
            elif looks_numeric(df[col]):
                anomalies.append(f"column '{col}' holds numeric-like strings (object) — cast to numeric")

    const_cols = [c for c in df.columns if df[c].nunique(dropna=False) <= 1]
    if const_cols:
        anomalies.append(f"constant/empty column(s): {const_cols}")

    # date ordering hint
    date_col = find_col(df, DATE_ALIASES)
    if date_col is not None:
        parsed = parse_dates(df[date_col])
        if parsed.notna().any():
            if parsed.is_monotonic_decreasing:
                anomalies.append(f"'{date_col}' is sorted NEWEST-first (descending)")
            elif not parsed.is_monotonic_increasing:
                anomalies.append(f"'{date_col}' is not chronologically sorted")

    if anomalies:
        print("  anomalies:")
        for a in anomalies:
            print(f"     - {a}")
    else:
        print("  anomalies: none detected")

    return {
        "file": path.name,
        "loaded": True,
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "columns": list(df.columns),
        "anomalies": anomalies,
        "_df": df,
    }


# --------------------------------------------------------------------------- #
# 2. Explore fund_master
# --------------------------------------------------------------------------- #

def explore_fund_master(fm: pd.DataFrame) -> dict:
    print("\n" + "=" * 78)
    print("FUND MASTER EXPLORATION")
    print("=" * 78)

    out: dict = {}

    def show(label: str, col_aliases: list[str]):
        col = find_col(fm, col_aliases)
        if col is None:
            print(f"\n  [{label}] column not found")
            out[label] = []
            return
        vals = sorted(v for v in fm[col].dropna().unique())
        print(f"\n  Unique {label} ({len(vals)}) [col='{col}']:")
        for v in vals:
            print(f"     - {v}")
        out[label] = list(map(str, vals))

    show("fund_house", ["fund_house", "fundhouse", "amc"])
    show("category", ["category", "scheme_category"])
    show("sub_category", ["sub_category", "subcategory"])
    show("risk_grade", ["risk_grade", "risk_category", "risk", "riskgrade"])

    print("\n  AMFI scheme-code structure")
    print("  " + "-" * 40)
    for line in AMFI_CODE_STRUCTURE.splitlines():
        print("  " + line)

    return out


# --------------------------------------------------------------------------- #
# 3. Validate AMFI codes + NAV quality
# --------------------------------------------------------------------------- #

def validate_codes(fm: pd.DataFrame, nav: pd.DataFrame) -> dict:
    print("\n" + "=" * 78)
    print("AMFI CODE VALIDATION  (every fund_master code must exist in nav_history)")
    print("=" * 78)

    fm_code = find_col(fm, CODE_ALIASES)
    nav_code = find_col(nav, CODE_ALIASES)
    nav_date = find_col(nav, DATE_ALIASES)
    nav_val = find_col(nav, NAV_ALIASES)

    res: dict = {
        "fm_code_col": fm_code, "nav_code_col": nav_code,
        "nav_date_col": nav_date, "nav_val_col": nav_val,
    }
    if fm_code is None or nav_code is None:
        print("  !! could not locate scheme-code columns in both tables — skipping.")
        res["status"] = "SKIPPED"
        return res

    fm_codes = set(pd.to_numeric(fm[fm_code], errors="coerce").dropna().astype(int))
    nav_codes = set(pd.to_numeric(nav[nav_code], errors="coerce").dropna().astype(int))

    missing = sorted(fm_codes - nav_codes)   # in master but no NAV history  (BAD)
    orphan = sorted(nav_codes - fm_codes)    # NAV history but not in master (info)

    res.update({
        "n_fund_master_codes": len(fm_codes),
        "n_nav_history_codes": len(nav_codes),
        "missing_in_nav_history": missing,
        "orphans_not_in_master": orphan,
        "all_codes_have_history": len(missing) == 0,
    })

    print(f"  fund_master codes : {len(fm_codes)}")
    print(f"  nav_history codes : {len(nav_codes)}")
    print(f"  missing in nav_history (FAIL if any): {missing if missing else 'none'}")
    print(f"  in nav_history but not in fund_master: {orphan if orphan else 'none'}")
    print(f"  RESULT: {'PASS — every fund_master code has NAV history' if not missing else 'FAIL'}")

    # ---- NAV-level quality -------------------------------------------------
    if nav_val is not None:
        nav_num = pd.to_numeric(nav[nav_val], errors="coerce")
        res["nav_rows"] = int(len(nav))
        res["nav_nulls"] = int(nav_num.isna().sum())
        res["nav_non_positive"] = int((nav_num <= 0).sum())
        bad = nav.loc[(nav_num <= 0).fillna(False)]
        cols = [c for c in (nav_code, nav_date, nav_val) if c]
        res["nav_non_positive_examples"] = bad[cols].head(10).to_dict("records") if len(bad) else []
    if nav_date is not None:
        d = parse_dates(nav[nav_date])
        res["nav_date_min"] = str(d.min().date()) if d.notna().any() else None
        res["nav_date_max"] = str(d.max().date()) if d.notna().any() else None
        res["nav_unparseable_dates"] = int(d.isna().sum())
    if nav_code is not None and nav_date is not None:
        res["nav_dup_code_date"] = int(nav.duplicated(subset=[nav_code, nav_date]).sum())

    # ---- per-scheme coverage ----------------------------------------------
    if nav_code is not None and nav_date is not None:
        print("\n  Per-scheme NAV coverage:")
        d = parse_dates(nav[nav_date])
        tmp = nav.assign(_d=d)
        cov_rows = []
        for code, grp in tmp.groupby(nav_code):
            row = {
                "scheme_code": int(code),
                "rows": int(len(grp)),
                "from": str(grp["_d"].min().date()) if grp["_d"].notna().any() else None,
                "to": str(grp["_d"].max().date()) if grp["_d"].notna().any() else None,
            }
            cov_rows.append(row)
            print(f"     {row['scheme_code']}: {row['rows']:>5} rows  {row['from']} -> {row['to']}")
        res["coverage"] = cov_rows

    return res


# --------------------------------------------------------------------------- #
# 3b. Cross-dataset referential integrity
# --------------------------------------------------------------------------- #

def cross_reference(profiles: list[dict], fund_master: pd.DataFrame) -> list[dict]:
    """Every amfi_code appearing in any dataset should also exist in fund_master.
    Reports, per file, how many distinct codes are NOT covered by fund_master."""
    print("\n" + "=" * 78)
    print("CROSS-DATASET CODE INTEGRITY  (every amfi_code should exist in fund_master)")
    print("=" * 78)
    fm_col = find_col(fund_master, CODE_ALIASES)
    if fm_col is None:
        print("  fund_master has no code column — skipped.")
        return []
    fm_codes = set(pd.to_numeric(fund_master[fm_col], errors="coerce").dropna().astype(int))

    rows: list[dict] = []
    for p in profiles:
        if not p.get("loaded"):
            continue
        df = p["_df"]
        col = find_col(df, CODE_ALIASES)
        if col is None:
            continue
        codes = set(pd.to_numeric(df[col], errors="coerce").dropna().astype(int))
        missing = sorted(codes - fm_codes)
        rows.append({
            "file": p["file"], "code_col": col,
            "distinct_codes": len(codes),
            "missing_from_fund_master": len(missing),
            "examples": missing[:8],
        })
        flag = "OK" if not missing else f"{len(missing)} NOT in fund_master e.g. {missing[:5]}"
        print(f"  {p['file']:<28} codes={len(codes):>4}  -> {flag}")
    return rows


# --------------------------------------------------------------------------- #
# 4. Cleaned processed output + written summary
# --------------------------------------------------------------------------- #

def write_processed(nav: pd.DataFrame, val: dict) -> Path | None:
    code_col = val.get("nav_code_col")
    date_col = val.get("nav_date_col")
    val_col = val.get("nav_val_col")
    if not (code_col and date_col and val_col):
        return None
    clean = nav.copy()
    clean[date_col] = parse_dates(clean[date_col])
    clean[val_col] = pd.to_numeric(clean[val_col], errors="coerce")
    before = len(clean)
    clean = clean.dropna(subset=[date_col, val_col])      # drop unparseable
    clean = clean[clean[val_col] > 0]                     # drop zero/negative NAVs
    clean = clean.drop_duplicates(subset=[code_col, date_col])
    clean = clean.sort_values([code_col, date_col]).reset_index(drop=True)
    dropped = before - len(clean)
    val["rows_dropped_in_cleaning"] = int(dropped)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "nav_history_clean.csv"
    clean.to_csv(out, index=False, encoding="utf-8")
    print(f"\n  wrote {out.relative_to(BASE_DIR)} "
          f"({len(clean)} clean rows; {dropped} dropped)")
    return out


def write_summary(profiles: list[dict], fm_explore: dict, val: dict,
                  xref: list[dict]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "data_quality_summary.md"
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    lines: list[str] = []
    lines.append("# Day 1 — Data Quality Summary\n")
    lines.append(f"_Generated (UTC): {ts}_\n")

    lines.append("## 1. Source data\n")
    lines.append(
        "- **Primary:** the 10 provided CSV datasets in `data/raw/` — fund master, NAV history, "
        "AUM by fund house, monthly SIP inflows, category inflows, industry folio counts, scheme "
        "performance, investor transactions, portfolio holdings and benchmark indices.\n")
    lines.append(
        "- **Supplementary:** live AMFI NAV pulls in `data/raw/live_api/` (via `live_nav_fetch.py`, "
        "6 scheme codes). Known anomaly: 5 of those 6 codes resolve to a *different* fund on the "
        "live feed than the assignment brief states — see the table below and "
        "`data/raw/live_api/fetch_manifest.csv`.\n")

    man_path = RAW_DIR / "live_api" / "fetch_manifest.csv"
    if man_path.exists():
        man = pd.read_csv(man_path)
        lines.append("### Brief label vs live AMFI scheme name\n")
        lines.append("| Code | Brief label (assignment) | Live API scheme name | Matches? |")
        lines.append("|-----:|--------------------------|----------------------|:--------:|")
        for _, r in man.iterrows():
            mk = "✅" if bool(r.get("matches_brief")) else "❌"
            lines.append(f"| {r['scheme_code']} | {r.get('brief_name','')} | "
                         f"{r.get('api_scheme_name','')} | {mk} |")
        if "matches_brief" in man.columns:
            n_mis = int((~man["matches_brief"].astype(bool)).sum())
            lines.append(
                f"\n**{n_mis} of {len(man)} codes resolve to a different fund than the brief states.** "
                "Downstream analysis must key on the live AMFI scheme name / code, not the brief label.\n")

    lines.append("\n## 2. File inventory\n")
    lines.append("| File | Rows | Cols | Anomalies |")
    lines.append("|------|-----:|-----:|-----------|")
    for p in profiles:
        if not p.get("loaded"):
            lines.append(f"| {p['file']} | — | — | load error: {p.get('error','')} |")
            continue
        an = "; ".join(p["anomalies"]) if p["anomalies"] else "none"
        lines.append(f"| {p['file']} | {p['rows']} | {p['cols']} | {an} |")

    lines.append("\n## 3. Fund master\n")
    for label in ("fund_house", "category", "sub_category", "risk_grade"):
        vals = fm_explore.get(label, [])
        lines.append(f"- **{label}** ({len(vals)}): {', '.join(vals) if vals else '—'}")
    lines.append("\n### AMFI scheme-code structure\n")
    for line in AMFI_CODE_STRUCTURE.splitlines():
        lines.append(f"> {line}")

    lines.append("\n## 4. AMFI code validation\n")
    if val.get("status") == "SKIPPED":
        lines.append("- Skipped: scheme-code columns could not be located in both tables.")
    else:
        lines.append(f"- fund_master codes: **{val.get('n_fund_master_codes')}**")
        lines.append(f"- nav_history codes: **{val.get('n_nav_history_codes')}**")
        miss = val.get("missing_in_nav_history") or []
        orph = val.get("orphans_not_in_master") or []
        lines.append(f"- Codes in fund_master **missing** from nav_history: "
                     f"**{miss if miss else 'none'}**")
        lines.append(f"- Codes in nav_history not in fund_master: {orph if orph else 'none'}")
        verdict = "✅ PASS — every fund_master code has NAV history." if not miss \
            else "❌ FAIL — some fund_master codes have no NAV history."
        lines.append(f"- **Result: {verdict}**")

        lines.append("\n### NAV quality\n")
        lines.append(f"- NAV rows (raw): {val.get('nav_rows')}")
        lines.append(f"- Null NAVs: {val.get('nav_nulls')}")
        lines.append(f"- Non-positive NAVs (<= 0): {val.get('nav_non_positive')}")
        for ex in (val.get("nav_non_positive_examples") or []):
            lines.append(f"  - offending row: {ex}")
        lines.append(f"- Unparseable dates: {val.get('nav_unparseable_dates')}")
        lines.append(f"- Duplicate (scheme_code, date) pairs: {val.get('nav_dup_code_date')}")
        lines.append(f"- Date range: {val.get('nav_date_min')} → {val.get('nav_date_max')}")
        if "rows_dropped_in_cleaning" in val:
            lines.append(
                f"- Rows dropped while building `data/processed/nav_history_clean.csv`: "
                f"{val.get('rows_dropped_in_cleaning')} "
                "(null/unparseable + non-positive + duplicate).")

        cov = val.get("coverage") or []
        if cov:
            lines.append("\n### Per-scheme NAV coverage\n")
            lines.append("| scheme_code | rows | from | to |")
            lines.append("|------------:|-----:|------|----|")
            for r in cov:
                lines.append(f"| {r['scheme_code']} | {r['rows']} | {r['from']} | {r['to']} |")

    if xref:
        lines.append("\n## 5. Cross-dataset code integrity\n")
        lines.append("Every `amfi_code` in another dataset should exist in `fund_master`:\n")
        lines.append("| File | code col | distinct codes | not in fund_master | examples |")
        lines.append("|------|----------|---------------:|-------------------:|----------|")
        for r in xref:
            ex = r["examples"] if r["examples"] else ""
            lines.append(f"| {r['file']} | {r['code_col']} | {r['distinct_codes']} | "
                         f"{r['missing_from_fund_master']} | {ex} |")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n  wrote {out.relative_to(BASE_DIR)}")
    return out


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def locate(profiles: list[dict], name_hint: str, must_have: list[str]):
    """Find a loaded dataframe by filename hint, else by required columns."""
    for p in profiles:
        if p.get("loaded") and name_hint in p["file"].lower():
            return p["_df"]
    for p in profiles:
        if not p.get("loaded"):
            continue
        df = p["_df"]
        if all(find_col(df, alias_group) for alias_group in must_have):
            return df
    return None


def main() -> int:
    print("=" * 78)
    print("DATA INGESTION — Day 1")
    print("=" * 78)

    csvs = sorted(RAW_DIR.glob("*.csv"))
    if not csvs:
        print(f"\nNo CSVs found in {RAW_DIR}. Run `python live_nav_fetch.py` first,")
        print("or drop the 10 provided datasets into data/raw/.")
        return 1

    print(f"\nFound {len(csvs)} CSV file(s) in data/raw/:")
    for c in csvs:
        print(f"  - {c.name}")

    profiles = [profile_csv(c) for c in csvs]

    fund_master = locate(profiles, "fund_master", [CODE_ALIASES])
    nav_history = locate(profiles, "nav_history", [CODE_ALIASES, NAV_ALIASES])

    fm_explore: dict = {}
    val: dict = {"status": "SKIPPED"}

    if fund_master is not None:
        fm_explore = explore_fund_master(fund_master)
    else:
        print("\n(fund_master not found — exploration skipped)")

    if fund_master is not None and nav_history is not None:
        val = validate_codes(fund_master, nav_history)
        write_processed(nav_history, val)
    else:
        print("\n(fund_master and/or nav_history not found — validation skipped)")

    xref = cross_reference(profiles, fund_master) if fund_master is not None else []

    write_summary(profiles, fm_explore, val, xref)

    print("\n" + "=" * 78)
    print("DONE.")
    print("=" * 78)
    # Non-zero exit only if validation ran and genuinely failed.
    if val.get("status") != "SKIPPED" and not val.get("all_codes_have_history", True):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
