"""Exploratory complete-case adjustment using reported WDI irrigation shares.

Source-reported annual values may include estimates. This national all-crop
share is not wheat irrigation. Six tests: rain and irrigation coefficients for
three fixed rain measures, BH-adjusted together. No missing-year interpolation.
Calendar HAC weights calendar distance, never adjacent rows across long gaps.
"""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from analyze import DATA,load_rain_years
from crop_rain_analysis import wheat_measures,bh,RESULTS


def calendar_hac(design,values,years,maxlags=3):
    beta=np.linalg.lstsq(design,values,rcond=None)[0]
    residual=values-design@beta
    scores=design*residual[:,None]
    middle=scores.T@scores
    for i in range(len(years)):
        for j in range(i+1,len(years)):
            lag=years[j]-years[i]
            if 0 < lag <= maxlags:
                term=np.outer(scores[i],scores[j])
                middle+=(1-lag/(maxlags+1))*(term+term.T)
    inv=np.linalg.inv(design.T@design)
    cov=inv@middle@inv*len(years)/(len(years)-design.shape[1])
    stderr=np.sqrt(np.maximum(np.diag(cov),0))
    df=len(years)-design.shape[1]
    return beta,stderr,df


def main():
    source=DATA/'water_covariates_reported.csv'
    water=pd.read_csv(source)
    water=water[water.indicator.eq('AG.LND.IRIG.AG.ZS')].set_index('year').value.rename('irrigated_share_percent')
    wheat=wheat_measures(pd.read_csv(DATA/'faostat_crop_measures.csv'))
    frame=load_rain_years().join(wheat[['yield_kg_ha']]).join(water).dropna().loc[:2023]
    plan_path=RESULTS/'irrigation_sensitivity_plan.json'
    if not plan_path.exists():
        plan_path.write_text(json.dumps({'frozen_before_fit':datetime.now(timezone.utc).isoformat(),'status':'exploratory supplementary sensitivity after source availability inspected',
            'model':'wheat yield ~ intercept + year + fixed rain measure + national irrigated land share',
            'rain':['total_mm','former_mm','latter_mm'],'family_size':6,'coefficients_tested':['rain','irrigation'],
            'coverage':'reported common years through 2023 only; no interpolation','covariance':'calendar-distance HAC, maxlag=3',
            'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest()},indent=2)+'\n')
    if len(frame)<12:
        raise ValueError('Too few measured common years for irrigation sensitivity')
    rows=[]
    years=frame.index.to_numpy(dtype=float)
    for measure in ['total_mm','former_mm','latter_mm']:
        design=np.column_stack([np.ones(len(frame)),years-years.mean(),frame[measure],frame.irrigated_share_percent])
        beta,se,df=calendar_hac(design,frame.yield_kg_ha.to_numpy(),years)
        for index,label in [(2,'rain'),(3,'irrigation')]:
            critical=stats.t.ppf(.975,df)
            rows.append({'rain_measure':measure,'coefficient':label,'n':len(frame),'years':';'.join(str(int(y)) for y in years),
                         'estimate':beta[index],'ci_low':beta[index]-critical*se[index],'ci_high':beta[index]+critical*se[index],
                         'p_calendar_hac':2*stats.t.sf(abs(beta[index]/se[index]),df),
                         'status':'exploratory source-reported complete cases; no causal attribution'})
    out=pd.DataFrame(rows)
    out['q_calendar_hac_family6']=bh(out.p_calendar_hac)
    out.to_csv(RESULTS/'irrigation_sensitivity.csv',index=False)
    print(out[['rain_measure','coefficient','n','estimate','p_calendar_hac','q_calendar_hac_family6']].to_string(index=False))

if __name__=='__main__':main()
