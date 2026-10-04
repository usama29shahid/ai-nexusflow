{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::nexus-telemetry-{{NEXUS_ENV}}"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": ["arn:aws:s3:::nexus-telemetry-{{NEXUS_ENV}}/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": [
        "arn:aws:s3:::nexus-telemetry-{{NEXUS_ENV}}/indexes/signoz/*",
        "arn:aws:s3:::nexus-telemetry-{{NEXUS_ENV}}/indexes/openobserve/*",
        "arn:aws:s3:::nexus-telemetry-{{NEXUS_ENV}}/indexes/openmetadata/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::nexus-telemetry-{{NEXUS_ENV}}/indexes/openobserve/*"]
    }
  ]
}
