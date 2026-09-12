"""Check renderer bounds, source consistency and deliverable completeness."""
from _figbase import *
import _figbase as base
import runpy
import hashlib
from matplotlib.text import Text

report={'scope':'Six Q4 figures; not a compiled whole-paper layout review','figures':{},'sources':{}}
def check(fig,name):
    fig.canvas.draw();r=fig.canvas.get_renderer();canvas=fig.bbox
    outside=[]
    for t in fig.findobj(Text):
        if not t.get_visible() or not t.get_text().strip():continue
        b=t.get_window_extent(r)
        if b.x0<canvas.x0-1 or b.y0<canvas.y0-1 or b.x1>canvas.x1+1 or b.y1>canvas.y1+1:
            outside.append(t.get_text())
    assert not outside,(name,outside)
    for ext in ['pdf','png']:
        p=HERE/f'{name}.{ext}';assert p.exists() and p.stat().st_size>1000
    report['figures'][name]={'text_inside_canvas':True,'size_inches':fig.get_size_inches().tolist(),'pdf_png_present':True}
    plt.close(fig)
base.finish=check
for script in sorted(HERE.glob('gen_fig_q4_f*.py')):runpy.run_path(str(script),run_name='__main__')
m=pd.read_csv(HERE/'data/monthly_comparison.csv')
p=pd.read_csv(Q4/'outputs/q4_2_comparison/policy_cost_comparison.csv').set_index('model').loc['weekday_mean_4w']
s=pd.read_csv(Q4/'outputs/q4_3_stochastic/update_subset_comparison.csv').set_index('updates').loc['6+12+18']
assert np.isclose(m.q42_cost_yuan.sum(),p.total_yuan,rtol=0,atol=1e-6)
assert np.isclose(m.q43_cost_yuan.sum(),s.total_cost_yuan,rtol=0,atol=1e-6)
assert np.isclose(m.q42_emergency_kwh.sum(),p.emergency_kwh,rtol=0,atol=1e-6)
assert np.isclose(m.q43_emergency_kwh.sum(),s.emergency_kwh,rtol=0,atol=1e-6)
for p in [Q4/'outputs/q4_2_comparison/policy_weekday_mean_4w.npz',Q4/'outputs/q4_3_stochastic/policy.npz',HERE/'data/representative_day.npz',HERE/'data/monthly_comparison.csv']:
    report['sources'][str(p.relative_to(Q4))]=hashlib.sha256(p.read_bytes()).hexdigest()
report['monthly_totals_match_original_results']=True
report['visual_review']='All six PNGs viewed individually; fixed F5 long category label; unified stair rendering in F4. No figure overlap or clipping observed in final review.'
(HERE/'data/figure_qa.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
