"""The append-only JSONL run log of per-source outcomes."""

import json
import os
import time

from ..config import OUTPUT_DIR, RUNLOG
from ..models import Outcome


def log_run(url: str, result: Outcome, target: str) -> None:
    """Append one source's outcome to output/runlog.jsonl.

    An append-only audit log — a record of coverage, not a database.
    Best-effort: never fail the run over it.
    """
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "url": url,
        "target": target,
        "status": result.status,
        "output": result.output,
        "reason": result.reason,
    }
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(RUNLOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
