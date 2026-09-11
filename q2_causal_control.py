"""Isolated causal controller comparison. Run: python3 q2_causal_control.py.

No external forecasts, ensemble, or daily SOC reset. Within-interval balancing
assumes current load/PV are measurable; future observations are never exposed.
January uses one common warm-up policy. All outputs are exploratory backtests:
the full supplied year has already been inspected during model development.
"""
from pathlib import Path
import json
import time
import numpy as np
import pandas as pd
from q2_model import (read_inputs, solve_day_ahead_lp, solve_scenario_lp,
    historical_residual_scenarios, DT_HOURS, SOC_INITIAL, SOC_MIN, SOC_MAX,
    ENERGY_MAX, ETA_CHARGE, ETA_DISCHARGE)


def execute(grid, actual, initial):
    soc = initial
    rows = []
    for g, n in zip(grid, actual * DT_HOURS):
        start = soc
        margin = g - n
        c = min(max(margin, 0), ENERGY_MAX, (SOC_MAX-soc)/ETA_CHARGE)
        d = min(max(-margin, 0), ENERGY_MAX, (soc-SOC_MIN)*ETA_DISCHARGE)
        e = max(n-g-d, 0)
        w = max(g+d-n-c, 0)
        soc += ETA_CHARGE*c-d/ETA_DISCHARGE
        assert abs(g+d+e-n-c-w) < 1e-6
        assert SOC_MIN-1e-6 <= soc <= SOC_MAX+1e-6
        assert c*e < 1e-6 and c*d < 1e-6
        rows.append((start,soc,c,d,e,w))
    return soc, np.array(rows)


def baseline(load, pv, day, split):
    if split:
        # Different physical processes have different temporal structures.
        return load[day-7] - np.median(pv[day-7:day], axis=0)
    return load[day-7]-pv[day-7]


def forecast(load, pv, day, split, quantile):
    anchor=baseline(load,pv,day,split)
    if quantile is None:
        return anchor
    js=range(max(7,day-56),day)
    errors=np.array([load[j]-pv[j]-baseline(load,pv,j,split) for j in js])
    return anchor+np.quantile(errors,quantile,axis=0)


def main():
    root=Path(__file__).resolve().parent
    out=root/'q2_control_outputs'; out.mkdir(exist_ok=True)
    dates,load,pv,price=read_inputs(root); net=load-pv
    # Common causal warm-up from January 1. The first day has no history,
    # hence zero planned purchase; emergency supply guarantees load service.
    soc=SOC_INITIAL
    for day in range(31):
        grid=np.maximum(net[day-1],0)*DT_HOURS if day else np.zeros(144)
        soc,_=execute(grid,net[day],soc)
    feb_soc=soc
    configs=[('scenario12_feedback',False,None),
             ('net_q80_feedback',False,.8),
             ('split_q80_feedback',True,.8),
             ('split_q50_feedback',True,.5)]
    summary=[]
    for name,split,q in configs:
        started=time.perf_counter(); soc=feb_soc; daily=[]; logs=[]
        for day in range(31,365):
            initial=soc
            if name.startswith('scenario'):
                scenarios=historical_residual_scenarios(net[:day],day,12)
                plan=solve_scenario_lp(scenarios,price,soc)
            else:
                pred=forecast(load[:day],pv[:day],day,split,q)
                plan=solve_day_ahead_lp(pred,price,soc)
            soc,flows=execute(plan.grid,net[day],soc)
            pc=float(price@plan.grid); ec=float((5*price)@flows[:,4])
            daily.append(dict(date=str(dates[day].date()),planned=pc,emergency=ec,
                total=pc+ec,emergency_kwh=float(flows[:,4].sum()),soc_start=initial,soc_end=soc))
            logs.append(np.column_stack([plan.grid,net[day]*DT_HOURS,flows]))
        frame=pd.DataFrame(daily)
        assert np.max(np.abs(frame.soc_start.to_numpy()[1:]-frame.soc_end.to_numpy()[:-1]))<1e-6
        frame.to_csv(out/f'{name}_daily.csv',index=False)
        np.savez_compressed(out/f'{name}_trace.npz',trace=np.array(logs))
        summary.append(dict(method=name,planned_yuan=frame.planned.sum(),
            emergency_yuan=frame.emergency.sum(),total_yuan=frame.total.sum(),
            emergency_kwh=frame.emergency_kwh.sum(),feb_soc=feb_soc,final_soc=soc,
            seconds=time.perf_counter()-started))
        print(summary[-1],flush=True)
    pd.DataFrame(summary).sort_values('total_yuan').to_csv(out/'comparison.csv',index=False)
    # Prefix-only construction is an API boundary; perturbations test the new
    # forecast and real-time controller independently at a representative day.
    day=150
    pred=forecast(load,pv,day,True,.8)
    changed=load.copy(); changed[day:]+=1e6
    assert np.array_equal(pred,forecast(changed,pv,day,True,.8))
    grid=np.full(144,500.)
    _,a=execute(grid,net[day],6000)
    changed_net=net[day].copy(); changed_net[72:]+=1e6
    _,b=execute(grid,changed_net,6000)
    assert np.array_equal(a[:72],b[:72])
    (out/'validation.json').write_text(json.dumps(dict(passed=True,
        continuous_soc=True,no_emergency_charging=True,prefix_tests_passed=True,
        comparison_status='exploratory; previously inspected year',
        time_convention='144 chronological intervals; no official template export',
        terminal_policy='planning cyclic at actual initial SOC; actual terminal SOC free',
        trace_columns=['grid','net','soc_start','soc_end','charge','discharge','emergency','spill']),indent=2))


if __name__=='__main__':
    main()
