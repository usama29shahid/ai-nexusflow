FROM apache/airflow:3.3.2-python3.12

# Thin scheduler/UI image: docker CLI only so LocalExecutor tasks can `docker run` nexus-elt.
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
# BashOperator, MinIO S3 remote logs, FAB login (keeps AIRFLOW_ADMIN_*).
ARG AIRFLOW_CONSTRAINTS_URL="https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt"
RUN pip install --no-cache-dir \
      "apache-airflow-providers-standard==1.19.0" \
      "apache-airflow-providers-amazon==9.36.0" \
      "apache-airflow-providers-fab==3.9.0" \
      --constraint "${AIRFLOW_CONSTRAINTS_URL}"
