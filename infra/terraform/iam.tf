data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "athena_access" {
  statement {
    sid    = "AthenaWorkgroupQueryAccess"
    effect = "Allow"

    actions = [
      "athena:GetWorkGroup",
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:GetQueryResultsStream",
      "athena:StopQueryExecution",
      "athena:ListQueryExecutions",
    ]

    resources = [
      aws_athena_workgroup.energy_analytics.arn
    ]
  }

  statement {
    sid    = "AthenaCatalogMetadataAccess"
    effect = "Allow"

    actions = [
      "athena:ListDataCatalogs",
      "athena:GetDataCatalog",
      "athena:ListDatabases",
      "athena:GetDatabase",
      "athena:ListTableMetadata",
      "athena:GetTableMetadata",
    ]

    resources = ["*"]
  }
}

resource "aws_iam_policy" "athena_access" {
  name   = "EuropeanEnergyAthenaAccess"
  policy = data.aws_iam_policy_document.athena_access.json
}


# ------------------------------------------------------------
# S3 access for the runtime pipeline
# ------------------------------------------------------------

data "aws_iam_policy_document" "s3_access" {
  statement {
    sid    = "ListEnergyBucket"
    effect = "Allow"

    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]

    resources = [
      aws_s3_bucket.energy_data.arn
    ]
  }

  statement {
    sid    = "ReadWriteEnergyObjects"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]

    resources = [
      "${aws_s3_bucket.energy_data.arn}/*"
    ]
  }
}

resource "aws_iam_policy" "s3_access" {
  name   = "EuropeanEnergyDataAnalyticsS3Access"
  policy = data.aws_iam_policy_document.s3_access.json
}


# ------------------------------------------------------------
# Glue Data Catalog access for the runtime pipeline
# ------------------------------------------------------------

data "aws_iam_policy_document" "glue_catalog_access" {
  statement {
    sid    = "GlueCatalogAccess"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
    ]

    resources = ["*"]
  }
}

resource "aws_iam_policy" "glue_catalog_access" {
  name   = "EuropeanEnergyGlueCatalogAccess"
  policy = data.aws_iam_policy_document.glue_catalog_access.json
}



resource "aws_iam_group" "energy_pipeline_users" {
  name = "EnergyPipelineUsers"
}


resource "aws_iam_group_policy_attachment" "s3_access" {
  group      = aws_iam_group.energy_pipeline_users.name
  policy_arn = aws_iam_policy.s3_access.arn
}


resource "aws_iam_user_policy_attachment" "glue_catalog_access" {
  user       = "energy-pipeline"
  policy_arn = aws_iam_policy.glue_catalog_access.arn
}

resource "aws_iam_user_policy_attachment" "athena_access" {
  user       = "energy-pipeline"
  policy_arn = aws_iam_policy.athena_access.arn
}

resource "aws_iam_user_group_membership" "energy_pipeline" {
  user = "energy-pipeline"

  groups = [
    aws_iam_group.energy_pipeline_users.name,
  ]
}