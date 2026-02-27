#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
ENV_FILE="$RUN_DIR/dev.env"
QUIET="${1:-}"

mkdir -p "$RUN_DIR"

gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
    return
  fi
  date +%s%N
}

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

: "${APP_LOGIN_USERNAME:=local_admin}"
: "${APP_LOGIN_PASSWORD:=local_$(gen_secret)}"

: "${API_LOGIN_USER:=api_user}"
: "${API_LOGIN_PASSWORD:=api_$(gen_secret)}"
: "${API_AUTH_SECRET:=secret_$(gen_secret)}"

: "${SIMPLYPARSE_API_TOKEN:=token_$(gen_secret)}"
: "${PYTHON_SERVICE_AUTH_TOKEN:=$SIMPLYPARSE_API_TOKEN}"
: "${CORS_ALLOW_ORIGINS:=http://127.0.0.1:8080,http://localhost:8080}"

cat >"$ENV_FILE" <<EOF
export APP_LOGIN_USERNAME="${APP_LOGIN_USERNAME}"
export APP_LOGIN_PASSWORD="${APP_LOGIN_PASSWORD}"
export API_LOGIN_USER="${API_LOGIN_USER}"
export API_LOGIN_PASSWORD="${API_LOGIN_PASSWORD}"
export API_AUTH_SECRET="${API_AUTH_SECRET}"
export SIMPLYPARSE_API_TOKEN="${SIMPLYPARSE_API_TOKEN}"
export PYTHON_SERVICE_AUTH_TOKEN="${PYTHON_SERVICE_AUTH_TOKEN}"
export CORS_ALLOW_ORIGINS="${CORS_ALLOW_ORIGINS}"
EOF

export APP_LOGIN_USERNAME APP_LOGIN_PASSWORD
export API_LOGIN_USER API_LOGIN_PASSWORD API_AUTH_SECRET
export SIMPLYPARSE_API_TOKEN PYTHON_SERVICE_AUTH_TOKEN CORS_ALLOW_ORIGINS

if [[ "$QUIET" != "--quiet" ]]; then
  echo "Loaded dev env from: $ENV_FILE"
  echo "APP_LOGIN_USERNAME=$APP_LOGIN_USERNAME"
  echo "API_LOGIN_USER=$API_LOGIN_USER"
  echo "CORS_ALLOW_ORIGINS=$CORS_ALLOW_ORIGINS"
fi
