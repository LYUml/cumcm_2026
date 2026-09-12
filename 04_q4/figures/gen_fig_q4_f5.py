"""F5: update subsets, cost and emergency; real saved ablation results.
Recipe basic.grouped_bar, preserving light fill/solid edge and zero baseline.
Absolute outcome bars follow the manuscript plan, not additive module effects.
"""
from _figbase import *  # shared setup_style(), PALETTE
init_style()
df=pd.read_csv(Q4/'outputs/q4_3_stochastic/update_subset_comparison.csv').set_index('updates').loc[['00-only','6','6+12','6+12+18']]
fig,axes=plt.subplots(2,1,figsize=(6,3.65),sharex=True)
fig.subplots_adjust(left=.16,right=.97,bottom=.19,top=.94,hspace=.40)
x=np.arange(4)
for ax,key,scale,label,tag in [(axes[0],'total_cost_yuan',1e6,'Total cost\n(million CNY)','(a)'),(axes[1],'emergency_kwh',1000,'Emergency energy\n(MWh)','(b)')]:
    polish(ax,tag);vals=df[key].to_numpy()/scale
    fills=[_lighten(PALETTE[0],t) for t in [.77,.63,.48,.25]]
    bars=ax.bar(x,vals,.54,color=fills,edgecolor=PALETTE[0],lw=1.05,zorder=3)
    ax.bar_label(bars,labels=[f'{v:.3f}' if scale==1e6 else f'{v:.2f}' for v in vals],padding=3,fontsize=8)
    ax.set_ylim(0,vals.max()*1.24);ax.set_ylabel(label)
    ax.yaxis.set_major_locator(MaxNLocator(4))
axes[-1].set_xticks(x,['None','06:00','06:00 + 12:00','06:00 + 12:00\n+ 18:00'])
axes[-1].set_xlabel('Intraday updates (all policies also plan at 00:00)',labelpad=5)
finish(fig,'fig_q4_f5')
