from meeting_summary_pipeline.transcript import truncate_transcript, vtt_to_text


def test_vtt_to_text_removes_headers_timestamps_tags_and_duplicates():
    vtt = """WEBVTT

1
00:00:01.000 --> 00:00:04.000
<v Justin>Welcome to the meeting.</v>

2
00:00:04.000 --> 00:00:06.000
Welcome to the meeting.

3
00:00:06.000 --> 00:00:08.000
Maya &amp; Taylor discussed next steps.
"""

    assert vtt_to_text(vtt) == "Welcome to the meeting.\nMaya & Taylor discussed next steps."


def test_truncate_transcript_keeps_short_text_unchanged():
    assert truncate_transcript("short", max_chars=100) == "short"


def test_truncate_transcript_marks_long_text():
    text = "a" * 120
    truncated = truncate_transcript(text, max_chars=80)
    assert "[Transcript truncated for model context]" in truncated
    assert len(truncated) < len(text) + 50
