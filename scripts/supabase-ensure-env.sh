#!/usr/bin/env bash
# Ensure .nexusflow/supabase.env is the sole Compose env for docker/supabase:
# create once from .env.example + generate-keys, always symlink docker/supabase/.env,
# refuse placeholders (and heal dual-file drift when a sibling .env has real secrets).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPABASE_DIR="${ROOT}/docker/supabase"
ENV_FILE="${ROOT}/.nexusflow/supabase.env"
EXAMPLE="${SUPABASE_DIR}/.env.example"
SIBLING_ENV="${SUPABASE_DIR}/.env"

mkdir -p "${ROOT}/.nexusflow"

# Exit 0 = placeholders/empty critical secrets present; exit 1 = looks generated.
supabase_env_has_placeholders() {
  python3 - "$1" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
if not path.is_file():
    sys.exit(0)
text = path.read_text(encoding="utf-8", errors="replace")

def val(key: str) -> str:
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, flags=re.M)
    return (m.group(1).strip() if m else "")

checks = ("JWT_SECRET", "POSTGRES_PASSWORD", "ANON_KEY", "SERVICE_ROLE_KEY")
demo_jwt = "super-secret-jwt-token-with-at-least-32-characters-long"
for key in checks:
    v = val(key)
    if not v:
        sys.exit(0)
    if v.startswith("your-") or "your-super-secret" in v or v == demo_jwt:
        sys.exit(0)
sys.exit(1)
PY
}

link_supabase_env() {
  ln -sfn "${ENV_FILE}" "${SIBLING_ENV}"
}

apply_lab_url_defaults() {
  python3 - "${ENV_FILE}" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()

def set_var(text: str, key: str, value: str) -> str:
    pattern = rf"^{re.escape(key)}=.*$"
    line = f"{key}={value}"
    if re.search(pattern, text, flags=re.M):
        return re.sub(pattern, line, text, count=1, flags=re.M)
    return text.rstrip() + f"\n{line}\n"

replacements = {
    "SUPABASE_PUBLIC_URL": "http://127.0.0.1:8000",
    "API_EXTERNAL_URL": "http://127.0.0.1:8000/auth/v1",
    "SITE_URL": "http://127.0.0.1:3001",
    "KONG_HTTP_PORT": "8000",
    "API_GW_HTTP_PORT": "8000",
    "STUDIO_PORT": "3001",
    "ENABLE_EMAIL_AUTOCONFIRM": "true",
    "ENABLE_EMAIL_SIGNUP": "true",
    "DISABLE_SIGNUP": "false",
    "DOCKER_SOCKET_LOCATION": "/var/run/docker.sock",
    "PGRST_DB_SCHEMAS": "public,storage,graphql_public",
    "OPENAI_API_KEY": "",
}
for k, v in replacements.items():
    text = set_var(text, k, v)
path.write_text(text)
print("Lab URL / auth defaults written")
PY
}

rotate_dashboard_password() {
  python3 - "${ENV_FILE}" <<'PY'
from pathlib import Path
import secrets
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()
dash = secrets.token_urlsafe(18)
if re.search(r"^DASHBOARD_PASSWORD=", text, flags=re.M):
    text = re.sub(r"^DASHBOARD_PASSWORD=.*$", f"DASHBOARD_PASSWORD={dash}", text, count=1, flags=re.M)
else:
    text = text.rstrip() + f"\nDASHBOARD_PASSWORD={dash}\n"
path.write_text(text)
print("Dashboard password rotated")
PY
}

run_key_generators() {
  (
    cd "${SUPABASE_DIR}"
    sh utils/generate-keys.sh --update-env </dev/null
    sh utils/add-new-auth-keys.sh --update-env </dev/null
  )
}

# Heal: placeholder ENV_FILE + regular sibling with real secrets → adopt sibling.
adopt_sibling_secrets_if_needed() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    return 0
  fi
  if ! supabase_env_has_placeholders "${ENV_FILE}"; then
    return 0
  fi
  if [[ -f "${SIBLING_ENV}" && ! -L "${SIBLING_ENV}" ]] && ! supabase_env_has_placeholders "${SIBLING_ENV}"; then
    echo "Adopting generated secrets from ${SIBLING_ENV} into ${ENV_FILE} (repair dual-env drift)..."
    cp "${SIBLING_ENV}" "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
  fi
}

if [[ ! -f "${EXAMPLE}" ]]; then
  echo "Missing ${EXAMPLE}" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Creating ${ENV_FILE} from .env.example + generate-keys.sh..."
  cp "${EXAMPLE}" "${ENV_FILE}"
  apply_lab_url_defaults
  link_supabase_env
  run_key_generators
  rotate_dashboard_password
else
  echo "Supabase env exists: ${ENV_FILE}"
  adopt_sibling_secrets_if_needed
  link_supabase_env
fi

chmod 600 "${ENV_FILE}"
link_supabase_env

if supabase_env_has_placeholders "${ENV_FILE}"; then
  echo "Placeholder secrets still present in ${ENV_FILE}; refusing to start." >&2
  echo "Fix: delete ${ENV_FILE} and re-run ./scripts/start.sh supabase (only on a fresh DB volume)," >&2
  echo "  or copy real secrets into ${ENV_FILE}, then re-run." >&2
  exit 1
fi

echo "Supabase env OK (symlinked ${SIBLING_ENV} → ${ENV_FILE}). Do not commit."
