#!/usr/bin/env bash
# clang-tidy over every package's compile_commands.json. Run after `colcon build`
# with -DCMAKE_EXPORT_COMPILE_COMMANDS=ON; checks are in .clang-tidy.
set -euo pipefail
shopt -s nullglob

databases=(build/*/compile_commands.json)
if [ ${#databases[@]} -eq 0 ]; then
  echo "No compile_commands.json under build/: no C++ to check."
  exit 0
fi
for db in "${databases[@]}"; do
  run-clang-tidy -quiet -p "$(dirname "$db")"
done
