"""F3: Q4-2 March-20 operation, from saved grid/trace and attachments.
Recipe basic.multipanel; four separate unit-consistent panels. No dual axis.
"""
from _figbase import *  # shared setup_style(), PALETTE
init_style();d=evidence();trace=d['q42_trace']
fig,axes=plt.subplots(4,1,figsize=(6,4.78),sharex=True,gridspec_kw={'height_ratios':[.9,1.1,.85,.9]})
fig.subplots_adjust(left=.15,right=.97,bottom=.16,top=.94,hspace=.55)
for ax,tag in zip(axes,['(a)','(b)','(c)','(d)']):polish(ax,tag)
staircase(axes[0],d['actual_price'],COLORS['text'],'Actual')
staircase(axes[0],d['forecast_price'],PALETTE[0],'Forecast','--')
axes[0].set_ylabel('Price\n(CNY/kWh)');legend(axes[0],2)
staircase(axes[1],d['actual_net_kw']/1000,COLORS['text'],'Actual net load')
staircase(axes[1],d['q42_grid']*6/1000,PALETTE[0],'Planned purchase')
axes[1].stairs(trace[:,4]*6/1000,EDGES,fill=True,facecolor=_lighten(PALETTE[1],.4),edgecolor=PALETTE[1],lw=.9,label='Emergency')
axes[1].set_ylabel('Power\n(MW)');legend(axes[1],3)
battery(axes[2],trace[:,2],trace[:,3]);legend(axes[2],2)
stored(axes[3],np.r_[trace[0,0],trace[:,1]])
time_axis(axes[-1]);finish(fig,'fig_q4_f3')
