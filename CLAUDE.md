## Public repo

This repo is public. Anything committed, pushed, or written into an issue, PR or comment can be read, copied and indexed by anyone, and stays in forks and caches after deletion. The robot lives in a private home, so the rule is: **no secrets and no private data, ever**.

What counts as private:

- **Secrets:** `.env*` files, keys, tokens, API keys, Wi-Fi SSIDs and passphrases. Wi-Fi credentials reach the Pi only through an untracked env file on the Pi, never through `scripts/provision-pi.sh` or any committed file.
- **The home:** SLAM maps (`maps/`, `*.pgm` and their map `*.yaml`), recordings (`*.mcap`, `*.db3`, `*.bag`), audio (`*.wav`, `*.flac`), camera captures. Keep them outside the repo or in a gitignored folder.
- **Images:** fine for docs, but only robot close-ups, no rooms, and stripped of EXIF GPS data and camera serials (`exiftool -all= <file>`). The same goes for photos attached to issues and PRs.
- **Personal info:** no real address, phone number or email (commits use the `…@users.noreply.github.com` address), no public IP. The GitHub handle `mkogel` and private LAN addresses (`192.168.x.x`, `10.x.x.x`) are fine.

The guard has four layers; never work around one:

1. GitHub secret scanning with push protection.
2. pre-commit (`pre-commit install` once per clone): gitleaks with `.gitleaks.toml`, and `scripts/privacy_check.py` for deny-listed paths and image metadata.
3. The Claude Code hook in `.claude/settings.json` (`.claude/hooks/guard.py`). It scans outgoing commits before `git push` and the text of `gh issue|pr|release|gist|api` writes, and blocks on a finding. It also blocks `gh pr merge`, pushes to `main`, force-pushes and `--no-verify`. It needs Python 3.10+ and gitleaks on `PATH`.
4. This section.

When a check blocks you: remove the private data and rewrite the commit, or describe it generically ("the home Wi-Fi", "a public IP"). A real false positive goes into `.gitleaksignore` (by fingerprint) or the deny-list in `.gitignore`, in a PR Max reviews. Never add inline `gitleaks:allow`, never use `--no-verify`, never edit the hook to get past it. Tests: `python -m unittest discover -s scripts/tests`.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
