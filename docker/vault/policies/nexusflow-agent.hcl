# Vault policy for nexusflow Vault Agent (read project secrets only).

path "secret/data/nexusflow/*" {
  capabilities = ["read"]
}

path "secret/metadata/nexusflow/*" {
  capabilities = ["read"]
}
