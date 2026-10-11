"""Select a topic from the topic list, or use the optional GitHub Actions input."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
import sys


def main() -> int:
    topic = os.environ.get("MANUAL_TOPIC", "").strip()
    if not topic:
        filename = Path(sys.argv[1] if len(sys.argv) > 1 else "topics.txt")
        topics = [line.strip() for line in filename.read_text(encoding="utf-8").splitlines()
                  if line.strip() and not line.lstrip().startswith("#")]
        if not topics:
            raise SystemExit("No topics configured in topics.txt")
        # Each GitHub workflow execution advances the topic even if retried
        # multiple times on the same day. A manual topic always overrides.
        day = dt.datetime.now(dt.timezone.utc).date().toordinal()
        run = int(os.environ.get("GITHUB_RUN_NUMBER", "1") or "1")
        index = (day + max(0, run - 1)) % len(topics)
        topic = topics[index]
    print(" ".join(topic.split())[:170])


if __name__ == "__main__":
    main()
