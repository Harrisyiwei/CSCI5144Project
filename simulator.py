"""Causal daily tiering simulator. USD, GiB (2**30 bytes), 30-day months.
Explicit illustrative rates, not an AWS bill. Standard library only.
"""
from dataclasses import dataclass,asdict
from collections import defaultdict
from pathlib import Path
import csv,json,random,math,argparse
GIB=2**30
MIN_SIZE=128*1024
POLICIES=('standard','lifecycle','intelligent','adaptive')
SCENARIOS=('hot','cold','bursty','cooling','mixed')
@dataclass(frozen=True)
class Prices:
    standard:float=.023
    ia:float=.0125
    aia:float=.004
    get_standard:float=.0004/1000
    get_ia:float=.001/1000
    put:float=.005/1000
    transition:float=.01/1000
    retrieve:float=.01
    monitor:float=.0025/1000
    controller:float=0
    migration_multiplier:float=1
@dataclass(frozen=True)
class Object:
    id:str
    size_bytes:int
@dataclass
class State:
    tier:str='standard'
    entered:int=0
    last:int=0
    ewma:float=0

def generate(scenario,seed=17,n=240,days=180,size_bytes=None):
    rng=random.Random(seed)
    objects=[Object(f'o{i:04}',size_bytes or rng.choice([64*1024,1024**2,64*1024**2,GIB])) for i in range(n)]
    reads=[[0]*n for _ in range(days)]
    for i in range(n):
        phase=rng.randrange(40)
        for d in range(days):
            if scenario=='hot':p=.65
            elif scenario=='cold':p=.002
            elif scenario=='bursty':p=.8 if (d+phase)%40<5 else .002
            elif scenario=='cooling':p=.7*math.exp(-d/12)+.002
            elif scenario=='mixed':p=.65 if i<n//5 else .002
            else:raise ValueError(scenario)
            reads[d][i]=int(rng.random()<p)
    return objects,reads

def simulate(objects,reads,policy,prices=Prices(),lifecycle_day=30):
    if policy not in POLICIES:raise ValueError(policy)
    if not objects or not reads:raise ValueError('Empty workload')
    if any(len(row)!=len(objects) or any(c<0 or int(c)!=c for c in row) for row in reads):raise ValueError('Invalid counts')
    states=[State() for _ in objects];cost=defaultdict(float,initial_put=len(objects)*prices.put)
    moves=0;daily=[];occupancy=defaultdict(int)
    for day,counts in enumerate(reads):
        for obj,s,count in zip(objects,states,counts):
            gb=obj.size_bytes/GIB;eligible=obj.size_bytes>=MIN_SIZE
            def change(target):
                nonlocal moves
                if target==s.tier:return
                if policy!='intelligent':
                    if s.tier=='ia':
                        cost['minimum_duration']+=max(0,30-(day-s.entered))*max(gb,MIN_SIZE/GIB)*prices.ia/30
                        cost['migration']+=(gb*prices.retrieve+prices.get_ia+prices.put)*prices.migration_multiplier
                    else:cost['migration']+=prices.transition*prices.migration_multiplier
                s.tier=target;s.entered=day;moves+=1
            # Decisions use prior completed days only.
            if policy=='intelligent':
                idle=day-s.last
                change(('aia' if idle>=90 else 'ia' if idle>=30 else 'standard') if eligible else 'standard')
            elif policy=='lifecycle' and eligible and day>=lifecycle_day:change('ia')
            elif policy=='adaptive' and eligible and day>=7:
                expected=s.ewma*30
                hot=gb*prices.standard+expected*prices.get_standard
                cold=max(gb,MIN_SIZE/GIB)*prices.ia+expected*(prices.get_ia+gb*prices.retrieve)
                if s.tier=='standard':
                    if day-s.last>=7 and cold+prices.transition*prices.migration_multiplier<.9*hot:change('ia')
                else:
                    exit_cost=(gb*prices.retrieve+prices.get_ia+prices.put)*prices.migration_multiplier
                    penalty=max(0,30-(day-s.entered))*max(gb,MIN_SIZE/GIB)*prices.ia/30
                    if hot+exit_cost+penalty<.9*cold:change('standard')
            if policy=='intelligent':
                cost['get']+=count*prices.get_standard
                if count:change('standard')
            elif s.tier=='ia':
                cost['get']+=count*prices.get_ia;cost['retrieval']+=count*gb*prices.retrieve
            else:cost['get']+=count*prices.get_standard
            if count:s.last=day
            s.ewma=.2*count+.8*s.ewma
            rate=prices.standard if s.tier=='standard' else prices.aia if s.tier=='aia' else prices.ia
            billed=max(gb,MIN_SIZE/GIB) if s.tier=='ia' and policy!='intelligent' else gb
            cost['storage']+=billed*rate/30
            if policy=='intelligent' and eligible:cost['monitoring']+=prices.monitor/30
            if policy=='adaptive':cost['controller']+=prices.controller/30
            occupancy[s.tier]+=1
        daily.append({'day':day,'cumulative_usd':sum(cost.values())})
    # Expiration at horizon settles remaining IA minimum-duration obligations.
    if policy!='intelligent':
        for o,s in zip(objects,states):
            if s.tier=='ia':cost['minimum_duration']+=max(0,30-(len(reads)-s.entered))*max(o.size_bytes/GIB,MIN_SIZE/GIB)*prices.ia/30
    daily[-1]['cumulative_usd']=sum(cost.values())
    return {'policy':policy,'total_usd':sum(cost.values()),'costs':dict(cost),'moves':moves,'object_days':dict(occupancy),'daily':daily}

def write_csv(path,rows):
    rows=list(rows)
    with open(path,'w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def export_trace(folder,objects,reads):
    folder.mkdir(parents=True,exist_ok=True)
    write_csv(folder/'objects.csv',[asdict(o) for o in objects])
    write_csv(folder/'reads.csv',({'day':d,'object_id':o.id,'count':c} for d,row in enumerate(reads) for o,c in zip(objects,row) if c))

def load_trace(folder,days):
    with open(folder/'objects.csv') as f:objects=[Object(r['id'],int(r['size_bytes'])) for r in csv.DictReader(f)]
    ids={o.id:i for i,o in enumerate(objects)}
    if len(ids)!=len(objects) or any(o.size_bytes<=0 for o in objects):raise ValueError('Invalid objects')
    reads=[[0]*len(objects) for _ in range(days)]
    with open(folder/'reads.csv') as f:
        for r in csv.DictReader(f):
            d,c=int(r['day']),int(r['count'])
            if not 0<=d<days or c<0:raise ValueError('Invalid reads')
            reads[d][ids[r['object_id']]]+=c
    return objects,reads

def suite(out):
    out.mkdir(parents=True,exist_ok=True);seeds=[17,29,43,71,101];raw=[];daily=[]
    for scenario in SCENARIOS:
        for seed in seeds:
            o,reads=generate(scenario,seed)
            if scenario=='mixed' and seed==17:export_trace(out/'example_trace',o,reads)
            for policy in POLICIES:
                r=simulate(o,reads,policy)
                raw.append({'scenario':scenario,'seed':seed,'policy':policy,'total_usd':r['total_usd'],'moves':r['moves'],**{k:r['costs'].get(k,0) for k in ['storage','get','retrieval','migration','monitoring','minimum_duration','controller','initial_put']}})
                if seed==17:daily.extend({'scenario':scenario,'policy':policy,**x} for x in r['daily'])
    write_csv(out/'runs.csv',raw);write_csv(out/'daily.csv',daily);summary=[]
    for scenario in SCENARIOS:
        group=[r for r in raw if r['scenario']==scenario]
        for policy in POLICIES:
            vals=[r['total_usd'] for r in group if r['policy']==policy];avg=sum(vals)/5
            sd=math.sqrt(sum((v-avg)**2 for v in vals)/4);paired=[]
            for seed in seeds:
                a=next(r['total_usd'] for r in group if r['seed']==seed and r['policy']==policy)
                b=next(r['total_usd'] for r in group if r['seed']==seed and r['policy']=='intelligent')
                paired.append(100*(b-a)/b)
            pa=sum(paired)/5;ps=math.sqrt(sum((v-pa)**2 for v in paired)/4)
            summary.append({'scenario':scenario,'policy':policy,'mean_usd':avg,'sd_usd':sd,'savings_vs_it_pct':pa,'paired_ci95_halfwidth_pp':2.776*ps/math.sqrt(5)})
    write_csv(out/'summary.csv',summary);sweep=[]
    for size in [64*1024,128*1024,1024**2,64*1024**2,GIB]:
        for migration in [.5,1,10]:
            for overhead in [0,.0000025,.000025]:
                for seed in seeds[:3]:
                    o,reads=generate('mixed',seed,n=120,size_bytes=size)
                    for policy in ['intelligent','adaptive']:
                        r=simulate(o,reads,policy,Prices(controller=overhead,migration_multiplier=migration))
                        sweep.append({'size_bytes':size,'migration_multiplier':migration,'controller_per_object_month':overhead,'seed':seed,'policy':policy,'total_usd':r['total_usd']})
    write_csv(out/'sensitivity.csv',sweep)
    horizon_rows=[]
    for scenario in ['cold','mixed']:
        for days in [30,60,90,180]:
            for seed in seeds[:3]:
                o,reads=generate(scenario,seed,n=120,days=180,size_bytes=GIB)
                reads=reads[:days]
                for policy in POLICIES:
                    r=simulate(o,reads,policy)
                    horizon_rows.append({'scenario':scenario,'days':days,'seed':seed,'policy':policy,'total_usd':r['total_usd']})
    write_csv(out/'horizons.csv',horizon_rows)
    (out/'metadata.json').write_text(json.dumps({'days':180,'objects':240,'seeds':seeds,'prices':asdict(Prices()),'rate_status':'Explicit illustrative us-east-1 style inputs, not a live AWS quote','expiration_day':180,'sweep_objects':120,'sweep_seeds':seeds[:3],'total_runs':len(raw)+len(sweep)+len(horizon_rows)},indent=2))
    print(json.dumps(summary,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('results'));p.add_argument('--trace',type=Path);p.add_argument('--days',type=int,default=180);a=p.parse_args()
    if a.trace:
        o,reads=load_trace(a.trace,a.days)
        print(json.dumps([{k:v for k,v in simulate(o,reads,x).items() if k!='daily'} for x in POLICIES],indent=2))
    else:suite(a.output)
