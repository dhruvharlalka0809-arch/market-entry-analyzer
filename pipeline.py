import json
import os
import re
from dataclasses import dataclass, field

import anthropic

from prompts import (
    ANALYSIS_SYSTEM_PROMPT,
    REGENERATION_SYSTEM_PROMPT,
    VALIDATION_SCHEMA,
    VALIDATION_SYSTEM_PROMPT,
    VERDICT_RECONCILIATION_SYSTEM_PROMPT,
    VERIFICATION_SCHEMA,
    VERIFICATION_SYSTEM_PROMPT,
)

MODEL = "claude-sonnet-4-6"

VALID_VERDICTS = {"Enter", "Don't Enter", "Enter with conditions"}


@dataclass
class ValidationResult:
    valid: bool
    clarifying_question: str = ""


@dataclass
class VerificationResult:
    claims_checked: int = 0
    flagged_claims: list = field(default_factory=list)
    verdict_consistent: bool = True
    has_decision_threshold: bool = True


@dataclass
class AnalysisResult:
    report: str
    source_count: int
    verification_summary: str
    error: str = ""


def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
    return anthropic.Anthropic(api_key=api_key)


def validate_input(client: anthropic.Anthropic, question: str) -> ValidationResult:
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=VALIDATION_SYSTEM_PROMPT,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": VALIDATION_SCHEMA,
            }
        },
        messages=[{"role": "user", "content": question}],
    )

    text = next(b.text for b in response.content if b.type == "text")
    result = json.loads(text)

    if result["has_company"] and result["has_market"]:
        return ValidationResult(valid=True)

    return ValidationResult(
        valid=False, clarifying_question=result["clarifying_question"]
    )


def generate_report(
    client: anthropic.Anthropic, question: str, competitors: str = ""
) -> tuple[str, list[dict], int]:
    user_content = f"<business_question>{question}</business_question>"
    if competitors.strip():
        user_content += f"\n<known_competitors>{competitors}</known_competitors>"

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=ANALYSIS_SYSTEM_PROMPT,
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}],
        messages=[{"role": "user", "content": user_content}],
    )

    draft_parts = []
    search_results = []

    for block in response.content:
        if block.type == "text":
            draft_parts.append(block.text)
        elif block.type == "web_search_tool_result":
            if isinstance(block.content, list):
                for result in block.content:
                    if hasattr(result, "url"):
                        search_results.append(
                            {
                                "url": result.url,
                                "title": getattr(result, "title", ""),
                                "snippet": getattr(
                                    result,
                                    "encrypted_content",
                                    getattr(result, "page_content", ""),
                                ),
                            }
                        )

    draft_report = "\n".join(draft_parts)
    source_count = len(search_results)

    return draft_report, search_results, source_count


def _format_search_results_for_verification(search_results: list[dict]) -> str:
    parts = []
    for i, r in enumerate(search_results, 1):
        parts.append(
            f"[{i}] {r.get('title', 'Untitled')}\n"
            f"    URL: {r.get('url', 'N/A')}\n"
            f"    Content: {r.get('snippet', 'No content')[:500]}"
        )
    return "\n\n".join(parts) if parts else "No search results were returned."


def verify_report(
    client: anthropic.Anthropic,
    draft_report: str,
    search_results: list[dict],
) -> VerificationResult:
    formatted_results = _format_search_results_for_verification(search_results)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=VERIFICATION_SYSTEM_PROMPT,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": VERIFICATION_SCHEMA,
            }
        },
        messages=[
            {
                "role": "user",
                "content": (
                    f"<draft_report>\n{draft_report}\n</draft_report>\n\n"
                    f"<search_results>\n{formatted_results}\n</search_results>"
                ),
            }
        ],
    )

    text = next(b.text for b in response.content if b.type == "text")
    result = json.loads(text)

    return VerificationResult(
        claims_checked=result["claims_checked"],
        flagged_claims=result["flagged_claims"],
        verdict_consistent=result["verdict_consistent"],
        has_decision_threshold=result["has_decision_threshold"],
    )


def _extract_section(report: str, section_name: str) -> tuple[str, int, int]:
    lines = report.split("\n")
    start = None
    end = None

    for i, line in enumerate(lines):
        if section_name.lower() in line.lower() and line.strip().startswith("##"):
            start = i
        elif start is not None and line.strip().startswith("## ") and i > start:
            end = i
            break

    if start is None:
        return "", -1, -1

    if end is None:
        end = len(lines)

    return "\n".join(lines[start:end]), start, end


def _extract_verdict_from_executive_summary(report: str) -> str:
    section_content, _, _ = _extract_section(report, "Executive Summary")
    if not section_content:
        return ""

    for verdict in sorted(VALID_VERDICTS, key=len, reverse=True):
        pattern = re.compile(
            rf"verdict[:\s]*\**\s*{re.escape(verdict)}", re.IGNORECASE
        )
        if pattern.search(section_content):
            return verdict

    for verdict in sorted(VALID_VERDICTS, key=len, reverse=True):
        if verdict.lower() in section_content.lower():
            return verdict

    return ""


def _regenerate_section(
    client: anthropic.Anthropic,
    section_name: str,
    section_content: str,
    issues: list[dict],
    search_results: list[dict],
) -> str:
    formatted_results = _format_search_results_for_verification(search_results)
    issues_text = "\n".join(
        f"- {issue['claim']}: {issue['issue']}" for issue in issues
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=REGENERATION_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"<flagged_section>\nSection: {section_name}\n{section_content}\n</flagged_section>\n\n"
                    f"<issues>\n{issues_text}\n</issues>\n\n"
                    f"<search_results>\n{formatted_results}\n</search_results>"
                ),
            }
        ],
    )

    return next(b.text for b in response.content if b.type == "text")


def _reconcile_verdict(
    client: anthropic.Anthropic,
    verdict: str,
    recommendation_content: str,
    search_results: list[dict],
) -> str:
    formatted_results = _format_search_results_for_verification(search_results)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=VERDICT_RECONCILIATION_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"<verdict>{verdict}</verdict>\n\n"
                    f"<current_section>\n{recommendation_content}\n</current_section>\n\n"
                    f"<search_results>\n{formatted_results}\n</search_results>"
                ),
            }
        ],
    )

    return next(b.text for b in response.content if b.type == "text")


def _apply_fixes(
    client: anthropic.Anthropic,
    draft_report: str,
    verification: VerificationResult,
    search_results: list[dict],
) -> tuple[str, list[str]]:
    fix_log = []
    report = draft_report

    # --- Fix unsourced claims ---
    if verification.flagged_claims:
        sections_to_fix = {}
        for claim in verification.flagged_claims:
            section = claim["section"]
            if section not in sections_to_fix:
                sections_to_fix[section] = []
            sections_to_fix[section].append(claim)

        for section_name, issues in sections_to_fix.items():
            section_content, start, end = _extract_section(report, section_name)
            if start == -1:
                fix_log.append(
                    f"Could not locate section '{section_name}' for repair"
                )
                continue

            new_content = _regenerate_section(
                client, section_name, section_content, issues, search_results
            )

            lines = report.split("\n")
            header_line = lines[start]

            re_verification = verify_report(
                client,
                f"{header_line}\n{new_content}",
                search_results,
            )

            if re_verification.flagged_claims:
                fix_log.append(
                    f"Regenerated '{section_name}' — re-verification found "
                    f"{len(re_verification.flagged_claims)} remaining issue(s), "
                    f"replaced with explicit 'no data' statements"
                )
                for remaining in re_verification.flagged_claims:
                    new_content = new_content.replace(
                        remaining["claim"],
                        "[No reliable data available — original claim could not be verified]",
                    )
            else:
                fix_log.append(
                    f"Regenerated '{section_name}' — "
                    f"{len(issues)} issue(s) corrected, re-verification passed"
                )

            lines[start + 1 : end] = [new_content, ""]
            report = "\n".join(lines)

    # --- Fix verdict inconsistency ---
    if not verification.verdict_consistent:
        verdict = _extract_verdict_from_executive_summary(report)
        if not verdict:
            fix_log.append(
                "Verdict inconsistency detected but could not extract verdict "
                "from Executive Summary — manual review recommended"
            )
        else:
            rec_content, rec_start, rec_end = _extract_section(
                report, "Recommendation Detail"
            )
            if rec_start == -1:
                fix_log.append(
                    "Verdict inconsistency detected but could not locate "
                    "Recommendation Detail section for repair"
                )
            else:
                new_rec = _reconcile_verdict(
                    client, verdict, rec_content, search_results
                )

                lines = report.split("\n")
                header_line = lines[rec_start]

                rec_re_verification = verify_report(
                    client,
                    f"{header_line}\n{new_rec}",
                    search_results,
                )

                if rec_re_verification.flagged_claims:
                    for remaining in rec_re_verification.flagged_claims:
                        new_rec = new_rec.replace(
                            remaining["claim"],
                            "[No reliable data available — original claim could not be verified]",
                        )
                    fix_log.append(
                        f"Reconciled Recommendation Detail with Executive Summary "
                        f"verdict '{verdict}' — re-verification cleaned "
                        f"{len(rec_re_verification.flagged_claims)} unsourced claim(s)"
                    )
                else:
                    fix_log.append(
                        f"Reconciled Recommendation Detail with Executive Summary "
                        f"verdict '{verdict}' — re-verification passed"
                    )

                lines[rec_start + 1 : rec_end] = [new_rec, ""]
                report = "\n".join(lines)

    return report, fix_log


def _build_transparency_footer(
    source_count: int,
    verification: VerificationResult,
    fix_log: list[str],
) -> str:
    parts = [
        "\n---",
        "**How this was produced**",
        f"- Sources consulted: {source_count}",
    ]

    if not verification.flagged_claims and verification.verdict_consistent:
        parts.append(
            f"- Verification pass: checked {verification.claims_checked} claims, "
            f"no issues found"
        )
    else:
        issues = []
        if verification.flagged_claims:
            issues.append(f"flagged {len(verification.flagged_claims)} claim(s)")
        if not verification.verdict_consistent:
            issues.append("detected verdict inconsistency")
        parts.append(
            f"- Verification pass: checked {verification.claims_checked} claims, "
            + ", ".join(issues)
        )
        for entry in fix_log:
            parts.append(f"  - {entry}")

    parts.append(f"- Model: {MODEL}")

    return "\n".join(parts)


def run_analysis(
    question: str,
    competitors: str = "",
    on_status: callable = None,
) -> AnalysisResult:
    def status(msg):
        if on_status:
            on_status(msg)

    try:
        client = get_client()
    except ValueError as e:
        return AnalysisResult(
            report="", source_count=0, verification_summary="", error=str(e)
        )

    try:
        status("Validating input...")
        validation = validate_input(client, question)
        if not validation.valid:
            return AnalysisResult(
                report="",
                source_count=0,
                verification_summary="",
                error=f"clarification_needed:{validation.clarifying_question}",
            )

        status("Researching market data (this may take 60-120 seconds)...")
        draft_report, search_results, source_count = generate_report(
            client, question, competitors
        )

        if not draft_report.strip():
            return AnalysisResult(
                report="",
                source_count=0,
                verification_summary="",
                error="The analysis produced no content. Please try again.",
            )

        status("Verifying claims against sources...")
        verification = verify_report(client, draft_report, search_results)

        status("Applying corrections if needed...")
        final_report, fix_log = _apply_fixes(
            client, draft_report, verification, search_results
        )

        footer = _build_transparency_footer(source_count, verification, fix_log)
        final_report = final_report.rstrip() + "\n" + footer

        return AnalysisResult(
            report=final_report,
            source_count=source_count,
            verification_summary=footer,
        )

    except anthropic.RateLimitError:
        return AnalysisResult(
            report="",
            source_count=0,
            verification_summary="",
            error="Rate limited by the API. Please wait a minute and try again.",
        )
    except anthropic.APIStatusError as e:
        return AnalysisResult(
            report="",
            source_count=0,
            verification_summary="",
            error=f"API error ({e.status_code}): {e.message}",
        )
    except anthropic.APIConnectionError:
        return AnalysisResult(
            report="",
            source_count=0,
            verification_summary="",
            error="Could not connect to the Anthropic API. Check your internet connection.",
        )
