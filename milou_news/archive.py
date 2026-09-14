"""Local, dated report persistence for the read-only delivery slice."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


class ReportStore:
    """Persist reports below a directory without modifying source data."""

    def __init__(self, root):
        self.root = Path(root)

    def save(self, markdown: str, generated_at: Optional[datetime] = None,
             metadata: Optional[Dict] = None) -> Path:
        generated_at = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        directory = self.root / generated_at.strftime("%Y") / generated_at.strftime("%m") / generated_at.strftime("%d")
        directory.mkdir(parents=True, exist_ok=True)
        payload = {"generated_at": generated_at.isoformat(), "markdown": markdown, "metadata": metadata or {}}
        routine = (metadata or {}).get("routine")
        suffix = ""
        if routine:
            safe_routine = re.sub(r"[^a-z0-9-]+", "-", str(routine).lower()).strip("-")
            suffix = "-" + safe_routine if safe_routine else ""
        stem = "report-" + generated_at.strftime("%H%M%S") + suffix
        json_path = directory / (stem + ".json")
        markdown_path = directory / (stem + ".md")
        counter = 2
        while json_path.exists() or markdown_path.exists():
            json_path = directory / ("%s-%d.json" % (stem, counter))
            markdown_path = directory / ("%s-%d.md" % (stem, counter))
            counter += 1
        json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        markdown_path.write_text(markdown, encoding="utf-8")
        return json_path

    def reports(self) -> List[Dict]:
        reports = []
        for path in self.root.glob("*/*/*/report-*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["path"] = str(path)
                reports.append(payload)
            except (OSError, ValueError):
                continue
        return sorted(reports, key=lambda item: item.get("generated_at", ""), reverse=True)

    def get(self, path: str) -> Optional[Dict]:
        candidate = (self.root / path).resolve()
        if self.root.resolve() not in candidate.parents or candidate.suffix != ".json":
            return None
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
