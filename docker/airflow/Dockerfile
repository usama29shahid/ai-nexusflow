FROM apache/airflow:2.10.5-python3.12

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*
USER airflow
