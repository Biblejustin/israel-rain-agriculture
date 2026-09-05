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

## Climate extension through 2025

`monitor_climate.py` now fetches **CRU-CY4.10** directly from the
[official CRU release](https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/crucy.2606161920.v4.10/).
Released June 2026, it contains January 1901–December 2025. The live fetch
validates country, variable, exact units, full declared period, missing codes,
physical ranges and truncation before replacing source files. `--offline`
reproduces from hash-checked archived data and documentation. Future CRU
versions require an explicit reviewed addition; the fetch never guesses a
new version or silently appends another product.

The monitor adds rainfall, monthly average daily mean/maximum temperature,
potential evapotranspiration and wet-day frequency. Raw CRU-CY4.08 and 4.10
remain separate under `data/climate/cru_cy_<version>/`. There are 1,476 and
1,500 monthly records per variable respectively. Source country averages use
area weights over the CRU Israel grid mask. The country files expose neither
constituent grid cells nor a numeric land-area denominator; those remain
unknown. **No bounding box, equal-cell average, cultivated-area denominator
or equivalence to CCKP/FAOSTAT territory is invented.**

[CRU methodology](https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/crucy.2606161920.v4.10/Read_Me_CRU_CY.txt)
states that source gaps can fall back to the 1961–1990 climatology. These are
observation-derived gridded estimates, not raw station observations. Complete
monthly files do not prove complete station support. Station counts and the
fraction falling back to climatology are unavailable in country files.
[Version 4.10 boundary notes](https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/crucy.2606161920.v4.10/Read_Me_CRU_CY_Updated_Country_Definitions.txt)
change Italy/Malta; no Israel change is listed. That does not certify identical
geography to World Bank country aggregates or agricultural statistics.

Every shared month is compared between CRU-CY4.08 and 4.10, for all five
variables. Every shared complete season/year is also compared. A separate
comparison isolates **CCKP4.08 versus CRU-CY4.08**, which share an upstream
version but have materially different values: monthly rainfall MAE 12.86mm,
maximum difference 85.34mm, across all 1,476 common months. High correlation
(~0.996) does not make these interchangeable. The frozen CCKP rainfall files,
original analysis plan and prospective wheat coefficients remain unchanged.

New diagnostic baseline = **1991–2020**, requiring 30 complete baseline years
for each metric. Rain year = October–September; former rain = October–November;
latter rain = March–April. Temperature means are weighted by actual calendar
days. PET is supplied in **mm/day** and converted using each month's actual
length, including leap February. Rain minus PET is a climatic water-balance
proxy; its standardized departure is **not SPI, SPEI, soil moisture or crop
water consumption**. March–May mean daily maximum temperature is a fixed
seasonal heat proxy, not recorded crop phenology or heatwave-day counts.
Missing months invalidate the affected metric; incomplete edge years retain
counts and unavailable totals.

As fetched September 2026, the 2025 rain year totals **218.8mm**, or **53.6%**
of this product's fixed baseline. March–May mean daily maximum temperature is
**1.29°C above baseline**. These describe the CRU country mask, not farm losses
or prophetic fulfillment. The human-readable report is
[`results/climate_monitor.md`](results/climate_monitor.md).

`climate_extension_plan.json` fixes a separate **five-test exploratory** family
before fitting: wheat yield versus year, CRU-CY4.10 rain and March–May heat;
then the same model with reported national irrigation share. Fits stop in
2023. Calendar-distance HAC3 uncertainty preserves actual gaps; BH includes
all five planned coefficients, with unavailable tests assigned p=1. The rain
coefficient stays positive after heat adjustment (63 years; q≈0.00030).
Heat alone is not independently resolved (q≈0.167). The combined irrigation
model has only 17 reported years: rain/heat intervals include zero. National
irrigation share has q≈0.020 but remains an aggregate association: neither
crop-specific irrigation nor causal explanation is identified.

The [CBS 2017 agricultural census, Table 9](https://www.cbs.gov.il/he/publications/DocLib/2024/1906_agriculture_census_2017/t09.pdf)
contains broad crop-group/district irrigation areas for one year. Its field
crops are not wheat, and its reported territory includes Israeli localities
in the source's Judea and Samaria Area. It cannot become an annual wheat
irrigation control by interpolation. The IMS daily station portal was
verified; station ingestion and station quality/coverage validation remain
unavailable here. `data/climate/source_availability.json` records these
limits. Existing 17-year WDI reported coverage is preserved without invented
years or crop allocation.

**Prospective validation remains ineligible:** FAOSTAT wheat currently ends
2024, leaving zero future crop/rain pairs from the frozen 2025 start. At least
10 future pairs are required; CRU-CY also fails the approved frozen-product
compatibility gate. Even 10 CRU-CY pairs would not silently authorize replacing
the frozen CCKP input. No validation score or refit is performed.

```bash
python monitor_climate.py             # live official source fetch + diagnostics
python monitor_climate.py --offline   # verify archived hashes + reproduce
python -m pytest tests -q
PYTHON=/absolute/path/to/python bash update.sh
```

Portable monitor artifacts: `data/climate/source_manifest.json`,
`source_availability.json`, both versioned `monthly.csv` and
`annual_diagnostics.csv`; `results/climate_monitor.json`,
`climate_monitor.md`, `climate_overlap_summary.json`,
`climate_version_overlap_monthly.csv`, `climate_version_overlap_annual.csv`,
`climate_aggregation_overlap_monthly.csv`, and
`climate_heat_irrigation_sensitivity.csv`. Every result links back to source
hashes and frozen plan/model hashes. Raw source files and official notes are
archived beside each version. CRU4.10 data: ODbL/DbCL, Attribution and
Share-Alike; CRU4.08 release states Open Government Licence. Attribution:
Climatic Research Unit, University of East Anglia. Reference:
[Harris et al. (2020)](https://doi.org/10.1038/s41597-020-0453-3).
