#!/usr/bin/env bash
# Pure helpers for Supabase Vault seeding. Sourced by scripts/vault-bootstrap.sh.
# No network. vault_exec is provided by the caller.

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
