resource "aws_sns_topic" "energy_alerts" {
  name = "european-energy-alerts"
}

resource "aws_sns_topic_subscription" "energy_email" {
  topic_arn = aws_sns_topic.energy_alerts.arn
  protocol  = "email"
  endpoint  = var.sns_alert_email
}
