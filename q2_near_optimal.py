"""Exploratory near-optimal Q2 policy with adaptive battery recourse.

At 00:00 only grid purchases are committed. Battery actions, curtailment, and
emergency purchases are scenario-dependent recourse decisions. Actual execution
uses only the current measured net load and SOC; emergency power never charges
the battery. SOC is carried continuously from Feb 1 through Dec 31.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

_Q2_DIR = Path(__file__).resolve().parent / "02_q2"
sys.path.insert(0, str(_Q2_DIR))
from q2_model import (
    DT_HOURS, ENERGY_MAX, ETA_CHARGE, ETA_DISCHARGE,
    SOC_INITIAL, SOC_MAX, SOC_MIN, historical_residual_scenarios, read_inputs,
    load_workbook,
)


def split_residual_scenarios(load, pv, day, count=12):
    """Causal cycle/trend baseline plus coherent historical whole-day errors."""
    def baseline(j):
        # Weekly load cycle; robust recent PV level/trend. All indices are < j.
        return load[j-7] - np.median(pv[j-7:j],axis=0)
    candidates=np.arange(max(7,day-56),day)
    matching=candidates[(day-candidates)%7==0]
    remaining=candidates[~np.isin(candidates,matching)][::-1]
    chosen=np.concatenate([matching[::-1],remaining])[:count]
    current=baseline(day)
    residuals=np.asarray([load[j]-pv[j]-baseline(j) for j in chosen])
    return current[None,:]+residuals


def solve_adaptive_plan(scenarios_kw, price, initial_soc, terminal_floor, planning_penalty=5.0):
    """Two-stage LP with common grid plan and scenario-adaptive battery recourse."""
    scenarios = np.asarray(scenarios_kw, float)
    ns, nt = scenarios.shape
    # common grid; then c,d,soc,emergency,spill for every scenario
    g0 = 0
    c0 = nt
    d0 = c0 + ns * nt
    s0 = d0 + ns * nt
    e0 = s0 + ns * nt
    w0 = e0 + ns * nt
    nv = w0 + ns * nt
    obj = np.zeros(nv)
    obj[g0:c0] = price
    for k in range(ns):
        obj[c0+k*nt:c0+(k+1)*nt] = 1e-4/ns
        obj[d0+k*nt:d0+(k+1)*nt] = 1e-4/ns
        obj[e0+k*nt:e0+(k+1)*nt] = planning_penalty*price/ns

    aeq = lil_matrix((2*ns*nt, nv))
    beq = np.zeros(2*ns*nt)
    for k in range(ns):
        for t in range(nt):
            r = k*nt+t
            aeq[r,g0+t] = 1
            aeq[r,c0+k*nt+t] = -1
            aeq[r,d0+k*nt+t] = 1
            aeq[r,e0+k*nt+t] = 1
            aeq[r,w0+k*nt+t] = -1
            beq[r] = scenarios[k,t]*DT_HOURS
            r = ns*nt+k*nt+t
            aeq[r,s0+k*nt+t] = 1
            aeq[r,c0+k*nt+t] = -ETA_CHARGE
            aeq[r,d0+k*nt+t] = 1/ETA_DISCHARGE
            if t:
                aeq[r,s0+k*nt+t-1] = -1
            else:
                beq[r] = initial_soc
    bounds = (
        [(0,None)]*nt +
        [(0,ENERGY_MAX)]*(ns*nt) +
        [(0,ENERGY_MAX)]*(ns*nt) +
        [(SOC_MIN,SOC_MAX)]*(ns*nt) +
        [(0,None)]*(ns*nt) +
        [(0,None)]*(ns*nt)
    )
    # Terminal storage floor for every scenario.
    aub = lil_matrix((ns,nv)); bub = np.full(ns,-terminal_floor)
    for k in range(ns):
        aub[k,s0+(k+1)*nt-1] = -1
    res=linprog(obj,A_ub=aub.tocsr(),b_ub=bub,A_eq=aeq.tocsr(),b_eq=beq,
                bounds=bounds,method='highs')
    if not res.success:
        raise RuntimeError(res.message)
    return res.x[g0:c0]


def execute_feedback(grid, actual_net_kw, initial_soc):
    """Causal physical controller; current measurement only."""
    soc=initial_soc
    flow=np.zeros((144,6)) # start,end,c,d,emergency,spill
    for t,(g,nkw) in enumerate(zip(grid,actual_net_kw)):
        start=soc; margin=g-nkw*DT_HOURS
        if margin>=0:
            c=min(margin,ENERGY_MAX,(SOC_MAX-soc)/ETA_CHARGE)
            d=e=0.; w=margin-c; soc+=ETA_CHARGE*c
        else:
            need=-margin
            d=min(need,ENERGY_MAX,(soc-SOC_MIN)*ETA_DISCHARGE)
            e=need-d; c=w=0.; soc-=d/ETA_DISCHARGE
        flow[t]=start,soc,c,d,e,w
        assert abs(g+d+e-nkw*DT_HOURS-c-w)<1e-6
    return soc,flow


def causal_january_warmup(net):
    """Carry the stated Jan-1 SOC to Feb-1 without using future observations."""
    soc=SOC_INITIAL
    for day in range(31):
        # Day 1 has no prior observation; later days use only yesterday's curve.
        grid=np.maximum(net[day-1],0)*DT_HOURS if day else np.zeros(144)
        soc,_=execute_feedback(grid,net[day],soc)
    return soc


def _merge_emergency(values):
    """Merge adjacent positive 10-minute emergency intervals."""
    groups=[]; i=0
    while i<144:
        if values[i]<=1e-7:
            i+=1; continue
        j=i+1
        while j<144 and values[j]>1e-7:
            j+=1
        def stamp(slot):
            minutes=slot*10
            return f'{minutes//60}:{minutes%60:02d}' if minutes<1440 else '24:00'
        groups.append((f'{stamp(i)}-{stamp(j)}',float(values[i:j].sum())))
        i=j
    return groups


def export_result2_actual(project_root,output_path,dates,price,grids,traces):
    """Export committed grid and physically executed battery/emergency flows."""
    template=project_root/'00_problem/appendix/附件5/result2.xlsx'
    shutil.copy2(template,output_path)
    wb=load_workbook(output_path)
    ws=wb['计划购电量']
    for row,(day,grid) in enumerate(zip(range(31,365),grids),start=2):
        for col,value in enumerate(grid,start=2):
            ws.cell(row,col).value=round(float(value),6)
        ws.cell(row,146).value=round(float(grid.sum()),6)
        ws.cell(row,147).value=round(float(price@grid),6)
    wb.remove(wb['充放电量']); battery=wb.create_sheet('充放电量',1)
    battery.append(['日期','时间段','充电量','放电量','时刻','储电量'])
    blocks=['0:00-4:00','4:00-8:00','8:00-12:00','12:00-16:00','16:00-20:00','20:00-24:00']
    for day,flow in zip(range(31,365),traces):
        for b,label in enumerate(blocks):
            sl=slice(24*b,24*(b+1))
            battery.append([dates[day].to_pydatetime() if b==0 else None,label,
                round(float(flow[sl,2].sum()),6),round(float(flow[sl,3].sum()),6),
                '0:00' if b==0 else ('24:00' if b==1 else None),
                round(float(flow[0,0] if b==0 else flow[-1,1]),6) if b<2 else None])
    wb.remove(wb['紧急购电量']); emergency=wb.create_sheet('紧急购电量',2)
    emergency.append(['日期','购电时间段','购电量'])
    for day,flow in zip(range(31,365),traces):
        groups=_merge_emergency(flow[:,4])
        if not groups:
            emergency.append([dates[day].to_pydatetime(),None,0.0])
        for k,(label,amount) in enumerate(groups):
            emergency.append([dates[day].to_pydatetime() if k==0 else None,label,round(amount,6)])
    wb.save(output_path)


def run_policy(net, price, terminal_floor, planning_penalty, scenario_count=12,
               load=None, pv=None, scenario_mode='recent', initial_soc=SOC_INITIAL):
    soc=initial_soc; rows=[]; grids=[]; traces=[]
    for day in range(31,365):
        scenarios=(
            split_residual_scenarios(load[:day],pv[:day],day,scenario_count)
            if scenario_mode=='split' else
            historical_residual_scenarios(net[:day],day,scenario_count)
        )
        grid=solve_adaptive_plan(scenarios,price,soc,terminal_floor,planning_penalty)
        start=soc; soc,flow=execute_feedback(grid,net[day],soc)
        pc=float(price@grid); ec=float((5*price)@flow[:,4])
        rows.append((pc,ec,pc+ec,flow[:,4].sum(),start,soc))
        grids.append(grid); traces.append(flow)
    return np.asarray(rows),np.asarray(grids),np.asarray(traces)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--floor',type=float)
    parser.add_argument('--penalties',type=float,nargs='+')
    parser.add_argument('--tag',default='')
    parser.add_argument('--scenario-mode',choices=['recent','split'],default='recent')
    parser.add_argument('--initial-soc',type=float)
    args=parser.parse_args()
    project_root=Path(__file__).resolve().parent
    out=project_root/'02_q2/q2_near_optimal_outputs'; out.mkdir(exist_ok=True)
    dates,load,pv,price=read_inputs(project_root); net=load-pv
    initial_soc=(causal_january_warmup(net) if args.initial_soc is None
                 else args.initial_soc)
    # Small, interpretable policy grid. True settlement multiplier remains 5;
    # planning_penalty changes conservativeness under scenario misspecification.
    configs=(
        [(args.floor,p) for p in args.penalties]
        if args.floor is not None and args.penalties
        else [
            (1200,4.0),(1200,5.0),(1200,6.0),
            (3000,4.0),(3000,5.0),(3000,6.0),
            (6000,4.0),(6000,5.0),(6000,6.0),
        ]
    )
    suffix=f'_{args.tag}' if args.tag else ''
    summary=[]; best=None
    for floor,penalty in configs:
        tic=time.perf_counter()
        rows,grids,traces=run_policy(net,price,floor,penalty,load=load,pv=pv,
                                     scenario_mode=args.scenario_mode,initial_soc=initial_soc)
        record=dict(terminal_floor_kwh=floor,planning_penalty=penalty,
            scenario_mode=args.scenario_mode,initial_soc_kwh=initial_soc,
            planned_yuan=float(rows[:,0].sum()),emergency_yuan=float(rows[:,1].sum()),
            total_yuan=float(rows[:,2].sum()),emergency_kwh=float(rows[:,3].sum()),
            min_soc=float(traces[:,:,1].min()),max_soc=float(traces[:,:,1].max()),
            final_soc=float(rows[-1,5]),seconds=time.perf_counter()-tic)
        summary.append(record); print(record,flush=True)
        if best is None or record['total_yuan']<best[0]['total_yuan']:
            best=(record,rows,grids,traces)
    table=pd.DataFrame(summary).sort_values('total_yuan')
    table.to_csv(out/f'comparison{suffix}.csv',index=False)
    record,rows,grids,traces=best
    np.savez_compressed(out/f'best_policy{suffix}.npz',grid=grids,trace=traces,
                        dates=np.asarray(dates[31:].astype(str)))
    max_balance=float(np.max(np.abs(
            grids+traces[:,:,3]+traces[:,:,4]-net[31:]*DT_HOURS-
            traces[:,:,2]-traces[:,:,5])))
    max_link=float(np.max(np.abs(rows[1:,4]-rows[:-1,5])))
    simultaneous=int(np.sum((traces[:,:,2]>1e-7)&(traces[:,:,3]>1e-7)))
    emergency_charge=int(np.sum((traces[:,:,4]>1e-7)&(traces[:,:,2]>1e-7)))
    checks=dict(passed=bool(max_balance<1e-6 and max_link<1e-6 and
                            simultaneous==0 and emergency_charge==0 and
                            traces[:,:,1].min()>=SOC_MIN-1e-6 and
                            traces[:,:,1].max()<=SOC_MAX+1e-6),best=record,
        max_balance_residual_kwh=max_balance,
        max_soc_link_error_kwh=max_link,
        simultaneous_charge_discharge=simultaneous,
        emergency_while_charging=emergency_charge,
        information_rule='day d scenarios use indices strictly less than d; execution uses current interval only',
        scope='exploratory in-sample policy comparison on supplied historical year')
    (out/f'validation{suffix}.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
    daily=pd.DataFrame(rows,columns=['planned_yuan','emergency_yuan','total_yuan',
        'emergency_kwh','soc_start_kwh','soc_end_kwh'])
    daily.insert(0,'date',dates[31:].date)
    daily.to_csv(out/f'best_daily{suffix}.csv',index=False)
    export_result2_actual(project_root,out/f'result2{suffix}.xlsx',dates,price,grids,traces)
    print('\nBEST',json.dumps(record,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
