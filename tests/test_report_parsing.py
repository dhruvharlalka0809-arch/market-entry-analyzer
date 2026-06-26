from pipeline import (
    _extract_section,
    _extract_verdict_from_executive_summary,
    _format_search_results_for_verification,
)


def test_extract_section_returns_expected_body_and_bounds():
    report = """# Report

## 1. Executive Summary
- Verdict: Enter with conditions

## 2. Market Overview
Market is growing.
"""

    section, start, end = _extract_section(report, "Executive Summary")

    assert "Verdict: Enter with conditions" in section
    assert start >= 0
    assert end > start


def test_extract_verdict_prioritizes_longer_verdicts():
    report = """## 1. Executive Summary
- Verdict: **Enter with conditions**

## 6. Recommendation Detail
Proceed only if the pilot economics hold.
"""

    assert _extract_verdict_from_executive_summary(report) == "Enter with conditions"


def test_format_search_results_handles_empty_and_truncates_content():
    empty = _format_search_results_for_verification([])
    formatted = _format_search_results_for_verification(
        [
            {
                "title": "Market report",
                "url": "https://example.com",
                "snippet": "x" * 600,
            }
        ]
    )

    assert empty == "No search results were returned."
    assert "Market report" in formatted
    assert "https://example.com" in formatted
    assert len(formatted) < 700
