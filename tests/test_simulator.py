import tempfile
import unittest

from simulator import *


class Tests(unittest.TestCase):
    """Test cases for the simulator."""

    def one(self, p, days=180, size=GIB, events=None, prices=Prices()):
        r = [[0] for _ in range(days)]
        for d, c in (events or {}).items():
            r[d][0] = c
        return simulate([Object("a", size)], r, p, prices)

    def test_standard_analytic(self):
        self.assertAlmostEqual(
            self.one("standard", 30, events={0: 2})["total_usd"],
            0.023 + 2 * 0.0004 / 1000 + 0.005 / 1000,
        )

    def test_it_thresholds(self):
        self.assertEqual(
            self.one("intelligent", 91)["object_days"],
            {"standard": 30, "ia": 60, "aia": 1},
        )

    def test_it_read_reset(self):
        r = self.one("intelligent", 61, events={30: 1})
        self.assertEqual(r["object_days"]["ia"], 1)
        self.assertNotIn("retrieval", r["costs"])
        self.assertNotIn("migration", r["costs"])

    def test_it_small(self):
        r = self.one("intelligent", size=64 * 1024)
        self.assertEqual(r["moves"], 0)
        self.assertNotIn("monitoring", r["costs"])

    def test_exact_128k(self):
        self.assertEqual(self.one("intelligent", 31, MIN_SIZE)["object_days"]["ia"], 1)

    def test_lifecycle_age(self):
        r = self.one("lifecycle", 60, events={d: 1 for d in range(60)})
        self.assertEqual(r["object_days"]["ia"], 30)
        self.assertAlmostEqual(r["costs"]["retrieval"], 0.3)

    def test_minimum_expiry(self):
        self.assertAlmostEqual(
            self.one("lifecycle", 31)["costs"]["minimum_duration"],
            29 * 0.0125 / 30,
        )

    def test_lifecycle_small(self):
        self.assertEqual(self.one("lifecycle", size=64 * 1024)["moves"], 0)

    def test_cold_it_analytic(self):
        self.assertAlmostEqual(
            self.one("intelligent")["total_usd"],
            0.023 + 2 * 0.0125 + 3 * 0.004 + 6 * 0.0000025 + 0.000005,
        )

    def test_controller_cost(self):
        self.assertAlmostEqual(
            self.one("adaptive", 30, prices=Prices(controller=0.1))["total_usd"]
            - self.one("adaptive", 30)["total_usd"],
            0.1,
        )

    def test_causal_prefix(self):
        o = [Object("a", GIB)]
        a = simulate(o, [[0]] * 90, "adaptive")
        b = simulate(o, [[0]] * 45 + [[1]] * 45, "adaptive")
        self.assertEqual(a["daily"][:45], b["daily"][:45])

    def test_promotion_copy(self):
        r = self.one("adaptive", 90, events={d: 1 for d in range(40, 90)})
        self.assertGreaterEqual(r["moves"], 2)
        self.assertGreater(r["costs"]["migration"], 0.01)

    def test_reproducible(self):
        self.assertEqual(generate("mixed", 17), generate("mixed", 17))

    def test_accounting(self):
        for p in POLICIES:
            o, r = generate("bursty", n=10)
            x = simulate(o, r, p)
            self.assertAlmostEqual(x["total_usd"], sum(x["costs"].values()))
            self.assertEqual(x["total_usd"], x["daily"][-1]["cumulative_usd"])

    def test_trace_roundtrip(self):
        with tempfile.TemporaryDirectory() as t:
            o, r = generate("mixed", n=5, days=10)
            export_trace(Path(t), o, r)
            self.assertEqual((o, r), load_trace(Path(t), 10))


if __name__ == "__main__":
    unittest.main()
