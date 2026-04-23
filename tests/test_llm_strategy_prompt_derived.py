import unittest


class TestLlmStrategyPromptDerived(unittest.TestCase):
    def test_prompt_mentions_derived_features(self):
        from tools import llm_strategy_generator as g

        self.assertIn("derived_features", g.LLM_STRATEGY_PROMPT)
        self.assertIn("base_column", g.LLM_STRATEGY_PROMPT)


if __name__ == "__main__":
    unittest.main()

