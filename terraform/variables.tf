variable "aws_region" {
  description = "AWS region for resources"
  type = string
  default = "eu-north-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type = string
  default = "universal-telegram-bot"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type = string
  default = "prod"
}

variable "backup_retention_days" {
  description = "Number of days to retain backups"
  type = number
  default = 30
}

variable "backup_transition_to_glacier_days" {
  description = "Days after which to move backups to Glacier"
  type = number
  default = 90
}