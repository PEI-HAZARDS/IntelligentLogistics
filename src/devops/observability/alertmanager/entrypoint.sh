#!/bin/sh
# Render alertmanager config from template substituting env vars, then start alertmanager.
# Needed because Alertmanager does not expand environment variables in its config natively.
# If ALERT_EMAIL_TO is unset, falls back to a null (blackhole) receiver so the
# container starts cleanly without email credentials.
set -e

TEMPLATE=/etc/alertmanager/alertmanager.yml.template
RENDERED=/tmp/alertmanager.yml

if [ -z "${ALERT_EMAIL_TO}" ]; then
  # No email configured — write a minimal config with a null receiver
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
else
  sed \
    -e "s|\${SMTP_FROM}|${SMTP_FROM}|g" \
    -e "s|\${SMTP_AUTH_USERNAME}|${SMTP_AUTH_USERNAME}|g" \
    -e "s|\${SMTP_AUTH_PASSWORD}|${SMTP_AUTH_PASSWORD}|g" \
    -e "s|\${ALERT_EMAIL_TO}|${ALERT_EMAIL_TO}|g" \
    "$TEMPLATE" > "$RENDERED"
fi

exec /bin/alertmanager \
  --config.file="$RENDERED" \
  --storage.path=/alertmanager \
  --cluster.listen-address=
