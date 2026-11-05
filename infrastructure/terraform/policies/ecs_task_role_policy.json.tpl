{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3DocumentStorageOperations",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "${documents_bucket_arn}",
        "${documents_bucket_arn}/*"
      ]
    },
    {
      "Sid": "AllowSESTransactionalMailDispatch",
      "Effect": "Allow",
      "Action": [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "ses:FromAddress": "${ses_sender_email}"
        }
      }
    },
    {
      "Sid": "AllowKMSEnvelopeCryptoOperations",
      "Effect": "Allow",
      "Action": [
        "kms:GenerateDataKey",
        "kms:Decrypt"
      ],
      "Resource": "${kms_key_arn}"
    }
  ]
}
