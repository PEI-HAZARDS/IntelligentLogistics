#!/bin/sh
# Render alertmanager config from template substituting env vars, then start alertmanager.
# Needed because Alertmanager does not expand environment variables in its config natively.
#
# Behaviour:
#   - ALERT_EMAIL_TO unset → minimal null receiver (no credentials needed)
#   - ALERT_EMAIL_TO set, SLACK_WEBHOOK_URL unset → email only (SLACK_BEGIN/END sections removed)
#   - Both set → email + Slack (full template rendered)
set -e

TEMPLATE=/etc/alertmanager/alertmanager.yml.template
RENDERED=/tmp/alertmanager.yml

if [ -z "${ALERT_EMAIL_TO}" ]; then
  cat > "$RENDERED" <<'EOF'
route:
  receiver: 'null'
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  group_by: ['alertname']
receivers:
  - name: 'null'
inhibit_rules: []
EOF
elif [ -z "${SLACK_WEBHOOK_URL}" ]; then
  # Email only — strip SLACK_BEGIN..SLACK_END blocks before substituting
  awk '/# SLACK_BEGIN/{skip=1} /# SLACK_END/{skip=0; next} !skip' "$TEMPLATE" | \
    sed \
      -e "s|\${SMTP_FROM}|${SMTP_FROM}|g" \
      -e "s|\${SMTP_AUTH_USERNAME}|${SMTP_AUTH_USERNAME}|g" \
      -e "s|\${SMTP_AUTH_PASSWORD}|${SMTP_AUTH_PASSWORD}|g" \
      -e "s|\${ALERT_EMAIL_TO}|${ALERT_EMAIL_TO}|g" \
    > "$RENDERED"
else
  # Email + Slack — substitute all vars, remove markers only
  sed \
    -e "s|\${SMTP_FROM}|${SMTP_FROM}|g" \
    -e "s|\${SMTP_AUTH_USERNAME}|${SMTP_AUTH_USERNAME}|g" \
    -e "s|\${SMTP_AUTH_PASSWORD}|${SMTP_AUTH_PASSWORD}|g" \
    -e "s|\${ALERT_EMAIL_TO}|${ALERT_EMAIL_TO}|g" \
    -e "s|\${SLACK_WEBHOOK_URL}|${SLACK_WEBHOOK_URL}|g" \
    -e "s|\${SLACK_CHANNEL}|${SLACK_CHANNEL:-#alerts}|g" \
    -e '/# SLACK_BEGIN/d' \
    -e '/# SLACK_END/d' \
    "$TEMPLATE" > "$RENDERED"
fi

exec /bin/alertmanager \
  --config.file="$RENDERED" \
  --storage.path=/alertmanager \
  --cluster.listen-address=
