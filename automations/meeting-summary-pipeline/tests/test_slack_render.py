from meeting_summary_pipeline.slack_render import render_slack_message


def test_render_slack_message_includes_required_sections_and_archive():
    summary = """## Executive Summary
- A useful update.

## Key Decisions
- None stated.

## Action Items
- Justin: follow up.

## Cross-Team FYIs
- Labs needs support.

## Risks / Blockers
- None stated.
"""
    msg = render_slack_message(
        topic="IPN Labs Programming Sync",
        meeting_date="2026-06-01",
        group="ipn-labs",
        summary_markdown=summary,
        drive_folder_url="https://drive.google.com/folders/abc",
        attendees=["Justin", "Maya"],
    )

    assert "*IPN Labs Programming Sync*" in msg
    assert "*Date:* 2026-06-01 | *Group:* `ipn-labs`" in msg
    assert "*Attendees:* Justin, Maya" in msg
    assert "*Archive:* https://drive.google.com/folders/abc" in msg
    assert "## Action Items" in msg
