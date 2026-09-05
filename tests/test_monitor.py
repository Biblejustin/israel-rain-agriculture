import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
import analyze
from crop_rain_analysis import wheat_measures,test_pair as evaluate_pair,interaction,bh
from monitor_water import normalize_kinneret

class MonitorTests(unittest.TestCase):
    def test_yield_units_and_identity(self):
        data=pd.DataFrame({'crop':['Wheat']*3,'year':[2000]*3,'element_code':[5510,5312,5412], 'unit':['t','ha','kg/ha'],'value':[100,50,2000]})
        result=wheat_measures(data)
        self.assertEqual(result.loc[2000,'yield_kg_ha'],2000)
        data.loc[2,'value']=2
        with self.assertRaises(ValueError): wheat_measures(data)

    def test_future_outcomes_never_enter_test(self):
        years=np.arange(1991,2027)
        rng=np.random.default_rng(1)
        rain=pd.Series(rng.normal(size=len(years)),index=years)
        outcome=2*rain+pd.Series(rng.normal(size=len(years)),index=years)
        first=evaluate_pair(rain,outcome,1991,2026,np.random.default_rng(3),n_perm=50)
        outcome.loc[2024:]=1e9
        second=evaluate_pair(rain,outcome,1991,2026,np.random.default_rng(3),n_perm=50)
        self.assertEqual(first,second)
        self.assertEqual(first['n'],33)

    def test_duplicate_and_missing_months(self):
        with tempfile.TemporaryDirectory() as directory:
            data=pd.DataFrame({'year':[2000]*3+[2001]*9,'month':[10,11,12]+list(range(1,10)),'precip_mm':[1.0]*12})
            target=Path(directory)/'rain_cckp_monthly.csv'
            data.loc[0,'precip_mm']=np.nan
            data.to_csv(target,index=False)
            with patch.object(analyze,'DATA',Path(directory)):
                self.assertEqual(len(analyze.load_rain_years()),0)
                pd.concat([data,data.iloc[:1]]).to_csv(target,index=False)
                with self.assertRaises(ValueError): analyze.load_rain_years()

    def test_water_schema_and_unknown_gaps(self):
        rows=[{'Survey_Date':'2026-01-01T00:00:00','Kinneret_Level':-212,'_id':1}, {'Survey_Date':'2026-01-03T00:00:00','Kinneret_Level':-211.9,'_id':2}]
        result=normalize_kinneret(rows,'2026-01-04T00:00:00Z')
        self.assertEqual(len(result),2)
        self.assertTrue(result.publication_date.isna().all())
        with self.assertRaises(ValueError): normalize_kinneret(rows+rows[:1],'2026-01-04T00:00:00Z')

    def test_missing_test_counts_in_family(self):
        self.assertAlmostEqual(bh([.01,np.nan])[0],.02)

    def test_formal_interaction_detects_changed_slope(self):
        years=np.arange(1961,2024)
        rng=np.random.default_rng(1)
        rain=pd.Series(rng.normal(size=len(years)),index=years)
        outcome=rain*np.where(years<=1990,1,4)+pd.Series(rng.normal(0,.1,len(years)),index=years)
        result=interaction(rain,outcome)
        self.assertLess(result['p_hac'],.001)
        self.assertAlmostEqual(result['coefficient_difference'],3,delta=.1)

if __name__=='__main__': unittest.main()

class CalendarHacTests(unittest.TestCase):
    def test_long_calendar_gaps_never_treated_as_adjacent_years(self):
        from irrigation_sensitivity import calendar_hac
        rng=np.random.default_rng(44)
        design=np.column_stack([np.ones(20),rng.normal(size=20)])
        values=rng.normal(size=20)
        _,zero,_=calendar_hac(design,values,np.arange(20)*10,maxlags=0)
        _,three,_=calendar_hac(design,values,np.arange(20)*10,maxlags=3)
        np.testing.assert_allclose(zero,three)
