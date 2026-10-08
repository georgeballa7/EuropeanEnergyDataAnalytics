variable "aws_region" {
  description = "AWS region used for the bootstrap resources."
  type        = string
  default     = "eu-central-1"
}

variable "aws_profile" {
  description = "Local AWS CLI profile used for bootstrapping."
  type        = string
  default     = "george-admin"
}


variable "terraform_state_bucket_name" {
  description = "Name of the S3 bucket containing the main Terraform state."
  type        = string
}

variable "terraform_state_key" {
  description = "Object key of the main Terraform state."
  type        = string
  default     = "european-energy/terraform.tfstate"
}

variable "data_bucket_name" {
  description = "Name of the European Energy Data Lake S3 bucket."
  type        = string
}

variable "runtime_user_name" {
  description = "IAM user used by the European Energy runtime pipeline."
  type        = string
  default     = "energy-pipeline"
}

variable "runtime_group_name" {
  description = "IAM group used by the European Energy runtime pipeline."
  type        = string
  default     = "EnergyPipelineUsers"
}

variable "s3_policy_name" {
  description = "Name of the runtime S3 IAM policy."
  type        = string
  default     = "EuropeanEnergyDataAnalyticsS3Access"
}

variable "glue_policy_name" {
  description = "Name of the runtime Glue IAM policy."
  type        = string
  default     = "EuropeanEnergyGlueCatalogAccess"
}

variable "athena_policy_name" {
  description = "Name of the runtime Athena IAM policy."
  type        = string
  default     = "EuropeanEnergyAthenaAccess"
}
