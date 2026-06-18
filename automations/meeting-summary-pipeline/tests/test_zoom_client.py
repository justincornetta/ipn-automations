from meeting_summary_pipeline.zoom_client import (
    extract_meeting_id_from_event,
    extract_recording_file_id_from_event,
    recording_files_from_meeting,
)


def test_extracts_meeting_and_transcript_file_from_zoom_event():
    event = {
        "event": "recording.completed",
        "payload": {
            "object": {
                "uuid": "abc/def==",
                "recording_files": [
                    {"id": "mp4", "file_type": "MP4", "recording_type": "shared_screen"},
                    {"id": "vtt", "file_type": "VTT", "recording_type": "audio_transcript"},
                ],
            }
        },
    }

    assert extract_meeting_id_from_event(event) == "abc/def=="
    assert extract_recording_file_id_from_event(event) == "vtt"


def test_recording_files_filters_to_transcripts():
    meeting = {
        "id": 123,
        "uuid": "uuid",
        "topic": "Board Meeting",
        "start_time": "2026-06-01T12:00:00Z",
        "recording_files": [
            {"id": "video", "file_type": "MP4", "recording_type": "shared_screen", "download_url": "https://x/video"},
            {"id": "transcript", "file_type": "VTT", "recording_type": "audio_transcript", "download_url": "https://x/vtt"},
        ],
    }

    files = recording_files_from_meeting(meeting)
    assert len(files) == 1
    assert files[0].id == "transcript"
    assert files[0].idempotency_key == "uuid:transcript"


def test_recording_files_honors_specific_file_id():
    meeting = {
        "id": 123,
        "uuid": "uuid",
        "topic": "Board Meeting",
        "start_time": "2026-06-01T12:00:00Z",
        "recording_files": [
            {"id": "a", "file_type": "VTT", "recording_type": "audio_transcript", "download_url": "https://x/a"},
            {"id": "b", "file_type": "VTT", "recording_type": "audio_transcript", "download_url": "https://x/b"},
        ],
    }

    files = recording_files_from_meeting(meeting, only_file_id="b")
    assert [file.id for file in files] == ["b"]
