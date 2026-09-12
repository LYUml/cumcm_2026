"""F6 supplementary: monthly aggregate policy outcomes from daily saved results.
Recipe basic.grouped_bar: paired light-fill bars, hatching for grayscale use.
"""
from _figbase import *  # shared setup_style(), PALETTE
init_style();df=pd.read_csv(HERE/'data/monthly_comparison.csv')
fig,axes=plt.subplots(2,1,figsize=(6,3.7),sharex=True)
fig.subplots_adjust(left=.15,right=.97,bottom=.17,top=.92,hspace=.38)
x=np.arange(len(df))
for ax,suffix,scale,label,tag in [(axes[0],'cost_yuan',1e6,'Total cost\n(million CNY)','(a)'),(axes[1],'emergency_kwh',1000,'Emergency energy\n(MWh)','(b)')]:
    polish(ax,tag)
    for k,(prefix,name) in enumerate([('q42','Q4-2'),('q43','Q4-3')]):
        c=PALETTE[k]
        ax.bar(x+(k-.5)*.35,df[f'{prefix}_{suffix}']/scale,.32,
            color=_lighten(c,.55),edgecolor=c,lw=.9,hatch='//' if k==1 else None,label=name,zorder=3)
    ax.set_ylim(bottom=0);ax.set_ylabel(label);ax.yaxis.set_major_locator(MaxNLocator(4))
legend(axes[0],2)
axes[-1].set_xticks(x,pd.to_datetime(df.month).dt.strftime('%b'))
axes[-1].set_xlabel('2025 evaluation months')
finish(fig,'fig_q4_f6')
