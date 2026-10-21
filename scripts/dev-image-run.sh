#!/usr/bin/env bash
# Runs commands in a throwaway dev-image container on a WSL copy of a Windows checkout, for agents
# on the Windows host. The devcontainer workspace is Max's own clone, so builds, tests and commits
# run here instead. See docs/agents/windows-host.md.
#
# From Git Bash at the repo root:
#   cat scripts/dev-image-run.sh | MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -e bash -s -- \
#     "$(pwd -W)" 'colcon build --base-paths src sim && colcon test --base-paths src sim'
#
# The copy (~/dev-image-run/<repo>) includes .git and keeps build/, install/ and log/ between
# runs. Each run first overwrites it from the checkout, so a commit made in the copy must be
# fetched back before the next run:
#   git fetch //wsl.localhost/Ubuntu-24.04/home/<user>/dev-image-run/<repo> <branch>
# The commands run in /ws with ROS (and install/, once built) sourced and pre-commit installed.
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: dev-image-run.sh <windows checkout path> <commands>" >&2
  exit 2
fi
source_dir=$(wslpath -u "$1")
copy="$HOME/dev-image-run/$(basename "$source_dir")"
cache="$HOME/dev-image-run/.cache" # pre-commit's hook environments, kept between runs
mkdir -p "$copy" "$cache"
rsync -a --delete --exclude /build --exclude /install --exclude /log "$source_dir/" "$copy/"

# Its own ROS domain, so nothing talks to Max's running devcontainer.
docker run --rm -i --user 1000 -e HOME=/tmp/home -e ROS_DOMAIN_ID=77 \
  -e FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA -v "$copy":/ws -v "$cache":/cache -e PRE_COMMIT_HOME=/cache/pre-commit -w /ws \
  ghcr.io/mkogel/stubentiger-dev:jazzy bash -s << EOF
set -eo pipefail
mkdir -p "\$HOME"
git config --global safe.directory '*'
pre-commit install -f > /dev/null
source /opt/ros/jazzy/setup.bash
if [ -f install/setup.bash ]; then source install/setup.bash; fi
$2
EOF
