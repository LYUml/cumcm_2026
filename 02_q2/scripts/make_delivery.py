"""Create corrected comparison files, required-date tables, and paper figures."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'02_q2/src'))

OUT=ROOT/'02_q2/outputs'
dates=pd.to_datetime(pd.read_csv(OUT/'selected_daily.csv').date)
daily=pd.read_csv(OUT/'selected_daily.csv'); natural=pd.read_csv(OUT/'natural_day_storage.csv')
z=np.load(OUT/'selected_policy_numeric_trace.npz'); grid=z['grid']; trace=z['trace']
models=pd.read_csv(OUT/'model_comparison/comparison.csv')
models.to_csv(OUT/'cost_comparison.csv',index=False,encoding='utf-8-sig')

targets=['2025-03-20','2025-06-21','2025-09-23','2025-12-21']
slots=[59,71,83,95,107,119]
purchase=[]; battery=[]; emergency=[]
for ds in targets:
 i=int(np.flatnonzero(dates.astype(str).str[:10].eq(ds))[0]); d=daily.iloc[i]; n=natural.iloc[i]
 rec={'date':ds}
 for s in slots: rec[interval_label:=f'{(s+1)*10//60}:{(s+1)*10%60:02d}-{(s+2)*10//60}:{(s+2)*10%60:02d}']=grid[i,s]
 rec.update({'daily_planned_kwh':grid[i].sum(),'planned_cost_yuan':d.planned_yuan,
             'emergency_cost_yuan':d.emergency_yuan,'total_cost_yuan':d.total_yuan})
 purchase.append(rec)
 br={'date':ds,'soc_00_kwh':n.soc_00_kwh,'soc_24_kwh':n.soc_24_kwh}
 for b in range(6):
  br[f'charge_{4*b:02d}_{4*(b+1):02d}_kwh']=n[f'charge_{4*b:02d}_{4*(b+1):02d}_kwh']
  br[f'discharge_{4*b:02d}_{4*(b+1):02d}_kwh']=n[f'discharge_{4*b:02d}_{4*(b+1):02d}_kwh']
 battery.append(br)
 vals=trace[i,:,4]; j=0
 while j<144:
  if vals[j]<=1e-7: j+=1; continue
  k=j+1
  while k<144 and vals[k]>1e-7:k+=1
  def lab(s,end=False):
   m=(s+1+(1 if end else 0))*10; return f'{(m%1440)//60}:{m%60:02d}'+('+1' if m>=1440 else '')
  emergency.append({'date':ds,'interval':f'{lab(j)}-{lab(k-1,True)}','emergency_kwh':vals[j:k].sum()}); j=k
pd.DataFrame(purchase).to_csv(OUT/'specified_dates_purchase.csv',index=False)
pd.DataFrame(battery).to_csv(OUT/'specified_dates_storage.csv',index=False)
pd.DataFrame(emergency,columns=['date','interval','emergency_kwh']).to_csv(OUT/'specified_dates_emergency.csv',index=False)

from figures.make_cost_figures import make_cost_figures
make_cost_figures(OUT, ROOT/'02_q2/src/data/legacy_comparison_strict4h_fine.csv')

from figures.make_example_figure import make_example_figure
make_example_figure(OUT, ROOT)
