resource "aws_s3_bucket" "energy_data" {
  bucket = "european-energy-data-analytics-488658242500-eu-central-1-an"
}


resource "aws_s3_bucket_public_access_block" "energy_data" {
  bucket = aws_s3_bucket.energy_data.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "energy_data" {
  bucket = aws_s3_bucket.energy_data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }

    bucket_key_enabled = false
  }
}