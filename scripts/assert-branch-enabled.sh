#!/usr/bin/env bash
# Fail if a capability in config/branches.yaml is missing or disabled.
# Usage (repo root, usually via ./scripts/start.sh):
#   ./scripts/assert-branch-enabled.sh dlt_dbt_clickhouse
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <branch_name>" >&2
  exit 2
fi

export NEXUS_ASSERT_BRANCH="$1"
uv run python -c '
import os
import sys

from common.branches import is_branch_enabled

name = os.environ["NEXUS_ASSERT_BRANCH"]
if not is_branch_enabled(name):
    raise SystemExit(f"branch {name} is disabled in config/branches.yaml")
print(f"branch {name} enabled")
print("NEXUS_ENV=" + os.environ.get("NEXUS_ENV", ""))
print("NEXUS_RUN_ID=" + os.environ.get("NEXUS_RUN_ID", ""))
'
