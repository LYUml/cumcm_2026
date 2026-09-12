"""Q2 cost figures: Vivid stacked-bar recipe, with measured label margins.

Native width 6 in matches Prism's 0.96 * 160 mm = 6.05 in inclusion width.
Data roles retain the project palette and light fill / original edge pairing.
"""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

Q2 = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Q2/'src'))
from plot_utils import setup_style, save_fig, PALETTE, COLORS, _lighten


def _axes(ax):
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.spines['bottom'].set_color(COLORS['ref_line'])
    ax.tick_params(axis='both', which='both', top=False, right=False,
                   labelsize=9, length=3)
    ax.tick_params(axis='y', length=0, pad=8)
    ax.grid(False)
    ax.grid(axis='x', color=COLORS['grid'], linewidth=.6, alpha=.55)
    ax.set_axisbelow(True)


def _save_checked(fig, axes, out, name):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for ax in axes:
        bounds = ax.get_window_extent(renderer)
        for txt in ax.texts:
            box = txt.get_window_extent(renderer)
            if box.x0 < bounds.x0 or box.x1 > bounds.x1:
                raise AssertionError(f'{name}: label outside axes: {txt.get_text()}')
    for ext in ('pdf', 'png'):
        save_fig(fig, out / f'{name}.{ext}')


def make_cost_figures(out: Path, legacy_path: Path):
    setup_style()
    figure_out = out/'figures'
    figure_out.mkdir(parents=True, exist_ok=True)
    # Explicit sizing prevents inherited large theme fonts squeezing the axes.
    with plt.rc_context({'font.family': 'DejaVu Serif', 'font.size': 9,
                         'axes.labelsize': 9, 'legend.fontsize': 8.5,
                         'pdf.fonttype': 42}):
        v = json.loads((out / 'validation.json').read_text())
        old = pd.read_csv(legacy_path).iloc[0]
        plan = np.array([old.planned_yuan, v['planned_yuan']]) / 1e6
        emergency = np.array([old.emergency_yuan, v['emergency_yuan']]) / 1e6
        fig, (a, b) = plt.subplots(2, 1, figsize=(6, 4.2))
        fig.subplots_adjust(left=.27, right=.975, bottom=.12, top=.88, hspace=.72)
        a.barh([0, 1], plan, height=.44, color=_lighten(PALETTE[0], .40),
               edgecolor=PALETTE[0], linewidth=.9, label='Day-ahead')
        a.barh([0, 1], emergency, left=plan, height=.44,
               color=_lighten(PALETTE[1], .38), edgecolor=PALETTE[1],
               linewidth=.9, label='Emergency')
        a.set(yticks=[0, 1], yticklabels=['Legacy\nimplementation', 'Strict midnight\navailability'],
              xlim=(0, 16.5), ylim=(1.6, -.6), xticks=[0, 4, 8, 12, 16],
              xlabel='Realized expenditure (million CNY)')
        _axes(a)
        a.legend(frameon=False, ncol=2, loc='lower left', bbox_to_anchor=(0, 1.08),
                 borderaxespad=0, handlelength=1.6)
        for k, value in enumerate(plan + emergency):
            a.text(16.15, k, f'{value:.4f}', ha='right', va='center',
                   fontsize=9, fontweight='bold', color=COLORS['text'])
        delta = np.array([plan[1]-plan[0], emergency[1]-emergency[0],
                          (plan+emergency)[1]-(plan+emergency)[0]]) * 1000
        for k, value in enumerate(delta):
            color = PALETTE[0] if k == 0 else PALETTE[1]
            b.barh(k, value, height=.48, color=_lighten(color, .40),
                   edgecolor=color, linewidth=1, hatch='//' if k == 2 else None)
            b.text(value + (3 if value >= 0 else -3), k, f'{value:+.2f}',
                   ha='left' if value >= 0 else 'right', va='center', fontsize=9,
                   fontweight='bold' if k == 2 else 'normal', color=COLORS['text'])
        b.set(yticks=[0,1,2], yticklabels=['Day-ahead', 'Emergency', 'Total'],
              xlim=(-35, 150), ylim=(2.65,-.65), xticks=[0,40,80,120],
              xlabel='Correction increment (thousand CNY)')
        _axes(b)
        b.axvline(0, color=COLORS['ref_line'], linewidth=.9)
        _save_checked(fig, [a,b], figure_out, 'q2_cost_chronology')

        models = pd.read_csv(out/'model_comparison/comparison.csv').sort_values('total_yuan')
        fig,a = plt.subplots(figsize=(6,3.65))
        fig.subplots_adjust(left=.30, right=.975, bottom=.16, top=.86)
        y = np.arange(len(models))
        plan = models.planned_yuan.to_numpy()/1e6
        emergency = models.emergency_yuan.to_numpy()/1e6
        a.barh(y,plan,height=.53,color=_lighten(PALETTE[0],.40),edgecolor=PALETTE[0],
               linewidth=.9,label='Day-ahead')
        a.barh(y,emergency,left=plan,height=.53,color=_lighten(PALETTE[1],.38),
               edgecolor=PALETTE[1],linewidth=.9,label='Emergency')
        a.set(yticks=y,yticklabels=models.policy,xlim=(0,18),ylim=(5.6,-.6),
              xticks=[0,4,8,12,16],xlabel='Realized expenditure (million CNY)')
        _axes(a)
        a.legend(frameon=False,ncol=2,loc='lower left',bbox_to_anchor=(0,1.055),
                 borderaxespad=0,handlelength=1.6)
        for k,(_,row) in enumerate(models.iterrows()):
            weight='bold' if row.selected else 'normal'
            a.get_yticklabels()[k].set_fontweight(weight)
            a.text(17.65,k,f'{row.total_yuan/1e6:.3f}',ha='right',va='center',
                   fontsize=9,fontweight=weight,color=COLORS['text'])
        _save_checked(fig,[a],figure_out,'q2_model_comparison')


if __name__ == '__main__':
    q2=Path(__file__).resolve().parents[2]
    make_cost_figures(q2/'outputs',q2/'src/data/legacy_comparison_strict4h_fine.csv')
