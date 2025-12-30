output "bucket_name" {
  description = "Name of the S3 backup bucket"
  value       = aws_s3_bucket.backup_bucket.id
}

output "bucket_arn" {
  description = "ARN of the S3 backup bucket"
  value       = aws_s3_bucket.backup_bucket.arn
}

output "bucket_region" {
  description = "Region of the S3 backup bucket"
  value       = aws_s3_bucket.backup_bucket.region
}

output "iam_user_name" {
  description = "Name of the IAM user for backups"
  value       = aws_iam_user.backup_user.name
}

output "iam_user_arn" {
  description = "ARN of the IAM user"
  value       = aws_iam_user.backup_user.arn
}

output "aws_access_key_id" {
  description = "AWS Access Key ID for backup user"
  value       = aws_iam_access_key.backup_user_key.id
}

output "aws_secret_access_key" {
  description = "AWS Secret Access Key for backup user"
  value       = aws_iam_access_key.backup_user_key.secret
  sensitive   = true
}