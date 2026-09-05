# Israel rain, crops and water security

Monitor country rainfall, crop-specific production/area/yield and measured
Lake Kinneret water levels. Biblical passages such as Deuteronomy 11:14 and
8:8 provide transparent thematic context. Statistical associations cannot
establish prophetic fulfillment.

## Current historical finding

September 4, 2026 review extension, **1991–2023**, 33 years, linear trends removed:

| Wheat outcome × total rain | Correlation | HAC p | BH q, 30 follow-up tests |
|---|---:|---:|---:|
| Production tonnes | +0.617 | 0.000071 | 0.000267 |
| Harvested area | +0.060 | 0.629 | 0.650 |
| Yield kg/ha | **+0.558** | **0.000002** | **0.000014** |

The production association appears in yield, while harvested area shows little
association with rain. Yield and production/area agree to source rounding.
Yield's 3-year block-permutation sensitivity p = **0.00165**. Historical data
were already explored; these are follow-up associations, not independent
confirmation. Country-average rain remains an imperfect proxy for wheat-region
rain and leaves temperature, crop management and irrigation confounding.

A formal rain × post-1990 interaction for wheat yield gives HAC p = **0.408**
(q = **0.490** in the same 30-test family). Separate significant/nonsignificant
era correlations do not establish changed association. Prior claims that
harvests became independent of rain and that these regressions identified
irrigation as the cause are withdrawn.

An additional **17 observed-year** complete-case sensitivity uses WDI's
reported national irrigated-land share (2001–2023, with gaps). For total rain,
the adjusted rain coefficient is 6.23 kg/ha per mm, calendar-HAC p = 0.067,
q = 0.100 across six supplementary tests. The small, differently covered
sample and all-crop irrigation denominator limit comparison with the 33-year
analysis. Source values may include estimates. No causal irrigation effect
is established. [All sensitivity results](results/irrigation_sensitivity.csv)
include each of the three fixed rain windows and both tested coefficients.

[54-test historical screen](results/crop_rain_54.csv) ·
[Wheat decomposition](results/wheat_decomposition.csv) ·
[Formal interactions](results/era_interaction.csv) ·
[Provenance and model manifest](results/crop_rain_manifest.json)

## Frozen analysis and future validation

[analysis_plan.json](analysis_plan.json) was saved before fetching the extended
crop and water data. Original exploratory family stays **54 tests**: five
original crop-production series plus cereal yield × three rain measures ×
three historical periods. Added crops do not silently enlarge that family.
The wheat follow-up uses **30 tests**: three outcomes × three rain windows ×
three periods, plus three total-rain by era interactions. HAC p-values share
a BH family of 30; unavailable tests count as p=1. Block sensitivities retain
within-block ordering, not all possible long-range dependence.

All model fitting stops in **2023**. Crop 2024 was already present in the
review snapshot, so it is not called unseen. Years **2025 onward are reserved**;
future evaluation requires at least ten complete annual pairs from the same
rain product. Current source still stops before that holdout. The initial
rain/year and year-only prediction coefficients are saved once in
[prospective_wheat_model.json](results/prospective_wheat_model.json), never
overwritten on refresh. No future-year scores or predictive success claimed.
Supplementary irrigation plan is frozen separately after source availability
inspection and before its first fit.

Rain year runs October–September, labelled by ending year. Former rain =
October–November; latter rain = March–April. These are fixed proxy windows.
Duplicate months fail validation; missing months exclude a whole rain year.
Missing values never become zero. Trend intervals now use HAC(3), and main
associations include linear time trends. Formal interactions allow separate
era intercepts and trends. Gapped irrigation years use calendar-distance HAC,
so consecutive rows separated by many years do not count as one-year lags.

## Operational observations

| File | Source and coverage | Meaning |
|---|---|---|
| `data/kinneret_levels.csv` | [Israel official CKAN API](https://data.gov.il/api/3/action/datastore_search?resource_id=2de7b543-e13d-4e7e-b4c8-56071bc4d3c8&limit=2); 11,326 observations, latest 2026-09-03 | Level = −213.325 m relative to source sea-level datum; actual dates and gaps retained |
| `data/water_security_metadata.json` | Same fetched snapshot | Exact 7/30-day changes, seasonal observed range, gaps, source hash and freshness |
| `data/water_covariates_reported.csv` | [World Bank WDI irrigated land](https://data.worldbank.org/indicator/AG.LND.IRIG.AG.ZS), agricultural withdrawal share, total withdrawal share | Reported annual water-use values; no local interpolation; national all-crop measures |
| `data/faostat_crop_measures.csv` | [FAOSTAT QCL bulk](https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip), 1961–2024 | 1,344 rows: 7 crops × area/yield/production × 64 years; units and source flags preserved |
| `data/faostat_crops.csv` | Same | Backward-compatible production tonnes, now includes barley and dates |
| `data/faostat_production_index.csv` | FAOSTAT Production Indices, 1961–2024 | Aggregate output index, not crop productivity |
| `data/wb_cereal_yield.csv` | World Bank WDI AG.YLD.CREL.KG, 1961–2023 | Aggregate cereal yield |
| `data/rain_cckp_monthly.csv`, `rain_cckp_annual.csv` | Pinned World Bank CCKP / CRU TS4.08, 1901–2023 | **Stale historical baseline**, latest complete rain year 2023; cannot monitor current drought |

Kinneret levels also respond to transfers, pumping and evaporation. Latest
measurement date is not certification of uninterrupted coverage. Per-record
publication/provisional flags are not supplied by the API; these are explicitly
unknown rather than inferred from fetch time. No lake threshold is labelled
prophetic. Aquifer levels, crop-region IMS daily rainfall and desalination
supply are not yet integrated. The [IMS source portal](https://ims.gov.il/en/MetaDataSources)
was checked but no validated station feed was joined; station observations
must remain separately versioned from the gridded historical product.

The fixed crop set requests wheat, barley, grapes, figs, pomegranates, olives,
dates and existing citrus. **Pomegranates unavailable in this bulk source**;
not represented as zero or guessed from mixed-fruit categories. Dates correspond
to one traditional interpretation of the “honey” in Deuteronomy 8:8. Source
metadata lists requested versus available crops and flag definitions. Current
FAOSTAT crop yield element is **5412 (kg/ha)**; legacy 5419 units are handled
explicitly and yield must agree with tonnes/area within 5%.

## Reproduce

```bash
python monitor_water.py        # official live water + reported annual covariates
python fetch_data.py           # crops/WDI; preserves pinned rain unless missing
python fetch_data.py --force-faostat
python fetch_data.py --refresh-cru  # explicit same-version historical re-fetch
python crop_rain_analysis.py    # 54 + 30 historical families
python irrigation_sensitivity.py
python analyze.py              # descriptive trends and legacy comparisons
python make_plots.py
python -m unittest discover -s tests -v
bash update.sh                 # operational sequence used by correlations hub
```

Uses pandas, NumPy, SciPy, statsmodels, requests and matplotlib from the shared
workspace environment. Bulk CSV processing streams chunks to keep memory
bounded. Replacement guards reject malformed, duplicate or shrinking catalogs.
Existing source snapshots and original review results remain available in
`results/review_original_54.csv` and pre-extension hashes. Current figures
replace old captions that asserted irrigation caused decoupling.
