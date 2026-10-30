#!/usr/bin/env bash
# Compatibility entry point: inspect source only; never switch, stage, commit or push.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
python3 "$repo_root/tools/check_remote_source.py" --root "$repo_root" "$@"
echo "源码检查完成；请人工审查待推送提交，再通过应用界面推送 origin/main。"
