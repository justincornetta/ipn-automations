from meeting_summary_pipeline.classify import classify_meeting, folder_name_for, slugify


def test_classifies_known_meeting_groups():
    assert classify_meeting("IPN Board of Directors Monthly Meeting") == "board"
    assert classify_meeting("PsychedelX 2026 Task Force") == "psychedelx"
    assert classify_meeting("IPN Labs Programming Sync") == "ipn-labs"
    assert classify_meeting("Community Task Force Weekly") == "community"
    assert classify_meeting("Partnership Sponsor Review") == "operations"


def test_classifies_unknown_as_uncategorized():
    assert classify_meeting("Weekly Catchup") == "uncategorized"


def test_folder_name_for_is_stable_and_date_prefixed():
    year, folder = folder_name_for("Board Meeting: June / Strategy", "2026-06-01T18:30:00Z")
    assert year == "2026"
    assert folder == "2026-06-01__board-meeting-june-strategy"


def test_slugify_falls_back_for_empty_input():
    assert slugify("!!!") == "zoom-meeting"
