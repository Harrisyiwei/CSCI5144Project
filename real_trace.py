"""Replay CLUE file-access timestamps through Harris's unchanged policy simulator.

This is a hypothetical S3 *cohort replay*, not a reconstruction of true S3 bills:
we select only objects observed in a PRE-evaluation history window, model
these objects as freshly uploaded on evaluation day 0, then retain every
selected object for the chosen evaluation horizon. Size values are modeled
from an IBM object-size sample; CLUE accesses are observed but are not proven
S3 GETs. See REAL_TRACE_METHOD.md before interpreting results.
"""

import argparse
import csv
from datetime import date, timedelta
import gzip
import json
from pathlib import Path
import random

from simulator import MIN_SIZE, POLICIES, Prices, Object, export_trace, simulate, write_csv

BASE = Path(__file__).resolve().parent
DEFAULT_EVENTS = BASE / "data" / "clue_ibm_accesses_with_assigned_sizes.csv.gz"
DEFAULT_OBJECTS = BASE / "data" / "clue_ibm_objects.csv.gz"
DEFAULT_IBM = BASE / "data" / "ibm_object_sizes_sample.csv"


def open_table(path):
    if str(path).endswith('.gz'):
        return gzip.open(path, 'rt', newline='', encoding='utf-8')
    return open(path, 'r', newline='', encoding='utf-8')


def load_real_cohort(events_path, objects_path, start, days=180, history_days=90,
                     size_seed=None, ibm_sizes_path=None):
    """Return (objects, sparse daily counts, metadata) without future-based selection.

    Selection uses *only* IDs seen in history, never accesses from the test
    window. No read counts from the history are fed into the test replay; all
    policies start in their initial tier on test day zero.
    """
    if isinstance(start, str):
        start = date.fromisoformat(start)
    if days < 1 or history_days < 1:
        raise ValueError('days and history_days must be positive')
    begin_history = start - timedelta(days=history_days)
    end = start + timedelta(days=days)

    sizes = {}
    with open_table(objects_path) as f:
        r = csv.DictReader(f)
        required = {'object_id', 'assigned_size_bytes'}
        if not required.issubset(set(r.fieldnames or [])):
            raise ValueError(f'objects file needs columns {sorted(required)}')
        for row in r:
            oid = row['object_id']
            size = int(row['assigned_size_bytes'])
            if oid in sizes or not oid or size <= 0:
                raise ValueError('invalid/duplicate object in size file')
            sizes[oid] = size

    history_ids = set()
    potential = []
    entire_trace_count = 0
    raw_window_events = 0
    with open_table(events_path) as f:
        r = csv.DictReader(f)
        required = {'timestamp_utc', 'object_id'}
        if not required.issubset(set(r.fieldnames or [])):
            raise ValueError(f'events file needs columns {sorted(required)}')
        for row in r:
            entire_trace_count += 1
            ts = row['timestamp_utc']
            if not ts.endswith('Z') or len(ts) < 10:
                raise ValueError(f'expected UTC ISO timestamp: {ts}')
            d = date.fromisoformat(ts[:10])
            oid = row['object_id']
            if oid not in sizes:
                raise ValueError(f'object {oid} missing from size table')
            if begin_history <= d < start:
                history_ids.add(oid)
            elif start <= d < end:
                raw_window_events += 1
                potential.append(((d - start).days, oid))

    selected = sorted(history_ids)
    if not selected:
        raise ValueError('no objects observed in history window')

    if size_seed is not None:
        if ibm_sizes_path is None:
            raise ValueError('ibm_sizes_path required to resample sizes')
        with open_table(ibm_sizes_path) as f:
            ibm = [int(r['size_bytes']) for r in csv.DictReader(f)]
        if not ibm or any(size <= 0 for size in ibm):
            raise ValueError('invalid IBM size sample')
        # Replicate the original CLUE-IBM assignment for a given seed: sample
        # over ALL original object IDs in sorted order, not merely the cohort.
        rng = random.Random(size_seed)
        sizes = {oid: rng.choice(ibm) for oid in sorted(sizes)}

    index = {oid: i for i, oid in enumerate(selected)}
    objects = [Object(oid, sizes[oid]) for oid in selected]
    reads = [[0] * len(objects) for _ in range(days)]
    selected_events = 0
    active_ids = set()
    for day, oid in potential:
        i = index.get(oid)
        if i is not None:
            reads[day][i] += 1
            selected_events += 1
            active_ids.add(oid)

    meta = {
        'data_description': 'CLUE-LDS anonymized Nextcloud-like file access timestamps; IBM object-size sample assigned independently',
        'history_start_utc': begin_history.isoformat(),
        'history_end_exclusive_utc': start.isoformat(),
        'evaluation_start_utc': start.isoformat(),
        'evaluation_end_exclusive_utc': end.isoformat(),
        'history_days': history_days,
        'evaluation_days': days,
        'history_seen_objects': len(selected),
        'eligible_objects_128_KiB_or_more': sum(o.size_bytes >= MIN_SIZE for o in objects),
        'evaluation_selected_events': selected_events,
        'evaluation_selected_objects_with_reads': len(active_ids),
        'evaluation_selected_objects_with_no_reads': len(selected) - len(active_ids),
        'evaluation_all_raw_events': raw_window_events,
        'evaluation_events_excluded_new_ids': raw_window_events - selected_events,
        'total_input_events': entire_trace_count,
        'assigned_size_seed': size_seed if size_seed is not None else 'preassigned_5144',
        'assumptions': [
            'Selection uses only object IDs observed during the history window (no future lookahead).',
            'All selected objects are hypothetically uploaded to S3 at evaluation start (day 0).',
            'All selected objects remain stored for the entire evaluation horizon; actual creations/deletions are unknown.',
            'Previous history selects cohort only; policy inactivity clocks/EWMA are reset at simulation start.',
            'File-access events are treated as full-object GETs; real Nextcloud accesses may not be S3 GETs.',
            'CLUE object sizes are not measured; they are modeled by independent draws from a small IBM sample.',
            'Only 1/128 of CLUE path hashes were included in the source sample.',
            'All costs are from Harris simulator illustrative prices, not actual AWS bills.',
        ],
    }
    return objects, reads, meta


def run_real(events, objects_csv, output, start='2019-01-01', days=180,
             history_days=90, size_seed=None, ibm_sizes=None,
             export_input=True, generate_chart=True):
    o, reads, meta = load_real_cohort(
        events, objects_csv, start, days, history_days, size_seed, ibm_sizes)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if export_input:
        export_trace(output / 'imported_trace', o, reads)

    reports = []
    daily_rows = []
    results = {}
    for p in POLICIES:
        result = simulate(o, reads, p)
        results[p] = result
        reports.append({
            'policy': p,
            'total_usd': result['total_usd'],
            'moves': result['moves'],
            **{k: result['costs'].get(k, 0.0) for k in [
                'initial_put', 'storage', 'get', 'retrieval', 'migration',
                'monitoring', 'minimum_duration', 'controller']},
        })
        daily_rows.extend({'policy': p, **r} for r in result['daily'])
        assert abs(sum(result['costs'].values()) - result['total_usd']) < 1e-6
    it = results['intelligent']['total_usd']
    for r in reports:
        r['savings_vs_it_pct'] = 100.0 * (it - r['total_usd']) / it if it else 0.0

    write_csv(output / 'results.csv', reports)
    write_csv(output / 'daily.csv', daily_rows)
    meta['prices'] = vars(Prices())
    meta['policies'] = list(POLICIES)
    meta['observed_vs_modeled'] = 'Observed: access timestamps and stable anonymized file IDs. Modeled: all sizes, object retention, S3 GET semantics, S3 tier transitions, and costs.'
    (output / 'metadata.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')

    if generate_chart:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(9, 4.8))
            order = list(POLICIES)
            vals = [results[p]['total_usd'] for p in order]
            bars = ax.bar(['Standard','Lifecycle','Intelligent-Tiering','Adaptive EWMA'], vals)
            ax.set_ylabel('Modeled total cost (USD)')
            ax.set_title(f'CLUE observed reads + IBM modeled sizes | {days}-day cohort replay')
            for b,v in zip(bars, vals):
                ax.annotate(f'${v:,.3f}', (b.get_x() + b.get_width()/2, v),
                            ha='center', va='bottom', fontsize=9)
            ax.set_ylim(0, max(vals)*1.18 if vals else 1)
            ax.grid(axis='y', alpha=.2)
            fig.tight_layout()
            fig.savefig(output / 'real_trace_policy_costs.png', dpi=175)
            plt.close(fig)
        except ImportError:
            pass
    return reports, meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', type=Path, default=DEFAULT_EVENTS)
    parser.add_argument('--objects', type=Path, default=DEFAULT_OBJECTS)
    parser.add_argument('--ibm-sizes', type=Path, default=DEFAULT_IBM)
    parser.add_argument('--start', default='2019-01-01', help='Evaluation start, YYYY-MM-DD')
    parser.add_argument('--days', type=int, default=180)
    parser.add_argument('--history-days', type=int, default=90)
    parser.add_argument('--size-seed', type=int, default=None, help='Optional independent reassignment of IBM sizes')
    parser.add_argument('--output', type=Path, default=BASE / 'results' / 'real_trace')
    parser.add_argument('--no-chart', action='store_true')
    args = parser.parse_args()
    result, meta = run_real(args.events, args.objects, args.output,
                            args.start, args.days, args.history_days,
                            args.size_seed, args.ibm_sizes, generate_chart=not args.no_chart)
    print(json.dumps({
        'evaluation_start':meta['evaluation_start_utc'],
        'days':meta['evaluation_days'],
        'objects':meta['history_seen_objects'],
        'observed_evaluation_accesses':meta['evaluation_selected_events'],
        'policies':result,
        'output':str(args.output),
    }, indent=2))


if __name__ == '__main__':
    main()
