"""Export real figure inputs without rerunning or modifying either optimizer.

Use the original Q4-2 scenario functions. Extract the Q4-3 point_price function
verbatim by AST to avoid fitting unrelated ARX forecasters at module import.
Local saved NPZ is trusted; only Q4-2 date metadata needs allow_pickle=True.
"""
from _figbase import *
import ast
sys.path.insert(0,str(ROOT/'02_q2/src'))
sys.path.insert(0,str(Q4/'scripts'))
from q2_model import read_inputs, SOC_MIN, SOC_MAX
from q2_near_optimal import split_residual_scenarios
from q2_availability import slotwise_median
from run_q4_2_comparison import read_prices, chosen_history, price_scenarios
from types import SimpleNamespace

dates,load,pv,_=read_inputs(ROOT)
prices=read_prices()
fc=np.full_like(prices,np.nan)
for day in range(7,len(prices)):
    fc[day]=prices[[day-lag for lag in [7,14,21,28] if day>=lag]].mean(axis=0)
day=dates.get_loc(pd.Timestamp('2025-03-20'));i=day-31
q2=np.load(Q4/'outputs/q4_2_comparison/policy_weekday_mean_4w.npz',allow_pickle=True)
q3=np.load(Q4/'outputs/q4_3_stochastic/policy.npz')
source=Q4/'scripts/run_q4_3_stochastic.py'
tree=ast.parse(source.read_text())
function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='point_price')
data=SimpleNamespace(ISSUE_STARTS={0:0,6:35,12:71,18:107},INTERVAL_HOURS=1/6)
ns=dict(np=np,data=data,PRICE_FORECASTS={'weekday_mean_4w':fc},PRICE_MODEL='weekday_mean_4w',ACTUAL_PRICE=prices)
exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),ns)
issue_curves=np.full((4,144),np.nan)
for k,h in enumerate([0,6,12,18]):issue_curves[k,data.ISSUE_STARTS[h]:]=ns['point_price'](day,h)
hist=chosen_history(day)
out=HERE/'data';out.mkdir(exist_ok=True)
np.savez_compressed(out/'representative_day.npz',
    actual_price=prices[day],forecast_price=fc[day],issue_price=issue_curves,
    actual_net_kw=load[day]-pv[day],forecast_net_kw=load[day-7]-slotwise_median(pv,day,7),
    net_scenarios_kw=split_residual_scenarios(load[:day],pv[:day],day,12),
    price_scenarios=price_scenarios(prices,fc,day),
    scenario_dates=np.asarray(dates[hist].strftime('%Y-%m-%d'),dtype='U10'),
    q42_grid=q2['grid'][i],q42_trace=q2['trace'][i],
    q43_plan=q3['plan'][i],q43_final=q3['adjusted'][i],
    q43_charge=q3['charge'][i],q43_discharge=q3['discharge'][i],
    q43_soc=np.r_[q3['soc_open'][i],q3['soc'][i]],
    soc_min=SOC_MIN,soc_max=SOC_MAX)
frame=pd.DataFrame({'date':dates[31:],'q42_cost_yuan':q2['rows'][:,2],
    'q42_emergency_kwh':q2['rows'][:,3], 'q43_cost_yuan':q3['total_cost'],
    'q43_emergency_kwh':q3['emergency'].sum(axis=1)})
frame['month']=frame.date.dt.strftime('%Y-%m')
monthly=frame.groupby('month').sum(numeric_only=True)
monthly.to_csv(out/'monthly_comparison.csv')
assert np.isclose(monthly.q42_cost_yuan.sum(),14653577.061809808)
assert np.isclose(monthly.q43_cost_yuan.sum(),14146342.349102983)
pd.DataFrame({'hour':TIME,'actual_price':prices[day],**{f'price_issue_{h:02}':issue_curves[k] for k,h in enumerate([0,6,12,18])}}).to_csv(out/'issue_price_forecasts.csv',index=False)
print(monthly)
print('Scenario dates:',dates[hist].strftime('%Y-%m-%d').tolist())
print('Real representative-day ranges:',{k:(float(np.nanmin(v)),float(np.nanmax(v))) for k,v in np.load(out/'representative_day.npz').items() if np.issubdtype(v.dtype,np.number)})
