resource "aws_glue_catalog_database" "energy_analytics" {
  name        = "european_energy_analytics"
  description = "Silver and Gold energy analytics datasets stored as Parquet in Amazon S3."
}