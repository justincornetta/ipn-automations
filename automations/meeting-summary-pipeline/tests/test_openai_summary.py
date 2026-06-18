from meeting_summary_pipeline.openai_summary import generate_summary


def test_generate_summary_falls_back_without_openai_key():
    summary = generate_summary(
        api_key=None,
        model="gpt-5.4-nano",
        topic="Community Task Force",
        meeting_date="2026-06-18",
        group="community",
        attendees=["Justin", "Maya"],
        transcript_text="Justin: We discussed member onboarding.\nMaya: The next step is to review the workshop plan.",
    )

    assert "Fallback summary" in summary
    assert "## Executive Summary" in summary
    assert "Justin: We discussed member onboarding." in summary
