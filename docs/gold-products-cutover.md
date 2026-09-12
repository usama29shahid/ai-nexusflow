# Gold products SCD2 (decision / implementation log)

**Status: implemented (code + docs; verify with dbt run/test against ClickHouse).**  
**Purpose:** Implementation record for first Gold slice. Normative rules live in [dbt-modeling.md](dbt-modeling.md).

| Topic | Canonical doc |
| --- | --- |
| SCD2 columns, hashes, Pattern A delete | [dbt-modeling.md](dbt-modeling.md) |
| Layer DB `gold_{env}` | [environments.md](environments.md) |
| Prior silver peers | [bronze-silver-cutover.md](bronze-silver-cutover.md) |

## Change log

| Date | Change |
| --- | --- |
| 2026-09-09 | Add silver `row_hash` + `_extracted_at` on `stg_route__products__images` and `__subcategory` (hash trio on every silver peer). |
| 2026-09-09 | Add `dim_product`, `brg_product_image`, `brg_product_subcategory` SCD2 (incremental delete+insert). |
| 2026-09-09 | Gold YAML, unit tests, tags (`gold`, `scd2`, `products`, `elementary`), Elementary `meta.timestamp_column`. |
| 2026-09-09 | Rename Gold `scd_hash`→`row_hash`, `is_current`→`is_active`; flags Int8; tags/meta YAML-only; richer RAG descriptions. |
| 2026-09-09 | SCD2 change seam: shared `scd_bound_at` so closed `valid_to` = new `valid_from` (general Gold rule). Document dim↔dim natural+as-of vs fact/mart Version FK for later marts. |
| 2026-09-10 | Fix reappear after Pattern A delete: split `new_rows` into truly-new vs reappear; reappear opens at `scd_bound_at` with new SK (no `source_created_at` / first `_extracted_at` replay). |
| 2026-09-10 | Unit tests for incremental reappear (`this` + `scd2_bound_at` override); `scd2_bound_at()` macro for deterministic seams. |
| 2026-09-10 | ClickHouse SCD anti-joins: `LEFT ANTI JOIN` instead of `LEFT JOIN … IS NULL` (`join_use_nulls=0` otherwise drops new/delete/reappear). |
| 2026-09-10 | Unit tests for incremental truly-new, Pattern A delete, and attribute-change seam (dim + both bridges). |
| 2026-09-10 | DRY: single `scd_bound_opens` projection for reappear+change; YAML anchors for shared unit-test fixtures. |
| 2026-09-10 | `scd2_bound_at()` = compile-time `run_started_at` literal (no `now64` CTE drift); shared across Gold models in one dbt run. |
| 2026-09-12 | Bridge incremental truly-new stays on `_extracted_at` (first-ever, like dim `source_created_at`). Pattern A delete on a replace closes at the product's silver extract so URL / subcategory-id swap has no duration overlap. |

## Locked decisions

- All three Gold tables are **SCD2**; change detection uses silver/Gold **`row_hash`** (same column name — no `scd_hash` alias).
- **Change seam:** one `scd_bound_at` per dbt invocation (`scd2_bound_at()` ← `run_started_at` literal); on attribute change, prior `valid_to` = new `valid_from` = that bound (general rule for all Gold SCD2).
- **Bridge membership replace:** old `valid_to` = new `valid_from` = that product's silver `_extracted_at`. Full wipe (no sibling silver) still expires at `scd_bound_at`.
- Delete = **Pattern A expire** active row (`is_active=0`, `is_deleted=1` as **Int8**); no new tombstone version row. Dim and bridge full wipe: `valid_to=scd_bound_at`. Bridge replace (sibling silver still on that product): `valid_to` = product silver `_extracted_at` (see membership-replace bullet).
- **Reappear after delete:** key back in silver with no active Gold row but `pk_hash` already in Gold → new version at `scd_bound_at` + new SK (not first-version dates). Gap after delete `valid_to` is OK.
- **Anti-joins:** `LEFT ANTI JOIN` for new / delete / truly-new detection (not `LEFT JOIN … IS NULL`).
- Effective dates: `valid_from` / `valid_to`; flags: `is_active` / `is_deleted` (Int8 0/1, not Bool).
- Audit: `inserted_at` / `updated_at` are Gold-only (not silver `_inserted_at`).
- `source_updated_at` informational only on `dim_product`.
- Surrogate key per version: `dim_product_sk` / `brg_product_image_sk` / `brg_product_subcategory_sk`.
- **Joins:** dim/bridge ↔ dim/bridge = natural key + as-of; fact/mart → dim/bridge = version SK when freezing (deferred until marts/facts exist).
- Model SQL `config()` = materialization only; tags/meta/docs in YAML.
- `--full-refresh` on Gold rebuilds from silver only (history reset).

## Verify checklist

- [x] `uv run dbt run -s tag:products` (silver + gold) as transformer
- [x] `uv run dbt test -s tag:gold` (data tests)
- [x] `uv run dbt test --select "test_type:unit"` (silver + gold; gold covers initial + truly-new / delete / change / reappear / URL and subcategory-id replace)
- [x] `uv run dbt docs generate`
- [x] Elementary on-run-end hooks write to `elementary_dev`
