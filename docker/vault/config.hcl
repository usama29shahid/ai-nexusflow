# HashiCorp Vault — single-node Raft (local / VPS).
# API is exposed on localhost:8200 from Compose; TLS disabled on the Docker network.
# See docs/vault.md.

storage "raft" {
  path    = "/vault/data"
  node_id = "nexusflow-1"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

disable_mlock = true
ui            = true

api_addr     = "http://vault:8200"
cluster_addr = "http://vault:8201"

default_lease_ttl = "768h"
max_lease_ttl     = "8760h"
