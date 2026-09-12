"""Shared Q4 figure style and evidence loading; matches the existing Q2 figures."""
from pathlib import Path
import os
import sys
import json
import importlib.util
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

HERE = Path(__file__).resolve().parent
Q4 = HERE.parent
ROOT = Q4.parent
sys.path.insert(0, str(Q4))
from _utils.plot_utils import setup_style, save_fig, PALETTE, COLORS, _lighten

def init_style():
    # Derive exactly the palette used by Q2 from the same workspace seed.
    previous = Path.cwd()
    os.chdir(ROOT)
    setup_style()
    os.chdir(previous)
    plt.rcParams.update({'font.family':'DejaVu Serif', 'font.size':8.5,
        'axes.labelsize':9, 'axes.titlesize':9, 'xtick.labelsize':8,
        'ytick.labelsize':8, 'legend.fontsize':7.5, 'pdf.fonttype':42,
        'ps.fonttype':42, 'axes.grid':False, 'axes.linewidth':0.65,
        'xtick.direction':'out', 'ytick.direction':'out', 'savefig.bbox':None})

init_style()

def polish(ax, tag=None):
    ax.spines[['top','right']].set_visible(False)
    for name in ['left','bottom']:
        ax.spines[name].set_color(COLORS['ref_line'])
    ax.set_axisbelow(True)
    ax.grid(axis='y', color=COLORS['grid'], alpha=.48, linewidth=.55, linestyle='--')
    ax.tick_params(length=2.5, width=.6, top=False, right=False)
    if tag:
        ax.set_title(tag, loc='left', pad=5)

def legend(ax, ncol=3):
    return ax.legend(loc='lower right', bbox_to_anchor=(1,1.005), ncol=ncol,
                     frameon=False, handlelength=1.8, columnspacing=1.0,
                     handletextpad=.4, borderaxespad=0)

def finish(fig, name):
    fig.canvas.draw()
    # Preserve exact physical dimensions. Both outputs share the same canvas.
    save_fig(fig, str(HERE / (name+'.pdf')))
    fig.savefig(HERE/(name+'.png'), dpi=300, bbox_inches=None)
    plt.close(fig)

def evidence():
    return np.load(HERE/'data/representative_day.npz', allow_pickle=False)

EDGES = np.arange(1,146)/6
TIME = EDGES[:-1]

def time_axis(ax):
    ax.set_xlim(EDGES[0],EDGES[-1])
    ax.set_xticks([1/6,6,12,18,145/6],
                  ['00:10','06:00','12:00','18:00','00:10\n(next day)'])
    labels=ax.get_xticklabels()
    labels[0].set_ha('left'); labels[-1].set_ha('right')
    ax.set_xlabel('Time (purchase row dated 2025-03-20)', labelpad=4)

def staircase(ax, values, color, label, ls='-', lw=1.2):
    return ax.stairs(values, EDGES, baseline=None, color=color, label=label,
                     linewidth=lw, linestyle=ls, zorder=4)

def battery(ax, charge, discharge):
    for vals,c,label in [(discharge*6/1000, PALETTE[2],'Discharge'),
                         (-charge*6/1000,PALETTE[4],'Charge')]:
        ax.stairs(vals, EDGES, fill=True, facecolor=_lighten(c,.5),
                  edgecolor=c, linewidth=1, label=label, zorder=3)
    ax.axhline(0, color=COLORS['ref_line'], linewidth=.6)
    ax.set_ylabel('Battery\n(MW)');ax.set_yticks([-5,0,5]);ax.set_ylim(-5.6,5.6)

def stored(ax, soc):
    d=evidence();lo=float(d['soc_min'])/1000;hi=float(d['soc_max'])/1000
    ax.plot(EDGES,soc/1000,color=PALETTE[0],lw=1.35)
    ax.fill_between(EDGES,lo,soc/1000,color=PALETTE[0],alpha=.12)
    for b in [lo,hi]:ax.axhline(b,color=COLORS['ref_line'],ls='--',lw=.8)
    ax.set_ylim(lo-.6,hi+.6);ax.set_yticks([lo,6,hi]);ax.set_ylabel('Stored energy\n(MWh)')

__all__ = [name for name in globals() if not name.startswith('_')] + ['_lighten']
