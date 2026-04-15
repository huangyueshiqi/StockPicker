import unittest


class TestMappingRegeneration(unittest.TestCase):
    def test_should_generate_mapping_when_strategy_regenerated(self):
        import qlib_premium_value_strategy as s

        self.assertTrue(s.should_generate_mapping(strategy_regenerated=True, mapping_exists=True))

    def test_should_generate_mapping_when_mapping_missing(self):
        import qlib_premium_value_strategy as s

        self.assertTrue(s.should_generate_mapping(strategy_regenerated=False, mapping_exists=False))

    def test_should_not_generate_mapping_when_reusing_strategy_and_mapping_exists(self):
        import qlib_premium_value_strategy as s

        self.assertFalse(s.should_generate_mapping(strategy_regenerated=False, mapping_exists=True))


if __name__ == "__main__":
    unittest.main()

