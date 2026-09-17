#!/usr/bin/env bash
# 完整交付包默认附带后端源码；独立前端仓库可指定 BACKEND_SOURCE_DIR。
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_dir="${BACKEND_SOURCE_DIR:-$script_dir/../monitoring-service}"
if [[ ! -f "$source_dir/deploy/install.sh" || ! -f "$source_dir/database.go" ]]; then
  echo '缺少 MySQL 版后端源码。请先克隆/更新 monitoring-service，再用 BACKEND_SOURCE_DIR 指定其目录。' >&2
  exit 1
fi
exec bash "$source_dir/deploy/install.sh" "$@"
