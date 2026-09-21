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
        api = FixtureApi({"/user": {"login": "octocat"}}, {"/users/octocat/events?per_page=100": "HTTP 403: forbidden"})
        report = generate_github_radar(api, self.config)
        self.assertIn("user activity: HTTP 403: forbidden", report)

    def test_kpis_and_empty_activity_are_distinct_from_coverage(self):
        api = FixtureApi(
            {"/user": {"login": "octocat"},
             "/users/octocat/events?per_page=100": [],
             "/orgs/Allied-Steel-Buildings/repos?per_page=100&sort=updated": []})
        report = generate_github_radar(api, self.config,
                                       datetime(2026, 9, 15, 9, tzinfo=timezone.utc))
        self.assertIn("No activity to report.", report)
        self.assertIn("Repositories scanned:**", report)
        self.assertIn("Coverage, pagination", report)
        self.assertNotIn("Priority: Allied-Steel-Buildings activity", report)

    def test_user_activity_uses_the_documented_endpoint(self):
        """GitHub serves this feed from /users/{username}/events.

        There is no /user/events endpoint; requesting one returns HTTP 404 and
        silently drops the authenticated user's activity from every report.
        """
        requested = []

        class Recording(FixtureApi):
            def get(self, endpoint):
                requested.append(endpoint)
                return super().get(endpoint)

        api = Recording({"/user": {"login": "octocat"},
                         "/users/octocat/events?per_page=100": [],
                         "/orgs/Allied-Steel-Buildings/repos?per_page=100&sort=updated": []})
        generate_github_radar(api, self.config, datetime(2026, 9, 15, 9, tzinfo=timezone.utc))
        self.assertIn("/users/octocat/events?per_page=100", requested)
        self.assertNotIn("/user/events?per_page=100", requested)

    def test_unknown_login_reports_the_gap_rather_than_guessing(self):
        api = FixtureApi({}, {"/user": "HTTP 401: bad credentials"})
        report = generate_github_radar(api, self.config,
                                       datetime(2026, 9, 15, 9, tzinfo=timezone.utc))
        self.assertIn("authenticated login is unknown", report)

    def test_config_is_bounded(self):
        with self.assertRaises(ValueError):
            RadarConfig.from_mapping({"repositories": ["a/b"], "window_hours": 745})


if __name__ == "__main__":
    unittest.main()
