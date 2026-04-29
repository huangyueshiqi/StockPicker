import unittest

from fund.run_cluster_batch import parse_clusters_arg


class TestParseClustersArg(unittest.TestCase):
    def test_all_returns_none(self):
        self.assertIsNone(parse_clusters_arg("all"))
        self.assertIsNone(parse_clusters_arg(" ALL "))

    def test_single_int(self):
        self.assertEqual(parse_clusters_arg("0"), [0])
        self.assertEqual(parse_clusters_arg("  12 "), [12])

    def test_comma_separated(self):
        self.assertEqual(parse_clusters_arg("0,1,2"), [0, 1, 2])
        self.assertEqual(parse_clusters_arg("0, 1, 2"), [0, 1, 2])

    def test_bracket_list(self):
        self.assertEqual(parse_clusters_arg("[0,1,2]"), [0, 1, 2])
        self.assertEqual(parse_clusters_arg(" [ 0, 1, 2 ] "), [0, 1, 2])


if __name__ == "__main__":
    unittest.main()

