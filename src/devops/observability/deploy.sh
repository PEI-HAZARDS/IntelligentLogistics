#!/bin/bash
# Deploy observability stack to Jenkins CI server.
# Usage:
#   ./deploy.sh          — SCP files + bring up stack
#   ./deploy.sh scp      — SCP only
#   ./deploy.sh up       — docker compose up only (files already on server)
#   ./deploy.sh down     — docker compose down
#   ./deploy.sh logs     — follow logs
#
# NOTE: compose commands run via SSH on the remote host so bind mount paths
# are resolved correctly by the remote Docker daemon.
set -euo pipefail

# ---------------------------------------------------------------------------
# Config — read from .env if present
# ---------------------------------------------------------------------------
ENV_FILE="$(dirname "$0")/.env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

REMOTE_USER="${REMOTE_USER:-pei_user}"
REMOTE_HOST="${JENKINS_VM_IP:?JENKINS_VM_IP not set in .env}"
REMOTE_DIR="${REMOTE_DIR:-~/observability}"
SSH_TARGET="${REMOTE_USER}@${REMOTE_HOST}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "[deploy] $*"; }
die()  { echo "[deploy] ERROR: $*" >&2; exit 1; }

check_smtp() {
  if [[ "${SMTP_AUTH_PASSWORD:-}" == "your-app-password-here" ]] || [[ -z "${SMTP_AUTH_PASSWORD:-}" ]]; then
    die "SMTP_AUTH_PASSWORD is not configured in .env — alertmanager will not send emails."
  fi
  if [[ "${SMTP_AUTH_USERNAME:-}" == "your-project-email@gmail.com" ]] || [[ -z "${SMTP_AUTH_USERNAME:-}" ]]; then
    die "SMTP_AUTH_USERNAME is not configured in .env"
  fi
  if [[ "${ALERT_EMAIL_TO:-}" == "your-team-email@example.com" ]] || [[ -z "${ALERT_EMAIL_TO:-}" ]]; then
    die "ALERT_EMAIL_TO is not configured in .env"
  fi
}

do_scp() {
  log "Copying files to ${SSH_TARGET}:${REMOTE_DIR} ..."
  # Ensure remote dir exists
  ssh "${SSH_TARGET}" "mkdir -p ${REMOTE_DIR}"

  scp -r \
    "$(dirname "$0")/alertmanager" \
    "$(dirname "$0")/grafana" \
    "$(dirname "$0")/prometheus" \
    "$(dirname "$0")/loki" \
    "$(dirname "$0")/promtail" \
    "$(dirname "$0")/tempo" \
    "$(dirname "$0")/docker-compose.yml" \
    "${SSH_TARGET}:${REMOTE_DIR}/"

  # Copy .env separately (contains secrets — not in git)
  log "Copying .env to server ..."
  scp "${ENV_FILE}" "${SSH_TARGET}:${REMOTE_DIR}/.env"

  log "SCP complete."
}

do_up() {
  log "Bringing up observability stack on ${SSH_TARGET} ..."
  ssh "${SSH_TARGET}" "cd ${REMOTE_DIR} && docker compose up -d"
  log "Stack is up. Grafana → http://${REMOTE_HOST}:3000"
}

do_down() {
  log "Bringing down observability stack on ${SSH_TARGET} ..."
  ssh "${SSH_TARGET}" "cd ${REMOTE_DIR} && docker compose down"
}

do_logs() {
  ssh "${SSH_TARGET}" "cd ${REMOTE_DIR} && docker compose logs -f"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
CMD="${1:-deploy}"

case "$CMD" in
  deploy)
    check_smtp
    do_scp
    do_up
    ;;
  scp)
    check_smtp
    do_scp
    ;;
  up)
    do_up
    ;;
  down)
    do_down
    ;;
  logs)
    do_logs
    ;;
  *)
    echo "Usage: $0 [deploy|scp|up|down|logs]"
    exit 1
    ;;
esac
