#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
COLLECT_SCRIPT="${SCRIPT_DIR}/collect.sh"

PLUGIN_IDS=(
  openai-news
  google-blog
  github-changelog
  hugging-face-blog
  google-deepmind
  nvidia-ai
  aws-machine-learning
  kimi-k2-releases
  glm-releases
  deepseek-status
  openai-status
  anthropic-status
  github-status
  techcrunch-ai
  paperswithcode-daily
)

usage() {
  cat <<'EOF'
用法：
  scripts/collect-expanded.sh [--digest] [collect 参数...]
  scripts/collect-expanded.sh collect [--digest] [collect 参数...]

说明：
  未提供日期选择参数时默认收集最近 1 天；日期参数会继续透传给 collect.sh。
  固定追加 v1.5 计划中的 15 个 --with-plugin 来源。
  日期、核验参数和 --digest 使用数组安全透传，不执行 shell 字符串。
  插件未安装时由 mynews 返回结构化 plugin_not_found，不退化为 built-in-only。
EOF
}

main() {
  if (($# > 0)) && [[ "$1" == "--help" || "$1" == "-h" ]]; then
    usage
    return 0
  fi
  for argument in "$@"; do
    if [[ "$argument" == "--with-plugin" ]]; then
      printf '错误：扩展脚本固定管理 --with-plugin，不能由调用者覆盖\n' >&2
      return 2
    fi
  done
  local -a plugin_args=()
  for plugin_id in "${PLUGIN_IDS[@]}"; do
    plugin_args+=(--with-plugin "$plugin_id")
  done
  exec "$COLLECT_SCRIPT" "$@" "${plugin_args[@]}"
}

main "$@"
