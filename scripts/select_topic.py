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
        index = dt.datetime.now(dt.timezone.utc).date().toordinal() % len(topics)
        topic = topics[index]
    print(" ".join(topic.split())[:170])


if __name__ == "__main__":
    main()
