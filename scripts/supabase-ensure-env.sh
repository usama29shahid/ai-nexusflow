#!/usr/bin/env bash
# Create .nexusflow/supabase.env from upstream .env.example + generate-keys.sh when missing.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPABASE_DIR="${ROOT}/docker/supabase"
ENV_FILE="${ROOT}/.nexusflow/supabase.env"
EXAMPLE="${SUPABASE_DIR}/.env.example"

mkdir -p "${ROOT}/.nexusflow"

if [[ -f "${ENV_FILE}" ]]; then
  echo "Supabase env exists: ${ENV_FILE}"
  exit 0
fi

if [[ ! -f "${EXAMPLE}" ]]; then
  echo "Missing ${EXAMPLE}" >&2
  exit 1
fi

echo "Creating ${ENV_FILE} from .env.example + generate-keys.sh..."
cp "${EXAMPLE}" "${ENV_FILE}"

# Lab defaults: loopback API, email autoconfirm (no SMTP), Studio on 3001.
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

# Upstream generator expects .env in the docker/supabase directory.
ln -sfn "${ENV_FILE}" "${SUPABASE_DIR}/.env"
(
  cd "${SUPABASE_DIR}"
  # Non-interactive: write secrets into linked .env
  sh utils/generate-keys.sh --update-env </dev/null
  sh utils/add-new-auth-keys.sh --update-env </dev/null
)

# Strong Studio password (generator may leave a weak default).
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

chmod 600 "${ENV_FILE}"
echo "Wrote ${ENV_FILE} (chmod 600). Do not commit."
