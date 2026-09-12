import unittest

from scripts.build_cloud_site import HTML, INDEX_PATH


class CloudSiteBuildTest(unittest.TestCase):
    def test_generated_index_matches_builder(self):
        self.assertEqual(INDEX_PATH.read_text(encoding="utf-8"), HTML)

    def test_refresh_is_manual_and_failure_values_are_preserved(self):
        self.assertNotIn("setInterval(", HTML)
        self.assertNotIn('item.price = "";', HTML)
        self.assertIn("取得失敗（前回値）", HTML)

    def test_status_uses_japan_quote_time(self):
        self.assertIn("newestJapanQuoteTime", HTML)
        self.assertIn("株価時点（日本株）", HTML)

    def test_site_opens_without_password_gate(self):
        self.assertNotIn('type="password"', HTML)
        self.assertNotIn("decryptData", HTML)
        self.assertNotIn("パスワード未入力", HTML)
        self.assertIn("loadPublishedData", HTML)
        self.assertIn("data.json", HTML)

    def test_site_syncs_yahoo_portfolios_on_open_and_refresh(self):
        self.assertIn('action: "portfolios"', HTML)
        self.assertIn("syncYahooPortfolioList", HTML)
        self.assertIn("mergeYahooPortfolioSnapshot", HTML)
        self.assertIn("Yahoo銘柄・タブ同期中", HTML)
        self.assertIn("await syncYahooPortfolioList();", HTML)


if __name__ == "__main__":
    unittest.main()
