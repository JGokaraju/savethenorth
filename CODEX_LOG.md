# CODEX_LOG — where OpenAI Codex was used

> Stub for the team. The OpenAI prize judges how Codex contributed, so record each use as it happens:
> what you asked, what it produced, and what you kept or changed.

| Date | Area / file(s) | Prompt / task given to Codex | Result | Kept? Notes |
|---|---|---|---|---|
| YYYY-MM-DD | e.g. `backend/science/ime.py` | e.g. "Review the IME implementation against Varon et al. 2018" | | |
| | | | | |

## Suggested places to use Codex before submission
- Review `backend/agent/orchestrator.py` (Responses API loop) against the model you configure in `OPENAI_MODEL`.
- Ask Codex to propose EMIT-specific effective-wind coefficients (α, β) with citations, and record the answer before
  changing `backend/config/case.yaml` (flagged `verify: true`).
- Generate additional unit tests for edge cases in `backend/science/` (e.g. masks touching the crop edge).
- Tighten the skills in `skills/*.md` after watching a live GPT run.

## Other AI assistance
Most of the initial scaffold, science core, tools, UI and tests were written with an AI coding assistant (Claude Code).
Commits carry a `Co-Authored-By` trailer.
