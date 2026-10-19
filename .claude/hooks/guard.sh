#!/bin/sh
# Runs guard.py with the first working Python 3.10+. On Windows `python3` can be
# a Microsoft Store stub, so each candidate is tried before use. Without any
# Python, git and gh calls are blocked (fail closed); everything else passes.
input=$(cat)
guard="${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/guard.py"
for py in python3 python py; do
  if "$py" -c 'import sys; sys.exit(sys.version_info < (3, 10))' </dev/null >/dev/null 2>&1; then
    printf '%s' "$input" | "$py" "$guard"
    exit $?
  fi
done
if printf '%s' "$input" | grep -qE '\b(git|gh)\b'; then
  echo "Blocked: the public-repo guard needs Python 3.10+ to check git and gh calls." >&2
  exit 2
fi
exit 0
