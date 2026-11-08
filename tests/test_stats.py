import unittest

from eval.stats import mcnemar_exact, rates, wilson


class StatsTests(unittest.TestCase):
    def test_wilson_matches_reference_values(self):
        low, high = wilson(31, 45)
        self.assertAlmostEqual(low, 0.5434, places=3)
        self.assertAlmostEqual(high, 0.8047, places=3)
        self.assertIsNone(wilson(0, 0))
        self.assertEqual(wilson(0, 3)[0], 0.0)

    def test_mcnemar_exact_two_sided(self):
        self.assertEqual(mcnemar_exact(0, 0), 1.0)
        self.assertAlmostEqual(mcnemar_exact(6, 2), 0.2890625)
        self.assertAlmostEqual(mcnemar_exact(0, 6), 0.03125)

    def test_rates_count_invalid_as_incorrect(self):
        records = [{"gold": "violation", "pred": "allow"}, {"gold": "violation", "pred": "parse_error", "error": "x"},
                   {"gold": "allow", "pred": "escalate"}, {"gold": "allow", "pred": "allow"}]
        r = rates(records)
        self.assertEqual(r["accuracy"], (1, 4))
        self.assertEqual(r["unsafe-allow rate"], (1, 2))
        self.assertEqual(r["false-block rate"], (1, 2))
        self.assertEqual(r["invalid"], (1, 4))


if __name__ == "__main__":
    unittest.main()
