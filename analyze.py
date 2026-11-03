"""Make presentation data and optional scientific figures. Requires matplotlib for PNGs."""
import csv,json,statistics
from pathlib import Path
ROOT=Path(__file__).parent
R=ROOT/'results'
def rows(name):
    with open(R/name) as f:return list(csv.DictReader(f))
def mean(vals):return statistics.mean(float(x) for x in vals)
summary=rows('summary.csv');hr=rows('horizons.csv');sw=rows('sensitivity.csv')
horizons={p:[mean(r['total_usd'] for r in hr if r['scenario']=='cold' and int(r['days'])==d and r['policy']==p) for d in [30,60,90,180]] for p in ['intelligent','adaptive']}
savings=[100*(b-a)/b for a,b in zip(horizons['adaptive'],horizons['intelligent'])]
data={'summary':summary,'horizons':horizons,'horizon_savings':savings,'days':[30,60,90,180]}
(R/'presentation_data.json').write_text(json.dumps(data,indent=2))
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    fig,ax=plt.subplots(figsize=(9,4.5))
    for p,color,label in [('intelligent','#2962a3','Modeled Intelligent-Tiering'),('adaptive','#c5572f','Adaptive heuristic')]:ax.plot([30,60,90,180],horizons[p],marker='o',color=color,label=label)
    ax.set(xlabel='Retention horizon (days)',ylabel='Modeled cost (USD)',title='Cold synthetic workload: early savings reverse over time')
    ax.set_xticks([30,60,90,180]);ax.legend();ax.grid(axis='y',alpha=.2);fig.tight_layout();fig.savefig(R/'horizon_costs.png',dpi=200);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4.8))
    policies=['standard','lifecycle','intelligent','adaptive'];colors=['#738095','#a88946','#2962a3','#c5572f']
    for j,p in enumerate(policies):
        vals=[]
        for s in ['hot','cold','bursty','cooling','mixed']:
            cost=float(next(r['mean_usd'] for r in summary if r['scenario']==s and r['policy']==p))
            baseline=float(next(r['mean_usd'] for r in summary if r['scenario']==s and r['policy']=='intelligent'))
            vals.append(cost/baseline)
        ax.bar([i+(j-1.5)*.18 for i in range(5)],vals,width=.18,label=p,color=colors[j])
    ax.set_xticks(range(5),['Hot','Cold','Bursty','Cooling','Mixed']);ax.set(ylabel='Cost / Intelligent-Tiering cost',title='180-day synthetic workloads (five seeds)');ax.axhline(1,color='#222',linewidth=.7);ax.legend(ncol=4);fig.tight_layout();fig.savefig(R/'workload_costs.png',dpi=200);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4.5))
    sizes=[65536,131072,1048576,67108864,1073741824]
    for m in [.5,1,10]:
        vals=[]
        for size in sizes:
            g=[r for r in sw if int(r['size_bytes'])==size and float(r['migration_multiplier'])==m and float(r['controller_per_object_month'])==0]
            a=mean(r['total_usd'] for r in g if r['policy']=='adaptive');b=mean(r['total_usd'] for r in g if r['policy']=='intelligent');vals.append(100*(b-a)/b)
        ax.plot(range(5),vals,marker='o',label=f'Migration fee x{m:g}')
    ax.set_xticks(range(5),['64 KiB','128 KiB','1 MiB','64 MiB','1 GiB']);ax.set(ylabel='Adaptive savings versus IT (%)',title='Mixed workload: size and migration fee sensitivity');ax.axhline(0,color='#333',linewidth=.7);ax.legend();fig.tight_layout();fig.savefig(R/'sensitivity.png',dpi=200)
except ImportError:print('JSON complete. Install matplotlib to render figures.')
print(json.dumps({'horizon_savings':savings,'horizons':horizons},indent=2))
