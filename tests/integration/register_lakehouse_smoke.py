"""Re-register raw_dlt_smoke.smoke in Polaris after docker compose down/up.

Polaris uses an in-memory catalog: namespaces/tables are lost on restart even though
Iceberg files remain in MinIO. Run this after bringing the lakehouse profile back up:

    set -a && source .env && set +a
    ./scripts/lakehouse-restore.sh
"""

from __future__ import annotations

import sys

from pyiceberg.exceptions import NoSuchNamespaceError, NoSuchTableError

from lakehouse_catalog import (
    catalog_name,
    find_latest_smoke_metadata_location,
    load_dotenv,
    load_polaris_catalog,
    nexus_env,
)


# 2 = nothing to register (first-time setup). 1 = Polaris/MinIO error (fail bootstrap).
EXIT_NO_METADATA = 2


def _normalize_metadata_location(location: str) -> str:
    return location.rstrip("/")


def main() -> None:
    load_dotenv()
    env = nexus_env()
    cat = load_polaris_catalog(env)
    identifier = ("raw_dlt_smoke", "smoke")
    full_name = f"{catalog_name(env)}.raw_dlt_smoke.smoke"

    latest = find_latest_smoke_metadata_location(env)
    if latest is None:
        print(
            "No Iceberg metadata in MinIO for raw_dlt_smoke.smoke. "
            "Run: uv run python tests/integration/dlt_lakehouse_smoke.py",
            file=sys.stderr,
        )
        sys.exit(EXIT_NO_METADATA)
    latest = _normalize_metadata_location(latest)

    try:
        table = cat.load_table(identifier)
        current = _normalize_metadata_location(table.metadata_location)
        if current == latest:
            print(f"Already registered with latest metadata: {full_name}")
            print(f"  metadata={latest}")
            print("OK")
            return
        print(f"Stale Polaris registration for {full_name}")
        print(f"  catalog metadata={current}")
        print(f"  minio latest    ={latest}")
        print("Dropping stale registration...")
        cat.drop_table(identifier)
    except NoSuchTableError:
        pass
    except NoSuchNamespaceError:
        print(
            "Namespace raw_dlt_smoke missing in Polaris. "
            "Re-run polaris-setup bootstrap (./scripts/lakehouse-restore.sh).",
            file=sys.stderr,
        )
        sys.exit(1)

    cat.register_table(identifier, latest)
    print(f"Registered {full_name}")
    print(f"  metadata={latest}")
    print("OK")


if __name__ == "__main__":
    main()
