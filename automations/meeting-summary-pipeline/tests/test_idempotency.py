from meeting_summary_pipeline.idempotency import should_process_existing_status


def test_idempotency_skips_posted_recordings():
    assert should_process_existing_status("posted") is False


def test_idempotency_retries_failed_and_missing_statuses():
    assert should_process_existing_status("failed") is True
    assert should_process_existing_status("processing") is True
    assert should_process_existing_status(None) is True
