"""Per-source outcome records and the append-only JSONL run log."""

import json
import os
import time

from ..config import OUTPUT_DIR, RUNLOG


def outcome(status, output=None, reason=None):
    """A per-source result for the run log: status is converted / captured /
    skipped / failed."""
    return {"status": status, "output": output, "reason": reason}


def log_run(url, result, target):
    """Append one source's outcome to output/runlog.jsonl (an append-only audit log —
    a record of coverage, not a database). Best-effort: never fail the run over it."""
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "url": url,
        "target": target,
        **result,
    }
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(RUNLOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
