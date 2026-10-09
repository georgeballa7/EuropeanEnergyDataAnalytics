resource "aws_cloudwatch_dashboard" "energy_pipeline" {
  dashboard_name = "EuropeanEnergyPipeline"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 2

        properties = {
          markdown = "# European Energy Data Pipeline\nInfrastructure Monitoring"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 2
        width  = 12
        height = 6

        properties = {
          title  = "S3 – Storage Size"
          region = var.aws_region
          view   = "timeSeries"
          period = 86400
          stat   = "Average"

          metrics = [
            [
              "AWS/S3",
              "BucketSizeBytes",
              "BucketName",
              aws_s3_bucket.energy_data.id,
              "StorageType",
              "StandardStorage"
            ]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 2
        width  = 12
        height = 6

        properties = {
          title  = "Athena – Query Execution Time"
          region = var.aws_region
          view   = "timeSeries"
          period = 300
          stat   = "Average"

          metrics = [
            [
              "AWS/Athena",
              "TotalExecutionTime",
              "WorkGroup",
              aws_athena_workgroup.energy_analytics.name,
              "QueryState",
              "SUCCEEDED",
              "QueryType",
              "DML"
            ]
          ]
        }
      }
    ]
  })
}


resource "aws_cloudwatch_metric_alarm" "athena_failed_queries" {
  alarm_name        = "EuropeanEnergy-Athena-FailedQueries"
  alarm_description = "Alerts when an Athena DML query fails."

  namespace   = "AWS/Athena"
  metric_name = "TotalExecutionTime"

  dimensions = {
    WorkGroup  = aws_athena_workgroup.energy_analytics.name
    QueryState = "FAILED"
    QueryType  = "DML"
  }

  statistic           = "SampleCount"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"

  treat_missing_data = "notBreaching"

  alarm_actions = [
    aws_sns_topic.energy_alerts.arn
  ]
}
