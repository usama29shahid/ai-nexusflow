{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketLocation",
        "s3:ListBucket",
        "s3:ListBucketMultipartUploads"
      ],
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
      "Action": [
        "s3:AbortMultipartUpload",
        "s3:GetObject",
        "s3:ListMultipartUploadParts",
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::nexus-dlt-dbt-clickhouse-{{NEXUS_ENV}}/*",
        "arn:aws:s3:::nexus-telemetry-{{NEXUS_ENV}}/*",
        "arn:aws:s3:::nexus-airflow-logs-{{NEXUS_ENV}}/*",
        "arn:aws:s3:::nexus-dlt-dbt-spark-iceberg-archive-{{NEXUS_ENV}}/*",
        "arn:aws:s3:::nexus-dlt-dbt-spark-iceberg-{{NEXUS_ENV}}/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::nexus-dlt-dbt-spark-iceberg-{{NEXUS_ENV}}/*"]
    },
    {
      "Effect": "Deny",
      "Action": ["s3:DeleteObject"],
      "Resource": [
        "arn:aws:s3:::nexus-dlt-dbt-clickhouse-{{NEXUS_ENV}}/*",
        "arn:aws:s3:::nexus-telemetry-{{NEXUS_ENV}}/*",
        "arn:aws:s3:::nexus-dlt-dbt-spark-iceberg-archive-{{NEXUS_ENV}}/*"
      ]
    }
  ]
}
