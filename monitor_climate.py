"""Versioned CRU-CY national climate monitor and explicitly exploratory controls.

Source-derived gridded estimates, never raw station coverage or farm observations.
Pinned CCKP historical data and prospective model are read-only. No holdout scoring.
"""
import argparse
import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

import numpy as np
import pandas as pd
import requests
from scipy import stats

from crop_rain_analysis import wheat_measures, bh
from irrigation_sensitivity import calendar_hac

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'climate'
RESULTS = ROOT / 'results'
BASE = 'https://crudata.uea.ac.uk/cru/data/hrg/'
VERSIONS = {
    '4.08': ('cru_ts_4.08/crucy.2407032054.v4.08/', 2023),
    '4.10': ('cru_ts_4.10/crucy.2606161920.v4.10/', 2025),
}
VARIABLES = {
    'pre': ('Precipitation', 'mm/month'),
    'tmp': ('Mean Temperature', 'degrees Celsius'),
    'tmx': ('Maximum Temperature', 'degrees Celsius'),
    'pet': ('Potential Evapotranspiration', 'mm/day'),
    'wet': ('Rain Days', 'days'),
}
DOC_NAMES = ['Read_Me_CRU_CY.txt', 'Read_Me_CRU_CY_Updated_Country_Definitions.txt']
FROZEN = ['analysis_plan.json', 'results/prospective_wheat_model.json',
          'data/rain_cckp_monthly.csv', 'data/rain_cckp_annual.csv']
GEOGRAPHY = {
    'source_country_label': 'Israel', 'geography_id': 'CRU-CY:Israel',
    'spatial_resolution_degrees': 0.5,
    'spatial_denominator': 'Source area-weighted mean over CRU country grid-cell allocation; not cultivated area or population',
    'weighting': 'source-supplied area weights; no local equal-cell average or bounding-box substitution',
    'mask_equivalent_to_cckp_isr': None,
    'approved_frozen_product_equivalence': False,
    'mask_equivalent_to_faostat_israel': None,
    'mask_equivalence_status': 'unverified; do not use as a direct CCKP continuation or crop-region exposure',
    'mask_cell_count': None, 'mask_area_km2': None,
    'mask_coverage_limitation': 'Country files do not expose constituent cells, land fractions or denominator area; no invented numerical denominator',
    'release_boundary_note': '4.10 country-definition notes change Italy/Malta only; older exact Israel mask still not independently reconstructed',
    'area_weighting_source': BASE + VERSIONS['4.10'][0] + 'Read_Me_CRU_CY.txt',
}


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n')


def parse_country(blob, version, variable):
    """Validate source country, units, period, shape and physically possible values."""
    lines = blob.decode('utf-8').splitlines()
    if len(lines) < 5 or 'Climatic Research Unit Country File' not in lines[0]:
        raise ValueError('Not a CRU country file')
    header = re.fullmatch(r'Country\s*=\s*(.*?)\s*:\s*parameter\s*=\s*(.*?)\s*:\s*Units\s*=\s*(.*?)\s*', lines[1])
    if not header or header.groups() != ('Israel', *VARIABLES[variable]):
        raise ValueError('Country/parameter/units mismatch')
    end = VERSIONS[version][1]
    period = re.search(r'Period\s*=\s*(\d+)\.(\d+)\s*:\s*missing value\s*=\s*(-?[\d.]+)', lines[2])
    if not period or tuple(map(int, period.groups()[:2])) != (1901, end):
        raise ValueError('Unexpected source period')
    if lines[3].split() != ['YEAR', 'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC', 'MAM', 'JJA', 'SON', 'DJF', 'ANN']:
        raise ValueError('Unexpected columns')
    missing = float(period.group(3))
    rows, years = [], []
    for line in lines[4:]:
        cells = line.split()
        if len(cells) != 18:
            raise ValueError('Truncated or malformed annual row')
        year = int(cells[0]); years.append(year)
        for month, raw in enumerate(cells[1:13], 1):
            value = float(raw)
            if not np.isfinite(value):
                raise ValueError('Nonfinite source value')
            value = np.nan if value == missing else value
            if pd.notna(value):
                bounds = {'pre': (0, 5000), 'tmp': (-90, 70), 'tmx': (-90, 80),
                          'pet': (0, 50), 'wet': (0, calendar.monthrange(year, month)[1])}
                lo, hi = bounds[variable]
                if not lo <= value <= hi:
                    raise ValueError(f'Invalid {variable} value')
            rows.append({'year': year, 'month': month, 'value': value})
    if years != list(range(1901, end + 1)):
        raise ValueError('Missing, duplicate, unordered or future source year')
    return pd.DataFrame(rows), {'header': lines[:3], 'unit': VARIABLES[variable][1]}


def source_url(version, variable):
    return f'{BASE}{VERSIONS[version][0]}countries/{variable}/crucy.v{version}.1901.{VERSIONS[version][1]}.Israel.{variable}.per'


def fetch_sources(offline=False):
    """Validate entire release set before replacing source snapshots; preserve failure state."""
    if offline:
        manifest = json.loads((DATA / 'source_manifest.json').read_text())
        payloads = {}
        for item in manifest['documentation']:
            if digest((ROOT / item['path']).read_bytes()) != item['sha256']:
                raise ValueError('Cached climate documentation hash mismatch')
        for item in manifest['files']:
            content = (ROOT / item['path']).read_bytes()
            if digest(content) != item['sha256']:
                raise ValueError('Cached climate source hash mismatch')
            payloads[(item['version'], item['variable'])] = content
        return payloads, manifest
    specs = [(version, variable) for version in VERSIONS for variable in VARIABLES]
    def get_one(spec):
        version, variable = spec
        url = source_url(version, variable)
        response = requests.get(url, timeout=90)
        response.raise_for_status()
        frame, header = parse_country(response.content, version, variable)
        path = DATA / f'cru_cy_{version}' / 'raw' / f'Israel.{variable}.per'
        item = {'version': version, 'variable': variable, 'source_url': url,
                'fetched_at': datetime.now(timezone.utc).isoformat(),
                'http_last_modified': response.headers.get('Last-Modified'),
                'path': str(path.relative_to(ROOT)), 'sha256': digest(response.content),
                'byte_size': len(response.content), **header}
        if path.exists():
            prior, _ = parse_country(path.read_bytes(), version, variable)
            if frame.value.notna().sum() < prior.value.notna().sum():
                raise ValueError('Climate source lost previously present values')
        return spec, response.content, item
    # Fetches are independent; mutations happen only after every validation succeeds.
    with ThreadPoolExecutor(max_workers=4) as pool:
        downloaded = list(pool.map(get_one, specs))
    docs = []
    for version in VERSIONS:
        for name in DOC_NAMES + [f'Release_Notes_CRU_CY_{version}.txt']:
            url = BASE + VERSIONS[version][0] + name
            response = requests.get(url, timeout=90); response.raise_for_status()
            if 'CRU' not in response.text or '<html' in response.text.lower():
                raise ValueError('Unexpected climate source documentation')
            path = DATA / f'cru_cy_{version}' / 'raw' / name
            docs.append((path, response.content, {'path': str(path.relative_to(ROOT)),
                'source_url': url, 'sha256': digest(response.content)}))
    manifest = {'schema_version': 1, 'files': [item for _, _, item in downloaded],
        'documentation': [item for _, _, item in docs],
        'attribution': 'Climatic Research Unit, University of East Anglia',
        'reference': 'https://doi.org/10.1038/s41597-020-0453-3',
        'licensing': {'4.10': 'ODbL + DbCL, Attribution and Share-Alike', '4.08': 'Open Government Licence; acknowledge CRU and Met Office'},
        'license_sources': [BASE + 'cru_ts_4.10/', BASE + 'cru_ts_4.08/'],
        'release_announced_at': {'4.08': '2024-06-27', '4.10': '2026-06-25'},
        'geography': GEOGRAPHY,
        'data_status': 'observation-derived monthly gridded estimates; not forecasts; may contain source climatology substitution',
        'station_coverage': 'unavailable in country files; 100% monthly completeness is not 100% station observation coverage',
        'refresh_policy': 'pinned releases; future version requires explicit reviewed addition and overlap comparison'}
    for _, content, item in downloaded:
        path = ROOT / item['path']; path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            tmp.write(content); temp_path = Path(tmp.name)
        temp_path.replace(path)
    for path, content, _ in docs:
        path.write_bytes(content)
    write_json(DATA / 'source_manifest.json', manifest)
    return {spec: blob for spec, blob, _ in downloaded}, manifest


def build_monthly(payloads, version):
    frames = []
    for variable in VARIABLES:
        frame, _ = parse_country(payloads[(version, variable)], version, variable)
        frames.append(frame.set_index(['year', 'month']).value.rename(variable))
    out = pd.concat(frames, axis=1).reset_index()
    out['date'] = pd.to_datetime(dict(year=out.year, month=out.month, day=1))
    out['days_in_month'] = out.date.dt.days_in_month
    out['pet_mm'] = out.pet * out.days_in_month
    out['balance_mm'] = out.pre - out.pet_mm
    out['product'] = f'CRU-CY{version}'
    out['geography_id'] = GEOGRAPHY['geography_id']
    out['source_status'] = 'gridded estimate; station support unavailable'
    return out


def complete_aggregate(frame, variable, expected, how='sum'):
    selected = frame[variable]
    n = int(selected.notna().sum())
    if len(frame) != expected or n != expected:
        return np.nan, n
    if how == 'day_weighted_mean':
        return float(np.average(selected, weights=frame.days_in_month)), n
    return float(selected.sum()), n


def annual_diagnostics(monthly):
    if monthly.duplicated(['year', 'month']).any():
        raise ValueError('Duplicate climate month')
    rows = []
    for year in range(int(monthly.year.min()), int(monthly.year.max()) + 2):
        rain_year = monthly[(monthly.year.eq(year - 1) & monthly.month.ge(10)) |
                            (monthly.year.eq(year) & monthly.month.le(9))]
        spring = monthly[monthly.year.eq(year) & monthly.month.between(3, 5)]
        calyear = monthly[monthly.year.eq(year)]
        former = rain_year[rain_year.month.isin([10, 11])]
        latter = rain_year[rain_year.month.isin([3, 4])]
        row = {'year': year, 'product': monthly['product'].iloc[0], 'geography_id': GEOGRAPHY['geography_id']}
        for metric, group, var, expected, how in [
            ('rain_mm', rain_year, 'pre', 12, 'sum'), ('former_mm', former, 'pre', 2, 'sum'),
            ('latter_mm', latter, 'pre', 2, 'sum'), ('pet_mm', rain_year, 'pet_mm', 12, 'sum'),
            ('balance_mm', rain_year, 'balance_mm', 12, 'sum'), ('wet_days', rain_year, 'wet', 12, 'sum'),
            ('spring_tmx_c', spring, 'tmx', 3, 'day_weighted_mean'),
            ('annual_tmp_c', calyear, 'tmp', 12, 'day_weighted_mean')]:
            value, n = complete_aggregate(group, var, expected, how)
            row[metric] = value; row[metric + '_months'] = n
        rows.append(row)
    out = pd.DataFrame(rows)
    baseline = out[out.year.between(1991, 2020)]
    for metric in ['rain_mm', 'former_mm', 'latter_mm', 'pet_mm', 'balance_mm', 'wet_days', 'spring_tmx_c', 'annual_tmp_c']:
        values = baseline[metric].dropna()
        mean = float(values.mean()) if len(values) == 30 else np.nan
        sd = float(values.std(ddof=1)) if len(values) == 30 else np.nan
        out[metric + '_baseline_n'] = len(values)
        out[metric + '_anomaly'] = out[metric] - mean
        out[metric + '_z'] = (out[metric] - mean) / sd if sd > 0 else np.nan
        if metric == 'rain_mm':
            out['rain_percent_baseline'] = 100 * out[metric] / mean if mean > 0 else np.nan
    return out


def monthly_anomalies(monthly):
    out = monthly.copy()
    for variable in ['pre', 'tmp', 'tmx', 'pet_mm', 'balance_mm', 'wet']:
        for month in range(1, 13):
            baseline = out.loc[out.year.between(1991, 2020) & out.month.eq(month), variable].dropna()
            selected = out.month.eq(month)
            out.loc[selected, variable + '_baseline_n'] = len(baseline)
            out.loc[selected, variable + '_anomaly'] = out.loc[selected, variable] - baseline.mean() if len(baseline) == 30 else np.nan
    return out


def compare_series(old, new, columns, labels, keys):
    merged = old.merge(new, on=keys, how='outer', suffixes=('_old', '_new'), validate='one_to_one')
    rows, summary = [], []
    for col in columns:
        pair = merged[merged[col + '_old'].notna() & merged[col + '_new'].notna()]
        delta = pair[col + '_new'] - pair[col + '_old']
        for (_, row), change in zip(pair.iterrows(), delta):
            rows.append({**{key: int(row[key]) for key in keys}, 'variable': col,
                'old_product': labels[0], 'new_product': labels[1],
                'old_value': row[col + '_old'], 'new_value': row[col + '_new'], 'delta_new_minus_old': change})
        summary.append({'variable': col, 'old_product': labels[0], 'new_product': labels[1],
            'overlap_n': len(pair), 'old_only_n': int((merged[col + '_old'].notna() & merged[col + '_new'].isna()).sum()),
            'new_only_n': int((merged[col + '_old'].isna() & merged[col + '_new'].notna()).sum()),
            'mean_delta': float(delta.mean()) if len(pair) else None,
            'mae': float(delta.abs().mean()) if len(pair) else None,
            'max_abs_delta': float(delta.abs().max()) if len(pair) else None,
            'rmse': float(np.sqrt((delta ** 2).mean())) if len(pair) else None,
            'pearson_r': float(pair[col + '_old'].corr(pair[col + '_new'])) if len(pair) > 2 and pair[col + '_old'].std() > 0 and pair[col + '_new'].std() > 0 else None,
            'changed_values': int((delta.abs() > 1e-9).sum())})
    return pd.DataFrame(rows), summary


def exploratory_models(annual, crops, water):
    wheat = wheat_measures(crops)
    frame = annual.set_index('year')[['rain_mm', 'spring_tmx_c']].join(wheat[['yield_kg_ha']])
    irr = water[water.indicator.eq('AG.LND.IRIG.AG.ZS')]
    if irr.year.duplicated().any() or irr.interpolated_locally.astype(str).str.lower().isin(['true', '1']).any():
        raise ValueError('Irrigation must contain unique reported years, no local interpolation')
    frame = frame.join(irr.set_index('year').value.rename('irrigated_share_percent'))
    frame = frame.loc[frame.index.to_series().between(1961, 2023)]
    rows = []
    for model, covariates in [('rain_heat', ['rain_mm', 'spring_tmx_c']),
                              ('rain_heat_irrigation', ['rain_mm', 'spring_tmx_c', 'irrigated_share_percent'])]:
        used = frame[['yield_kg_ha'] + covariates].dropna().sort_index()
        years = used.index.to_numpy(float)
        design = np.column_stack([np.ones(len(used)), years - years.mean(), used[covariates]]) if len(used) else np.empty((0, 2 + len(covariates)))
        valid = len(used) >= 12 and np.linalg.matrix_rank(design) == design.shape[1]
        if valid:
            beta, se, df = calendar_hac(design, used.yield_kg_ha.to_numpy(), years)
            reference = np.column_stack([np.ones(len(used)), years - years.mean(), used.rain_mm])
            reference_beta = float(np.linalg.lstsq(reference, used.yield_kg_ha, rcond=None)[0][2])
        for i, label in enumerate(covariates, 2):
            row = {'model': model, 'coefficient': label, 'n': len(used),
                'years': ';'.join(str(int(y)) for y in years),
                'status': 'exploratory national aggregate; geography not verified against agricultural reporting' if valid else 'unavailable: insufficient observations or rank',
                'estimate': np.nan, 'ci_low': np.nan, 'ci_high': np.nan, 'p_calendar_hac': np.nan,
                'rain_only_beta_same_years': reference_beta if valid else np.nan}
            if valid and se[i] > 0:
                critical = stats.t.ppf(.975, df)
                row.update(estimate=beta[i], ci_low=beta[i] - critical * se[i], ci_high=beta[i] + critical * se[i],
                           p_calendar_hac=2 * stats.t.sf(abs(beta[i] / se[i]), df))
            rows.append(row)
    out = pd.DataFrame(rows)
    out['q_calendar_hac_family5'] = bh(out.p_calendar_hac.fillna(1))
    return out


def holdout_eligibility(annual, crops, plan):
    wheat = wheat_measures(crops)
    future_yield = wheat.loc[wheat.index >= plan['holdout_start'], 'yield_kg_ha'].dropna()
    climate_years = set(annual.loc[annual.rain_mm.notna() & annual.year.ge(plan['holdout_start']), 'year'])
    pairs = sorted(climate_years & set(future_yield.index))
    return {'status': 'ineligible', 'holdout_start': plan['holdout_start'], 'minimum_future_pairs': 10,
        'available_future_crop_years': [int(y) for y in future_yield.index],
        'available_cru_cy_future_rain_years': sorted(int(y) for y in climate_years),
        'candidate_cru_cy_pairs': [int(y) for y in pairs],
        'candidate_pair_count': len(pairs), 'approved_same_product_pair_count': 0,
        'compatible_with_frozen_rain_aggregation': False,
        'reasons': ['CRU-CY is separately aggregated and not approved as frozen CCKP rainfall input'] +
                   (['Fewer than 10 future pairs'] if len(pairs) < 10 else []),
        'scoring_performed': False, 'frozen_model_refitted': False}


def _run(offline=False):
    frozen = {name: digest((ROOT / name).read_bytes()) for name in FROZEN}
    extension_plan = json.loads((ROOT / 'climate_extension_plan.json').read_text())
    assert extension_plan['family_size'] == 5 and extension_plan['historical_fit_years'] == [1961, 2023]
    payloads, manifest = fetch_sources(offline)
    monthly, annual, coverage = {}, {}, {}
    for version in VERSIONS:
        monthly[version] = monthly_anomalies(build_monthly(payloads, version))
        annual[version] = annual_diagnostics(monthly[version])
        (DATA / f'cru_cy_{version}').mkdir(parents=True, exist_ok=True)
        monthly[version].to_csv(DATA / f'cru_cy_{version}' / 'monthly.csv', index=False)
        annual[version].to_csv(DATA / f'cru_cy_{version}' / 'annual_diagnostics.csv', index=False)
        coverage[version] = {}
        for variable in VARIABLES:
            frame = monthly[version]
            observed = frame[frame[variable].notna()]
            vectors = frame.pivot(index='year', columns='month', values=variable).dropna()
            coverage[version][variable] = {'expected_months': len(frame), 'present_months': len(observed),
                'missing_months': frame.loc[frame[variable].isna(), 'date'].dt.strftime('%Y-%m').tolist(),
                'first_month': observed.date.min().strftime('%Y-%m') if len(observed) else None,
                'last_month': observed.date.max().strftime('%Y-%m') if len(observed) else None,
                'repeated_annual_vectors': int(vectors.duplicated().sum()),
                'station_observation_coverage': None, 'unit': VARIABLES[variable][1]}
    overlap, comparison = compare_series(monthly['4.08'], monthly['4.10'], list(VARIABLES), ('CRU-CY4.08', 'CRU-CY4.10'), ['year', 'month'])
    overlap.to_csv(RESULTS / 'climate_version_overlap_monthly.csv', index=False)
    overlap_a, comparison_a = compare_series(annual['4.08'], annual['4.10'], ['rain_mm', 'former_mm', 'latter_mm', 'spring_tmx_c', 'annual_tmp_c', 'pet_mm', 'balance_mm', 'wet_days'], ('CRU-CY4.08', 'CRU-CY4.10'), ['year'])
    overlap_a.to_csv(RESULTS / 'climate_version_overlap_annual.csv', index=False)
    cckp = pd.read_csv(ROOT / 'data/rain_cckp_monthly.csv').rename(columns={'precip_mm': 'pre'})
    cross, cross_summary = compare_series(cckp, monthly['4.08'], ['pre'], ('CCKP-CRU-TS4.08-ISR', 'CRU-CY4.08-Israel'), ['year', 'month'])
    cross.to_csv(RESULTS / 'climate_aggregation_overlap_monthly.csv', index=False)
    write_json(RESULTS / 'climate_overlap_summary.json', {'same_country_product_version_comparison': comparison,
        'annual_version_comparison': comparison_a, 'different_aggregation_same_upstream_version': cross_summary,
        'comparison_scope': 'every shared nonmissing month/year; no high-correlation equivalence certification'})
    crops = pd.read_csv(ROOT / 'data/faostat_crop_measures.csv')
    water = pd.read_csv(ROOT / 'data/water_covariates_reported.csv')
    models = exploratory_models(annual['4.10'], crops, water)
    models.to_csv(RESULTS / 'climate_heat_irrigation_sensitivity.csv', index=False)
    eligibility = holdout_eligibility(annual['4.10'], crops, json.loads((ROOT / 'analysis_plan.json').read_text()))
    latest = annual['4.10'].dropna(subset=['rain_mm']).iloc[-1]
    selected = ['year', 'rain_mm', 'rain_percent_baseline', 'rain_mm_z', 'former_mm', 'latter_mm',
                'spring_tmx_c', 'spring_tmx_c_anomaly', 'annual_tmp_c', 'annual_tmp_c_anomaly',
                'pet_mm', 'balance_mm', 'balance_mm_z', 'wet_days']
    latest_record = {key: float(latest[key]) if pd.notna(latest[key]) else None for key in selected}
    latest_record['year'] = int(latest_record['year'])
    report = {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'product': 'CRU-CY4.10', 'latest_complete_rain_year': latest_record,
        'latest_month': monthly['4.10'].date.max().strftime('%Y-%m'), 'coverage': coverage,
        'baseline': '1991-2020; per metric, require 30 complete years',
        'metric_units': {'rain_mm': 'mm per October-September rain year', 'former_mm': 'mm per October-November',
            'latter_mm': 'mm per March-April', 'spring_tmx_c': 'degrees Celsius, March-May day-weighted mean daily maximum',
            'annual_tmp_c': 'degrees Celsius, calendar-year day-weighted mean daily mean', 'pet_mm': 'mm per October-September',
            'balance_mm': 'mm per October-September', 'wet_days': 'days per October-September',
            'rain_percent_baseline': 'percent', '*_anomaly': 'same units as corresponding metric', '*_z': 'baseline sample standard deviations'},
        'geography': GEOGRAPHY, 'source_status': manifest['data_status'],
        'holdout': eligibility,
        'irrigation': {'reported_years': sorted(int(y) for y in water.loc[water.indicator.eq('AG.LND.IRIG.AG.ZS'), 'year']),
            'scope': 'national all-crop agricultural irrigated land share; no wheat-specific irrigation series',
            'source_status': 'reported values may contain upstream estimates; no local interpolation'},
        'limitations': ['CRU-CY station support/climatology-substitution fractions are unavailable; filled monthly records do not certify observed station coverage',
            'Monthly average daily maximum temperature does not measure heatwave duration or days above a threshold',
            'Rain minus PET is a climatic water-balance proxy, not soil moisture, crop water use, SPI or SPEI',
            'No IMS station observations spliced into CRU; no wheat-specific irrigation supplied',
            'Source country mask and agricultural reporting boundaries are not verified equivalent; no area-normalized crop attribution',
            '2024 crop outcomes were already seen; 2025 onward remain reserved; no prospective scoring'],
        'frozen_artifact_sha256': frozen,
        'extension_plan_sha256': digest((ROOT / 'climate_extension_plan.json').read_bytes()),
        'inputs_sha256': {'data/faostat_crop_measures.csv': digest((ROOT / 'data/faostat_crop_measures.csv').read_bytes()),
                          'data/water_covariates_reported.csv': digest((ROOT / 'data/water_covariates_reported.csv').read_bytes()),
                          'data/climate/source_manifest.json': digest((DATA / 'source_manifest.json').read_bytes())}}
    if frozen != {name: digest((ROOT / name).read_bytes()) for name in FROZEN}:
        raise ValueError('Frozen artifacts changed')
    write_json(RESULTS / 'climate_monitor.json', report)
    lines = ['# Israel climate monitor', '', f'CRU-CY4.10: monthly coverage through {report["latest_month"]}. Source area-weighted Israel grid mask.', '',
        'Gridded estimates can include climatology substitution. Station coverage unavailable. Equivalence to the CCKP aggregation is unverified; original baseline stays separate.', '',
        '| Parameter | Latest complete year | Value |', '|---|---:|---:|']
    for label, key, units in [('October-September rain', 'rain_mm', 'mm'), ('Rain / 1991-2020 mean', 'rain_percent_baseline', '%'),
        ('March-May mean daily maximum temperature', 'spring_tmx_c', '°C'), ('Spring maximum-temperature anomaly', 'spring_tmx_c_anomaly', '°C'),
        ('Calendar-year mean temperature anomaly', 'annual_tmp_c_anomaly', '°C'), ('October-September rain minus PET', 'balance_mm', 'mm')]:
        value = latest_record[key]
        formatted = f'{value:.2f} {units}' if value is not None else 'unavailable'
        lines.append(f'| {label} | {int(latest_record["year"])} | {formatted} |')
    lines += ['', 'Rain minus PET is a water-balance proxy; not measured drought damage. Temperature is a monthly mean of daily maxima; not heatwave-day counts.', '',
        f'Prospective wheat validation: **ineligible**. {eligibility["candidate_pair_count"]}/10 candidate future pairs; 0 approved same-product pairs. No frozen-model refit or scoring.', '',
        'Historical rain/heat adjustment: 5 fixed exploratory tests, calendar-distance HAC3, BH over all 5. Irrigation adjustment uses reported years only, national all-crop share. It cannot identify wheat irrigation effects.', '',
        '[Primary data and methodology](https://crudata.uea.ac.uk/cru/data/hrg/) · [CRU-CY4.10 source files](https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/crucy.2606161920.v4.10/)', '']
    (RESULTS / 'climate_monitor.md').write_text('\n'.join(lines))
    return {'product': report['product'], 'latest_month': report['latest_month'], 'latest_complete_rain_year': int(latest_record['year']), 'holdout': eligibility, 'model_tests': len(models)}


def main(offline=False):
    """Stage fetching and analysis; any validation/model error preserves prior snapshot."""
    global ROOT, DATA, RESULTS
    live_root, live_data, live_results = ROOT, DATA, RESULTS
    inputs = FROZEN + ['climate_extension_plan.json', 'data/faostat_crop_measures.csv', 'data/water_covariates_reported.csv']
    input_hashes = {name: digest((live_root / name).read_bytes()) for name in inputs}
    outputs = ['climate_version_overlap_monthly.csv', 'climate_version_overlap_annual.csv',
        'climate_aggregation_overlap_monthly.csv', 'climate_overlap_summary.json',
        'climate_heat_irrigation_sensitivity.csv', 'climate_monitor.md', 'climate_monitor.json']
    with tempfile.TemporaryDirectory(prefix='.climate-refresh-', dir=live_root) as directory:
        stage = Path(directory)
        for name in inputs:
            (stage / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(live_root / name, stage / name)
        if live_data.exists():
            shutil.copytree(live_data, stage / 'data/climate', dirs_exist_ok=True)
        try:
            ROOT, DATA, RESULTS = stage, stage / 'data/climate', stage / 'results'
            summary = _run(offline)
        finally:
            ROOT, DATA, RESULTS = live_root, live_data, live_results
        if input_hashes != {name: digest((live_root / name).read_bytes()) for name in inputs}:
            raise ValueError('Climate inputs changed during refresh; no outputs promoted')
        for name in outputs:
            if not (stage / 'results' / name).is_file():
                raise ValueError('Required climate output missing; no outputs promoted')
        # Validate all first; same-filesystem replacements follow. Success report last.
        promotions = [(path, live_data / path.relative_to(stage / 'data/climate'))
            for path in sorted((stage / 'data/climate').rglob('*')) if path.is_file()]
        promotions += [(stage / 'results' / name, live_results / name) for name in outputs]
        for source, destination in promotions:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists() or digest(source.read_bytes()) != digest(destination.read_bytes()):
                source.replace(destination)
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Use hash-checked archived source files')
    main(parser.parse_args().offline)
