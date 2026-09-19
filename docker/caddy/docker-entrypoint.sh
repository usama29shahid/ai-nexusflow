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
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
