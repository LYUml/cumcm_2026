"""F2: paired residual paths, March 20; exported original Q4-2 scenarios.
Recipe basic.line: nested empirical envelopes retain layered fill, without
pretending 12 constructed paths are statistical confidence intervals.
"""
from _figbase import *  # shared setup_style(), PALETTE
init_style();d=evidence()
fig,axes=plt.subplots(2,1,figsize=(6,3.8),sharex=True)
fig.subplots_adjust(left=.14,right=.97,bottom=.20,top=.89,hspace=.56)
for ax,key,actual,fc,scale,label,tag in [
    (axes[0],'net_scenarios_kw','actual_net_kw','forecast_net_kw',1000,'Net load (MW)','(a)'),
    (axes[1],'price_scenarios','actual_price','forecast_price',1,'Price (CNY/kWh)','(b)')]:
    polish(ax,tag);paths=d[key]/scale
    for lo,hi,alpha in [(0,1,.04),(.1,.9,.055),(.25,.75,.07)]:
        ax.fill_between(TIME,np.quantile(paths,lo,axis=0),np.quantile(paths,hi,axis=0),color=PALETTE[3],alpha=alpha,lw=0,zorder=1)
    for k,path in enumerate(paths):
        c=PALETTE[k%len(PALETTE)];ls='-' if k<len(PALETTE) else ':'
        ax.plot(TIME,path,color=c,ls=ls,lw=.9,alpha=.2,zorder=2)
    for k,c,ls in [(0,PALETTE[1],'-'),(1,PALETTE[2],'--')]:
        ax.plot(TIME,paths[k],color=c,ls=ls,lw=1.15,label=f"Residual {str(d['scenario_dates'][k])[5:]}",zorder=3)
    ax.plot(TIME,d[fc]/scale,color=PALETTE[0],ls='--',lw=1.25,label='Point forecast',zorder=5)
    ax.plot(TIME,d[actual]/scale,color=COLORS['text'],lw=1.25,label='Actual',zorder=6)
    ax.set_ylabel(label);ax.yaxis.set_major_locator(MaxNLocator(4));legend(ax,4)
time_axis(axes[-1]);finish(fig,'fig_q4_f2')
