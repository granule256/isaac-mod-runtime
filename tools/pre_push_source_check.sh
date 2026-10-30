#!/usr/bin/env bash
# Git pre-push hook: validate source only. This script never initiates a push.
set -euo pipefail
if [[ "${1:-}" != origin ]]; then
  echo "拒绝：远端源码只发布到 origin，禁止使用旧 public 远端。"
  exit 1
fi
repo_root="$(git rev-parse --show-toplevel)"
checker="$repo_root/tools/check_remote_source.py"
while read -r local_ref local_oid remote_ref remote_oid; do
  [[ "$local_oid" =~ ^0+$ ]] && continue
  if [[ "$remote_ref" != refs/heads/main && "$remote_ref" != refs/tags/* ]]; then
    echo "拒绝：请使用精简源码 main 分支或已审查的发布标签。"
    exit 1
  fi
  python3 "$checker" --root "$repo_root" --ref "$local_oid" || exit 1
  # A clean tip must not hide forbidden files in an earlier unpublished commit.
  commits="$(git rev-list "$local_oid" --not --remotes=origin)"
  while IFS= read -r commit; do
    [[ -z "$commit" || "$commit" == "$local_oid" ]] && continue
    python3 "$checker" --root "$repo_root" --ref "$commit" || exit 1
  done <<< "$commits"
done
