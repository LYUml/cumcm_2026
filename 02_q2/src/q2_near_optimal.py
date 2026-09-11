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
from sklearn.cluster import KMeans

_Q2_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_Q2_DIR))
from q2_model import (
    DT_HOURS, ENERGY_MAX, ETA_CHARGE, ETA_DISCHARGE,
    SOC_INITIAL, SOC_MAX, SOC_MIN, historical_residual_scenarios, read_inputs,
    load_workbook,
)
from q2_time_mapping import four_hour_blocks, interval_label
from q2_availability import complete_residual_candidates, slotwise_median, previous_row_curve


def split_residual_scenarios(load, pv, day, count=12):
    """Midnight-causal baseline plus fully observed historical daily errors."""
    def baseline(j):
        # Historical residuals are reconstructed after row j is complete.
        return load[j-7] - np.median(pv[j-7:j],axis=0)
    # The current baseline is slot-wise: row day-1 slot 143 is still pending.
    current=load[day-7] - slotwise_median(pv,day,7)
    candidates=complete_residual_candidates(day,56)
    matching=candidates[(day-candidates)%7==0]
    remaining=candidates[~np.isin(candidates,matching)][::-1]
    chosen=np.concatenate([matching[::-1],remaining])[:count]
    residuals=np.asarray([load[j]-pv[j]-baseline(j) for j in chosen])
    return current[None,:]+residuals


def solve_adaptive_plan(scenarios_kw, price, initial_soc, terminal_floor,
                        planning_penalty=5.0, node_groups=None,
                        return_diagnostics=False):
    """Stochastic LP; optional node groups impose multistage nonanticipativity."""
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

    na_pairs=[]
    if node_groups is not None:
        node_groups=np.asarray(node_groups)
        for t in range(nt):
            for group in np.unique(node_groups[:,t]):
                members=np.flatnonzero(node_groups[:,t]==group)
                na_pairs.extend((t,int(members[0]),int(k)) for k in members[1:])
    base_rows=2*ns*nt
    aeq = lil_matrix((base_rows+2*len(na_pairs), nv))
    beq = np.zeros(base_rows+2*len(na_pairs))
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
    for q,(t,ref,k) in enumerate(na_pairs):
        r=base_rows+2*q
        aeq[r,c0+k*nt+t]=1; aeq[r,c0+ref*nt+t]=-1
        aeq[r+1,d0+k*nt+t]=1; aeq[r+1,d0+ref*nt+t]=-1
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
    grid=res.x[g0:c0]
    if not return_diagnostics:
        return grid
    return grid, dict(
        charge=res.x[c0:d0].reshape(ns,nt),
        discharge=res.x[d0:s0].reshape(ns,nt),
        soc_end=res.x[s0:e0].reshape(ns,nt),
        emergency=res.x[e0:w0].reshape(ns,nt),
        spill=res.x[w0:].reshape(ns,nt),
        surrogate_objective=float(res.fun),
    )


def hierarchical_tree_groups(scenarios, stage_slots=24):
    """Nested binary scenario tree; each block uses only earlier-block information."""
    scenarios=np.asarray(scenarios,float); ns,nt=scenarios.shape
    groups=np.zeros((ns,nt),dtype=int)
    partitions=[np.arange(ns)]; next_id=0
    for start in range(0,nt,stage_slots):
        end=min(start+stage_slots,nt)
        for members in partitions:
            groups[members,start:end]=next_id; next_id+=1
        if end==nt:
            break
        children=[]
        for members in partitions:
            if len(members)<=1:
                children.append(members); continue
            values=scenarios[members,start:end]
            labels=KMeans(n_clusters=2,random_state=0,n_init=20).fit_predict(values)
            children.extend(members[labels==label] for label in (0,1))
        partitions=children
    return groups


def execute_feedback(grid, actual_net_kw, initial_soc):
    """Causal physical controller; current measurement only."""
    soc=initial_soc
    flow=np.zeros((len(grid),6)) # start,end,c,d,emergency,spill
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
        grid=np.maximum(previous_row_curve(net,day),0)*DT_HOURS
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
        start=interval_label(i).split('-')[0]
        end=interval_label(j-1).split('-')[1]
        groups.append((f'{start}-{end}',float(values[i:j].sum())))
        i=j
    return groups


def export_result2_actual(project_root,output_path,dates,price,grids,traces,
                          previous_last_flow=None):
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
    template_blocks=['0:00-4:00','4:00-8:00','8:00-12:00',
                     '12:00-16:00','16:00-20:00','20:00-24:00']
    shifted_blocks=four_hour_blocks()
    for idx,(day,flow) in enumerate(zip(range(31,365),traces)):
        if previous_last_flow is not None:
            prev=previous_last_flow if idx==0 else traces[idx-1,-1]
            report_flow=np.vstack([prev,flow[:143]])
            blocks=[(24*b,24*(b+1),label) for b,label in enumerate(template_blocks)]
            soc0=float(prev[0]); soc24=float(flow[142,1])
        else:
            report_flow=flow; blocks=shifted_blocks
            soc0=float(flow[0,0]); soc24=float(flow[-1,1])
        for b,(lo,hi,label) in enumerate(blocks):
            sl=slice(lo,hi)
            battery.append([dates[day].to_pydatetime() if b==0 else None,label,
                round(float(report_flow[sl,2].sum()),6),round(float(report_flow[sl,3].sum()),6),
                '0:00' if b==0 else ('24:00' if b==1 else None),
                round(soc0 if b==0 else soc24,6) if b<2 else None])
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
               load=None, pv=None, scenario_mode='recent', initial_soc=SOC_INITIAL,
               tree_stage_slots=0):
    soc=initial_soc; rows=[]; grids=[]; traces=[]
    for day in range(31,365):
        scenarios=(
            split_residual_scenarios(load[:day],pv[:day],day,scenario_count)
            if scenario_mode=='split' else
            historical_residual_scenarios(net[:day],day,scenario_count)
        )
        groups=(hierarchical_tree_groups(scenarios,tree_stage_slots)
                if tree_stage_slots else None)
        grid=solve_adaptive_plan(scenarios,price,soc,terminal_floor,planning_penalty,
                                 node_groups=groups)
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
    parser.add_argument('--tree-stage-slots',type=int,default=0,
                        help='positive value enables strict multistage nonanticipativity')
    args=parser.parse_args()
    project_root=Path(__file__).resolve().parents[2]
    out=project_root/'02_q2/outputs/experiments'; out.mkdir(parents=True,exist_ok=True)
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
                                     scenario_mode=args.scenario_mode,initial_soc=initial_soc,
                                     tree_stage_slots=args.tree_stage_slots)
        record=dict(terminal_floor_kwh=floor,planning_penalty=penalty,
            scenario_mode=args.scenario_mode,initial_soc_kwh=initial_soc,
            tree_stage_slots=args.tree_stage_slots,
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
