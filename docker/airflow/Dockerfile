FROM apache/airflow:2.10.5-python3.12

# Thin scheduler/web image: docker CLI only so tasks can `docker run` nexus-elt.
# Do not install dlt/dbt here (see docker/elt/).
USER root
ARG TARGETARCH
ARG DOCKER_STATIC_VERSION=27.3.1
RUN case "${TARGETARCH}" in \
      amd64) DOCKER_ARCH=x86_64 ;; \
      arm64) DOCKER_ARCH=aarch64 ;; \
      *) echo "Unsupported TARGETARCH=${TARGETARCH:-unset}" >&2; exit 1 ;; \
    esac \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL \
      "https://download.docker.com/linux/static/stable/${DOCKER_ARCH}/docker-${DOCKER_STATIC_VERSION}.tgz" \
      | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && rm -rf /var/lib/apt/lists/* \
    && docker --version
USER airflow
