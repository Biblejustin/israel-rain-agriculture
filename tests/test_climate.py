"""Scientific data contracts for the versioned climate extension."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import monitor_climate as climate

ROOT = Path(__file__).resolve().parents[1]


def monthly_fixture():
    dates = pd.date_range('1990-01-01', '2026-12-01', freq='MS')
    out = pd.DataFrame({'date': dates, 'year': dates.year, 'month': dates.month,
        'days_in_month': dates.days_in_month, 'product': 'synthetic-test',
        'pre': 1.0, 'tmx': 20.0, 'tmp': 15.0, 'pet_mm': dates.days_in_month * 2.0, 'wet': 1.0})
    out['balance_mm'] = out.pre - out.pet_mm
    return out


class ClimateTests(unittest.TestCase):
    def test_country_units_truncation_and_missing_code(self):
        blob = (ROOT / 'data/climate/cru_cy_4.10/raw/Israel.pre.per').read_bytes()
        frame, _ = climate.parse_country(blob, '4.10', 'pre')
        self.assertEqual(len(frame), 1500)
        for old, new in [(b'Israel', b'Jordan'), (b'mm/month', b'mm/day')]:
            with self.assertRaises(ValueError):
                climate.parse_country(blob.replace(old, new), '4.10', 'pre')
        with self.assertRaises(ValueError):
            climate.parse_country(b'\n'.join(blob.splitlines()[:-1]), '4.10', 'pre')
        lines = blob.decode().splitlines()
        cells = lines[4].split(); cells[1] = '-999.0'; lines[4] = ' '.join(cells)
        missing, _ = climate.parse_country('\n'.join(lines).encode(), '4.10', 'pre')
        self.assertTrue(pd.isna(missing.iloc[0].value))
        self.assertEqual(missing.value.notna().sum(), 1499)

    def test_actual_calendar_pet_and_exact_rain_year(self):
        data = monthly_fixture()
        out = climate.annual_diagnostics(data).set_index('year')
        self.assertEqual(out.loc[2000, 'rain_mm'], 12)
        self.assertEqual(out.loc[2000, 'pet_mm'], 732)
        self.assertEqual(out.loc[2001, 'pet_mm'], 730)
        self.assertEqual(out.loc[2000, 'balance_mm'], -720)
        # Previous October contributes only to the following rain year.
        data.loc[data.year.eq(1999) & data.month.eq(10), 'pre'] = 10
        out = climate.annual_diagnostics(data).set_index('year')
        self.assertEqual(out.loc[2000, 'rain_mm'], 21)
        self.assertEqual(out.loc[1999, 'rain_mm'], 12)

    def test_missing_or_duplicate_month_never_means_zero(self):
        data = monthly_fixture()
        data.loc[data.year.eq(2000) & data.month.eq(2), 'pre'] = np.nan
        out = climate.annual_diagnostics(data).set_index('year')
        self.assertTrue(pd.isna(out.loc[2000, 'rain_mm']))
        self.assertEqual(out.loc[2000, 'rain_mm_months'], 11)
        # A missing baseline year invalidates standardized departure.
        self.assertTrue(out.rain_mm_z.isna().all())
        with self.assertRaises(ValueError):
            climate.annual_diagnostics(pd.concat([data, data.iloc[:1]]))

    def test_temperature_day_weights_and_seasonal_baseline(self):
        data = monthly_fixture()
        data.loc[data.month.eq(4), 'tmx'] = 30
        out = climate.annual_diagnostics(data).set_index('year')
        self.assertAlmostEqual(out.loc[2000, 'spring_tmx_c'], (20 * 62 + 30 * 30) / 92)
        self.assertEqual(out.loc[2000, 'spring_tmx_c_baseline_n'], 30)
        self.assertTrue(pd.isna(out.loc[2027, 'spring_tmx_c']))
        # Monthly anomaly compares January to January, not full-year temperature.
        data.loc[data.month.eq(1), 'tmp'] = 5
        anomalies = climate.monthly_anomalies(data)
        self.assertTrue((anomalies.tmp_anomaly == 0).all())

    def test_future_outcomes_excluded_and_irrigation_not_interpolated(self):
        annual = pd.read_csv(ROOT / 'data/climate/cru_cy_4.10/annual_diagnostics.csv')
        crops = pd.read_csv(ROOT / 'data/faostat_crop_measures.csv')
        water = pd.read_csv(ROOT / 'data/water_covariates_reported.csv')
        original = climate.exploratory_models(annual, crops, water)
        # Scale all measures consistently, preserving source yield identity.
        selected = crops.year.ge(2024) & crops.element_code.isin([5510, 5412])
        crops.loc[selected, 'value'] *= 1000
        changed = climate.exploratory_models(annual, crops, water)
        pd.testing.assert_frame_equal(original, changed)
        self.assertEqual(len(original), 5)
        self.assertEqual(original.loc[original.model.eq('rain_heat_irrigation'), 'n'].tolist(), [17]*3)
        water.loc[water.indicator.eq('AG.LND.IRIG.AG.ZS'), 'interpolated_locally'] = True
        with self.assertRaises(ValueError): climate.exploratory_models(annual, crops, water)

    def test_overlap_retains_every_shared_value_and_extra_year(self):
        old = pd.DataFrame({'year': [1, 2, 3], 'pre': [10, 20, np.nan]})
        new = pd.DataFrame({'year': [1, 2, 3, 4], 'pre': [11, 21, 31, 41]})
        rows, summary = climate.compare_series(old, new, ['pre'], ('old', 'new'), ['year'])
        self.assertEqual(len(rows), 2)
        self.assertEqual(summary[0]['mean_delta'], 1)
        self.assertEqual(summary[0]['new_only_n'], 2)
        self.assertEqual(summary[0]['overlap_n'], 2)

    def test_ten_pairs_do_not_override_geographic_product_gate(self):
        years = list(range(2025, 2035))
        crops = pd.DataFrame([{'year': y, 'crop': 'Wheat', 'element_code': code, 'unit': unit, 'value': value}
            for y in years for code, unit, value in [(5510, 't', 100), (5312, 'ha', 50), (5412, 'kg/ha', 2000)]])
        report = climate.holdout_eligibility(pd.DataFrame({'year': years, 'rain_mm': 100}), crops, {'holdout_start': 2025})
        self.assertEqual(report['candidate_pair_count'], 10)
        self.assertEqual(report['approved_same_product_pair_count'], 0)
        self.assertFalse(report['scoring_performed'])
        self.assertEqual(report['status'], 'ineligible')

    def test_late_model_failure_preserves_entire_published_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = climate.FROZEN + ['climate_extension_plan.json', 'data/faostat_crop_measures.csv', 'data/water_covariates_reported.csv']
            for name in names:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / name, root / name)
            shutil.copytree(ROOT / 'data/climate', root / 'data/climate', dirs_exist_ok=True)
            for file in (ROOT / 'results').glob('climate_*'):
                if file.is_file(): shutil.copy(file, root / 'results' / file.name)
            before = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in root.rglob('*') if p.is_file()}
            with patch.object(climate, 'ROOT', root), patch.object(climate, 'DATA', root / 'data/climate'), patch.object(climate, 'RESULTS', root / 'results'):
                with patch.object(climate, 'exploratory_models', side_effect=ValueError('late model failure')):
                    with self.assertRaisesRegex(ValueError, 'late model failure'): climate.main(offline=True)
            after = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            self.assertEqual(list(root.glob('.climate-refresh-*')), [])

    def test_offline_pipeline_preserves_frozen_artifacts_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = climate.FROZEN + ['climate_extension_plan.json', 'data/faostat_crop_measures.csv', 'data/water_covariates_reported.csv']
            for name in names:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / name, root / name)
            shutil.copytree(ROOT / 'data/climate', root / 'data/climate', dirs_exist_ok=True)
            before = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in climate.FROZEN}
            with patch.object(climate, 'ROOT', root), patch.object(climate, 'DATA', root / 'data/climate'), patch.object(climate, 'RESULTS', root / 'results'):
                climate.main(offline=True)
                report = json.loads((root / 'results/climate_monitor.json').read_text())
                self.assertEqual(report['latest_month'], '2025-12')
                self.assertEqual(report['frozen_artifact_sha256'], before)
                self.assertEqual(report['holdout']['candidate_pair_count'], 0)
                self.assertIsNone(report['coverage']['4.10']['pre']['station_observation_coverage'])
                self.assertIsNone(report['geography']['mask_equivalent_to_cckp_isr'])
                self.assertFalse(report['geography']['approved_frozen_product_equivalence'])
                self.assertEqual(sum(len(pd.read_csv(root / 'data/climate' / f'cru_cy_{v}' / 'monthly.csv')) for v in climate.VERSIONS), 2976)
                damaged = root / 'data/climate/cru_cy_4.10/raw/Israel.pre.per'
                damaged.write_bytes(damaged.read_bytes() + b'\n')
                with self.assertRaises(ValueError): climate.fetch_sources(offline=True)
            self.assertEqual(before, {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in climate.FROZEN})


if __name__ == '__main__': unittest.main()
