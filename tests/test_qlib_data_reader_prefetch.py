import unittest

import pandas as pd


class _TestableQlibDataReader:
    pass


class TestQlibDataReaderPrefetch(unittest.TestCase):
    def test_prefetch_only_loads_once_and_slices_by_end_date(self):
        from framework.qlib_data_reader import QlibDataReader

        class Testable(QlibDataReader):
            def __init__(self, **kwargs):
                super().__init__(
                    mapping_file="x",
                    stock_pool_file="y",
                    macro_file="z",
                    **kwargs,
                )
                self.load_calls = 0
                self.last_load_args = None

            def _load_merged_data(self, start_date: str, end_date: str, filter_end_date: bool):
                self.load_calls += 1
                self.last_load_args = (start_date, end_date, filter_end_date)
                df = pd.DataFrame(
                    {
                        "datetime": pd.to_datetime(["2021-01-04", "2021-04-06", "2021-04-06"]),
                        "S_INFO_WINDCODE": ["000001.SZ", "000001.SZ", "000002.SZ"],
                        "TRADE_DT": ["20210104", "20210406", "20210406"],
                        "x": [1, 2, 3],
                    }
                )
                return df

        reader = Testable(backtest_start_date="20210101", backtest_end_date="20211231", lookback_years=5)

        d1 = reader.read_data(start_date="20160101", end_date="20210104")["qlib_data"]
        self.assertEqual(reader.load_calls, 1)
        self.assertTrue((d1["TRADE_DT"] == "20210104").all())

        d2 = reader.read_data(start_date="20160406", end_date="20210406")["qlib_data"]
        self.assertEqual(reader.load_calls, 1)
        self.assertTrue((d2["TRADE_DT"] == "20210406").all())


if __name__ == "__main__":
    unittest.main()

