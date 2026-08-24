#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
COLLECT_SCRIPT="${SCRIPT_DIR}/collect.sh"

usage() {
  cat <<'EOF'
用法：
  scripts/collect-expanded.sh [--digest] [collect 参数...]
  scripts/collect-expanded.sh collect [--digest] [collect 参数...]

说明：
  未提供日期选择参数时默认收集最近 1 天；日期参数会继续透传给 collect.sh。
  当前 newsFromAI 25 个自动 Feed 已进入 collect 默认 registry，本脚本只是兼容别名。
  日期、核验参数和 --digest 原样安全透传，不再重复追加旧版插件来源。
EOF
}

main() {
  if (($# > 0)) && [[ "$1" == "--help" || "$1" == "-h" ]]; then
    usage
    return 0
  fi
  for argument in "$@"; do
    if [[ "$argument" == "--with-plugin" ]]; then
      printf '错误：兼容别名不再接受 --with-plugin；默认 registry 已包含 newsFromAI 来源\n' >&2
      return 2
    fi
  done
  exec "$COLLECT_SCRIPT" "$@"
}

main "$@"
