"""F4: saved Q4-3 March-20 operation and exact point_price reconstructions.
Recipe basic.multipanel. Final purchases are NOT intermediate revision tails.
"""
from _figbase import *  # shared setup_style(), PALETTE
init_style();d=evidence()
fig,axes=plt.subplots(4,1,figsize=(6,4.78),sharex=True,gridspec_kw={'height_ratios':[1,1,.85,.9]})
fig.subplots_adjust(left=.15,right=.97,bottom=.16,top=.92,hspace=.59)
for ax,tag in zip(axes,['(a)','(b)','(c)','(d)']):
    polish(ax,tag)
    for h in [6,12,18]:ax.axvline(h,color=COLORS['ref_line'],ls='--',lw=.65,zorder=0)
staircase(axes[0],d['actual_price'],COLORS['text'],'Actual',lw=1.25)
for k,(h,c,ls) in enumerate(zip([0,6,12,18],[PALETTE[0],PALETTE[1],PALETTE[3],PALETTE[2]],['--',':','-.','-'])):
    staircase(axes[0],d['issue_price'][k],c,f'{h:02}:00',ls,lw=1.25)
axes[0].set_ylabel('Price\n(CNY/kWh)');legend(axes[0],5)
staircase(axes[1],d['q43_plan']*6/1000,PALETTE[3],'00:00 baseline','--')
staircase(axes[1],d['q43_final']*6/1000,PALETTE[0],'Final purchase')
axes[1].fill_between(EDGES,np.r_[d['q43_plan'],d['q43_plan'][-1]]*6/1000,
    np.r_[d['q43_final'],d['q43_final'][-1]]*6/1000,step='post',color=PALETTE[1],alpha=.17,label='Revision gap')
axes[1].set_ylabel('Purchase\n(MW)');legend(axes[1],3)
battery(axes[2],d['q43_charge'],d['q43_discharge']);legend(axes[2],2)
stored(axes[3],d['q43_soc'])
time_axis(axes[-1]);finish(fig,'fig_q4_f4')
