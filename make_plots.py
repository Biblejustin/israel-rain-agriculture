"""Israel rain + agriculture plots — house style of the sibling signs repos.

Conventions:
- Rain years Oct-Sep labeled by ending year (see analyze.py docstring).
- CCKP CRU TS 4.08 is a gridded country average: use it for trends and
  anomalies, not for absolute station comparisons.
- FAOSTAT production is calendar-year tonnes; the index is 2014-2016=100.
- Trend lines are OLS with HAC(3) 95% slope bounds. Historical smoothers are descriptive.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from analyze import load_rain_years, slope_ci, detrend

HERE = Path(__file__).parent
DATA = HERE / "data"
FIGS = HERE / "figures"
FIGS.mkdir(exist_ok=True)
RNG = np.random.default_rng(42)

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight",
    "font.size": 10, "axes.titlesize": 12,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linestyle": "--",
})


def trend_band(ax, x, y, color="#333333"):
    s, lo, hi = slope_ci(x, y)
    xf = np.array([x.min(), x.max()])
    a, b = np.polyfit(x, y, 1)
    ax.plot(xf, a * xf + b, color=color, lw=1.6,
             label=f"trend {s:+.1f}/dec [{lo:+.1f}, {hi:+.1f}]")
    for bound in (lo, hi):
        ab = bound / 10
        bb = y.mean() - ab * x.mean()
        ax.plot(xf, ab * xf + bb, color=color, lw=0.7, ls=":", alpha=0.6)


def plot_01_rain_years(rain: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(11, 5))
    x, y = rain.index.values.astype(float), rain["total_mm"].values
    ax.plot(x, y, color="#3366aa", lw=0.9, alpha=0.7)
    ax.plot(rain.index, rain["total_mm"].rolling(10, center=True).mean(),
             color="#aa3322", lw=2.2, label="10-yr rolling mean")
    trend_band(ax, x, y)
    ax.set_xlabel("rain year (Oct-Sep, labeled by ending year)")
    ax.set_ylabel("precipitation (mm)")
    ax.set_title("Israel rain-year precipitation, 1902-2023 (CRU TS 4.08 country average)")
    ax.legend(fontsize=9)
    plt.savefig(FIGS / "01_rain_years.png")
    plt.close()


def plot_02_former_latter(rain: pd.DataFrame):
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    for ax, col, name, color in (
            (axes[0], "former_mm", "Former rain (Oct-Nov, the yoreh)", "#7a5c2e"),
            (axes[1], "latter_mm", "Latter rain (Mar-Apr, the malqosh)", "#2e6b4f")):
        x, y = rain.index.values.astype(float), rain[col].values
        ax.plot(x, y, color=color, lw=0.9, alpha=0.7)
        ax.plot(rain.index, rain[col].rolling(10, center=True).mean(),
                 color="#aa3322", lw=2.0, label="10-yr rolling mean")
        trend_band(ax, x, y)
        ax.set_ylabel("mm")
        ax.set_title(name, fontsize=11)
        ax.legend(fontsize=8.5)
    axes[1].set_xlabel("rain year")
    fig.suptitle("The season's two shoulders: opening and closing rains, 1902-2023",
                  y=0.995)
    plt.savefig(FIGS / "02_former_latter_rain.png")
    plt.close()


def plot_03_production(idx: pd.Series, yield_: pd.Series):
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    for ax, series, name, unit in (
            (axes[0], idx, "FAO gross production index (2014-2016 = 100)", "index"),
            (axes[1], yield_.dropna(), "Cereal yield (World Bank)", "kg/ha")):
        x, y = series.index.values.astype(float), series.values
        ax.plot(x, y, color="#3366aa", lw=1.4, marker="o", ms=2.5)
        trend_band(ax, x, y)
        ax.set_ylabel(unit)
        ax.set_title(name, fontsize=11)
        ax.legend(fontsize=8.5)
    axes[1].set_xlabel("year")
    fig.suptitle("Israeli agriculture since 1961", y=0.995)
    plt.savefig(FIGS / "03_production.png")
    plt.close()


def plot_04_crops(crops: pd.DataFrame):
    order = [name for name in ["Wheat", "Barley", "Grapes", "Olives", "Figs", "Dates", "Pomegranates", "Citrus Fruit, Total"] if name in set(crops.crop)]
    fig, axes = plt.subplots(len(order), 1, figsize=(11, 2.4*len(order)), sharex=True)
    for ax, crop in zip(axes, order):
        sub = crops[crops["crop"] == crop].set_index("year")["production_tonnes"].dropna()
        x, y = sub.index.values.astype(float), sub.values
        ax.plot(x, y / 1000, color="#3366aa", lw=1.3)
        s, lo, hi = slope_ci(x, y)
        sig = " **" if (lo > 0 or hi < 0) else ""
        ax.set_title(f"{crop}: {s/1000:+.1f} kt/dec [{lo/1000:+.1f}, {hi/1000:+.1f}]{sig}",
                      fontsize=10.5)
        ax.set_ylabel("kt")
    axes[-1].set_xlabel("year")
    fig.subplots_adjust(top=0.95, hspace=0.38)
    fig.suptitle("Production of the storied crops, 1961-2024 (FAOSTAT, thousands of tonnes)",
                  y=0.995)
    plt.savefig(FIGS / "04_crops.png")
    plt.close()


def plot_05_decoupling(rain: pd.DataFrame, yield_: pd.Series):
    from scipy import stats as st
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharey=True)
    eras = [(1961, 1990, "1961-1990: historical comparison"),
             (1991, 2023, "1991-2023: historical comparison")]
    for ax, (lo, hi, title) in zip(axes, eras):
        r_e = rain.loc[(rain.index >= lo) & (rain.index <= hi), "total_mm"]
        y_e = yield_.dropna()
        y_e = y_e[(y_e.index >= lo) & (y_e.index <= hi)]
        common = r_e.index.intersection(y_e.index)
        rd, yd = detrend(r_e.loc[common]), detrend(y_e.loc[common])
        r, p = st.pearsonr(rd, yd)
        ax.scatter(rd, yd, s=28, color="#3366aa", alpha=0.75,
                    edgecolor="black", lw=0.4)
        a, b = np.polyfit(rd, yd, 1)
        xs = np.array([rd.min(), rd.max()])
        ax.plot(xs, a * xs + b, color="#aa3322", lw=1.8)
        ax.set_title(f"{title}\nr = {r:+.2f}  (iid Pearson p = {p:.3f}; descriptive)", fontsize=10.5)
        ax.set_xlabel("rain-year total, detrended (mm)")
    axes[0].set_ylabel("cereal yield, detrended (kg/ha)")
    fig.suptitle("Rain vs cereal yield: descriptive within-era associations", y=1.00)
    plt.savefig(FIGS / "05_decoupling.png")
    plt.close()


def main():
    rain = load_rain_years()
    idx = pd.read_csv(DATA / "faostat_production_index.csv").set_index("year")["index_2014_16_100"]
    crops = pd.read_csv(DATA / "faostat_crops.csv")
    yield_ = pd.read_csv(DATA / "wb_cereal_yield.csv").set_index("year")["cereal_yield_kg_ha"]

    plot_01_rain_years(rain)
    plot_02_former_latter(rain)
    plot_03_production(idx, yield_)
    plot_04_crops(crops)
    plot_05_decoupling(rain, yield_)
    print(f"Wrote 5 figures to {FIGS}/")


if __name__ == "__main__":
    main()
