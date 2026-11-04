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
            
    def test_negative_object_size(self):
        objects = [Object("file1", -100)]
        reads = [[0]]

        with self.assertRaises(ValueError):
            simulate(objects, reads, "standard")


    def test_duplicate_object_ids(self):
        objects = [
            Object("file1", 1024),
            Object("file1", 2048)
        ]
        reads = [[0, 0]]

        with self.assertRaises(ValueError):
            simulate(objects, reads, "standard")

    def test_negative_storage_price(self):
        objects = [Object("file1", GIB)]
        reads = [[0]]
        prices = Prices(standard=-0.023)

        with self.assertRaises(ValueError):
            simulate(objects, reads, "standard", prices=prices)
     
    def test_standard_storage_cost(self):
        objects = [Object("file1", GIB)]
        reads = [[0] for _ in range(30)]

        result = simulate(objects, reads, "standard")

        self.assertAlmostEqual(
            result["costs"]["storage"],
            0.023
        )

        self.assertAlmostEqual(
            result["costs"]["initial_put"],
            0.005 / 1000
        )

        self.assertAlmostEqual(
            result["total_usd"],
            0.023 + 0.005 / 1000
        )
    def test_ia_minimum_storage_duration(self):
        objects = [Object("file1", GIB)]
        reads = [[0] for _ in range(40)]

        result = simulate(objects, reads, "lifecycle")

        expected_ia_storage = 10 * 0.0125 / 30
        expected_minimum_charge = 20 * 0.0125 / 30

        self.assertAlmostEqual(
            result["costs"]["minimum_duration"],
            expected_minimum_charge
        )

        self.assertAlmostEqual(
            result["costs"]["storage"],
            30 * 0.023 / 30 + expected_ia_storage
        )
    def test_ia_early_promotion_cost(self):
        # Test the cost of moving a file from IA back to Standard.

        objects = [Object("file1", GIB)]
        reads = [[0] for _ in range(45)]

        for day in range(15, 45):
            reads[day][0] = 1

        result = simulate(objects, reads, "adaptive")

        self.assertGreaterEqual(result["moves"], 2)

        expected_copy_cost = 0.01 + 0.001 / 1000 + 0.005 / 1000

        self.assertGreaterEqual(
            result["costs"]["migration"],
            expected_copy_cost
        )
    def test_ia_early_exit_minimum_charge(self):
        # Test the remaining IA charge after early promotion.

        objects = [Object("file1", GIB)]
        reads = [[0] for _ in range(45)]

        for day in range(15, 45):
            reads[day][0] = 1

        result = simulate(objects, reads, "adaptive")

        expected_charge = 21 * 0.0125 / 30

        self.assertAlmostEqual(
            result["costs"]["minimum_duration"],
            expected_charge
        )
        
    def test_ia_get_and_retrieval_cost(self):
        # Test GET and retrieval costs for Standard-IA.

        objects = [Object("file1", GIB)]
        reads = [[0] for _ in range(35)]

        # Read the file twice after it moves to IA.
        reads[31][0] = 2

        result = simulate(objects, reads, "lifecycle")

        expected_get = 2 * (0.001 / 1000)
        expected_retrieval = 2 * 0.01

        self.assertAlmostEqual(
            result["costs"]["get"],
            expected_get
        )

        self.assertAlmostEqual(
            result["costs"]["retrieval"],
            expected_retrieval
        )
        
    def test_intelligent_get_and_retrieval_cost(self):
        # Test GET and retrieval costs for Intelligent-Tiering.

        objects = [Object("file1", GIB)]
        reads = [[0] for _ in range(40)]
        reads[35][0] = 2

        result = simulate(objects, reads, "intelligent")

        expected_get = 2 * (0.0004 / 1000)

        self.assertAlmostEqual(
            result["costs"]["get"],
            expected_get
        )

        self.assertEqual(
            result["costs"].get("retrieval", 0),
            0
        )

        self.assertEqual(
            result["costs"].get("migration", 0),
            0
        )
        
    def test_lifecycle_migration_cost(self):
        # Test the cost of moving a file from Standard to IA.

        objects = [Object("file1", GIB)]
        reads = [[0] for _ in range(31)]

        result = simulate(objects, reads, "lifecycle")

        expected_migration = 0.01 / 1000

        self.assertEqual(result["moves"], 1)

        self.assertAlmostEqual(
            result["costs"]["migration"],
            expected_migration
        )

if __name__ == "__main__":
    unittest.main()
