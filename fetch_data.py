"""Fetch Israel rainfall + agriculture catalogs (guarded).

Sources (all direct, no auth):

  RAIN — World Bank Climate Change Knowledge Portal, CRU TS 4.08 country
  series for ISR, 1901-2023, annual + monthly. Pinned to the 4.08 vintage:
  the older 4.07 collection still answers 200 with slightly different
  values, so an unpinned URL would silently mix vintages.

  AGRICULTURE — FAOSTAT bulk zips (the JSON API went auth-only in 2025),
  filtered to Israel (Area Code 105): Gross Production Index (2014-2016 =
  100) and crop production tonnes for wheat, grapes, olives, figs, citrus.
  The zips are ~50 MB combined and FAOSTAT updates roughly annually, so
  they are only re-downloaded when the local CSV is older than 90 days
  (or with --force-faostat).

  SUPPLEMENT — World Bank WDI cereal yield (kg/ha), 1961+.

Every replacement is guarded: a download that does not parse, loses
expected columns, or shrinks the catalog is refused and the old file kept.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).parent
DATA = HERE / "data"
UA = {"User-Agent": "israel-rain-agriculture/1.0"}

CCKP_BASE = ("https://cckpapi.worldbank.org/cckp/v1/"
              "cru-x0.5_timeseries_pr_timeseries_{res}_1901-2023_mean_"
              "historical_cru_ts4.08_mean/ISR?_format=json")
WDI_URL = ("https://api.worldbank.org/v2/country/ISR/indicator/"
            "AG.YLD.CREL.KG?format=json&per_page=200")
FAO_INDEX_ZIP = ("https://bulks-faostat.fao.org/production/"
                  "Production_Indices_E_All_Data_(Normalized).zip")
FAO_CROPS_ZIP = ("https://bulks-faostat.fao.org/production/"
                  "Production_Crops_Livestock_E_All_Data_(Normalized).zip")
ISRAEL_AREA_CODE = 105
CROP_PATTERN = "Wheat|Grapes|Olives|Figs|Citrus"


def guarded_write(df: pd.DataFrame, target: Path, required_cols: list[str],
                    min_rows_ratio: float = 0.95) -> None:
    """Refuse to replace target if df is malformed or shrinks the catalog."""
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        sys.exit(f"GUARD REFUSED {target.name}: missing columns {missing}")
    if target.exists():
        try:
            old_rows = len(pd.read_csv(target))
        except Exception:
            old_rows = 0
        if len(df) < old_rows * min_rows_ratio:
            sys.exit(f"GUARD REFUSED {target.name}: {len(df)} rows < "
                      f"{min_rows_ratio:.0%} of existing {old_rows}")
        target.replace(target.with_suffix(".csv.bak"))
    df.to_csv(target, index=False)
    print(f"  OK {target.name}: {len(df)} rows (guard passed)")


def fetch_cckp() -> None:
    for res, fname in (("annual", "rain_cckp_annual.csv"),
                        ("monthly", "rain_cckp_monthly.csv")):
        r = requests.get(CCKP_BASE.format(res=res), headers=UA, timeout=60)
        r.raise_for_status()
        series = r.json()["data"]["ISR"]
        rows = []
        for key, mm in series.items():
            year, month = int(key[:4]), int(key[5:7])
            rows.append({"year": year, "month": month,
                          "precip_mm": float(mm)})
        df = pd.DataFrame(rows).sort_values(["year", "month"])
        if res == "annual":
            # CCKP stamps annual values mid-year ("YYYY-07"); month is noise
            df = df[["year", "precip_mm"]]
            guarded_write(df, DATA / fname, ["year", "precip_mm"])
        else:
            guarded_write(df, DATA / fname, ["year", "month", "precip_mm"])
        time.sleep(0.5)


def fetch_wdi() -> None:
    r = requests.get(WDI_URL, headers=UA, timeout=60)
    r.raise_for_status()
    payload = r.json()[1]
    rows = [{"year": int(d["date"]), "cereal_yield_kg_ha": d["value"]}
             for d in payload if d["value"] is not None]
    df = pd.DataFrame(rows).sort_values("year")
    guarded_write(df, DATA / "wb_cereal_yield.csv",
                    ["year", "cereal_yield_kg_ha"])


def _fao_pull(url: str, keep) -> pd.DataFrame:
    r = requests.get(url, headers=UA, timeout=300)
    r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    csv_name = next(n for n in zf.namelist() if n.endswith(".csv")
                     and "Flag" not in n and "ItemCode" not in n)
    df = pd.read_csv(zf.open(csv_name), encoding="latin-1", low_memory=False)
    df = df[df["Area Code"] == ISRAEL_AREA_CODE]
    return keep(df)


def fetch_faostat(force: bool = False) -> None:
    target = DATA / "faostat_crops.csv"
    if target.exists() and not force:
        age_days = (time.time() - target.stat().st_mtime) / 86400
        if age_days < 90:
            print(f"  faostat: local copy {age_days:.0f}d old (<90d), skipping "
                   f"bulk download (use --force-faostat to override)")
            return

    print("  faostat: downloading bulk zips (~50 MB, updates ~annually)...")
    idx = _fao_pull(FAO_INDEX_ZIP, lambda d: d[
        (d["Item"] == "Agriculture")
        & d["Element"].str.contains("Gross Production Index", na=False)
    ][["Year", "Element", "Value"]].rename(
        columns={"Year": "year", "Element": "element", "Value": "index_2014_16_100"}))
    # Two index variants ship (current vs constant); keep the plain one
    plain = idx[~idx["element"].str.contains("Per capita", na=False)]
    plain = plain.groupby("year", as_index=False)["index_2014_16_100"].mean()
    guarded_write(plain, DATA / "faostat_production_index.csv",
                    ["year", "index_2014_16_100"])

    crops = _fao_pull(FAO_CROPS_ZIP, lambda d: d[
        (d["Element Code"] == 5510)
        & d["Item"].str.contains(CROP_PATTERN, na=False)
    ][["Year", "Item", "Value"]].rename(
        columns={"Year": "year", "Item": "crop", "Value": "production_tonnes"}))
    crops = crops.sort_values(["crop", "year"])
    n_crops = crops["crop"].nunique()
    if n_crops < 4:
        sys.exit(f"GUARD REFUSED faostat_crops: only {n_crops} crops matched")
    guarded_write(crops, DATA / "faostat_crops.csv",
                    ["year", "crop", "production_tonnes"])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force-faostat", action="store_true",
                     help="re-download FAOSTAT bulk zips regardless of age")
    ap.add_argument("--skip-faostat", action="store_true")
    args = ap.parse_args()
    DATA.mkdir(exist_ok=True)

    print("Fetching CCKP rainfall (CRU TS 4.08, 1901-2023)...")
    fetch_cckp()
    print("Fetching World Bank cereal yield...")
    fetch_wdi()
    if not args.skip_faostat:
        print("Fetching FAOSTAT agriculture...")
        fetch_faostat(force=args.force_faostat)


if __name__ == "__main__":
    main()
