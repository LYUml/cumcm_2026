"""Median-cost purchase-row figure using the Vivid style baseline.

6-inch width matches the Prism inclusion width (~6.05 inches). Interval plots
use 145 edges for all 144 values, including the final next-day ten minutes.
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

Q2 = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Q2/'src'))
from plot_utils import setup_style, save_fig, PALETTE, COLORS, _lighten
from q2_model import read_inputs


def make_example_figure(out, root):
    setup_style()
    figure_out = out/'figures'
    figure_out.mkdir(parents=True, exist_ok=True)
    daily = pd.read_csv(out/'selected_daily.csv')
    i = int((daily.total_yuan-daily.total_yuan.median()).abs().idxmin())
    with np.load(out/'selected_policy_numeric_trace.npz') as data:
        grid = data['grid'][i]
        flow = data['trace'][i]
    _, load, pv, _ = read_inputs(root)
    net = (load[i+31]-pv[i+31])/1000
    edges = np.arange(1,146)/6
    state = np.r_[flow[0,0], flow[:,1]]/1000
    emergency = flow[:,4]*6/1000
    short = np.flatnonzero(flow[:,4]>1e-7)
    lower = np.flatnonzero(flow[:,1]<=1200+1e-6)
    assert len(edges)==len(grid)+1 and np.isclose(edges[-1]-edges[0],24)
    with plt.rc_context({'font.family':'DejaVu Serif','font.size':8.5,
                         'axes.labelsize':9,'legend.fontsize':7.5,'pdf.fonttype':42}):
        fig,(a,b,c)=plt.subplots(3,1,figsize=(6,4.65),sharex=True,
                               gridspec_kw={'height_ratios':[1.35,.85,1.05]})
        fig.subplots_adjust(left=.13,right=.97,top=.92,bottom=.15,hspace=.40)
        for ax in (a,b,c):
            ax.spines[['top','right']].set_visible(False)
            ax.spines[['left','bottom']].set_color(COLORS['ref_line'])
            ax.tick_params(which='both',top=False,right=False,labelsize=8,length=3)
            ax.grid(False)
            ax.grid(axis='y',color=COLORS['grid'],alpha=.5,linewidth=.6)
            ax.set_axisbelow(True)
        a.stairs(net,edges,baseline=None,color=COLORS['text'],linewidth=1.05,label='Actual net load',zorder=3)
        a.stairs(grid*6/1000,edges,baseline=None,color=PALETTE[0],linewidth=1.25,
                 label='Committed purchase',zorder=4)
        a.stairs(emergency,edges,baseline=0,fill=True,color=_lighten(PALETTE[1],.25),
                 alpha=.85,label='Emergency',zorder=2)
        a.set_ylabel('Power (MW)')
        a.legend(frameon=False,ncol=3,loc='lower left',bbox_to_anchor=(0,1.04),
                 borderaxespad=0,handlelength=1.7,columnspacing=1.5)
        a.margins(y=.15)
        for values,color,label in [(flow[:,3]*6/1000,PALETTE[2],'Discharge'),
                                    (-flow[:,2]*6/1000,PALETTE[4],'Charge')]:
            b.stairs(values,edges,baseline=0,fill=True,color=_lighten(color,.38),alpha=.8)
            b.stairs(values,edges,baseline=None,color=color,linewidth=.9,label=label)
        b.axhline(0,color=COLORS['ref_line'],linewidth=.7)
        b.set(ylabel='Battery (MW)',ylim=(-5.7,5.7),yticks=[-5,0,5])
        b.legend(frameon=False,ncol=2,loc='lower left',bbox_to_anchor=(0,1.01),
                 borderaxespad=0,handlelength=1.7)
        c.plot(edges,state,color=PALETTE[0],linewidth=1.4)
        c.fill_between(edges,1.2,state,color=_lighten(PALETTE[0],.5),alpha=.3)
        for bound in (1.2,10.8):
            c.axhline(bound,color=COLORS['ref_line'],ls=(0,(4,3)),linewidth=.75)
        c.set(ylabel='Stored energy\n(MWh)',ylim=(.4,11.7),yticks=[1.2,6,10.8],
              xlim=(edges[0],edges[-1]),xlabel='Time (purchase row dated '+str(daily.date.iloc[i])+')')
        c.set_xticks([edges[0],4,8,12,16,20,edges[-1]],
                     ['00:10','04:00','08:00','12:00','16:00','20:00','00:10\n(next day)'])
        c.get_xticklabels()[0].set_ha('left')
        c.get_xticklabels()[-1].set_ha('right')
        # Annotate the first lower-bound event within the emergency episode.
        if len(short):
            episode_lower=lower[(lower>=short[0]) & (lower<=short[-1])]
            if len(episode_lower):
                t=int(episode_lower[0]); minute=(t+2)*10
                end_min=(int(short[-1])+2)*10
                annotation=(f'{minute//60:02d}:{minute%60:02d}: lower bound reached'
                            f'  ·  Emergency supply until {end_min//60:02d}:{end_min%60:02d}')
                c.scatter(edges[t+1],state[t+1],s=18,color=PALETTE[1],zorder=5)
                # Put commentary in the inter-panel gutter, leaving the curve clear.
                c.text(0,1.12,annotation,transform=c.transAxes,fontsize=7.4,
                       ha='left',va='bottom',color=COLORS['text'])
        fig.canvas.draw()
        renderer=fig.canvas.get_renderer()
        for ax in (a,b,c):
            for text in [ax.xaxis.label,ax.yaxis.label,*ax.get_xticklabels(),*ax.get_yticklabels()]:
                if text.get_visible() and text.get_text():
                    bb=text.get_window_extent(renderer)
                    assert bb.x0>=0 and bb.y0>=0 and bb.x1<=fig.bbox.x1 and bb.y1<=fig.bbox.y1
        for ext in ('pdf','png'):
            save_fig(fig,figure_out/f'q2_representative_day_corrected.{ext}')


if __name__=='__main__':
    root=Path(__file__).resolve().parents[3]
    make_example_figure(root/'02_q2/outputs',root)
