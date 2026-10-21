#!/usr/bin/env python3
"""Claude Code PreToolUse guard for this public repo.

Reads the hook payload of a Bash or PowerShell call and blocks it (exit 2,
reason on stderr) when it would:

- push commits that leak a secret or private data (gitleaks with .gitleaks.toml),
  touch a deny-listed path, carry an image with GPS data or a camera serial, or
  carry an author/committer email that is not a GitHub noreply address;
- post issue, PR, release, gist or API text that leaks a secret or private data;
- merge a PR, push to main, force-push, or skip git hooks with --no-verify.

Everything else passes untouched. On an internal error the guard blocks the
call it was checking (fail closed). See CLAUDE.md, "Public repo".
"""

from __future__ import annotations

import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import privacy_check  # noqa: E402

PROTECTED_BRANCHES = {"main", "master"}
GITLEAKS_CONFIG = REPO_ROOT / ".gitleaks.toml"
NOREPLY_EMAIL = re.compile(r"(?i)^[\w.+-]+@users\.noreply\.github\.com$|^noreply@")
OUTGOING = ["--branches", "--tags", "--not", "--remotes"]

SEPARATORS = set(";|&()\n")
COMMAND_PREFIXES = {
    "if", "then", "else", "elif", "do", "while", "until", "{", "}", "!", "time",
    "sudo", "command", "exec", "env", "nohup",
}  # fmt: skip
SHELLS = {"bash", "sh", "zsh", "dash", "pwsh", "powershell"}
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
PUSH_OPTS_WITH_VALUE = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
GH_TEXT_COMMANDS = {
    "issue": {"create", "comment", "edit", "close", "reopen"},
    "pr": {"create", "comment", "edit", "review", "close", "reopen"},
    "release": {"create", "edit"},
    "gist": {"create", "edit"},
}


@dataclass
class Plan:
    """What a command needs before it may run."""

    blocks: list[str] = field(default_factory=list)
    push_dirs: list[str] = field(default_factory=list)
    text_files: list[str] = field(default_factory=list)
    scan_text: bool = False


# --- Parsing ---------------------------------------------------------------


def strip_heredocs(command: str) -> str:
    """Drop heredoc bodies so the shell structure can be tokenised."""
    pattern = re.compile(
        r"<<-?[ \t]*(['\"]?)(\w+)\1([^\n]*)\n.*?\n[ \t]*\2[ \t]*(?=\n|$)", re.DOTALL
    )
    return pattern.sub(lambda m: "__HEREDOC__" + m.group(3), command)


def tokenize(command: str) -> list[str]:
    lexer = shlex.shlex(strip_heredocs(command), posix=True, punctuation_chars=";|&()<>\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def simple_commands(tokens: list[str]) -> list[list[str]]:
    """Split tokens into argv lists, dropping redirections and command prefixes."""
    commands, current = [], []
    skip_next = False
    for i, tok in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if tok and set(tok) <= SEPARATORS:
            if current:
                commands.append(current)
            current = []
            continue
        if tok and set(tok) <= set("<>&"):
            skip_next = True  # the redirection target
            continue
        if tok.isdigit() and i + 1 < len(tokens) and tokens[i + 1][:1] in "<>":
            continue
        if not current and (tok in COMMAND_PREFIXES or re.match(r"^\w+=", tok)):
            continue
        current.append(tok)
    if current:
        commands.append(current)
    return commands


def join(cwd: str, path: str) -> str:
    """Join paths, reading Git Bash paths like /c/Users as C:/Users on Windows."""
    if os.name == "nt":
        path = re.sub(r"^/([a-zA-Z])(?=/|$)", r"\1:", path)
    return os.path.join(cwd, path)


def program(argv: list[str]) -> str:
    name = re.split(r"[\\/]", argv[0])[-1].lower()
    return name.removesuffix(".exe")


# --- Analysis --------------------------------------------------------------


def analyze(command: str, cwd: str, plan: Plan | None = None) -> Plan:
    plan = plan or Plan()
    try:
        commands = simple_commands(tokenize(command))
    except ValueError:
        return analyze_unparsed(command, cwd, plan)
    for argv in commands:
        name = program(argv)
        if name in ("cd", "pushd", "set-location") and len(argv) > 1:
            cwd = join(cwd, os.path.expanduser(argv[-1]))
        elif name in SHELLS:
            for i, arg in enumerate(argv[1:-1], start=1):
                if arg.lower() in ("-c", "-command"):
                    analyze(argv[i + 1], cwd, plan)
                    break
        elif name == "git":
            analyze_git(argv, cwd, plan)
        elif name == "gh":
            analyze_gh(argv, cwd, plan)
    return plan


def analyze_unparsed(command: str, cwd: str, plan: Plan) -> Plan:
    """Conservative fallback for commands shlex cannot read (e.g. PowerShell here-strings)."""
    if re.search(r"\bgh\s+pr\s+merge\b|pulls/\d+/merge", command):
        plan.blocks.append("merging PRs is Max's job; agents never merge")
    for segment in re.findall(r"\bgit\b[^\n;|&]*\bpush\b[^\n;|&]*", command):
        if re.search(r"(?:^|\s)(?:-f|--force\S*|--mirror|--all|\+\S+)(?=\s|$)", segment):
            plan.blocks.append("force-pushing is not allowed")
        if re.search(r"(?:^|[\s:])(?:refs/heads/)?(?:main|master)(?=\s|$)", segment):
            plan.blocks.append("pushing to main is not allowed; open a PR from a branch")
        plan.push_dirs.append(cwd)
    if re.search(r"\bgit\b[^\n;|&]*\s--no-verify\b", command):
        plan.blocks.append("skipping git hooks (--no-verify) is not allowed")
    if re.search(r"\bgh\s+(?:issue|pr|release|gist|api)\b", command):
        plan.scan_text = True
    return plan


def analyze_git(argv: list[str], cwd: str, plan: Plan) -> None:
    i = 1
    while i < len(argv) and argv[i].startswith("-"):
        opt = argv[i]
        if opt in GIT_OPTS_WITH_VALUE and i + 1 < len(argv):
            if opt == "-C":
                cwd = join(cwd, argv[i + 1])
            i += 1
        i += 1
    if i >= len(argv):
        return
    sub, args = argv[i], argv[i + 1 :]
    if "--no-verify" in args or (
        sub == "commit" and any(short_flag(a, "n", "mFcCt") for a in args)
    ):
        plan.blocks.append("skipping git hooks (--no-verify) is not allowed")
    if sub == "push":
        analyze_push(args, cwd, plan)


def short_flag(arg: str, flag: str, takes_value: str) -> bool:
    """Is `flag` set in a short-option cluster like -anm, before any value-taking letter?"""
    if not arg.startswith("-") or arg.startswith("--"):
        return False
    for letter in arg[1:]:
        if letter == flag:
            return True
        if letter in takes_value:
            return False
    return False


def analyze_push(args: list[str], cwd: str, plan: Plan) -> None:
    positional = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in PUSH_OPTS_WITH_VALUE:
            i += 2
            continue
        if arg.startswith("--force") or short_flag(arg, "f", "o") or arg in ("--mirror", "--all"):
            plan.blocks.append("force-pushing (or pushing every branch) is not allowed")
        elif arg in ("-d", "--delete") or short_flag(arg, "d", "o"):
            plan.blocks.append("deleting remote branches is Max's job")
        elif not arg.startswith("-"):
            positional.append(arg)
        i += 1
    refspecs = positional[1:]
    current = current_branch(cwd)
    targets = [current] if not refspecs else []
    for spec in refspecs:
        if spec.startswith("+"):
            plan.blocks.append("force-pushing (+refspec) is not allowed")
            spec = spec[1:]
        src, _, dst = spec.rpartition(":") if ":" in spec else (spec, "", spec)
        if ":" in spec and not src:
            plan.blocks.append("deleting remote branches is Max's job")
        targets.append(current if dst == "HEAD" else dst.removeprefix("refs/heads/"))
    if PROTECTED_BRANCHES & set(targets):
        plan.blocks.append("pushing to main is not allowed; open a PR from a branch")
    plan.push_dirs.append(cwd)


def analyze_gh(argv: list[str], cwd: str, plan: Plan) -> None:
    sub = argv[1] if len(argv) > 1 else ""
    action = argv[2] if len(argv) > 2 else ""
    args = argv[2:]
    if (sub, action) == ("pr", "merge") or (
        sub == "api" and any(re.search(r"pulls/\d+/merge", a) for a in args)
    ):
        plan.blocks.append("merging PRs is Max's job; agents never merge")
        return
    if sub == "api":
        methods = [
            b for a, b in zip(args, args[1:] + [""], strict=True) if a in ("-X", "--method")
        ]
        methods += [a.split("=", 1)[1] for a in args if a.startswith("--method=")]
        methods += [a[2:] for a in args if a.startswith("-X") and len(a) > 2]
        fields = any(a in ("-f", "-F", "--field", "--raw-field", "--input") for a in args)
        if not fields and all(m.upper() in ("GET", "") for m in methods):
            return
    elif action not in GH_TEXT_COMMANDS.get(sub, set()):
        return
    plan.scan_text = True
    files = []
    for i, arg in enumerate(args):
        value = args[i + 1] if i + 1 < len(args) else ""
        if arg in ("--body-file", "--notes-file", "--input") or (arg == "-F" and sub != "api"):
            files.append(value)
        elif arg in ("-F", "--field") and value.partition("=")[2].startswith("@"):
            files.append(value.partition("=")[2][1:])
        elif (
            sub == "gist" and i > 0 and not arg.startswith("-") and not args[i - 1].startswith("-")
        ):
            files.append(arg)
    plan.text_files += [join(cwd, f) for f in files if f and f != "-"]


# --- Checks ----------------------------------------------------------------


def git(cwd: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def current_branch(cwd: str) -> str:
    try:
        return git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD").strip()
    except RuntimeError:
        return "HEAD"


def find_gitleaks() -> str:
    candidates = [os.environ.get("GITLEAKS", ""), shutil.which("gitleaks") or ""]
    local = os.environ.get("LOCALAPPDATA", "")
    if local:  # winget installs land here before the shell's PATH is refreshed
        candidates += glob.glob(
            os.path.join(local, "Microsoft", "WinGet", "Packages", "Gitleaks.*", "gitleaks.exe")
        )
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise RuntimeError("gitleaks is not installed (needed to scan what leaves this machine)")


def gitleaks(*args: str, stdin: str | None = None) -> list[str]:
    result = subprocess.run(
        [find_gitleaks(), *args, "-c", str(GITLEAKS_CONFIG), "--no-banner", "--no-color",
         "--redact", "--ignore-gitleaks-allow", "-v", "--exit-code", "3"],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )  # fmt: skip
    if result.returncode == 3:
        rules = re.findall(r"RuleID:\s*(\S+)", result.stdout + result.stderr)
        where = re.findall(r"(?:File|Commit):\s*(\S+)", result.stdout + result.stderr)
        found = f"rules {sorted(set(rules))} in {sorted(set(where))}"
        return [f"gitleaks found {len(rules)} leak(s): {found}"]
    if result.returncode != 0:
        raise RuntimeError(f"gitleaks failed: {result.stderr.strip()[-500:]}")
    return []


def check_push(cwd: str) -> list[str]:
    root = git(cwd, "rev-parse", "--show-toplevel").strip()
    commits = git(root, "rev-list", *OUTGOING).split()
    if not commits:
        return []
    problems = gitleaks("git", "--log-opts", " ".join(OUTGOING), root)
    for line in git(root, "log", "--format=%h %ae %ce", *OUTGOING).splitlines():
        sha, *emails = line.split()
        if not all(NOREPLY_EMAIL.match(e) for e in emails):
            problems.append(
                f"commit {sha} carries a personal email; set `git config user.email "
                "<id>+<login>@users.noreply.github.com` and rewrite the commit"
            )
    paths, images = set(), []
    raw = git(
        root, "log", "--format=", "--raw", "--no-abbrev", "--diff-filter=AMRC", "-z", *OUTGOING
    )
    fields = iter(f.strip() for f in raw.split("\0") if f.strip())
    for meta in fields:
        _, _, _, blob, status = meta.split()
        if status[:1] in "RC":  # renames and copies list the source path first
            next(fields)
        path = next(fields)
        paths.add(path)
        if privacy_check.is_image(path):
            images.append((path, blob))
    problems += [
        f"{p}: deny-listed path in an outgoing commit"
        for p in privacy_check.denied_paths(sorted(paths), root)
    ]
    for path, blob in images:
        data = subprocess.run(
            ["git", "cat-file", "blob", blob], cwd=root, capture_output=True, check=True
        ).stdout
        found = privacy_check.image_findings(data)
        if found:
            problems.append(
                f"{path}: image metadata carries {', '.join(found)}; {privacy_check.FIX_HINT}"
            )
    return problems


def check_text(command: str, files: list[str]) -> list[str]:
    text = command
    for name in files:
        if not os.path.isfile(name):
            # The hook sees the command before the shell expands it.
            hint = (
                "; pass a literal path, the guard does not expand variables" if "$" in name else ""
            )
            raise RuntimeError(f"cannot read {name} to scan it{hint}")
        text += "\n" + Path(name).read_text(encoding="utf-8", errors="replace")
    return gitleaks("stdin", stdin=text)


def problems_for(command: str, cwd: str) -> list[str]:
    plan = analyze(command, cwd)
    problems = list(dict.fromkeys(plan.blocks))
    if not problems:
        for push_dir in dict.fromkeys(plan.push_dirs):
            problems += check_push(push_dir)
        if plan.scan_text:
            problems += check_text(command, plan.text_files)
    return problems


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    try:
        problems = problems_for(command, join(os.getcwd(), payload.get("cwd") or "."))
    except Exception as error:  # fail closed, but only for commands that could publish
        if not re.search(r"\b(?:git|gh)\b", command):
            return 0
        problems = [f"guard could not check this command: {error}"]
    if not problems:
        return 0
    print("Blocked by the public-repo guard (.claude/hooks/guard.py):", file=sys.stderr)
    for problem in problems:
        print(f"- {problem}", file=sys.stderr)
    print(
        "See CLAUDE.md, 'Public repo'. Fix the cause; do not work around the guard.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
