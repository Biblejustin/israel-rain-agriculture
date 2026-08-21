"""Trend + coupling analysis for Israel rainfall and agriculture.

Conventions (matching the sibling signs repos):
- Rain is aggregated on Israel's hydrological "rain year" (October through
  September), labeled by the ENDING calendar year: rain_year 1902 = Oct 1901
  to Sep 1902. Calendar-year totals would split the Oct-May wet season.
- Former rain = October + November of the rain year (the yoreh that opens
  the season); latter rain = March + April (the malqosh that closes it).
  Deut 11:14 and Joel 2:23 language, measured, not assumed.
- All slopes carry 2,000-draw bootstrap 95% CIs, seeded for reproducibility.
- Rain × agriculture coupling is computed on within-era detrended series,
  split at 1990: by then the National Water Carrier (1964) was mature and
  drip irrigation ubiquitous; large-scale desalination (Ashkelon 2005,
  Sorek 2013) lands inside the second era. The prediction of the
  infrastructure story is that the coupling WEAKENS across eras.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).parent
DATA = HERE / "data"
RNG = np.random.default_rng(42)


def slope_ci(x: np.ndarray, y: np.ndarray, n_boot: int = 2000):
    """OLS slope per decade with bootstrap 95% CI."""
    a, _ = np.polyfit(x, y, 1)
    slopes = []
    n = len(x)
    for _ in range(n_boot):
        idx = RNG.integers(0, n, size=n)
        try:
            ai, _ = np.polyfit(x[idx], y[idx], 1)
            slopes.append(ai)
        except Exception:
            continue
    lo, hi = np.percentile(slopes, [2.5, 97.5])
    return a * 10, lo * 10, hi * 10


def detrend(series: pd.Series) -> pd.Series:
    x = series.index.values.astype(float)
    a, b = np.polyfit(x, series.values, 1)
    return series - (a * x + b)


def load_rain_years() -> pd.DataFrame:
    """Monthly CCKP -> rain-year totals + former/latter season splits."""
    m = pd.read_csv(DATA / "rain_cckp_monthly.csv")
    # Rain year label = ending calendar year; Oct-Dec belong to NEXT label
    m["rain_year"] = np.where(m["month"] >= 10, m["year"] + 1, m["year"])
    g = m.groupby("rain_year")
    out = pd.DataFrame({
        "total_mm": g["precip_mm"].sum(),
        "n_months": g.size(),
        "former_mm": m[m["month"].isin([10, 11])].groupby("rain_year")["precip_mm"].sum(),
        "latter_mm": m[m["month"].isin([3, 4])].groupby("rain_year")["precip_mm"].sum(),
    })
    out = out[out["n_months"] == 12].drop(columns="n_months")  # complete years only
    out["former_mm"] = out["former_mm"].fillna(0.0)
    out["latter_mm"] = out["latter_mm"].fillna(0.0)
    return out


def report_trend(label: str, series: pd.Series):
    s, lo, hi = slope_ci(series.index.values.astype(float),
                           series.values.astype(float))
    mean = series.mean()
    pct = s / mean * 100 if mean else 0
    sig = "**" if (lo > 0 or hi < 0) else "  "
    print(f"  {label:<42} {s:+8.2f}/dec [{lo:+8.2f}, {hi:+8.2f}] "
           f"({pct:+5.1f}%/dec) {sig}")
    return s, lo, hi


def era_coupling(rain: pd.Series, ag: pd.Series, lo: int, hi: int, label: str):
    r_e = rain[(rain.index >= lo) & (rain.index <= hi)]
    a_e = ag[(ag.index >= lo) & (ag.index <= hi)]
    common = r_e.index.intersection(a_e.index)
    if len(common) < 10:
        return
    rd, ad = detrend(r_e.loc[common]), detrend(a_e.loc[common])
    r, p = stats.pearsonr(rd, ad)
    sig = "**" if p < 0.05 else "  "
    print(f"  {label:<42} r = {r:+.3f}  (p = {p:.3f}, n = {len(common)}) {sig}")
    return r, p


def main():
    rain = load_rain_years()
    idx = pd.read_csv(DATA / "faostat_production_index.csv").set_index("year")["index_2014_16_100"]
    crops = pd.read_csv(DATA / "faostat_crops.csv")
    yield_ = pd.read_csv(DATA / "wb_cereal_yield.csv").set_index("year")["cereal_yield_kg_ha"]

    print("=" * 100)
    print("RAIN (CCKP CRU TS 4.08, rain years Oct-Sep, labeled by ending year)")
    print("=" * 100)
    print(f"  Span: {rain.index.min()}-{rain.index.max()}   "
           f"mean {rain['total_mm'].mean():.0f} mm   "
           f"driest {rain['total_mm'].idxmin()} ({rain['total_mm'].min():.0f} mm)   "
           f"wettest {rain['total_mm'].idxmax()} ({rain['total_mm'].max():.0f} mm)")
    report_trend("Rain-year total, full span", rain["total_mm"])
    report_trend("Rain-year total, 1990+", rain.loc[rain.index >= 1990, "total_mm"])
    report_trend("Former rain (Oct-Nov), full span", rain["former_mm"])
    report_trend("Latter rain (Mar-Apr), full span", rain["latter_mm"])
    report_trend("Former rain, 1990+", rain.loc[rain.index >= 1990, "former_mm"])
    report_trend("Latter rain, 1990+", rain.loc[rain.index >= 1990, "latter_mm"])

    print()
    print("=" * 100)
    print("AGRICULTURE (FAOSTAT, 1961-2024)")
    print("=" * 100)
    report_trend("Gross production index (2014-16=100)", idx)
    report_trend("Cereal yield kg/ha (WDI)", yield_.dropna())
    for crop, sub in crops.groupby("crop"):
        s = sub.set_index("year")["production_tonnes"].dropna()
        report_trend(f"{crop} production (t)", s)

    print()
    print("=" * 100)
    print("RAIN x AGRICULTURE COUPLING (within-era detrended Pearson r)")
    print("=" * 100)
    print("Production index vs rain-year total:")
    era_coupling(rain["total_mm"], idx, 1961, 1990, "  1961-1990 (pre-drip/desal era)")
    era_coupling(rain["total_mm"], idx, 1991, 2024, "  1991-2024 (drip + desalination era)")
    print("Cereal yield vs rain-year total (yield is the rain-sensitive margin):")
    era_coupling(rain["total_mm"], yield_.dropna(), 1961, 1990, "  1961-1990")
    era_coupling(rain["total_mm"], yield_.dropna(), 1991, 2023, "  1991-2023")

    print()
    print("Legend: ** = 95% CI excludes 0 (trends) / p < 0.05 (couplings)")


if __name__ == "__main__":
    main()
