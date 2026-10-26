#!/usr/bin/env bash
# Compare AI models as the image judge, on a frozen answer key of your verdicts.
# Spends the company OpenRouter key (OPENROUTER_API_KEY in .env), ~$0.03/image for opus.
# Usage:
#   scripts/judgeeval.sh build            freeze the answer key (free; --rebuild replaces it)
#   scripts/judgeeval.sh opus [--limit N] judge: opus|sonnet|haiku|gemini; 2 = ignore door shape, 3 = + corner close-ups
#   scripts/judgeeval.sh report           scores + output/.qa/judge_compare/report.html
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  build | report) exec uv run python scripts/judge_compare.py "$@" ;;
  "" | -h | --help) sed -n '2,8p' "$0"; exit 1 ;;
  *) exec uv run python scripts/judge_compare.py run "$@" ;;  # preset list lives in PRESETS
esac
