#!/bin/sh
# Render alertmanager config from template substituting env vars, then start alertmanager.
# Needed because Alertmanager does not expand environment variables in its config natively.
set -e

TEMPLATE=/etc/alertmanager/alertmanager.yml.template
RENDERED=/tmp/alertmanager.yml

sed \
  -e "s|\${SMTP_FROM}|${SMTP_FROM}|g" \
  -e "s|\${SMTP_AUTH_USERNAME}|${SMTP_AUTH_USERNAME}|g" \
  -e "s|\${SMTP_AUTH_PASSWORD}|${SMTP_AUTH_PASSWORD}|g" \
  -e "s|\${ALERT_EMAIL_TO}|${ALERT_EMAIL_TO}|g" \
  "$TEMPLATE" > "$RENDERED"

exec /bin/alertmanager \
  --config.file="$RENDERED" \
  --storage.path=/alertmanager \
  --cluster.listen-address=
