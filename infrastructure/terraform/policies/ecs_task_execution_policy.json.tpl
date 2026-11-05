{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowECRImagePull",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AllowCloudWatchLogsLogging",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "${log_group_arn}:*"
    },
    {
      "Sid": "AllowSecretsManagerRead",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "${db_secret_arn}",
        "${app_secret_arn}"
      ]
    },
    {
      "Sid": "AllowKMSDecryptForSecrets",
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt"
      ],
      "Resource": "${kms_key_arn}"
    }
  ]
}
