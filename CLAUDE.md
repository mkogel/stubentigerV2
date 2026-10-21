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

## Build and test

Work inside the devcontainer (`.devcontainer/`, image `ghcr.io/mkogel/stubentiger-dev:jazzy`); it has the whole toolchain. The laptop setup is in `docs/dev-setup.md`. The repo root is the colcon workspace: `src/` may run on the robot, `sim/` is laptop-only, and `src/` never depends on `sim/`.

These are the commands CI runs (`.github/workflows/ci.yml`), from the repo root:

```bash
source /opt/ros/jazzy/setup.bash

# Build (CI adds ccache and -Werror)
colcon build --base-paths src sim --cmake-args -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

# Test (`build-test` job; skips the tests labelled `gazebo`)
colcon test --base-paths src sim --ctest-args -LE gazebo
colcon test-result --verbose

# Headless Gazebo tests (`sim` job), about 1.5 min
colcon test --base-paths src sim --packages-select stubentiger_sim --ctest-args -L gazebo
colcon test-result --verbose

# Static checks, after the build
bash scripts/clang_tidy.sh    # clang-tidy from build/*/compile_commands.json
bash scripts/mypy.sh          # mypy on the stubentiger_* modules

# Lint: the single lint source (ruff, clang-format, xmllint, yamllint, whitespace, gitleaks)
pre-commit run --all-files

# Repo script tests (privacy guard, CI gate)
python3 -m unittest discover -s scripts/tests
```

The robot profile (`robot-arm64` job, as on the Pi) builds and tests `src/` only, on plain `ros:jazzy-ros-base`: `rosdep install --from-paths src --ignore-src -y`, then the build and test commands with `--base-paths src`.

Shell on a Windows host, running commands in WSL, the devcontainer or `ros2`: read `docs/agents/windows-host.md`.

CI has one required check, `ci`, which passes only when every other job passed. A new job joins it by being added to the `needs` of the `ci` job. Actions are pinned to full commit SHAs; Dependabot proposes updates. A new tool for the toolchain goes into `.devcontainer/Dockerfile`: a PR that changes `.devcontainer/` builds and tests against its own image.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
