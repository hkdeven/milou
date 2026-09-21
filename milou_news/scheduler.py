"""Durable local scheduler for registered, read-only routines."""
import json
import sqlite3
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


class Scheduler:
    def __init__(self, database, registry=None):
        self.database = str(database)
        self.registry = registry
        self._init_db()

    def _connect(self):
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self):
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS routine_config (
              name TEXT PRIMARY KEY, cadence TEXT NOT NULL, at TEXT NOT NULL,
              timezone TEXT NOT NULL, weekday INTEGER, enabled INTEGER NOT NULL,
              retry_limit INTEGER NOT NULL DEFAULT 1, access TEXT NOT NULL,
              fixture TEXT
            );
            CREATE TABLE IF NOT EXISTS run_ledger (
              id INTEGER PRIMARY KEY AUTOINCREMENT, routine TEXT NOT NULL,
              due_key TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL,
              error TEXT, started_at TEXT, completed_at TEXT, report_path TEXT,
              UNIQUE(routine, due_key)
            );
            """)

    def configure(self, config):
        """Replace registered configuration; reject anything not read-only."""
        entries = config.get("routines", config) if isinstance(config, dict) else config
        with self._connect() as db:
            for item in entries:
                if item.get("access", "read-only") != "read-only":
                    raise PermissionError("scheduler only permits read-only routines")
                if self.registry is not None:
                    try:
                        registered = self.registry.get(item["name"])
                    except KeyError:
                        raise ValueError("routine is not registered: %s" % item["name"])
                    if registered.access != "read-only":
                        raise PermissionError("registered routine is not read-only: %s" % item["name"])
                cadence = item.get("cadence", "on-demand")
                if cadence not in ("daily", "weekly", "on-demand"):
                    raise ValueError("unsupported cadence: %s" % cadence)
                if cadence != "on-demand":
                    datetime.strptime(item.get("at", "00:00"), "%H:%M")
                    ZoneInfo(item.get("timezone", "UTC"))
                weekday = item.get("weekday")
                if cadence == "weekly" and (not isinstance(weekday, int) or weekday not in range(7)):
                    raise ValueError("weekly routines require weekday 0-6")
                db.execute("""INSERT INTO routine_config
                    (name,cadence,at,timezone,weekday,enabled,retry_limit,access)
                    VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET
                    cadence=excluded.cadence,at=excluded.at,timezone=excluded.timezone,
                    weekday=excluded.weekday,enabled=excluded.enabled,
                    retry_limit=excluded.retry_limit,access=excluded.access""",
                    (item["name"], cadence, item.get("at", "00:00"), item.get("timezone", "UTC"),
                     weekday, int(item.get("enabled", True)), int(item.get("retry_limit", 1)), "read-only"))
                if "fixture" in item:
                    db.execute("UPDATE routine_config SET fixture=? WHERE name=?", (item["fixture"], item["name"]))

    def _due(self, row, now):
        local = now.astimezone(ZoneInfo(row["timezone"]))
        scheduled = time.fromisoformat(row["at"])
        if local.time() < scheduled:
            return None
        if row["cadence"] == "daily":
            return local.strftime("daily:%Y-%m-%d")
        if row["cadence"] == "weekly" and local.weekday() == row["weekday"]:
            return local.strftime("weekly:%G-W%V")
        return None

    def due(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self._connect() as db:
            rows = db.execute("SELECT * FROM routine_config WHERE enabled=1 ORDER BY name").fetchall()
            result = []
            for row in rows:
                key = self._due(row, now)
                if not key:
                    continue
                ledger = db.execute("SELECT * FROM run_ledger WHERE routine=? AND due_key=?", (row["name"], key)).fetchone()
                if ledger is None or (ledger["status"] == "failed" and ledger["attempts"] < row["retry_limit"] + 1):
                    result.append((row["name"], key))
            return tuple(result)

    def run_due(self, dispatcher, payloads, now=None, store=None):
        """Run every due routine.

        ``store`` is an optional :class:`~milou_news.archive.ReportStore`. Without
        it a scheduled run produced a report and discarded it; with it the report
        is persisted, its structure kept, and its path recorded in the ledger so
        a run can be traced to what it produced. A storage failure is recorded as
        a run failure rather than passing silently.
        """
        now = now or datetime.now(timezone.utc)
        results = []
        for name, key in self.due(now):
            with self._connect() as db:
                row = db.execute("SELECT * FROM run_ledger WHERE routine=? AND due_key=?", (name, key)).fetchone()
                attempts = (row["attempts"] if row else 0) + 1
                if row:
                    db.execute("UPDATE run_ledger SET status='running', attempts=?, started_at=?, error=NULL WHERE id=?", (attempts, now.isoformat(), row["id"]))
                else:
                    db.execute("INSERT INTO run_ledger(routine,due_key,status,attempts,started_at) VALUES(?,?,?,?,?)", (name, key, "running", attempts, now.isoformat()))
            result = dispatcher.dispatch(name, payloads.get(name, {}))
            report_path, store_error = None, None
            if store is not None and result.report is not None:
                try:
                    report_path = str(store.save(
                        result.report, generated_at=now,
                        metadata={"routine": name, "access": "read-only",
                                  "status": "scheduled"},
                        report=getattr(result, "structured", None)))
                except OSError as exc:
                    store_error = "report not stored: %s: %s" % (type(exc).__name__, exc)
            with self._connect() as db:
                error = result.error or store_error
                status = "success" if error is None else "failed"
                db.execute("UPDATE run_ledger SET status=?, error=?, completed_at=?, report_path=? WHERE routine=? AND due_key=?",
                           (status, error, now.isoformat(), report_path, name, key))
            results.append(result)
        return tuple(results)

    def ledger(self):
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM run_ledger ORDER BY id DESC").fetchall()]

    def status(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self._connect() as db:
            configured = db.execute("SELECT * FROM routine_config ORDER BY name").fetchall()
        ledger = self.ledger()
        return {"configured": len(configured), "enabled": sum(row["enabled"] for row in configured),
                "due": len(self.due(now)), "runs": len(ledger),
                "failures": sum(item["status"] == "failed" for item in ledger),
                "last_run": ledger[0] if ledger else None,
                "routines": [dict(row) for row in configured]}

    def load_config(self, path):
        self.configure(json.loads(Path(path).read_text(encoding="utf-8")))
