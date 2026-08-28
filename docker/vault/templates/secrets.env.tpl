# Rendered by HashiCorp Vault Agent — do not edit. See docs/vault.md.
{{- $env := env "NEXUS_ENV" }}
{{- with secret (printf "secret/data/nexusflow/%s/clickhouse" $env) }}
CLICKHOUSE_PASSWORD={{ .Data.data.password }}
{{- end }}
{{- with secret (printf "secret/data/nexusflow/%s/minio" $env) }}
MINIO_ROOT_USER={{ .Data.data.root_user }}
MINIO_ROOT_PASSWORD={{ .Data.data.root_password }}
{{- end }}
{{- with secret (printf "secret/data/nexusflow/%s/polaris" $env) }}
POLARIS_CLIENT_SECRET={{ .Data.data.client_secret }}
{{- end }}
{{- with secret (printf "secret/data/nexusflow/%s/airflow" $env) }}
AIRFLOW__CORE__FERNET_KEY={{ .Data.data.fernet_key }}
AIRFLOW__WEBSERVER__SECRET_KEY={{ .Data.data.web_secret }}
AIRFLOW_ADMIN_PASSWORD={{ .Data.data.admin_password }}
{{- end }}
{{- with secret (printf "secret/data/nexusflow/%s/github" $env) }}
GITHUB_TOKEN={{ .Data.data.token }}
{{- end }}
