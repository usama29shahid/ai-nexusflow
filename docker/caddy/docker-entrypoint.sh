#!/bin/sh
# Select Caddyfile by NEXUS_EDGE_MODE so deploy/automation does not hand-edit TLS settings.
# local → auto_https off + http:// site scheme (default)
# vps   → Let's Encrypt + bare hostnames; reject http:// scheme and public backend binds
set -eu

MODE="${NEXUS_EDGE_MODE:-local}"
case "${MODE}" in
local | vps) ;;
*)
	echo "caddy: NEXUS_EDGE_MODE must be 'local' or 'vps' (got: ${MODE})" >&2
	exit 1
	;;
esac

SRC="/templates/Caddyfile.${MODE}"
if [ ! -f "${SRC}" ]; then
	echo "caddy: missing ${SRC}" >&2
	exit 1
fi
if [ ! -f /templates/sites.caddy ]; then
	echo "caddy: missing /templates/sites.caddy" >&2
	exit 1
fi

cp "${SRC}" /etc/caddy/Caddyfile
cp /templates/sites.caddy /etc/caddy/sites.caddy

# One shared popup for docs., elementary., and cube. Hash is written here so
# the plaintext password never lands in the Caddyfile in git.
write_docs_basic_auth() {
	user="${NEXUS_DOCS_BASIC_AUTH_USER:-}"
	pass="${NEXUS_DOCS_BASIC_AUTH_PASSWORD:-}"
	if [ -z "${user}" ] || [ -z "${pass}" ]; then
		echo "caddy: fatal: NEXUS_DOCS_BASIC_AUTH_USER and NEXUS_DOCS_BASIC_AUTH_PASSWORD are required" >&2
		echo "caddy: seed Vault secret/nexusflow/\${NEXUS_ENV}/docs_basic_auth (./scripts/start.sh vault)" >&2
		exit 1
	fi
	case "${user}" in
	*[!A-Za-z0-9._-]*)
		echo "caddy: fatal: docs basic auth user has unsupported characters" >&2
		exit 1
		;;
	esac
	# htpasswd reads the password on stdin. Do not pass it as an argument.
	hash="$(printf '%s\n' "${pass}" | htpasswd -niBC 14 "${user}" | cut -d: -f2-)"
	hash="${hash%%$(printf '\r')}"
	case "${hash}" in
	'$2'*) ;;
	*)
		echo "caddy: fatal: password hash failed" >&2
		exit 1
		;;
	esac
	# Imported Caddyfiles keep a single $ in a bcrypt hash. Do not double it.
	{
		printf '%s\n' '(docs_basic_auth) {'
		printf '\tbasic_auth {\n'
		printf '\t\t%s %s\n' "${user}" "${hash}"
		printf '\t}\n'
		printf '}\n'
	} > /etc/caddy/docs-basicauth.caddy
	# Cube's playground sets its own Authorization header, which replaces the
	# browser Basic header. After the first successful popup, a host-only cookie
	# lets those API calls through. The cookie value is not the password.
	# The value is bound to the current DOCS_GATE_TTL window, so a copied cookie
	# stops matching when that window ends and Caddy reloads.
	secure=""
	if [ "${MODE}" = "vps" ]; then
		secure="; Secure"
	fi
	apply_docs_gate || exit 1
	echo "caddy: docs basic auth enabled for user ${user}"
}

# 24h UTC window. A copied docs_gate cookie is rejected after this window ends.
# Max-Age is the remaining seconds in the current window (refreshed every
# DOCS_GATE_REFRESH_INTERVAL; hourly keeps VPS reloads quiet while staying accurate).
# Failures retry after DOCS_GATE_RETRY_DELAY — not after a full window.
DOCS_GATE_TTL=86400
DOCS_GATE_REFRESH_INTERVAL=3600
DOCS_GATE_RETRY_DELAY=30

docs_gate_window() {
	echo $(( $(date +%s) / DOCS_GATE_TTL ))
}

docs_gate_max_age() {
	now="$(date +%s)"
	echo $(( DOCS_GATE_TTL - now % DOCS_GATE_TTL ))
}

# Sleep until the next Max-Age refresh, or until the window boundary if sooner.
docs_gate_sleep_delay() {
	now="$(date +%s)"
	rem=$(( now % DOCS_GATE_TTL ))
	if [ "${rem}" -eq 0 ]; then
		echo 1
		return 0
	fi
	until_boundary=$(( DOCS_GATE_TTL - rem ))
	delay="${DOCS_GATE_REFRESH_INTERVAL}"
	if [ "${until_boundary}" -lt "${delay}" ]; then
		delay="${until_boundary}"
	fi
	echo "${delay}"
}

refresh_docs_gate() {
	before=""
	if [ -f /etc/caddy/sites.caddy ]; then
		before="$(sha256sum /etc/caddy/sites.caddy | awk '{print $1}')"
	fi
	apply_docs_gate || return 1
	after="$(sha256sum /etc/caddy/sites.caddy | awk '{print $1}')"
	# Identical render (retry with the same Max-Age second): skip reload noise.
	if [ -n "${before}" ] && [ "${before}" = "${after}" ]; then
		return 0
	fi
	# reload re-adapts the Caddyfile in this process. {$NEXUS_CADDY_SITE_SCHEME}
	# must match boot: an empty value makes hostnames HTTPS-only and moves the
	# listener to :443, which drops local :80.
	if [ "${MODE}" = "local" ]; then
		export NEXUS_CADDY_SITE_SCHEME="${NEXUS_CADDY_SITE_SCHEME:-http://}"
	fi
	export NEXUS_PUBLIC_HOST="${NEXUS_PUBLIC_HOST:?NEXUS_PUBLIC_HOST is required for reload}"
	caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile || return 1
	return 0
}

apply_docs_gate() {
	gate="$(printf '%s' "cube-docs-gate-v2:${pass}:$(docs_gate_window)" | sha256sum | awk '{print $1}')"
	case "${#gate}" in
	64) ;;
	*)
		echo "caddy: docs gate hash was empty or not hex" >&2
		return 1
		;;
	esac
	case "${gate}" in
	*[!0-9a-f]*)
		echo "caddy: docs gate hash was empty or not hex" >&2
		return 1
		;;
	esac
	max_age="$(docs_gate_max_age)"
	case "${max_age}" in
	'' | *[!0-9]* | 0)
		echo "caddy: docs gate Max-Age was invalid (${max_age})" >&2
		return 1
		;;
	esac
	# Write a temp file then replace, so a failed refresh leaves the live sites.caddy alone.
	tmp="$(mktemp /etc/caddy/sites.caddy.XXXXXX)" || return 1
	if ! cp /templates/sites.caddy "${tmp}"; then
		rm -f "${tmp}"
		return 1
	fi
	if ! sed -i \
		-e "s/__NEXUS_DOCS_GATE__/${gate}/g" \
		-e "s/__NEXUS_DOCS_COOKIE_SECURE__/${secure}/g" \
		-e "s/__NEXUS_DOCS_COOKIE_MAX_AGE__/${max_age}/g" \
		"${tmp}"; then
		rm -f "${tmp}"
		return 1
	fi
	if grep -q '__NEXUS_DOCS_GATE__\|__NEXUS_DOCS_COOKIE_SECURE__\|__NEXUS_DOCS_COOKIE_MAX_AGE__' "${tmp}"; then
		echo "caddy: docs gate placeholder was not filled" >&2
		rm -f "${tmp}"
		return 1
	fi
	# Template must actually carry the cookie lines. A truncated template can lose
	# placeholders before sed, pass the check above, and still be unloadable.
	if ! grep -q "docs_gate=${gate}" "${tmp}" \
		|| ! grep -q "Max-Age=${max_age}" "${tmp}"; then
		echo "caddy: docs gate cookie lines missing from rendered sites.caddy" >&2
		rm -f "${tmp}"
		return 1
	fi
	if [ -f /etc/caddy/sites.caddy ] && cmp -s "${tmp}" /etc/caddy/sites.caddy; then
		rm -f "${tmp}"
		return 0
	fi
	if ! mv "${tmp}" /etc/caddy/sites.caddy; then
		rm -f "${tmp}"
		return 1
	fi
}

write_docs_basic_auth

if [ "${MODE}" = "local" ]; then
	if [ -z "${NEXUS_CADDY_SITE_SCHEME:-}" ]; then
		export NEXUS_CADDY_SITE_SCHEME="http://"
	fi
else
	# vps: refuse WSL-style HTTP scheme and missing ACME email (fail closed for automation).
	if [ "${NEXUS_CADDY_SITE_SCHEME:-}" = "http://" ]; then
		echo "caddy: fatal: NEXUS_EDGE_MODE=vps cannot use NEXUS_CADDY_SITE_SCHEME=http://" >&2
		echo "caddy: leave NEXUS_CADDY_SITE_SCHEME empty for HTTPS hostnames" >&2
		exit 1
	fi
	if [ -z "${NEXUS_CADDY_ACME_EMAIL:-}" ]; then
		echo "caddy: fatal: NEXUS_CADDY_ACME_EMAIL is required when NEXUS_EDGE_MODE=vps" >&2
		exit 1
	fi
	# Compose defaults backends to 127.0.0.1; reject an explicit public bind on VPS.
	BIND="${NEXUS_PUBLISH_BIND:-127.0.0.1}"
	if [ "${BIND}" = "0.0.0.0" ] || [ "${BIND}" = "::" ] || [ "${BIND}" = "[::]" ]; then
		echo "caddy: fatal: NEXUS_EDGE_MODE=vps cannot use NEXUS_PUBLISH_BIND=${BIND}" >&2
		echo "caddy: set NEXUS_PUBLISH_BIND=127.0.0.1 so ClickHouse/MinIO/etc. are not internet-facing" >&2
		exit 1
	fi
fi

echo "caddy: NEXUS_EDGE_MODE=${MODE} NEXUS_PUBLIC_HOST=${NEXUS_PUBLIC_HOST:-} scheme='${NEXUS_CADDY_SITE_SCHEME:-}' bind='${NEXUS_PUBLISH_BIND:-127.0.0.1}'"

# Refresh Max-Age on an interval and rotate the gate at each window boundary.
# The loop is a child so caddy stays PID 1. Failures retry after
# DOCS_GATE_RETRY_DELAY and must not exit or wait for the next UTC window.
# NEXUS_CADDY_GATE_REFRESH=0 skips it (unit tests).
if [ "${NEXUS_CADDY_GATE_REFRESH:-1}" != "0" ]; then
	(
		trap '' HUP
		while true; do
			sleep "$(docs_gate_sleep_delay)"
			until refresh_docs_gate; do
				echo "caddy: docs gate refresh failed; retry in ${DOCS_GATE_RETRY_DELAY}s" >&2
				sleep "${DOCS_GATE_RETRY_DELAY}"
			done
		done
	) &
fi
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
