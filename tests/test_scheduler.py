import tempfile
import unittest
from datetime import datetime, timezone

from milou_news.models import default_registry
from milou_news.scheduler import Scheduler
from milou_news.supervisor import SupervisorDispatcher
from milou_news.archive import ReportStore
from milou_news.web import make_handler
from http.server import ThreadingHTTPServer
import threading
import urllib.request


class SchedulerTests(unittest.TestCase):
    def test_timezone_due_and_idempotent_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler = Scheduler(directory + "/runs.sqlite")
            scheduler.configure({"routines": [{"name": "launch-decoder", "cadence": "daily", "at": "09:00", "timezone": "Europe/Amsterdam", "retry_limit": 1}]})
            now = datetime(2026, 9, 14, 7, 5, tzinfo=timezone.utc)  # 09:05 local
            self.assertEqual(scheduler.due(now), (("launch-decoder", "daily:2026-09-14"),))
            payload = {"launch-decoder": {"launches": []}}
            scheduler.run_due(SupervisorDispatcher(default_registry()), payload, now)
            self.assertEqual(scheduler.due(now), ())
            self.assertEqual(scheduler.ledger()[0]["status"], "success")

    def test_disabled_and_weekly_schedule(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler = Scheduler(directory + "/runs.sqlite")
            scheduler.configure({"routines": [{"name": "launch-radar", "cadence": "weekly", "weekday": 0, "at": "09:00", "timezone": "UTC", "enabled": False}]})
            self.assertEqual(scheduler.due(datetime(2026, 9, 13, 10, tzinfo=timezone.utc)), ())

    def test_failures_are_visible_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler = Scheduler(directory + "/runs.sqlite")
            scheduler.configure({"routines": [{"name": "launch-decoder", "cadence": "daily", "at": "00:00", "timezone": "UTC", "retry_limit": 1}]})
            now = datetime(2026, 9, 14, 1, tzinfo=timezone.utc)
            dispatcher = SupervisorDispatcher(default_registry())
            scheduler.run_due(dispatcher, {"launch-decoder": None}, now)
            self.assertEqual(scheduler.ledger()[0]["status"], "failed")
            self.assertEqual(len(scheduler.due(now)), 1)
            scheduler.run_due(dispatcher, {"launch-decoder": None}, now)
            self.assertEqual(scheduler.due(now), ())
            self.assertEqual(scheduler.status(now)["failures"], 1)

    def test_configuration_rejects_write_access(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler = Scheduler(directory + "/runs.sqlite")
            with self.assertRaises(PermissionError):
                scheduler.configure({"routines": [{"name": "x", "access": "write"}]})

    def test_authenticated_status_endpoint_exposes_scheduler_health(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler = Scheduler(directory + "/runs.sqlite")
            scheduler.configure({"routines": []})
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ReportStore(directory), "secret", scheduler=scheduler))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                request = urllib.request.Request("http://127.0.0.1:%d/status" % server.server_port,
                                                 headers={"Authorization": "Bearer secret"})
                self.assertIn('"configured": 0', urllib.request.urlopen(request).read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
