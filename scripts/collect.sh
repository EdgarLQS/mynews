#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
COLLECT_SCRIPT="${PROJECT_ROOT}/scripts/collect.sh"
LABEL="com.mynews.collect"
PLIST_LOG_DIR="${PROJECT_ROOT}/logs"
DEFAULT_COLLECT_DAYS=1
ACTIVE_LOCK_PATH=""
ACTIVE_TEMP_PATH=""

PROXY_VARIABLES=(
  HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY
  http_proxy https_proxy all_proxy no_proxy
)
SECRET_VARIABLES=(
  OPENAI_API_KEY ANTHROPIC_API_KEY CODEX_API_KEY GITHUB_TOKEN
  API_KEY ACCESS_TOKEN TOKEN
  "${PROXY_VARIABLES[@]}"
)

usage() {
  cat <<'EOF'
用法：
  scripts/collect.sh [--digest] [collect 参数...]
  scripts/collect.sh collect [--digest] [collect 参数...]
  scripts/collect.sh render-plist [--dry-run] [--output 绝对路径]
  scripts/collect.sh install [--dry-run]
  scripts/collect.sh status [--dry-run]
  scripts/collect.sh uninstall [--dry-run]

说明：
  直接执行时默认执行 uv run mynews collect --days 1，参数会原样安全透传。
  显式提供 --days、--date、--from 或 --to 时，不会追加默认日期范围。
  只有显式提供 --digest 时，采集成功后才追加 uv run mynews digest。
  运行目录固定为项目根目录，输出追加到项目 logs/collect.log。
  本地运行数据固定保存在项目内已忽略的 output/、state/ 和 logs/ 目录。
  render-plist 只渲染模板；install、status、uninstall 才会调用 launchctl。
  四个 launchd 动作都支持 --dry-run；预览不会调用 launchctl，也不会写入或删除文件。
  launchd 按主机本地时间每日 09:30 触发；采集进程使用 TZ=Asia/Shanghai，脚本不会修改系统时区。
  代理变量仅继承当前环境，不会打印或写入 plist。

示例：
  scripts/collect.sh
  scripts/collect.sh --days 7
  scripts/collect.sh render-plist --output /tmp/com.mynews.collect.plist
  scripts/collect.sh install
EOF
}

error() {
  printf '错误：%s\n' "$*" >&2
}

release_run_lock() {
  if [[ -n "$ACTIVE_TEMP_PATH" ]]; then
    /bin/rm -f -- "$ACTIVE_TEMP_PATH"
    ACTIVE_TEMP_PATH=""
  fi
  if [[ -n "$ACTIVE_LOCK_PATH" ]]; then
    /bin/rm -f -- "${ACTIVE_LOCK_PATH}/pid"
    /bin/rmdir -- "$ACTIVE_LOCK_PATH" 2>/dev/null || true
    ACTIVE_LOCK_PATH=""
  fi
}

trap release_run_lock EXIT

write_lock_pid() {
  local lock_path="$1"
  if ! printf '%s\n' "$$" >"${lock_path}/pid"; then
    /bin/rm -f -- "${lock_path}/pid"
    /bin/rmdir -- "$lock_path" 2>/dev/null || true
    error "无法写入采集锁：${lock_path}"
    return 1
  fi
}

acquire_run_lock() {
  local lock_path="$1" stale_path pid
  if /bin/mkdir -- "$lock_path" 2>/dev/null; then
    write_lock_pid "$lock_path" || return $?
    ACTIVE_LOCK_PATH="$lock_path"
    return 0
  fi
  if [[ -f "${lock_path}/pid" ]]; then
    pid="$(/bin/cat "${lock_path}/pid" 2>/dev/null || true)"
    if [[ "$pid" =~ ^[0-9]+$ ]] && /bin/kill -0 "$pid" 2>/dev/null; then
      error "已有采集任务运行，跳过本次执行：${lock_path}"
      return 3
    fi
    stale_path="${lock_path}.stale.$$"
    if /bin/mv -- "$lock_path" "$stale_path" 2>/dev/null; then
      /bin/rm -f -- "${stale_path}/pid"
      /bin/rmdir -- "$stale_path" 2>/dev/null || true
      if /bin/mkdir -- "$lock_path" 2>/dev/null; then
        write_lock_pid "$lock_path" || return $?
        ACTIVE_LOCK_PATH="$lock_path"
        return 0
      fi
    fi
  fi
  error "已有采集任务运行，跳过本次执行：${lock_path}"
  return 3
}

require_absolute() {
  local name="$1"
  local value="$2"
  case "$value" in
    /*) ;;
    *)
      error "${name} 必须是绝对路径：${value}"
      return 2
      ;;
  esac
}

home_dir() {
  local value="${HOME:-}"
  if [[ -z "$value" ]]; then
    error 'HOME 未设置'
    return 2
  fi
  require_absolute HOME "$value" || return $?
  printf '%s\n' "$value"
}

resolve_uv() {
  local candidate="${MYNEWS_UV_BIN:-}"
  if [[ -z "$candidate" ]]; then
    candidate="$(command -v uv || true)"
  fi
  if [[ -z "$candidate" ]]; then
    error '找不到 uv；请先准备 uv，不会自动安装依赖'
    return 1
  fi
  require_absolute MYNEWS_UV_BIN "$candidate" || return $?
  if [[ ! -x "$candidate" ]]; then
    error "uv 不可执行：${candidate}"
    return 1
  fi
  printf '%s\n' "$candidate"
}

resolve_launchctl() {
  local candidate="${MYNEWS_LAUNCHCTL_BIN:-}"
  if [[ -z "$candidate" ]]; then
    candidate="$(command -v launchctl || true)"
  fi
  if [[ -z "$candidate" ]]; then
    error '找不到 launchctl；不会自动安装或替换系统组件'
    return 1
  fi
  require_absolute MYNEWS_LAUNCHCTL_BIN "$candidate" || return $?
  if [[ ! -x "$candidate" ]]; then
    error "launchctl 不可执行：${candidate}"
    return 1
  fi
  printf '%s\n' "$candidate"
}

log_dir() {
  local value="${MYNEWS_LOG_DIR:-${PROJECT_ROOT}/logs}"
  require_absolute MYNEWS_LOG_DIR "$value" || return $?
  printf '%s\n' "$value"
}

has_collection_selector() {
  local argument
  for argument in "$@"; do
    case "$argument" in
      --days|--days=*|--date|--date=*|--from|--from=*|--to|--to=*)
        return 0
        ;;
    esac
  done
  return 1
}

has_help_argument() {
  local argument
  for argument in "$@"; do
    if [[ "$argument" == "--help" || "$argument" == "-h" ]]; then
      return 0
    fi
  done
  return 1
}

redact_line() {
  local line="$1"
  local key value
  for key in "${SECRET_VARIABLES[@]}"; do
    value="${!key-}"
    if [[ -n "$value" ]]; then
      line="${line//"$value"/[REDACTED_SECRET]}"
    fi
  done
  printf '%s\n' "$line"
}

redact_stream() {
  local line
  while IFS= read -r line || [[ -n "$line" ]]; do
    redact_line "$line"
  done
}

run_logged_command() {
  local log_file="$1"
  shift
  local temp_root="${TMPDIR:-/tmp}" temp_file command_status filter_status
  local pipeline_status
  temp_file="$(/usr/bin/mktemp "${temp_root}/mynews-command.XXXXXX")"
  ACTIVE_TEMP_PATH="$temp_file"
  set +e
  "$@" 2>&1 | redact_stream >"$temp_file"
  pipeline_status=("${PIPESTATUS[@]}")
  set -e
  command_status="${pipeline_status[0]}"
  filter_status="${pipeline_status[1]}"
  if [[ "$filter_status" -ne 0 ]]; then
    error '无法脱敏命令输出'
    return 1
  fi
  if ! /bin/cat "$temp_file" >>"$log_file"; then
    error "无法写入日志：${log_file}"
    return 1
  fi
  /bin/cat "$temp_file"
  /bin/rm -f -- "$temp_file"
  ACTIVE_TEMP_PATH=""
  return "$command_status"
}

run_collect() {
  local uv_bin log_root log_file command_status digest_status temp_root
  local lock_path digest_requested=false
  local -a collect_args=()
  while (($# > 0)); do
    if [[ "$1" == "--digest" ]]; then
      digest_requested=true
    else
      collect_args+=("$1")
    fi
    shift
  done
  if ((${#collect_args[@]} == 0)); then
    collect_args=(--days "$DEFAULT_COLLECT_DAYS")
  elif ! has_collection_selector "${collect_args[@]}" \
    && ! has_help_argument "${collect_args[@]}"; then
    collect_args=(--days "$DEFAULT_COLLECT_DAYS" "${collect_args[@]}")
  fi
  log_root="$(log_dir)"
  /bin/mkdir -p -- "$log_root"
  lock_path="${log_root}/collect.lock"
  acquire_run_lock "$lock_path" || return $?
  uv_bin="$(resolve_uv)"
  temp_root="${TMPDIR:-/tmp}"
  require_absolute TMPDIR "$temp_root" || return $?
  UV_CACHE_DIR="${UV_CACHE_DIR:-${temp_root}/mynews-uv-cache}"
  require_absolute UV_CACHE_DIR "$UV_CACHE_DIR" || return $?
  export UV_CACHE_DIR
  cd -- "$PROJECT_ROOT"
  log_file="${log_root}/collect.log"
  if run_logged_command "$log_file" "$uv_bin" run mynews collect "${collect_args[@]}"; then
    command_status=0
  else
    command_status=$?
  fi
  if [[ "$digest_requested" == true && ( "$command_status" -eq 0 || "$command_status" -eq 3 ) ]]; then
    if run_logged_command "$log_file" "$uv_bin" run mynews digest --run "${PROJECT_ROOT}/output/latest.json"; then
      digest_status=0
    else
      digest_status=$?
    fi
    if [[ "$digest_status" -ne 0 ]]; then
      return "$digest_status"
    fi
  fi
  return "$command_status"
}

xml_escape() {
  local value="$1"
  value="${value//&/&amp;}"
  value="${value//</&lt;}"
  value="${value//>/&gt;}"
  value="${value//\"/&quot;}"
  printf '%s' "$value"
}

plist_path() {
  local home
  home="$(home_dir)"
  local value="${MYNEWS_PLIST_PATH:-${home}/Library/LaunchAgents/${LABEL}.plist}"
  require_absolute MYNEWS_PLIST_PATH "$value" || return $?
  printf '%s\n' "$value"
}

launchd_domain() {
  local value="${MYNEWS_LAUNCHD_DOMAIN:-gui/$('/usr/bin/id' -u)}"
  if [[ ! "$value" =~ ^gui/[0-9]+$ ]]; then
    error "MYNEWS_LAUNCHD_DOMAIN 必须是 gui/<用户数字ID>：${value}"
    return 2
  fi
  printf '%s\n' "$value"
}

render_plist_xml() {
  local script_path project_root log_dir
  script_path="$(xml_escape "$COLLECT_SCRIPT")"
  project_root="$(xml_escape "$PROJECT_ROOT")"
  log_dir="$(xml_escape "$PLIST_LOG_DIR")"
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${script_path}</string>
    <string>collect</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${project_root}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>TZ</key>
    <string>Asia/Shanghai</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>30</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${log_dir}/launchd.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>${log_dir}/launchd.stderr.log</string>
</dict>
</plist>
EOF
}

lint_plist() {
  local path="$1"
  if [[ ! -x /usr/bin/plutil ]]; then
    error '找不到 /usr/bin/plutil，无法校验 plist'
    return 1
  fi
  /usr/bin/plutil -lint "$path" >/dev/null
}

render_plist_file() {
  local path="$1" parent temporary
  parent="${path%/*}"
  /bin/mkdir -p -- "$parent"
  temporary="$(/usr/bin/mktemp "${parent}/.${LABEL}.XXXXXX")"
  if ! render_plist_xml >"$temporary"; then
    /bin/rm -f -- "$temporary"
    return 1
  fi
  if ! lint_plist "$temporary"; then
    /bin/rm -f -- "$temporary"
    return 1
  fi
  /bin/mv -f -- "$temporary" "$path"
}

render_plist() {
  local output="" dry_run=false
  while (($# > 0)); do
    case "$1" in
      --help|-h)
        usage
        return 0
        ;;
      --output)
        if (($# < 2)); then
          error 'render-plist 的 --output 缺少路径'
          return 2
        fi
        output="$2"
        shift 2
        ;;
      --dry-run)
        dry_run=true
        shift
        ;;
      *)
        error "render-plist 不支持参数：$1"
        return 2
        ;;
    esac
  done
  if [[ "$dry_run" == true ]]; then
    if [[ -n "$output" ]]; then
      require_absolute render-plist-output "$output"
      printf 'dry-run：不会写入 plist：%s\n' "$output" >&2
    fi
    render_plist_xml
    return 0
  fi
  if [[ -n "$output" ]]; then
    require_absolute render-plist-output "$output"
    render_plist_file "$output"
    printf '已渲染 plist：%s\n' "$output"
  else
    render_plist_xml
  fi
}

launchctl_state() {
  local launchctl_bin="$1" domain="$2" status
  set +e
  "$launchctl_bin" print "${domain}/${LABEL}" >/dev/null 2>&1
  status=$?
  set -e
  return "$status"
}

launchctl_service_absent() {
  [[ "$1" -eq 1 || "$1" -eq 113 ]]
}

install_launchd() {
  local domain launchctl_bin path state dry_run=false
  if (($# > 0)); then
    case "$1" in
      --dry-run) dry_run=true ;;
      --help|-h) usage; return 0 ;;
      *) error "install 不支持参数：$1"; return 2 ;;
    esac
    if (($# > 1)); then
      error "install 不支持多个参数"
      return 2
    fi
  fi
  domain="$(launchd_domain)"
  home_dir >/dev/null
  path="$(plist_path)"
  if [[ "$dry_run" == true ]]; then
    printf 'dry-run：将渲染并加载 %s/%s，不会调用 launchctl\n' "$domain" "$LABEL"
    return 0
  fi
  launchctl_bin="$(resolve_launchctl)"
  render_plist_file "$path"
  if launchctl_state "$launchctl_bin" "$domain"; then
    "$launchctl_bin" bootout "${domain}/${LABEL}"
  else
    state=$?
    if ! launchctl_service_absent "$state"; then
      error "无法检查 launchd 任务状态，退出码：${state}"
      return "$state"
    fi
  fi
  "$launchctl_bin" bootstrap "$domain" "$path"
  printf '已安装 launchd 任务：%s/%s\n' "$domain" "$LABEL"
}

status_launchd() {
  local domain launchctl_bin state dry_run=false
  if (($# > 0)); then
    case "$1" in
      --dry-run) dry_run=true ;;
      --help|-h) usage; return 0 ;;
      *) error "status 不支持参数：$1"; return 2 ;;
    esac
    if (($# > 1)); then
      error "status 不支持多个参数"
      return 2
    fi
  fi
  domain="$(launchd_domain)"
  home_dir >/dev/null
  if [[ "$dry_run" == true ]]; then
    printf 'dry-run：将查询 %s/%s，不会调用 launchctl\n' "$domain" "$LABEL"
    return 0
  fi
  launchctl_bin="$(resolve_launchctl)"
  if launchctl_state "$launchctl_bin" "$domain"; then
    printf 'launchd 任务已加载：%s/%s\n' "$domain" "$LABEL"
    return 0
  else
    state=$?
    if launchctl_service_absent "$state"; then
      printf 'launchd 任务未加载：%s/%s\n' "$domain" "$LABEL"
      return 1
    fi
  fi
  error "无法检查 launchd 任务状态，退出码：${state}"
  return "$state"
}

uninstall_launchd() {
  local domain launchctl_bin path state dry_run=false
  if (($# > 0)); then
    case "$1" in
      --dry-run) dry_run=true ;;
      --help|-h) usage; return 0 ;;
      *) error "uninstall 不支持参数：$1"; return 2 ;;
    esac
    if (($# > 1)); then
      error "uninstall 不支持多个参数"
      return 2
    fi
  fi
  domain="$(launchd_domain)"
  home_dir >/dev/null
  path="$(plist_path)"
  if [[ "$dry_run" == true ]]; then
    printf 'dry-run：将卸载 %s/%s 并删除 %s，不会调用 launchctl\n' \
      "$domain" "$LABEL" "$path"
    return 0
  fi
  launchctl_bin="$(resolve_launchctl)"
  if launchctl_state "$launchctl_bin" "$domain"; then
    "$launchctl_bin" bootout "${domain}/${LABEL}"
  else
    state=$?
    if ! launchctl_service_absent "$state"; then
      error "无法检查 launchd 任务状态，退出码：${state}"
      return "$state"
    fi
  fi
  if [[ -e "$path" ]]; then
    /bin/rm -f -- "$path"
  fi
  printf '已卸载 launchd 任务：%s/%s\n' "$domain" "$LABEL"
}

main() {
  local action="${1:-}"
  case "$action" in
    --help|-h)
      usage
      ;;
    '')
      run_collect "$@"
      ;;
    collect)
      shift
      run_collect "$@"
      ;;
    render-plist)
      shift
      home_dir >/dev/null
      render_plist "$@"
      ;;
    install)
      shift
      install_launchd "$@"
      ;;
    status)
      shift
      status_launchd "$@"
      ;;
    uninstall)
      shift
      uninstall_launchd "$@"
      ;;
    *)
      run_collect "$@"
      ;;
  esac
}

main "$@"
