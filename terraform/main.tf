locals {
  bucket_name = "${var.project_name}-${var.environment}-db-backups"
  iam_user_name = "${var.project_name}-${var.environment}-backup-user"

  common_tags = {
    Project = var.project_name
    Environment = var.environment
    ManagedBy = "Terraform"
    Purpose = "DatabaseBackups"
  }
}

resource "aws_s3_bucket" "backup_bucket" {
  bucket = local.bucket_name

  tags = merge(local.common_tags, {
    Name = "${var.project_name} DB Backup Bucket"
  })
}

resource "aws_s3_bucket_versioning" "backup_bucket_versioning" {
  bucket = aws_s3_bucket.backup_bucket.id

  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_public_access_block" "backup_bucket_public_access" {
  bucket = aws_s3_bucket.backup_bucket.id

  block_public_acls = true
  block_public_policy = true
  ignore_public_acls = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backup_bucket_encryption" {
  bucket = aws_s3_bucket.backup_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backup_lifecycle" {
  bucket = aws_s3_bucket.backup_bucket.id

  rule {
    id     = "backup-lifecycle"
    status = "Enabled"

    dynamic "transition" {
      for_each = var.backup_retention_days > var.backup_transition_to_glacier_days ? [1] : []
      content {
        days          = var.backup_transition_to_glacier_days
        storage_class = "GLACIER"
      }
    }

    expiration {
      days = var.backup_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_iam_user" "backup_user" {
  name = local.iam_user_name
  path = "/service-accounts/"

  tags = merge(local.common_tags, {
    Name = "Backup Service Account"
  })
}

resource "aws_iam_user_policy" "backup_policy" {
  name = "${local.iam_user_name}-policy"
  user   = aws_iam_user.backup_user.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid = "ListBucket"
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = aws_s3_bucket.backup_bucket.arn
      },
      {
        Sid = "ManageBackupObjects"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:PutObjectAcl"
        ]
        Resource = "${aws_s3_bucket.backup_bucket.arn}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-server-side-encryption" = "AES256"
          }
        }
      }
    ]
  })
}

resource "aws_iam_access_key" "backup_user_key" {
  user = aws_iam_user.backup_user.name
}