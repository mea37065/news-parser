#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-news-parser}"
APP_USER="${APP_USER:-news-parser}"
APP_GROUP="${APP_GROUP:-$APP_USER}"
APP_DIR="${APP_DIR:-/opt/news-parser}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
UNIT_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/news-parser.service"
UNIT_TARGET="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root, for example: sudo $0" >&2
  exit 1
fi

if [[ ! -f "${UNIT_SOURCE}" ]]; then
  echo "Missing unit template: ${UNIT_SOURCE}" >&2
  exit 1
fi

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

install -d -o "${APP_USER}" -g "${APP_GROUP}" "${APP_DIR}"

if [[ ! -d "${APP_DIR}/venv" ]]; then
  "${PYTHON_BIN}" -m venv "${APP_DIR}/venv"
fi

"${APP_DIR}/venv/bin/python" -m pip install --upgrade pip
"${APP_DIR}/venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"

install -m 0644 "${UNIT_SOURCE}" "${UNIT_TARGET}"
sed -i \
  -e "s|User=news-parser|User=${APP_USER}|g" \
  -e "s|Group=news-parser|Group=${APP_GROUP}|g" \
  -e "s|WorkingDirectory=/opt/news-parser|WorkingDirectory=${APP_DIR}|g" \
  -e "s|EnvironmentFile=/opt/news-parser/.env|EnvironmentFile=${APP_DIR}/.env|g" \
  -e "s|ExecStart=/opt/news-parser/venv/bin/python /opt/news-parser/bot.py|ExecStart=${APP_DIR}/venv/bin/python ${APP_DIR}/bot.py|g" \
  -e "s|ReadWritePaths=/opt/news-parser|ReadWritePaths=${APP_DIR}|g" \
  "${UNIT_TARGET}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"

echo "Installed ${SERVICE_NAME}.service"
echo "Start it with: sudo systemctl start ${SERVICE_NAME}"
echo "Read logs with: sudo journalctl -u ${SERVICE_NAME} -f"
