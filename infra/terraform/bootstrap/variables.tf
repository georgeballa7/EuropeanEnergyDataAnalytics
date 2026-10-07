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