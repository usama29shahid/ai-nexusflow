-- ClickHouse RBAC bootstrap for AI-NexusFlow warehouse cutover.
-- Run as admin (default / CLICKHOUSE_USER) after Compose ClickHouse is up:
--   ./scripts/clickhouse-rbac-bootstrap.sh
-- See docs/rbac.md and docs/bronze-silver-cutover.md.
--
-- Placeholders {{LOADER_PASSWORD}}, {{TRANSFORMER_PASSWORD}}, {{READER_PASSWORD}},
-- {{ADMIN_PASSWORD}}, {{NEXUS_ENV}} are substituted by the shell wrapper.

CREATE DATABASE IF NOT EXISTS bronze_{{NEXUS_ENV}};
CREATE DATABASE IF NOT EXISTS silver_{{NEXUS_ENV}};
CREATE DATABASE IF NOT EXISTS elementary_{{NEXUS_ENV}};
CREATE DATABASE IF NOT EXISTS intermediate_{{NEXUS_ENV}};
CREATE DATABASE IF NOT EXISTS gold_{{NEXUS_ENV}};
CREATE DATABASE IF NOT EXISTS marts_{{NEXUS_ENV}};
CREATE DATABASE IF NOT EXISTS published_{{NEXUS_ENV}};

CREATE USER IF NOT EXISTS nexus_loader IDENTIFIED WITH sha256_password BY '{{LOADER_PASSWORD}}';
CREATE USER IF NOT EXISTS nexus_transformer IDENTIFIED WITH sha256_password BY '{{TRANSFORMER_PASSWORD}}';
CREATE USER IF NOT EXISTS nexus_reader IDENTIFIED WITH sha256_password BY '{{READER_PASSWORD}}';
CREATE USER IF NOT EXISTS nexus_admin IDENTIFIED WITH sha256_password BY '{{ADMIN_PASSWORD}}';

-- Rotate passwords on re-bootstrap (CREATE USER IF NOT EXISTS does not update them).
ALTER USER nexus_loader IDENTIFIED WITH sha256_password BY '{{LOADER_PASSWORD}}';
ALTER USER nexus_transformer IDENTIFIED WITH sha256_password BY '{{TRANSFORMER_PASSWORD}}';
ALTER USER nexus_reader IDENTIFIED WITH sha256_password BY '{{READER_PASSWORD}}';
ALTER USER nexus_admin IDENTIFIED WITH sha256_password BY '{{ADMIN_PASSWORD}}';

-- Loader: Bronze only
GRANT CREATE TABLE, CREATE VIEW, INSERT, SELECT, ALTER, DROP, TRUNCATE, SHOW, dictGet
    ON bronze_{{NEXUS_ENV}}.* TO nexus_loader;
GRANT SELECT ON INFORMATION_SCHEMA.COLUMNS TO nexus_loader;

-- Transformer: read Bronze; write silver / elementary / future gold+
GRANT SELECT, SHOW ON bronze_{{NEXUS_ENV}}.* TO nexus_transformer;
GRANT SELECT ON INFORMATION_SCHEMA.COLUMNS TO nexus_transformer;
GRANT CREATE TABLE, CREATE VIEW, INSERT, SELECT, ALTER, DROP, TRUNCATE, OPTIMIZE, SHOW, dictGet
    ON silver_{{NEXUS_ENV}}.* TO nexus_transformer;
GRANT CREATE TABLE, CREATE VIEW, INSERT, SELECT, ALTER, DROP, TRUNCATE, OPTIMIZE, SHOW, dictGet
    ON elementary_{{NEXUS_ENV}}.* TO nexus_transformer;
GRANT CREATE TABLE, CREATE VIEW, INSERT, SELECT, ALTER, DROP, TRUNCATE, OPTIMIZE, SHOW, dictGet
    ON intermediate_{{NEXUS_ENV}}.* TO nexus_transformer;
GRANT CREATE TABLE, CREATE VIEW, INSERT, SELECT, ALTER, DROP, TRUNCATE, OPTIMIZE, SHOW, dictGet
    ON gold_{{NEXUS_ENV}}.* TO nexus_transformer;
GRANT CREATE TABLE, CREATE VIEW, INSERT, SELECT, ALTER, DROP, TRUNCATE, OPTIMIZE, SHOW, dictGet
    ON marts_{{NEXUS_ENV}}.* TO nexus_transformer;
GRANT CREATE TABLE, CREATE VIEW, INSERT, SELECT, ALTER, DROP, TRUNCATE, OPTIMIZE, SHOW, dictGet
    ON published_{{NEXUS_ENV}}.* TO nexus_transformer;

-- Reader: consume gold/marts/published
GRANT SELECT, SHOW ON gold_{{NEXUS_ENV}}.* TO nexus_reader;
GRANT SELECT, SHOW ON marts_{{NEXUS_ENV}}.* TO nexus_reader;
GRANT SELECT, SHOW ON published_{{NEXUS_ENV}}.* TO nexus_reader;

-- Admin: full access (break-glass)
GRANT ALL ON *.* TO nexus_admin WITH GRANT OPTION;
