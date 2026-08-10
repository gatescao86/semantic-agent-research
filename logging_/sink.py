"""JSONL sink for RunLog records — one file per run_id, append-only.

Writing immediately (not buffered) means a crashed or interrupted experiment
run leaves a complete, readable partial log rather than losing everything.
"""

from __future__ import annotations

import json
from pathlib import Path

from logging_.schema import RunLog

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


class RunLogSink:
    def __init__(self, run_id: str, runs_dir: Path = RUNS_DIR) -> None:
        self.run_id = run_id
        self.path = runs_dir / f"{run_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, log: RunLog) -> None:
        with open(self.path, "a") as f:
            f.write(log.model_dump_json() + "\n")

    def read_all(self) -> list[RunLog]:
        if not self.path.exists():
            return []
        logs = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    logs.append(RunLog.model_validate(json.loads(line)))
        return logs
