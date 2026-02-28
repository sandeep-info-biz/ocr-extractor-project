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

: "${API_LOGIN_USER:=api_user}"
: "${API_LOGIN_PASSWORD:=api_$(gen_secret)}"
: "${API_AUTH_SECRET:=secret_$(gen_secret)}"

: "${SIMPLYPARSE_API_TOKEN:=token_$(gen_secret)}"
: "${PYTHON_SERVICE_AUTH_TOKEN:=$SIMPLYPARSE_API_TOKEN}"
: "${CORS_ALLOW_ORIGINS:=http://127.0.0.1:8080,http://localhost:8080}"
: "${SPRING_DATASOURCE_URL:=jdbc:postgresql://localhost:5432/ecvms_db}"
: "${SPRING_DATASOURCE_USERNAME:=postgres}"
: "${SPRING_DATASOURCE_PASSWORD:=root}"
: "${AUTO_TRAIN_MODEL_ONLY:=true}"
: "${ASYNC_INLINE_SUBMIT_ENABLED:=false}"

cat >"$ENV_FILE" <<EOF
export API_LOGIN_USER="${API_LOGIN_USER}"
export API_LOGIN_PASSWORD="${API_LOGIN_PASSWORD}"
export API_AUTH_SECRET="${API_AUTH_SECRET}"
export SIMPLYPARSE_API_TOKEN="${SIMPLYPARSE_API_TOKEN}"
export PYTHON_SERVICE_AUTH_TOKEN="${PYTHON_SERVICE_AUTH_TOKEN}"
export CORS_ALLOW_ORIGINS="${CORS_ALLOW_ORIGINS}"
export SPRING_DATASOURCE_URL="${SPRING_DATASOURCE_URL}"
export SPRING_DATASOURCE_USERNAME="${SPRING_DATASOURCE_USERNAME}"
export SPRING_DATASOURCE_PASSWORD="${SPRING_DATASOURCE_PASSWORD}"
export AUTO_TRAIN_MODEL_ONLY="${AUTO_TRAIN_MODEL_ONLY}"
export ASYNC_INLINE_SUBMIT_ENABLED="${ASYNC_INLINE_SUBMIT_ENABLED}"
EOF

export API_LOGIN_USER API_LOGIN_PASSWORD API_AUTH_SECRET
export SIMPLYPARSE_API_TOKEN PYTHON_SERVICE_AUTH_TOKEN CORS_ALLOW_ORIGINS
export SPRING_DATASOURCE_URL SPRING_DATASOURCE_USERNAME SPRING_DATASOURCE_PASSWORD
export AUTO_TRAIN_MODEL_ONLY
export ASYNC_INLINE_SUBMIT_ENABLED

if [[ "$QUIET" != "--quiet" ]]; then
  echo "Loaded dev env from: $ENV_FILE"
  echo "SPRING_DATASOURCE_URL=$SPRING_DATASOURCE_URL"
  echo "AUTO_TRAIN_MODEL_ONLY=$AUTO_TRAIN_MODEL_ONLY"
  echo "ASYNC_INLINE_SUBMIT_ENABLED=$ASYNC_INLINE_SUBMIT_ENABLED"
  echo "API_LOGIN_USER=$API_LOGIN_USER"
  echo "CORS_ALLOW_ORIGINS=$CORS_ALLOW_ORIGINS"
fi
