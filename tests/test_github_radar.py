import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from milou_news.github_radar import FixtureApi, RadarConfig, generate_github_radar


class GithubRadarTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        with (root / "fixtures/github-radar.json").open(encoding="utf-8") as handle:
            self.fixture = json.load(handle)
        with (root / "fixtures/github-radar-config.json").open(encoding="utf-8") as handle:
            self.config = RadarConfig.from_mapping(json.load(handle))

    def test_fixture_report_is_cited_bounded_and_deduplicated(self):
        report = generate_github_radar(
            FixtureApi(self.fixture["responses"]), self.config,
            datetime(2026, 9, 15, 9, tzinfo=timezone.utc),
        )
        self.assertIn("Authenticated user:** octocat", report)
        self.assertIn("https://github.com/hkdeven/milou/commit/u1", report)
        self.assertIn("https://github.com/hkdeven/milou/pull/1", report)
        self.assertEqual(report.count("https://github.com/hkdeven/milou/commit/u1"), 1)
        self.assertIn("Read-only authenticated", report)

    def test_permission_errors_are_visible(self):
        api = FixtureApi({"/user": {"login": "octocat"}}, {"/user/events?per_page=100": "HTTP 403: forbidden"})
        report = generate_github_radar(api, self.config)
        self.assertIn("user activity: HTTP 403: forbidden", report)

    def test_config_is_bounded(self):
        with self.assertRaises(ValueError):
            RadarConfig.from_mapping({"repositories": ["a/b"], "window_hours": 745})


if __name__ == "__main__":
    unittest.main()
