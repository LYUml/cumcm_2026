"""F1: accuracy versus policy value; aligned panels from forecast/policy CSVs.
Recipe basic.multipanel: shared method rows, two marker metrics, cost dots.
The cost axis is deliberately magnified, not a zero-based bar comparison.
"""
from _figbase import *  # shared setup_style(), PALETTE and evidence paths
init_style()
names=['ridge_arx','elastic_net_arx','seasonal_naive_7d','weekday_mean_4w']
labels=['Ridge ARX','Elastic-net ARX','7-day seasonal','4-week weekday']
a=pd.read_csv(Q4/'outputs/q4_2_comparison/price_forecast_comparison.csv').set_index('model').loc[names]
b=pd.read_csv(Q4/'outputs/q4_2_comparison/policy_cost_comparison.csv').set_index('model').loc[names]
fig,axes=plt.subplots(1,2,figsize=(6,2.65),sharey=True,gridspec_kw={'width_ratios':[1.05,1]})
fig.subplots_adjust(left=.24,right=.97,bottom=.23,top=.80,wspace=.25)
y=np.arange(4)
for ax,tag in zip(axes,['(a) Point error','(b) Realised cost']):
    polish(ax,tag);ax.axhspan(2.65,3.35,color=PALETTE[0],alpha=.07,zorder=0)
    ax.set_ylim(3.65,-.65)
axes[0].scatter(a.mae_yuan_per_kwh,y-.10,color=PALETTE[0],s=28,marker='o',label='MAE',zorder=4)
axes[0].scatter(a.rmse_yuan_per_kwh,y+.10,color=PALETTE[1],s=28,marker='D',label='RMSE',zorder=4)
axes[0].set_yticks(y,labels);axes[0].set_xlim(.035,.075)
axes[0].set_xticks([.04,.05,.06,.07]);axes[0].set_xlabel('Error (CNY/kWh)')
axes[0].legend(loc='lower left',bbox_to_anchor=(0,1.14),frameon=False,ncol=2)
cost=b.total_yuan.to_numpy()/1e6
axes[1].scatter(cost,y,c=[PALETTE[3]]*3+[PALETTE[0]],s=[28]*3+[46],marker='o',zorder=4)
axes[1].set_xlim(cost.min()-.007,cost.max()+.017)
axes[1].set_xticks([14.65,14.67,14.69]);axes[1].set_xlabel('Cost (million CNY)')
axes[1].annotate(f'{cost[-1]:.4f}',(cost[-1],y[-1]),xytext=(7,0),textcoords='offset points',va='center',fontsize=8,color=PALETTE[0])
finish(fig,'fig_q4_f1')
