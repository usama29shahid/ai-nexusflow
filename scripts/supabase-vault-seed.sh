#!/usr/bin/env bash
# Supabase Vault seed helpers. Sourced by vault-bootstrap.sh and
# supabase-vault-sync.sh. Caller must define vault_exec and set:
#   NEXUS_DIR, kv_base (and NEXUS_ENV when using defaults).
# Sets SUPABASE_VAULT_CHANGED=1 when a put/patch wrote values.

# Print the value to keep. A non-empty Vault value wins. An empty Vault value
# takes the file value (which may also be empty).
supabase_merge_value() {
  local vault_value="$1"
  local file_value="$2"
  if [[ -n "${vault_value}" ]]; then
    printf '%s' "${vault_value}"
  else
    printf '%s' "${file_value}"
  fi
}

# Exit 0 when an empty Vault field should be copied from the file.
supabase_needs_fill() {
  local vault_value="$1"
  local file_value="$2"
  [[ -z "${vault_value}" && -n "${file_value}" ]]
}

# Read one KV v2 secret as JSON. Failure returns non-zero and does not print a
# value the caller can mistake for an empty field.
supabase_read_secret_json() {
  local path="$1"
  local json errfile
  errfile="$(mktemp)"
  if ! json="$(vault_exec kv get -format=json "${path}" 2>"${errfile}")"; then
    echo "Failed to read ${path}. Refusing to rewrite it." >&2
    cat "${errfile}" >&2 || true
    rm -f "${errfile}"
    return 1
  fi
  rm -f "${errfile}"
  printf '%s' "${json}"
}

# Print one field from `vault kv get -format=json`. A missing field prints
# nothing and returns 0. Invalid JSON returns non-zero.
supabase_secret_field() {
  local json="$1"
  local key="$2"
  printf '%s' "${json}" | python3 -c '
import json
import sys

key = sys.argv[1]
try:
    payload = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)
inner = payload.get("data", {}).get("data", {})
if not isinstance(inner, dict):
    sys.exit(1)
val = inner.get(key)
if val is None:
    val = ""
sys.stdout.write(str(val))
' "${key}"
}

# Read KEY= from a file without sourcing it (values are not all shell-safe).
supabase_read_kv_file() {
  local file="$1"
  local key="$2"
  local line
  [[ -f "${file}" ]] || return 0
  line="$(grep -E "^${key}=" "${file}" 2>/dev/null | tail -1 || true)"
  line="${line#*=}"
  line="${line%$'\r'}"
  if [[ "${line}" == \"*\" && "${line}" == *\" ]]; then
    line="${line#\"}"
    line="${line%\"}"
  fi
  printf '%s' "${line}"
}

supabase_kv_exists() {
  vault_exec kv get -format=json "$1" >/dev/null 2>&1
}

# Fill or create secret/nexusflow/{env}/supabase from .nexusflow/supabase.env.
# Empty first put is allowed so Agent template paths exist; callers should run
# again after supabase.env is generated (see supabase-vault-sync.sh).
seed_supabase_api() {
  local path="${kv_base}/supabase"
  local env_file="${NEXUS_DIR}/supabase.env"
  local file_pub file_secret file_anon file_service file_jwt file_pg
  local vault_pub="" vault_secret="" vault_anon="" vault_service="" vault_jwt="" vault_pg=""
  local pub secret anon service jwt pg
  local exists=0 fill=0 secret_json
  file_pub="$(supabase_read_kv_file "${env_file}" SUPABASE_PUBLISHABLE_KEY)"
  file_secret="$(supabase_read_kv_file "${env_file}" SUPABASE_SECRET_KEY)"
  file_anon="$(supabase_read_kv_file "${env_file}" ANON_KEY)"
  file_service="$(supabase_read_kv_file "${env_file}" SERVICE_ROLE_KEY)"
  file_jwt="$(supabase_read_kv_file "${env_file}" JWT_SECRET)"
  file_pg="$(supabase_read_kv_file "${env_file}" POSTGRES_PASSWORD)"
  if supabase_kv_exists "${path}"; then
    exists=1
    # One JSON read. A failed read aborts before any write, so a blank is never
    # confused with "Vault did not answer".
    secret_json="$(supabase_read_secret_json "${path}")" || return 1
    vault_pub="$(supabase_secret_field "${secret_json}" publishable_key)" || return 1
    vault_secret="$(supabase_secret_field "${secret_json}" secret_key)" || return 1
    vault_anon="$(supabase_secret_field "${secret_json}" anon_key)" || return 1
    vault_service="$(supabase_secret_field "${secret_json}" service_role_key)" || return 1
    vault_jwt="$(supabase_secret_field "${secret_json}" jwt_secret)" || return 1
    vault_pg="$(supabase_secret_field "${secret_json}" postgres_password)" || return 1
  fi
  pub="$(supabase_merge_value "${vault_pub}" "${file_pub}")"
  secret="$(supabase_merge_value "${vault_secret}" "${file_secret}")"
  anon="$(supabase_merge_value "${vault_anon}" "${file_anon}")"
  service="$(supabase_merge_value "${vault_service}" "${file_service}")"
  jwt="$(supabase_merge_value "${vault_jwt}" "${file_jwt}")"
  pg="$(supabase_merge_value "${vault_pg}" "${file_pg}")"
  if [[ "${exists}" == "1" ]]; then
    if supabase_needs_fill "${vault_pub}" "${file_pub}"; then fill=1; fi
    if supabase_needs_fill "${vault_secret}" "${file_secret}"; then fill=1; fi
    if supabase_needs_fill "${vault_anon}" "${file_anon}"; then fill=1; fi
    if supabase_needs_fill "${vault_service}" "${file_service}"; then fill=1; fi
    if supabase_needs_fill "${vault_jwt}" "${file_jwt}"; then fill=1; fi
    if supabase_needs_fill "${vault_pg}" "${file_pg}"; then fill=1; fi
    if [[ "${fill}" == "0" ]]; then
      echo "  KV exists: ${path} (skip seed)"
      return 0
    fi
    echo "  Filling empty fields at ${path}"
    # patch keeps every other key on this path. put would replace the secret.
    vault_exec kv patch "${path}" \
      publishable_key="${pub}" \
      secret_key="${secret}" \
      anon_key="${anon}" \
      service_role_key="${service}" \
      jwt_secret="${jwt}" \
      postgres_password="${pg}"
    SUPABASE_VAULT_CHANGED=1
    return 0
  fi
  echo "  Seeding: ${path}"
  vault_exec kv put "${path}" \
    publishable_key="${pub}" \
    secret_key="${secret}" \
    anon_key="${anon}" \
    service_role_key="${service}" \
    jwt_secret="${jwt}" \
    postgres_password="${pg}"
  SUPABASE_VAULT_CHANGED=1
}

seed_supabase_role() {
  local path="$1"
  local username="$2"
  local user_key="$3"
  local pass_key="$4"
  local env_file="${NEXUS_DIR}/supabase-rbac.env"
  local user pass current secret_json vault_user
  user="$(supabase_read_kv_file "${env_file}" "${user_key}")"
  pass="$(supabase_read_kv_file "${env_file}" "${pass_key}")"
  if [[ -z "${user}" ]]; then
    user="${username}"
  fi
  if supabase_kv_exists "${path}"; then
    secret_json="$(supabase_read_secret_json "${path}")" || return 1
    current="$(supabase_secret_field "${secret_json}" password)" || return 1
    vault_user="$(supabase_secret_field "${secret_json}" username)" || return 1
    if [[ -n "${vault_user}" ]]; then
      user="${vault_user}"
    fi
    if [[ -n "${current}" ]]; then
      echo "  KV exists: ${path} (skip seed)"
      return 0
    fi
    if [[ -z "${pass}" ]]; then
      pass="$(python3 -c 'import secrets; print("k" + secrets.token_urlsafe(24))')"
    fi
    echo "  Filling empty password at ${path}"
    vault_exec kv patch "${path}" username="${user}" password="${pass}"
    SUPABASE_VAULT_CHANGED=1
    return 0
  fi
  if [[ -z "${pass}" ]]; then
    pass="$(python3 -c 'import secrets; print("k" + secrets.token_urlsafe(24))')"
  fi
  echo "  Seeding: ${path}"
  vault_exec kv put "${path}" username="${user}" password="${pass}"
  SUPABASE_VAULT_CHANGED=1
}
