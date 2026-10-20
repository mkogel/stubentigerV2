#!/usr/bin/env bash
# mypy (standard mode, settings in mypy.ini) on the stubentiger_* Python
# modules in src/ and sim/. Launch files are not type-checked. Source ROS first.
set -euo pipefail
shopt -s nullglob

modules=(src/stubentiger_*/stubentiger_*/ sim/stubentiger_*/stubentiger_*/)
if [ ${#modules[@]} -eq 0 ]; then
  echo "No stubentiger_* Python modules: nothing to type-check."
  exit 0
fi
mypy "${modules[@]}"
