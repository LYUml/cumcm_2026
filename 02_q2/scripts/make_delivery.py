"""Create corrected comparison files, required-date tables, and paper figures."""
from pathlib import Path
import json
import shutil
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'02_q2/src'))
from plot_utils import setup_style, save_fig, PALETTE, COLORS, _lighten
setup_style()
import matplotlib.pyplot as plt

OUT=ROOT/'02_q2/outputs'
from q2_model import read_inputs
dates=pd.to_datetime(pd.read_csv(OUT/'selected_daily.csv').date)
daily=pd.read_csv(OUT/'selected_daily.csv'); natural=pd.read_csv(OUT/'natural_day_storage.csv')
z=np.load(OUT/'selected_policy_numeric_trace.npz'); grid=z['grid']; trace=z['trace']
_,load,pv,_=read_inputs(ROOT); net=load-pv
old=pd.read_csv(ROOT/'02_q2/src/data/legacy_comparison_strict4h_fine.csv')
models=pd.read_csv(OUT/'model_comparison/comparison.csv')
v=json.loads((OUT/'validation.json').read_text())
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

# Figure 1: native 6.0 in width maps to the landscape 0.85-textwidth class.
# The upper panel preserves the absolute zero-based cost composition; the lower
# panel exposes the small chronology correction without truncating a bar axis.
legacy_plan=float(old.iloc[0].planned_yuan); legacy_emg=float(old.iloc[0].emergency_yuan)
new_plan=float(v['planned_yuan']); new_emg=float(v['emergency_yuan'])
fig,(a,b)=plt.subplots(2,1,figsize=(6.0,4.2),layout='constrained',
                       gridspec_kw={'height_ratios':[1.45,1.0]})
labels=['Legacy implementation','Strict midnight availability']; y=np.arange(2)
plan=np.array([legacy_plan,new_plan])/1e6; emg=np.array([legacy_emg,new_emg])/1e6
a.barh(y,plan,height=.58,color=_lighten(PALETTE[0],.40),edgecolor=PALETTE[0],lw=.9,label='Day-ahead')
a.barh(y,emg,left=plan,height=.58,color=_lighten(PALETTE[1],.38),edgecolor=PALETTE[1],lw=.9,label='Emergency')
a.set(yticks=y,yticklabels=labels,xlabel='Realized expenditure (million CNY)',xlim=(0,14.9))
a.invert_yaxis(); a.grid(axis='x',color=COLORS['grid'],lw=.7,alpha=.7); a.set_axisbelow(True)
a.legend(frameon=False,ncol=2,loc='lower right')
for k,total in enumerate(plan+emg):
 a.text(total+.07,k,f'{total:.4f}',va='center',ha='left',fontsize=8.5,fontweight='bold',color=COLORS['text'])

deltas=np.array([new_plan-legacy_plan,new_emg-legacy_emg,(new_plan+new_emg)-(legacy_plan+legacy_emg)])/1000
names=['Day-ahead','Emergency','Total']; yy=np.arange(3)
b.axvline(0,color=COLORS['ref_line'],lw=.9,zorder=1)
for k,(name,val) in enumerate(zip(names,deltas)):
 color=PALETTE[2] if k<2 else PALETTE[1]
 b.plot([0,val],[k,k],color=_lighten(color,.12),lw=3.0,solid_capstyle='round',zorder=2)
 b.scatter(val,k,s=58,color=color,edgecolor='white',lw=1.0,zorder=3)
 offset=.02*max(1.,float(np.max(np.abs(deltas))))
 b.text(val+(offset if val>=0 else -offset),k,f'{val:+,.2f}',va='center',
        ha=('left' if val>=0 else 'right'),fontsize=8.5,color=color,fontweight='bold')
xpad=max(2.,float(np.max(np.abs(deltas)))*.20)
b.set(yticks=yy,yticklabels=names,xlabel='Correction increment (thousand CNY)',
      xlim=(min(-.25,float(deltas.min())-xpad),float(deltas.max())+xpad))
b.invert_yaxis(); b.grid(axis='x',color=COLORS['grid'],lw=.7,alpha=.7); b.set_axisbelow(True)
for ext in ('png','pdf'): save_fig(fig,OUT/f'q2_cost_chronology.{ext}')
plt.close(fig)

# Figure 2: full policy comparison under the identical corrected chronology.
ordered=models.sort_values('total_yuan',ascending=True).reset_index(drop=True)
fig,a=plt.subplots(figsize=(6.0,3.9),layout='constrained')
y=np.arange(len(ordered)); plan=ordered.planned_yuan.to_numpy()/1e6
emg=ordered.emergency_yuan.to_numpy()/1e6
edge=[PALETTE[1] if bool(x) else PALETTE[0] for x in ordered.selected]
a.barh(y,plan,height=.62,color=_lighten(PALETTE[0],.42),edgecolor=edge,lw=1.0,label='Day-ahead')
a.barh(y,emg,left=plan,height=.62,color=_lighten(PALETTE[1],.36),edgecolor=edge,lw=1.0,label='Emergency')
a.set(yticks=y,yticklabels=ordered.policy,xlabel='Realized expenditure (million CNY)',xlim=(0,16.15))
a.invert_yaxis(); a.grid(axis='x',color=COLORS['grid'],lw=.65,alpha=.7); a.set_axisbelow(True)
a.legend(frameon=False,ncol=2,loc='lower center',bbox_to_anchor=(.5,1.01))
for k,total in enumerate(plan+emg):
 a.text(total+.07,k,f'{total:.3f}',va='center',fontsize=8,
        fontweight=('bold' if bool(ordered.selected.iloc[k]) else 'normal'),color=COLORS['text'])
for ext in ('png','pdf'): save_fig(fig,OUT/f'q2_model_comparison.{ext}')
plt.close(fig)

i=int((daily.total_yuan-daily.total_yuan.median()).abs().idxmin()); day=dates.iloc[i]
hours=(np.arange(144)+1)/6
# Figure 2: near-square 5.0 in native width maps to 0.70 textwidth with ~0.91 scaling.
fig,(a,b,c)=plt.subplots(3,1,figsize=(5.0,5.2),sharex=True,layout='constrained',
                         gridspec_kw={'height_ratios':[1.45,.85,1.05]})
a.step(hours,net[i+31]/1000,where='post',color=COLORS['text'],lw=1.15,label='Actual net load')
a.step(hours,grid[i]*6/1000,where='post',color=PALETTE[0],lw=1.45,label='Committed purchase')
a.fill_between(hours,0,trace[i,:,4]*6/1000,step='post',color=_lighten(PALETTE[1],.30),
               edgecolor=PALETTE[1],lw=.6,alpha=.72,label='Emergency')
a.set_ylabel('Power (MW)'); a.legend(frameon=False,ncol=3,fontsize=7.2,loc='upper center')
a.grid(axis='y',color=COLORS['grid'],lw=.65,alpha=.7); a.set_axisbelow(True)

charge=-trace[i,:,2]*6/1000; discharge=trace[i,:,3]*6/1000
b.fill_between(hours,0,discharge,step='post',color=_lighten(PALETTE[2],.30),
               edgecolor=PALETTE[2],lw=.55,label='Discharge')
b.fill_between(hours,0,charge,step='post',color=_lighten(PALETTE[4],.30),
               edgecolor=PALETTE[4],lw=.55,label='Charge')
b.axhline(0,color=COLORS['ref_line'],lw=.7)
b.set_ylabel('Battery\n(MW)'); b.legend(frameon=False,ncol=2,fontsize=7.2,loc='lower left')
b.grid(axis='y',color=COLORS['grid'],lw=.65,alpha=.7); b.set_axisbelow(True)

state_x=np.r_[hours[0],(np.arange(144)+2)/6]
c.plot(state_x,np.r_[trace[i,0,0],trace[i,:,1]]/1000,color=PALETTE[0],lw=1.55)
c.fill_between(state_x,1.2,np.r_[trace[i,0,0],trace[i,:,1]]/1000,
               color=_lighten(PALETTE[0],.50),alpha=.28)
c.axhline(1.2,color=COLORS['ref_line'],ls='--',lw=.75)
c.axhline(10.8,color=COLORS['ref_line'],ls='--',lw=.75)
c.text(24.05,10.8,'10.8',ha='right',va='bottom',fontsize=7,color=COLORS['text'])
c.text(24.05,1.2,'1.2',ha='right',va='bottom',fontsize=7,color=COLORS['text'])
c.set(xlabel='Official-template time',ylabel='Stored energy\n(MWh)',xlim=(0,24.2),ylim=(.7,11.4))
c.set_xticks(np.arange(0,25,4),[f'{h:02d}:00' for h in range(0,25,4)])
c.grid(axis='y',color=COLORS['grid'],lw=.65,alpha=.7); c.set_axisbelow(True)
for ext in ('png','pdf'): save_fig(fig,OUT/f'q2_representative_day_corrected.{ext}')
plt.close(fig)
