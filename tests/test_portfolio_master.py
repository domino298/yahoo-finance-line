import unittest

from portfolio_master import DEFAULT_EXCEL_PATH, portfolios_from_rows, read_excel_master, unique_symbols_from_rows


class PortfolioMasterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = read_excel_master(DEFAULT_EXCEL_PATH)

    def test_master_has_required_values(self):
        self.assertGreater(len(self.rows), 0)
        for row in self.rows:
            self.assertNotEqual(row["portfolio_id"], "")
            self.assertTrue(row["portfolio_name"])
            self.assertTrue(row["symbol"])
            self.assertTrue(row["name"])

    def test_unique_symbols_are_actually_unique(self):
        symbols = [item["symbol"] for item in unique_symbols_from_rows(self.rows)]
        self.assertEqual(len(symbols), len(set(symbols)))

    def test_portfolio_counts_match_master_rows(self):
        payload = portfolios_from_rows(self.rows, DEFAULT_EXCEL_PATH)
        rendered_count = sum(len(item["symbols"]) for item in payload["portfolios"])
        self.assertEqual(rendered_count, len(self.rows))
        for portfolio in payload["portfolios"]:
            self.assertEqual(portfolio["count_text"], f"{len(portfolio['symbols'])}件")


if __name__ == "__main__":
    unittest.main()
