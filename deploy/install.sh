#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="${REPO_URL:-https://github.com/userreksai/monitoring-web.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/monitoring-web}"
SERVICE_NAME="${SERVICE_NAME:-monitoring-web}"
SERVICE_USER="${SERVICE_USER:-monitoring-web}"
PORT="${PORT:-8900}"
API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8901}"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
ENV_FILE="${APP_DIR}/.env"

log() {
  printf '[monitoring-web] %s\n' "$*"
}

fail() {
  printf '[monitoring-web] ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
  fail "请使用 root 用户运行，或执行：sudo bash $0"
fi

if [[ ! -f /etc/os-release ]]; then
  fail "无法识别当前 Linux 系统"
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "24.04" ]]; then
  fail "此脚本仅支持 Ubuntu 24.04 LTS（检测到 ${PRETTY_NAME:-unknown}）"
fi

if [[ ! "${PORT}" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  fail "PORT 必须是 1-65535 之间的整数"
fi
if [[ ! "${API_BASE_URL}" =~ ^https?:// ]]; then
  fail "API_BASE_URL 必须以 http:// 或 https:// 开头"
fi

export DEBIAN_FRONTEND=noninteractive

log "安装系统依赖"
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl git

# Vite 7 要求 Node.js 20.19+；Ubuntu 默认版本不足时安装 Node.js 22 LTS。
NODE_VERSION="0"
if command -v node >/dev/null 2>&1; then
  NODE_VERSION="$(node -p 'process.versions.node')"
fi
if ! dpkg --compare-versions "${NODE_VERSION}" ge "20.19.0"; then
  log "安装 Node.js 22 LTS"
  NODE_SETUP="$(mktemp)"
  curl -fsSL https://deb.nodesource.com/setup_22.x -o "${NODE_SETUP}"
  bash "${NODE_SETUP}"
  rm -f "${NODE_SETUP}"
  apt-get install -y --no-install-recommends nodejs
fi
command -v npm >/dev/null 2>&1 || fail "Node.js 已安装，但未找到 npm"

PNPM_VERSION="11.19.0"
if ! command -v pnpm >/dev/null 2>&1 || [[ "$(pnpm --version)" != "${PNPM_VERSION}" ]]; then
  log "安装 pnpm ${PNPM_VERSION}"
  npm install --global "pnpm@${PNPM_VERSION}" --no-audit --no-fund
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  log "创建系统用户 ${SERVICE_USER}"
  useradd --system --user-group --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

if [[ -d "${APP_DIR}/.git" ]]; then
  log "更新 ${BRANCH} 分支代码"
  git -c safe.directory="${APP_DIR}" -C "${APP_DIR}" remote set-url origin "${REPO_URL}"
  git -c safe.directory="${APP_DIR}" -C "${APP_DIR}" fetch --prune origin "${BRANCH}"
  git -c safe.directory="${APP_DIR}" -C "${APP_DIR}" checkout "${BRANCH}"
  git -c safe.directory="${APP_DIR}" -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"
elif [[ -e "${APP_DIR}" ]] && [[ -n "$(find "${APP_DIR}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  fail "安装目录已存在且不是空 Git 仓库：${APP_DIR}"
else
  log "克隆代码到 ${APP_DIR}"
  mkdir -p "$(dirname "${APP_DIR}")"
  git clone --branch "${BRANCH}" --single-branch "${REPO_URL}" "${APP_DIR}"
fi

cd "${APP_DIR}"
[[ -f pnpm-lock.yaml ]] || fail "缺少 pnpm-lock.yaml，无法执行固定版本安装"
[[ -f server.mjs ]] || fail "缺少生产服务入口 server.mjs"

log "安装依赖并构建 Vue"
pnpm install --frozen-lockfile
pnpm run build
[[ -f dist/index.html ]] || fail "Vue 构建未生成 dist/index.html"

if [[ ! -f "${ENV_FILE}" ]]; then
  umask 077
  cat >"${ENV_FILE}" <<EOF
PORT=${PORT}
API_BASE_URL=${API_BASE_URL}
EOF
  log "已创建运行配置 ${ENV_FILE}"
else
  log "保留现有运行配置 ${ENV_FILE}"
fi
chown root:"${SERVICE_USER}" "${ENV_FILE}"
chmod 0640 "${ENV_FILE}"

SERVICE_PORT="$(sed -n 's/^PORT=\([0-9][0-9]*\)$/\1/p' "${ENV_FILE}" | tail -n 1)"
if [[ -z "${SERVICE_PORT}" || ! "${SERVICE_PORT}" =~ ^[0-9]+$ ]] || (( SERVICE_PORT < 1 || SERVICE_PORT > 65535 )); then
  fail "${ENV_FILE} 中缺少有效的 PORT"
fi

log "写入 systemd 服务 ${SERVICE_NAME}"
cat >"${UNIT_FILE}" <<EOF
[Unit]
Description=SMS Billing Monitoring Web Frontend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
Environment=NODE_ENV=production
EnvironmentFile=${ENV_FILE}
ExecStart=/usr/bin/node ${APP_DIR}/server.mjs
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

chmod 0644 "${UNIT_FILE}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

log "等待前端服务启动"
for _ in {1..30}; do
  if curl --fail --silent --max-time 2 "http://127.0.0.1:${SERVICE_PORT}/" >/dev/null; then
    log "部署完成：http://服务器IP:${SERVICE_PORT}"
    log "API 代理目标由 ${ENV_FILE} 中的 API_BASE_URL 配置"
    systemctl --no-pager --full status "${SERVICE_NAME}" | sed -n '1,8p'
    exit 0
  fi
  sleep 1
done

systemctl --no-pager --full status "${SERVICE_NAME}" || true
journalctl -u "${SERVICE_NAME}" -n 50 --no-pager || true
fail "前端服务未能在端口 ${SERVICE_PORT} 正常响应"
