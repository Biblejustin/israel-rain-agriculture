"""Official Kinneret measurements; source-defined water covariates, no imputation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data'
KIN_RESOURCE = '2de7b543-e13d-4e7e-b4c8-56071bc4d3c8'
KIN_API = 'https://data.gov.il/api/3/action/datastore_search'
KIN_URL = f'{KIN_API}?resource_id={KIN_RESOURCE}'
WATER_INDICATORS = {
    'AG.LND.IRIG.AG.ZS': 'Agricultural irrigated land (% of total agricultural land)',
    'ER.H2O.FWAG.ZS': 'Annual freshwater withdrawals, agriculture (% of total freshwater withdrawal)',
    'ER.H2O.FWTL.ZS': 'Annual freshwater withdrawals, total (% of internal renewable resources)',
}


def normalize_kinneret(records, fetched_at):
    frame = pd.DataFrame(records)
    required = {'Survey_Date', 'Kinneret_Level', '_id'}
    if not required.issubset(frame):
        raise ValueError(f'Kinneret schema missing {required-set(frame)}')
    out = pd.DataFrame({
        'observation_date': pd.to_datetime(frame.Survey_Date, errors='raise').dt.strftime('%Y-%m-%d'),
        'level_m': pd.to_numeric(frame.Kinneret_Level, errors='raise'),
        'source_record_id': frame['_id'],
    })
    if out.empty or not out.level_m.between(-220, -200).all():
        raise ValueError('Empty or implausible Kinneret values')
    if out.observation_date.duplicated().any():
        raise ValueError('Duplicate Kinneret measurement dates; inspect source revision')
    if (out.observation_date > fetched_at[:10]).any():
        raise ValueError('Future Kinneret observation')
    out['source_url'], out['fetched_at'] = KIN_URL, fetched_at
    out['publication_date'] = None  # API does not supply per-observation release date
    out['provisional_status'] = 'not supplied by source'
    out['unit'], out['location'] = 'm relative to source sea-level datum', 'Lake Kinneret, Israel'
    return out.sort_values('observation_date')


def atomic_csv(frame, path):
    tmp = path.with_suffix('.csv.tmp')
    frame.to_csv(tmp, index=False)
    tmp.replace(path)


def fetch_kinneret():
    now = datetime.now(timezone.utc).isoformat()
    records, offset, total = [], 0, None
    while total is None or offset < total:
        response = requests.get(KIN_API, params={'resource_id': KIN_RESOURCE, 'limit': 10000,
                                'offset': offset, 'sort': 'Survey_Date asc'}, timeout=60)
        response.raise_for_status()
        payload = response.json()
        if payload.get('success') is not True:
            raise ValueError('Kinneret API reported failure')
        result = payload['result']
        total = int(result['total'])
        page = result['records']
        if not page:
            raise ValueError('Kinneret pagination stopped before declared total')
        records.extend(page)
        offset += len(page)
    if len(records) != total:
        raise ValueError('Kinneret total changed during pagination; retry snapshot')
    frame = normalize_kinneret(records, now)
    target = DATA / 'kinneret_levels.csv'
    if target.exists() and len(frame) < 0.95 * len(pd.read_csv(target)):
        raise ValueError('Kinneret replacement lost >5% records')
    atomic_csv(frame, target)
    return frame


def fetch_irrigation():
    rows, availability = [], {}
    fetched = datetime.now(timezone.utc).isoformat()
    for code, label in WATER_INDICATORS.items():
        url = f'https://api.worldbank.org/v2/country/ISR/indicator/{code}?format=json&per_page=200'
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or len(payload) != 2:
            raise ValueError(f'Unexpected WDI schema for {code}')
        entries = [r for r in payload[1] or [] if r.get('value') is not None]
        availability[code] = {'label': label, 'reported_years': sorted(int(r['date']) for r in entries),
                              'source_url': url, 'source_last_updated': payload[0].get('lastupdated')}
        for r in entries:
            rows.append({'year': int(r['date']), 'indicator': code, 'label': label,
                         'value': r['value'], 'unit': 'percent', 'source_status': r.get('obs_status', ''),
                         'source_url': url, 'fetched_at': fetched,
                         'source_last_updated': payload[0].get('lastupdated'),
                         'provisional_status': 'source does not distinguish annual measurement from estimate',
                         'interpolated_locally': False})
    frame = pd.DataFrame(rows)
    if not frame.empty:
        atomic_csv(frame.sort_values(['indicator', 'year']), DATA / 'water_covariates_reported.csv')
    return availability


def build_metadata(frame, availability):
    dates = pd.to_datetime(frame.observation_date)
    gaps = dates.diff().dt.days.dropna()
    latest = frame.iloc[-1]
    def exact_change(days):
        target = (dates.iloc[-1] - pd.Timedelta(days=days)).strftime('%Y-%m-%d')
        old = frame.loc[frame.observation_date.eq(target), 'level_m']
        return float(latest.level_m-old.iloc[0]) if len(old) == 1 else None
    season_start = f'{dates.iloc[-1].year - int(dates.iloc[-1].month < 10)}-10-01'
    within = frame[frame.observation_date >= season_start]
    return {
        'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'kinneret': {'source_url': KIN_URL, 'resource_id': KIN_RESOURCE,
            'source_version': 'CKAN live datastore snapshot', 'location': latest.location,
            'unit': latest.unit, 'publication_date': None, 'fetched_at': latest.fetched_at,
            'observations': len(frame), 'observation_start': frame.observation_date.min(),
            'observation_end': frame.observation_date.max(), 'latest_level_m': float(latest.level_m),
            'change_7d_m': exact_change(7), 'change_30d_m': exact_change(30),
            'rain_season_start': season_start,
            'observed_season_refill_range_m': float(within.level_m.max()-within.level_m.min()),
            'unobserved_days_within_span': int((dates.iloc[-1]-dates.iloc[0]).days+1-len(frame)),
            'max_observation_gap_days': int(gaps.max()),
            'coverage_status': 'Observed measurement dates only; gaps retained; latest observation is not certified completeness',
            'denominator': 'one level measurement per listed date; no population denominator',
            'sha256': hashlib.sha256((DATA/'kinneret_levels.csv').read_bytes()).hexdigest(),
            'limitations': 'Level responds to pumping, transfers, evaporation and inflow. Gauge datum is source-defined. No prophetic threshold.'},
        'historical_rain': {'file':'rain_cckp_monthly.csv','version':'CRU TS4.08',
            'observation_end':'2023-12','last_complete_rain_year':2023,
            'freshness':'historical baseline only; cannot monitor current drought',
            'recent_station_status':'IMS recent station series not integrated; do not splice station and gridded products'},
        'irrigation_and_water_use': availability,
        'covariate_model_status':'Reported source values retained without local interpolation. Annual WDI labels can contain estimates/repeated releases. Separate complete-case irrigation_sensitivity.py is exploratory, not causal; national share is not wheat-specific irrigation.',
        'theme': 'Deuteronomy 11:14; interpretive tag only',
    }


def main():
    DATA.mkdir(exist_ok=True)
    frame = fetch_kinneret()
    try:
        availability = fetch_irrigation()
    except (requests.RequestException, ValueError, KeyError) as error:
        availability = {"refresh_status": "failed; prior annual CSV retained", "error": str(error),
                        "last_attempt": datetime.now(timezone.utc).isoformat()}
        print(f"Annual water-covariate refresh failed; Kinneret still refreshed: {error}")
    metadata = build_metadata(frame, availability)
    target = DATA / 'water_security_metadata.json'
    tmp = target.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(metadata, indent=2)+'\n')
    tmp.replace(target)
    print(f'Kinneret: {len(frame)} measurements, latest {frame.iloc[-1].observation_date}: {frame.iloc[-1].level_m} m')

if __name__ == '__main__':
    main()
