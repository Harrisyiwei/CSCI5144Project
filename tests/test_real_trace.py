import csv
import gzip
from pathlib import Path
import tempfile
import unittest

from real_trace import load_real_cohort
from simulator import POLICIES, simulate, export_trace, load_trace


class RealTraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.obj = self.folder / 'objects.csv.gz'
        self.ev = self.folder / 'events.csv.gz'
        with gzip.open(self.obj, 'wt', newline='') as f:
            w=csv.writer(f)
            w.writerow(['object_id','assigned_size_bytes'])
            w.writerows([['a', 1024*1024], ['b', 512], ['c', 1024*1024]])
        with gzip.open(self.ev, 'wt', newline='') as f:
            w=csv.writer(f)
            w.writerow(['timestamp_utc','object_id'])
            w.writerows([
                ['2018-12-02T00:00:00Z', 'a'],
                ['2018-12-31T23:59:59Z', 'b'],
                ['2019-01-01T00:00:00Z', 'a'],
                ['2019-01-01T00:01:00Z', 'a'],
                ['2019-01-02T00:00:00Z', 'c'],
                ['2019-01-03T00:00:00Z', 'b'],
                ['2019-01-04T00:00:00Z', 'a'],
            ])

    def test_history_only_cohort_prevents_future_leakage(self):
        o, reads, meta = load_real_cohort(self.ev, self.obj, '2019-01-01', days=4, history_days=30)
        self.assertEqual([x.id for x in o], ['a','b'])
        self.assertEqual(reads, [[2,0], [0,0], [0,1], [1,0]])
        self.assertEqual(meta['evaluation_selected_events'], 4)
        self.assertEqual(meta['evaluation_events_excluded_new_ids'], 1)

    def test_exact_day_boundaries_and_no_future_selection(self):
        o, reads, meta = load_real_cohort(self.ev, self.obj, '2019-01-01', days=2, history_days=30)
        self.assertEqual([x.id for x in o], ['a','b'])
        self.assertEqual(reads, [[2,0], [0,0]])

    def test_original_simulator_accepts_exported_trace(self):
        o, reads, _ = load_real_cohort(self.ev, self.obj, '2019-01-01', days=4, history_days=30)
        out = self.folder / 'export'
        export_trace(out, o, reads)
        o2, r2 = load_trace(out, 4)
        self.assertEqual(o,o2)
        self.assertEqual(reads,r2)
        for policy in POLICIES:
            x = simulate(o2, r2, policy)
            self.assertGreater(x['total_usd'],0)
            self.assertAlmostEqual(x['total_usd'],sum(x['costs'].values()),places=9)

    def test_validates_no_cohort(self):
        with self.assertRaises(ValueError):
            load_real_cohort(self.ev, self.obj, '2017-01-01', days=4, history_days=30)

    def test_rejects_zero_days(self):
        with self.assertRaises(ValueError):
            load_real_cohort(self.ev, self.obj, '2019-01-01', days=0)

    def test_data_sample_has_consistent_cohort(self):
        base = Path(__file__).resolve().parents[1]
        ev = base / 'data' / 'clue_ibm_accesses_with_assigned_sizes.csv.gz'
        ob = base / 'data' / 'clue_ibm_objects.csv.gz'
        if not ev.exists() or not ob.exists():
            self.skipTest('CLUE files not bundled')
        o, r, meta = load_real_cohort(ev, ob, '2019-01-01', days=180, history_days=90)
        self.assertEqual(meta['history_seen_objects'], 5841)
        self.assertEqual(meta['evaluation_selected_events'], 12579)
        self.assertEqual(sum(sum(day) for day in r), meta['evaluation_selected_events'])

    def test_seed_reproduces_previous_assignment(self):
        base = Path(__file__).resolve().parents[1]
        ev = base / 'data' / 'clue_ibm_accesses_with_assigned_sizes.csv.gz'
        ob = base / 'data' / 'clue_ibm_objects.csv.gz'
        ibm = base / 'data' / 'ibm_object_sizes_sample.csv'
        if not (ev.exists() and ob.exists() and ibm.exists()):
            self.skipTest('CLUE files not bundled')
        o1, _, _ = load_real_cohort(ev, ob, '2019-01-01', days=90)
        o2, _, _ = load_real_cohort(ev, ob, '2019-01-01', days=90, size_seed=5144, ibm_sizes_path=ibm)
        self.assertEqual(o1, o2)

if __name__ == '__main__':
    unittest.main()
