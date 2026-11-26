FROM caddy:2.9-alpine

# htpasswd hashes the docs popup password from stdin. The plaintext is not
# passed on the process command line.
RUN apk add --no-cache apache2-utils
