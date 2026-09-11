"""Create corrected comparison files, required-date tables, and paper figures."""
from pathlib import Path
import json, shutil
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import sys

ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'02_q2/outputs'
sys.path.insert(0,str(ROOT/'02_q2/src'))
from q2_model import read_inputs
dates=pd.to_datetime(pd.read_csv(OUT/'selected_daily.csv').date)
daily=pd.read_csv(OUT/'selected_daily.csv'); natural=pd.read_csv(OUT/'natural_day_storage.csv')
z=np.load(OUT/'selected_policy_numeric_trace.npz'); grid=z['grid']; trace=z['trace']
_,load,pv,_=read_inputs(ROOT); net=load-pv
old=pd.read_csv(ROOT/'02_q2/src/data/legacy_comparison_strict4h_fine.csv')
v=json.loads((OUT/'validation.json').read_text())
corrected=pd.DataFrame([{'policy':'Four-hour tree (selected; corrected chronology)',
 'terminal_floor_kwh':3000,'planning_penalty':4.5,'tree_stage_slots':24,
 'planned_yuan':v['planned_yuan'],'emergency_yuan':v['emergency_yuan'],
 'total_yuan':v['total_yuan'],'selected':True}])
legacy=old.assign(policy='Four-hour tree (legacy chronology)',selected=False)
pd.concat([corrected,legacy],ignore_index=True,sort=False).to_csv(OUT/'cost_comparison.csv',index=False)

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

plt.rcParams.update({'font.family':'DejaVu Serif','font.size':9,'pdf.fonttype':42,
 'axes.spines.top':False,'axes.spines.right':False})
blue='#214F73'; orange='#AC632E'
fig,ax=plt.subplots(figsize=(6,3.6),layout='constrained')
ax.bar(['Legacy\nchronology','Corrected\nchronology'],[old.iloc[0].total_yuan/1e6,v['total_yuan']/1e6],
 color=[blue,orange],edgecolor='white')
ax.set_ylabel('Realized expenditure (million CNY)'); ax.grid(axis='y',color='.88',lw=.6)
ax.set_title('Effect of correcting the midnight decision chronology',loc='left')
for k,y in enumerate([old.iloc[0].total_yuan/1e6,v['total_yuan']/1e6]): ax.text(k,y+0.0003,f'{y:.4f}',ha='center')
for ext in ('png','pdf'): fig.savefig(OUT/f'q2_cost_chronology.{ext}',dpi=300)
plt.close(fig)
i=int((daily.total_yuan-daily.total_yuan.median()).abs().idxmin()); day=dates.iloc[i]
hours=(np.arange(144)+1)/6
fig,(a,b)=plt.subplots(2,1,figsize=(6,4.4),sharex=True,layout='constrained',gridspec_kw={'height_ratios':[1.25,1]})
a.step(hours,grid[i]*6/1000,where='post',color=blue,lw=1.3,label='Committed purchase')
a.step(hours,net[i+31]/1000,where='post',color='.2',lw=1.0,label='Actual net load')
a.fill_between(hours,0,trace[i,:,4]*6/1000,step='post',color=orange,alpha=.55,label='Emergency purchase')
a.set_ylabel('Interval-average power (MW)'); a.legend(frameon=False,ncol=3,fontsize=7.5); a.grid(axis='y',color='.88',lw=.6)
a.set_title(f'Corrected executed schedule — {day.date()}',loc='left')
b.plot(np.r_[hours[0],(np.arange(144)+2)/6],np.r_[trace[i,0,0],trace[i,:,1]]/1000,color=blue,lw=1.4)
b.axhline(1.2,color='.45',ls='--',lw=.8); b.axhline(10.8,color='.45',ls='--',lw=.8)
b.set(xlabel='Official-template time (hours)',ylabel='Stored energy (MWh)',xlim=(0,24.2))
b.set_xticks(np.arange(0,25,4)); b.grid(axis='y',color='.88',lw=.6)
for ext in ('png','pdf'): fig.savefig(OUT/f'q2_representative_day_corrected.{ext}',dpi=300)
plt.close(fig)
