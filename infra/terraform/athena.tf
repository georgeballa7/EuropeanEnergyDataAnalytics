resource "aws_athena_workgroup" "energy_analytics" {
  name        = "european-energy-analytics"
  description = "Athena workgroup for the European Energy Data Analytics project."
  state       = "ENABLED"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    requester_pays_enabled             = false

    result_configuration {
      output_location = "s3://${aws_s3_bucket.energy_data.id}/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }

    engine_version {
      selected_engine_version = "AUTO"
    }
  }
}