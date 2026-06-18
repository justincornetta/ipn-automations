from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from meeting_summary_pipeline.config import load_config
from meeting_summary_pipeline.pipeline import MeetingSummaryPipeline


def _load_event_payload(raw: str | None) -> dict | None:
    if not raw:
        return None
    return json.loads(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the IPN meeting summary pipeline.")
    parser.add_argument("--event-json", default=None, help="Raw Zoom webhook event JSON.")
    parser.add_argument("--meeting-id", default=None, help="Zoom meeting id or UUID to process.")
    parser.add_argument("--recording-file-id", default=None, help="Specific Zoom recording file id to process.")
    parser.add_argument("--poll", action="store_true", help="Poll recent Zoom cloud recordings.")
    parser.add_argument("--dry-run", action="store_true", help="Generate artifacts without posting to Slack.")
    args = parser.parse_args()

    cfg = load_config()
    pipeline = MeetingSummaryPipeline(cfg)
    event_payload = _load_event_payload(args.event_json)

    if args.poll or not (event_payload or args.meeting_id):
        result = pipeline.poll_recent(dry_run=args.dry_run)
    else:
        result = pipeline.process_event(
            event_payload=event_payload,
            meeting_id=args.meeting_id,
            recording_file_id=args.recording_file_id,
            dry_run=args.dry_run,
        )

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
