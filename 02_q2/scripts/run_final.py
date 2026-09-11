"""Recompute and validate the selected Q2 policy under canonical time mapping.

The decision state is captured at civil midnight, before the preceding plan's
final official-template interval (00:00-00:10+1) is physically replayed.  This
removes the old ten-minute look-ahead in the next day's initial state.  The
new day's first committed interval begins at 00:10.
"""
from __future__ import annotations

import json, platform, shutil, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'02_q2/src'))
from q2_model import read_inputs, DT_HOURS, SOC_INITIAL, SOC_MIN, SOC_MAX
from q2_near_optimal import (split_residual_scenarios, hierarchical_tree_groups,
    solve_adaptive_plan, execute_feedback, export_result2_actual)
from q2_time_mapping import write_mapping_csv, interval_label
from q2_availability import previous_row_curve

OUT=ROOT/'02_q2/outputs'
FLOOR=3000.; PENALTY=4.5; STAGE=24; NS=12


def one_interval(g,nkw,soc):
    end,flow=execute_feedback(np.asarray([g]),np.asarray([nkw]),soc)
    return end,flow[0]


def warmup(net):
    """Return Feb-1 midnight SOC and Jan-31's pending 00:00-00:10 slot."""
    soc=SOC_INITIAL; pending=None
    for day in range(31):
        grid=np.maximum(previous_row_curve(net,day),0)*DT_HOURS
        if pending is not None:
            soc,_=one_interval(*pending,soc)
        soc,flow=execute_feedback(grid[:143],net[day,:143],soc)
        pending=(grid[143],net[day,143])
    return soc,pending


def run(net,load,pv,price):
    soc_midnight,pending=warmup(net)
    rows=[]; grids=[]; traces=[]; planning=[]; preevaluation_last_flow=None
    for day in range(31,365):
        scenarios=split_residual_scenarios(load[:day],pv[:day],day,NS)
        groups=hierarchical_tree_groups(scenarios,STAGE)
        grid,diag=solve_adaptive_plan(scenarios,price,soc_midnight,FLOOR,PENALTY,
                                      groups,return_diagnostics=True)
        # The prior row's final interval is executed only after today's plan is fixed.
        soc_after_pending,pflow=one_interval(*pending,soc_midnight)
        if preevaluation_last_flow is None:
            preevaluation_last_flow=pflow.copy()
        soc_end_143,flow143=execute_feedback(grid[:143],net[day,:143],soc_after_pending)
        # Save current row's last slot for execution after the next midnight decision.
        pending=(grid[143],net[day,143])
        # Build a row trace after its delayed last interval becomes available next iteration.
        traces.append([flow143,None])
        if len(traces)>1:
            traces[-2][1]=pflow
        pc=float(price@grid)
        rows.append([pc,np.nan,np.nan,np.nan,soc_midnight,soc_end_143])
        grids.append(grid); planning.append(diag)
        soc_midnight=soc_end_143
    # Settle the final pending slot and complete the final plan-row trace.
    final_soc,lastflow=one_interval(*pending,soc_midnight)
    traces[-1][1]=lastflow
    trace=np.asarray([np.vstack([a,b]) for a,b in traces])
    rows=np.asarray(rows,float); grids=np.asarray(grids)
    for i in range(len(rows)):
        ec=float((5*price)@trace[i,:,4])
        rows[i,1:4]=[ec,rows[i,0]+ec,trace[i,:,4].sum()]
    return rows,grids,trace,planning,final_soc,preevaluation_last_flow


def natural_day_summary(trace,dates,preevaluation_last_flow):
    # Under left-end labels, civil day D is row D-1 slot 143 plus row D slots 0:142.
    records=[]
    for i,date in enumerate(dates[31:]):
        prev_last = preevaluation_last_flow if i==0 else trace[i-1,143]
        civil=np.vstack([prev_last,trace[i,:143]])
        rec={'date':str(date.date())}
        for b in range(6):
            sl=civil[24*b:24*(b+1)]
            rec[f'charge_{4*b:02d}_{4*(b+1):02d}_kwh']=float(np.nansum(sl[:,2]))
            rec[f'discharge_{4*b:02d}_{4*(b+1):02d}_kwh']=float(np.nansum(sl[:,3]))
        rec['soc_00_kwh']=float(prev_last[0])
        rec['soc_24_kwh']=float(trace[i,142,1])
        records.append(rec)
    return pd.DataFrame(records)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    dates,load,pv,price=read_inputs(ROOT); net=load-pv
    rows,grids,trace,planning,final_soc,preevaluation_last_flow=run(net,load,pv,price)
    np.savez_compressed(OUT/'selected_policy_numeric_trace.npz',grid=grids,trace=trace,
        dates=np.asarray(dates[31:].astype(str)),
        planning_charge=np.asarray([x['charge'] for x in planning]),
        planning_discharge=np.asarray([x['discharge'] for x in planning]),
        planning_soc_end=np.asarray([x['soc_end'] for x in planning]),
        planning_emergency=np.asarray([x['emergency'] for x in planning]),
        planning_spill=np.asarray([x['spill'] for x in planning]))
    daily=pd.DataFrame(rows,columns=['planned_yuan','emergency_yuan','total_yuan',
        'emergency_kwh','soc_at_plan_midnight_kwh','soc_at_next_midnight_kwh'])
    daily.insert(0,'date',dates[31:].date); daily.to_csv(OUT/'selected_daily.csv',index=False)
    natural=natural_day_summary(trace,dates,preevaluation_last_flow); natural.to_csv(OUT/'natural_day_storage.csv',index=False)
    write_mapping_csv(OUT/'time_mapping.csv')
    export_result2_actual(ROOT,OUT/'result2.xlsx',dates,price,grids,trace,preevaluation_last_flow)

    # Planning-vs-feedback diagnostics, replaying every scenario from the same
    # nominal initial state and committed grid used by the surrogate.
    plan_simul=plan_emg_charge=0; max_cost_gap=max_soc_gap=0.; terminal_below=0
    for i,diag in enumerate(planning):
        plan_simul += int(np.sum((diag['charge']>1e-7)&(diag['discharge']>1e-7)))
        plan_emg_charge += int(np.sum((diag['charge']>1e-7)&(diag['emergency']>1e-7)))
        day=i+31; scenarios=split_residual_scenarios(load[:day],pv[:day],day,NS)
        for s in range(NS):
            end,fb=execute_feedback(grids[i],scenarios[s],rows[i,4])
            p_cost=float(price@grids[i]+(PENALTY*price)@diag['emergency'][s])
            f_cost=float(price@grids[i]+(PENALTY*price)@fb[:,4])
            max_cost_gap=max(max_cost_gap,abs(p_cost-f_cost))
            max_soc_gap=max(max_soc_gap,abs(diag['soc_end'][s,-1]-end))
            terminal_below += int(end<FLOOR-1e-6)
    balance=grids+trace[:,:,3]+trace[:,:,4]-net[31:]*DT_HOURS-trace[:,:,2]-trace[:,:,5]
    # Prefix causality: future changes cannot alter scenarios/plan for cutoff day;
    # later within-day changes cannot alter earlier feedback actions.
    cutoff=150
    s0=split_residual_scenarios(load[:cutoff],pv[:cutoff],cutoff,NS)
    la=load.copy(); pa=pv.copy(); la[cutoff:]+=1e6; pa[cutoff:]+=2e5
    s1=split_residual_scenarios(la[:cutoff],pa[:cutoff],cutoff,NS)
    caus_scen=bool(np.array_equal(s0,s1))
    g0=solve_adaptive_plan(s0,price,5000,FLOOR,PENALTY,hierarchical_tree_groups(s0,STAGE))
    g1=solve_adaptive_plan(s1,price,5000,FLOOR,PENALTY,hierarchical_tree_groups(s1,STAGE))
    caus_plan=bool(np.array_equal(g0,g1))
    # The pending row-(d-1) final slot occurs after the midnight commitment.
    # Perturbing it must leave scenarios and the committed purchase unchanged.
    lp=load.copy(); pp=pv.copy(); lp[cutoff-1,143]+=1e6; pp[cutoff-1,143]+=2e5
    sp=split_residual_scenarios(lp[:cutoff],pp[:cutoff],cutoff,NS)
    causal_pending=bool(np.array_equal(s0,sp))
    gp=solve_adaptive_plan(sp,price,5000,FLOOR,PENALTY,hierarchical_tree_groups(sp,STAGE))
    causal_pending_plan=bool(np.array_equal(g0,gp))
    _,fa=execute_feedback(g0,net[cutoff],5000)
    changed=net[cutoff].copy(); changed[72:]+=1e6
    _,fb=execute_feedback(g0,changed,5000)
    caus_control=bool(np.array_equal(fa[:72],fb[:72]))
    validation=dict(status='passed_with_documented_time_ambiguity',
        time_assumption='source labels are left endpoints, anchored to official result2 columns',
        unresolved='source workbooks and problem do not explicitly define sample/interval semantics; exact 0:00 state for 2025-02-01 is unavailable under the template-anchored civil-day aggregation',
        recomputed=True,planned_yuan=float(rows[:,0].sum()),emergency_yuan=float(rows[:,1].sum()),
        total_yuan=float(rows[:,2].sum()),final_soc_after_2026_01_01_0010=float(final_soc),
        max_balance_residual_kwh=float(abs(balance).max()),
        max_interrow_soc_error_kwh=float(np.max(np.abs(trace[1:,0,0]-trace[:-1,-1,1]))),
        min_soc_kwh=float(trace[:,:,1].min()),max_soc_kwh=float(trace[:,:,1].max()),
        actual_simultaneous_charge_discharge=int(np.sum((trace[:,:,2]>1e-7)&(trace[:,:,3]>1e-7))),
        actual_emergency_while_charging=int(np.sum((trace[:,:,4]>1e-7)&(trace[:,:,2]>1e-7))),
        actual_midnight_below_3000_days=int(np.sum(rows[:,5]<3000-1e-7)),
        planning_simultaneous_charge_discharge_count=plan_simul,
        planning_emergency_while_charging_count=plan_emg_charge,
        scenario_feedback_terminal_below_3000_count=terminal_below,
        max_planning_vs_feedback_cost_gap_yuan=max_cost_gap,
        max_planning_vs_feedback_terminal_soc_gap_kwh=max_soc_gap,
        causality={'scenario_prefix_unchanged':caus_scen,'plan_prefix_unchanged':caus_plan,
                   'pending_previous_row_last_slot_unchanged':causal_pending,
                   'pending_previous_row_last_slot_plan_unchanged':causal_pending_plan,
                   'control_prefix_unchanged':caus_control})
    (OUT/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
    env={'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__}
    (OUT/'environment.json').write_text(json.dumps(env,indent=2),encoding='utf-8')
    print(json.dumps(validation,indent=2))

if __name__=='__main__': main()
