# Vault Agent — template rendering only. AppRole auto_auth is in .nexusflow/agent-autoauth.hcl (generated).

vault {
  address = "http://vault:8200"
}

template {
  source      = "/vault/templates/secrets.env.tpl"
  destination = "/nexusflow/secrets.env"
  perms       = 0640
}
