{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::nexus-dlt-dbt-clickhouse-{{NEXUS_ENV}}",
        "arn:aws:s3:::nexus-telemetry-{{NEXUS_ENV}}",
        "arn:aws:s3:::nexus-airflow-logs-{{NEXUS_ENV}}",
        "arn:aws:s3:::nexus-dlt-dbt-spark-iceberg-archive-{{NEXUS_ENV}}",
        "arn:aws:s3:::nexus-dlt-dbt-spark-iceberg-{{NEXUS_ENV}}"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": [
        "arn:aws:s3:::nexus-dlt-dbt-clickhouse-{{NEXUS_ENV}}/*",
        "arn:aws:s3:::nexus-telemetry-{{NEXUS_ENV}}/*",
        "arn:aws:s3:::nexus-airflow-logs-{{NEXUS_ENV}}/*",
        "arn:aws:s3:::nexus-dlt-dbt-spark-iceberg-archive-{{NEXUS_ENV}}/*",
        "arn:aws:s3:::nexus-dlt-dbt-spark-iceberg-{{NEXUS_ENV}}/*"
      ]
    }
  ]
}
