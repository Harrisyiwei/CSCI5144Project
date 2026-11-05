"""Small controlled sensitivity analysis for modeled IBM object sizes and horizon."""
from collections import defaultdict
from pathlib import Path
import csv
import json
import statistics

from real_trace import BASE, DEFAULT_EVENTS, DEFAULT_IBM, DEFAULT_OBJECTS, load_real_cohort
from simulator import POLICIES, simulate, write_csv


def main():
    out = BASE / 'results' / 'real_trace'
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    experiments = [(180, seed) for seed in [5144, 17, 29, 43, 71]]
    experiments += [(90, 5144), (365, 5144)]
    for days, seed in experiments:
        objects, reads, meta = load_real_cohort(
            DEFAULT_EVENTS, DEFAULT_OBJECTS, '2019-01-01', days, 90,
            size_seed=seed, ibm_sizes_path=DEFAULT_IBM)
        costs = {p: simulate(objects, reads, p) for p in POLICIES}
        it = costs['intelligent']['total_usd']
        for p, result in costs.items():
            rows.append({
                'days':days, 'size_seed':seed, 'policy':p,
                'objects':len(objects),
                'observed_accesses':meta['evaluation_selected_events'],
                'total_usd':result['total_usd'],
                'moves':result['moves'],
                'savings_vs_it_pct':100*(it-result['total_usd'])/it,
            })
        print(f'finished {days} days / IBM size seed {seed}: IT=${it:.4f}, adaptive=${costs["adaptive"]["total_usd"]:.4f}',flush=True)
    write_csv(out/'sensitivity.csv',rows)
    results = []
    for policy in POLICIES:
        items = [x for x in rows if x['days']==180 and x['policy']==policy]
        savings = [x['savings_vs_it_pct'] for x in items]
        results.append({
            'policy':policy,
            'n_size_assignments':len(items),
            'avg_savings_vs_it_pct':statistics.mean(savings),
            'min_savings_vs_it_pct':min(savings),
            'max_savings_vs_it_pct':max(savings),
            'avg_cost_usd':statistics.mean(x['total_usd'] for x in items),
        })
    write_csv(out/'size_sensitivity_summary.csv',results)
    (out/'sensitivity_meta.json').write_text(json.dumps({
        'size_seed_set':[5144,17,29,43,71],
        'reason':'Object size absent in CLUE; test independent assignments from 543 deduplicated IBM sample sizes',
        'horizons':[90,180,365],
        'horizon_comparison_size_seed':5144,
        'warning':'Seed replicates reflect size imputation uncertainty only, NOT independent real workload samples or formal confidence intervals.',
    },indent=2),encoding='utf-8')

if __name__=='__main__':main()
