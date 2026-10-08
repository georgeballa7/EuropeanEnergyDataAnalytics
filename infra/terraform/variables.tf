variable "aws_region" {
  description = "AWS region used by the European Energy Data Analytics infrastructure."
  type        = string
  default     = "eu-central-1"
}
variable "sns_alert_email" {
  description = "Email recipient for European Energy monitoring alerts."
  type        = string
  sensitive   = true
}
