"""Frozen historical screen and wheat area/yield follow-up, all exploratory.

Future crop years stay outside all fits. HAC uncertainty allows 3 lags; block
permutation preserves within-block order but does not prove independence.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm

from analyze import DATA, load_rain_years

HERE = Path(__file__).resolve().parent
RESULTS = HERE / 'results'
PLAN = json.loads((HERE / 'analysis_plan.json').read_text())


def bh(pvals):
    p = np.asarray(pvals, dtype=float)
    p = np.where(np.isfinite(p), p, 1.0)
    order = np.argsort(p)
    result = np.empty(len(p))
    result[order] = np.minimum.accumulate((p[order]*len(p)/np.arange(1,len(p)+1))[::-1])[::-1]
    return np.minimum(1, result)


def wheat_measures(measures):
    w = measures[measures.crop.eq('Wheat')].copy()
    output = {}
    for code, name in [(5510,'production_tonnes'),(5312,'area_harvested_ha'),(5412,'yield_kg_ha')]:
        part = w[w.element_code.isin([5412,5419]) if code == 5412 else w.element_code.eq(code)].set_index('year')
        if part.index.duplicated().any():
            raise ValueError('Duplicate FAOSTAT measure year; inspect current/legacy elements')
        if part.empty:
            output[name] = pd.Series(dtype=float)
            continue
        if code == 5412:
            # Current QCL element 5412 is kg/ha; old 5419 used hg/ha.
            factors = {'kg/ha':1.0, 'hg/ha':0.1, '100 g/ha':0.1, 't/ha':1000.0}
            scale = part.unit.map(factors)
            if scale.isna().any():
                raise ValueError('Unknown yield unit')
            output[name] = part.value * scale
        else:
            output[name] = part.value
    out = pd.DataFrame(output).sort_index()
    out['yield_from_production_area_kg_ha'] = (out.production_tonnes*1000/out.area_harvested_ha).where(out.area_harvested_ha > 0)
    comparable = out[['yield_kg_ha','yield_from_production_area_kg_ha']].dropna()
    relative = abs(comparable.yield_kg_ha/comparable.yield_from_production_area_kg_ha - 1)
    if relative.gt(.05).any():
        raise ValueError('FAOSTAT yield unit or production/area identity inconsistent (>5%)')
    out['reported_yield_relative_identity_error'] = relative
    return out


def test_pair(rain, outcome, lo, hi, rng, n_perm=20000):
    frame = pd.concat([rain.rename('rain'),outcome.rename('outcome')],axis=1).dropna()
    frame = frame.loc[(frame.index >= lo)&(frame.index <= min(hi,PLAN['historical_end']))]
    n = len(frame)
    result = {'start':lo,'end':hi,'n':n,'status':'exploratory historical','r':np.nan,
              'p_partial_time':np.nan,'p_hac':np.nan,'p_block3':np.nan,
              'rain_coefficient':np.nan,'hac_ci_low':np.nan,'hac_ci_high':np.nan}
    if n < 10 or frame.rain.std() == 0 or frame.outcome.std() == 0:
        result['status'] = 'insufficient observations'
        return result
    years = frame.index.to_numpy(dtype=float)
    years = years-years.mean()
    x,y = frame.rain.to_numpy(),frame.outcome.to_numpy()
    rd = x-np.polyval(np.polyfit(years,x,1),years)
    yd = y-np.polyval(np.polyfit(years,y,1),years)
    r = float(stats.pearsonr(rd,yd).statistic)
    t = r*np.sqrt((n-3)/max(1e-15,1-r*r))
    model = sm.OLS(y,np.column_stack([np.ones(n),years,x])).fit(cov_type='HAC',cov_kwds={'maxlags':3},use_t=True)
    low,high = model.conf_int()[2]
    result.update(r=r,p_partial_time=float(2*stats.t.sf(abs(t),n-3)),
                  p_hac=float(model.pvalues[2]),rain_coefficient=float(model.params[2]),
                  hac_ci_low=float(low),hac_ci_high=float(high))
    # Never bridge missing years in a time-dependence sensitivity.
    if np.all(np.diff(frame.index.to_numpy()) == 1):
        blocks = [rd[i:i+3] for i in range(0,n,3)]
        norm = np.linalg.norm(rd)*np.linalg.norm(yd)
        extreme = 0
        for _ in range(n_perm):
            shuffled = np.concatenate([blocks[i] for i in rng.permutation(len(blocks))])
            extreme += abs(float(shuffled@yd/norm)) >= abs(r)
        result['p_block3'] = (extreme+1)/(n_perm+1)
    else:
        result['block_status'] = 'not computed: non-contiguous annual observations'
    return result


def interaction(rain, outcome):
    frame = pd.concat([rain.rename('rain'),outcome.rename('outcome')],axis=1).dropna()
    frame = frame.loc[(frame.index>=1961)&(frame.index<=PLAN['historical_end'])]
    out = {'n':len(frame),'rain':'total_mm','start':1961,'end':PLAN['historical_end'],
           'status':'exploratory era interaction, not irrigation attribution','p_hac':np.nan,
           'coefficient_difference':np.nan,'hac_ci_low':np.nan,'hac_ci_high':np.nan}
    if len(frame)<20 or min(sum(frame.index<=1990),sum(frame.index>1990))<10:
        return out
    t = frame.index.to_numpy(dtype=float)-1990
    post = (frame.index>1990).astype(float)
    rain = frame.rain.to_numpy()
    # Separate era intercept/trends and an explicit difference in rain slope.
    design=np.column_stack([np.ones(len(frame)),t,post,t*post,rain,rain*post])
    fit=sm.OLS(frame.outcome.to_numpy(),design).fit(cov_type='HAC',cov_kwds={'maxlags':3},use_t=True)
    low,high=fit.conf_int()[5]
    out.update(p_hac=float(fit.pvalues[5]),coefficient_difference=float(fit.params[5]),hac_ci_low=float(low),hac_ci_high=float(high))
    return out


def main():
    RESULTS.mkdir(exist_ok=True)
    rain=load_rain_years()
    crops=pd.read_csv(DATA/'faostat_crops.csv')
    outcomes={name:part.set_index('year').production_tonnes for name,part in crops.groupby('crop')}
    outcomes['cereal yield']=pd.read_csv(DATA/'wb_cereal_yield.csv').set_index('year').cereal_yield_kg_ha
    rng=np.random.default_rng(PLAN['uncertainty']['seed'])
    original=[]
    for name in PLAN['exploratory_original_family']['outcomes']:
        for lo,hi in PLAN['exploratory_original_family']['eras']:
            for measure in PLAN['exploratory_original_family']['rain']:
                result=test_pair(rain[measure],outcomes.get(name,pd.Series(dtype=float)),lo,hi,rng)
                original.append({'outcome':name,'rain':measure,**result})
    original=pd.DataFrame(original)
    assert len(original)==54
    for method in ['partial_time','hac','block3']:
        original['q_'+method]=bh(original['p_'+method])
    original.to_csv(RESULTS/'crop_rain_54.csv',index=False)

    wheat=wheat_measures(pd.read_csv(DATA/'faostat_crop_measures.csv'))
    # Extended future years remain visible as observations, never enter fitting.
    wheat['analysis_partition']=np.where(wheat.index<=2023,'exploratory historical',
                                  np.where(wheat.index>=PLAN['holdout_start'],'reserved holdout','previously seen crop year; excluded'))
    wheat.to_csv(RESULTS/'wheat_measure_identity.csv',index_label='year')
    rows,interactions=[],[]
    for outcome in PLAN['wheat_followup_family']['outcomes']:
        for lo,hi in PLAN['wheat_followup_family']['eras']:
            for measure in PLAN['wheat_followup_family']['rain']:
                result=test_pair(rain[measure],wheat[outcome],lo,hi,rng)
                rows.append({'outcome':outcome,'rain':measure,**result})
        interactions.append({'outcome':outcome,**interaction(rain.total_mm,wheat[outcome])})
    assert len(rows)+len(interactions)==30
    qs=bh([x['p_hac'] for x in rows+interactions])
    for row,q in zip(rows+interactions,qs): row['q_hac_family30']=float(q)
    pd.DataFrame(rows).to_csv(RESULTS/'wheat_decomposition.csv',index=False)
    pd.DataFrame(interactions).to_csv(RESULTS/'era_interaction.csv',index=False)
    # Freeze the two training fits now; holdout evaluation remains separate.
    train=rain[['total_mm']].join(wheat[['yield_kg_ha']]).dropna().loc[1961:2023]
    year=train.index.to_numpy(dtype=float)-1990
    fit=sm.OLS(train.yield_kg_ha,np.column_stack([np.ones(len(train)),year,train.total_mm])).fit()
    baseline=sm.OLS(train.yield_kg_ha,np.column_stack([np.ones(len(train)),year])).fit()
    manifest={'generated_at':datetime.now(timezone.utc).isoformat(),'status':'historical exploratory analysis; holdout not evaluated',
              'analysis_end':2023,'rain_product':'CRU TS4.08 country mean, complete Oct-Sep years',
              'holdout_start':PLAN['holdout_start'],'holdout_min_pairs':10,
              'validation_model':{'columns':['intercept','year minus 1990','total_mm'],'coefficients':list(fit.params),
                                  'year_only_coefficients':list(baseline.params)},
              'original_family':54,'followup_hac_family':30,
              'irrigation_model':'Primary historical model excludes irrigation; irrigation_sensitivity.py separately fits source-reported complete-case annual shares, with calendar-distance HAC and no interpolation',
              'limitations':['Country rain is not crop-region rain.','Yield = production / area up to source rounding; three outcomes are dependent.',
                             'Rain by era interaction tests association change, not irrigation causation.',
                             'HAC and 3-year block sensitivity do not remove all serial dependence or confounding.'],
              'input_sha256':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'analysis_plan.json',DATA/'rain_cckp_monthly.csv',DATA/'faostat_crop_measures.csv',DATA/'wb_cereal_yield.csv']}}
    (RESULTS/'crop_rain_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    frozen_model=RESULTS/'prospective_wheat_model.json'
    if not frozen_model.exists():
        frozen_model.write_text(json.dumps({'frozen_at':manifest['generated_at'],'model':manifest['validation_model'],'input_sha256':manifest['input_sha256'],'holdout_start':PLAN['holdout_start']},indent=2)+'\n')
    print(pd.DataFrame(rows).query("start == 1991 and rain == 'total_mm'").to_string(index=False))
    print(pd.DataFrame(interactions).to_string(index=False))

if __name__=='__main__': main()
