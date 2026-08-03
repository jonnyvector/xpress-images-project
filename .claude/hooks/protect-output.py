#!/usr/bin/env python3
"""PreToolUse/Bash guard for output/.

output/ holds every generated image and learned signature. It is gitignored, so
there is no git safety net: a bad ``rm -rf`` is permanent. Images cost ~$0.134
each to regenerate and signatures cannot be regenerated at all.

Erasure of output/ is DENIED. mv and ``rsync --delete`` ASK, since moving files
*into* output/ is legitimate and only the caller knows the direction.

The check is token-based, not substring-based: it splits the command into
segments, takes each segment's leading verb, and tests the remaining tokens as
paths. Substring matching produced false positives on any command that merely
*mentions* a deletion — a commit message describing this very hook, a grep, an
echo — which is worse than useless, since a guard that blocks ordinary work
gets disabled.
"""

import json
import re
import shlex
import sys

DENY_MSG = """Blocked: this deletes files under output/, which holds irreplaceable generated
images and learned signatures and is gitignored (no git recovery).

To remove a project, use the app's delete - it soft-deletes into output/.trash/
instead of erasing. If a hard delete is genuinely intended, the operator must
run it by hand outside Claude Code."""

ASK_MSG = """This moves or mirrors paths under output/ (irreplaceable generated images,
gitignored). Confirm the direction is correct before approving."""

ERASE_VERBS = {"rm", "rmdir", "shred", "srm", "trash"}
SEGMENT_SPLIT = re.compile(r"\|\||&&|[;\n|&()]")
# `<<EOF`, `<<-EOF`, `<< "EOF"` — the body is prose, not a command.
HEREDOC_START = re.compile(r"<<-?\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?")


def strip_heredocs(cmd: str) -> str:
    """Drop heredoc bodies. They are data (commit messages, file contents),
    never commands, and their prose routinely mentions rm and output/."""
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        match = HEREDOC_START.search(line)
        i += 1
        if match:
            delim = match.group(1)
            while i < len(lines) and lines[i].strip() != delim:
                i += 1
            i += 1  # skip the delimiter line itself
    return "\n".join(out)


def tokenize(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:  # unbalanced quotes — fall back to whitespace split
        return segment.split()


def leading_verb(tokens: list[str]) -> str:
    """First token that is not a VAR=value prefix or a command wrapper."""
    for i, token in enumerate(tokens):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            continue
        if token in ("sudo", "env", "command", "xargs", "time", "nohup"):
            continue
        return token.rsplit("/", 1)[-1]  # /bin/rm -> rm
    return ""


def is_output_path(token: str) -> bool:
    """Does this token name the generated-output tree? Rejects lookalikes such
    as my_output/ and test_output/."""
    if token.startswith("-"):
        return False
    normalized = token.lstrip("'\"").rstrip("'\"")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return (
        normalized == "output"
        or normalized.startswith("output/")
        or normalized.endswith("/output")
        or "/output/" in normalized
    )


def decide(decision: str, reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # never block on a malformed payload
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command:
        sys.exit(0)

    for segment in SEGMENT_SPLIT.split(strip_heredocs(command)):
        tokens = tokenize(segment)
        if not tokens:
            continue
        verb = leading_verb(tokens)
        args = tokens[1:]
        hits_output = any(is_output_path(t) for t in args)

        # `git clean -x`/-X removes ignored files, i.e. all of output/, without
        # ever naming the path — so this one cannot be gated on hits_output.
        if verb == "git" and "clean" in args:
            flags = [t for t in args if t.startswith("-") and not t.startswith("--")]
            if any("x" in f or "X" in f for f in flags):
                decide("deny", DENY_MSG)
            continue

        if not hits_output:
            continue
        if verb in ERASE_VERBS:
            decide("deny", DENY_MSG)
        if verb == "find" and ("-delete" in args or "-exec" in args):
            decide("deny", DENY_MSG)
        if verb == "mv" or (verb == "rsync" and "--delete" in args):
            decide("ask", ASK_MSG)

    sys.exit(0)


if __name__ == "__main__":
    main()
