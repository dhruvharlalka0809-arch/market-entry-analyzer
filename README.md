# AI Market Entry Strategy Analyzer

An AI-assisted strategy tool for answering market entry questions with sourced research, decision thresholds, and a verification pass.

This project is designed to simulate a consulting-style market entry workstream: validate the question, research the market, produce a structured recommendation, check factual claims against sources, and return a transparent executive report.

## What It Does

- Validates that the user provided a specific company and market.
- Researches market size, competitors, risks, and entry barriers.
- Produces a six-section market entry report.
- Requires a clear verdict: `Enter`, `Don't Enter`, or `Enter with conditions`.
- Adds quantified decision thresholds so the recommendation is testable.
- Runs a verification pass to flag unsupported claims and repair weak sections.
- Appends a transparency footer showing source count, checked claims, and corrections.

## Output Preview

See [docs/sample_report.md](docs/sample_report.md) for the expected report structure and decision logic.

## Decision Workflow

1. User enters a market entry question, such as:

   ```text
   Should Spotify enter the podcast advertising market in Southeast Asia?
   ```

2. The app validates that the question includes:

   - a specific company
   - a specific market, geography, industry, or segment

3. The analysis pipeline creates a sourced report covering:

   - executive summary
   - market overview
   - competitive landscape
   - risks and entry barriers
   - decision thresholds
   - recommendation detail

4. A verification step checks numeric claims, competitor facts, verdict consistency, and decision thresholds.

## Why It Matters

Market entry recommendations often fail because they mix assumptions, unsourced claims, and vague conclusions. This tool forces a more disciplined structure:

- every major number needs source support
- missing data must be stated instead of invented
- the final recommendation must match the executive verdict
- decision thresholds make the recommendation measurable

## Tech Stack

- Python
- Streamlit
- Anthropic Claude API
- Web search tool use
- Pytest

## Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Add your API key to `.env`:

```bash
ANTHROPIC_API_KEY=your-api-key-here
```

Then run:

```bash
streamlit run app.py
```

## Test

The test suite includes adversarial checks for vague prompts, prompt injection, unsupported claims, contradiction handling, and low-data markets.

Some tests require a live `ANTHROPIC_API_KEY` because they exercise the full research and verification pipeline.

```bash
pytest tests/test_adversarial.py -v
```

Without an API key, the live tests are skipped.

## Example Questions

```text
Should Netflix enter the live sports streaming market in Brazil?
```

```text
Should IKEA enter the modular housing market in Japan?
```

```text
Should Starbucks enter the energy drink market in Germany?
```

## Recruiter Positioning

Built an AI-powered Market Entry Strategy Analyzer that validates business questions, performs sourced market research, checks claims against evidence, and generates consulting-style recommendations with decision thresholds.

## Data And Source Note

This tool relies on current web research and model-generated analysis. Outputs should be reviewed before being used for real investment, expansion, or commercial decisions.
