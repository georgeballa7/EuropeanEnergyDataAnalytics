# ------------------------------------------------------------
# AWS account information
# ------------------------------------------------------------

data "aws_caller_identity" "current" {}


# ------------------------------------------------------------
# GitHub Actions OIDC provider
# ------------------------------------------------------------

resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = [
    "sts.amazonaws.com"
  ]
}


# ------------------------------------------------------------
# Trust policy for the GitHub Actions Terraform deployment role
# ------------------------------------------------------------

data "aws_iam_policy_document" "github_actions_assume_role" {
  statement {
    sid    = "AllowGitHubActionsProduction"
    effect = "Allow"

    actions = [
      "sts:AssumeRoleWithWebIdentity"
    ]

    principals {
      type = "Federated"

      identifiers = [
        aws_iam_openid_connect_provider.github.arn
      ]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"

      values = [
        "sts.amazonaws.com"
      ]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"

      values = [
        "repo:georgeballa7@245966496/EuropeanEnergyDataAnalytics@1368037476:environment:production"
      ]
    }
  }
}


# ------------------------------------------------------------
# IAM role assumed by GitHub Actions through OIDC
# ------------------------------------------------------------

resource "aws_iam_role" "github_terraform_deploy" {
  name        = "GitHubTerraformDeployRole"
  description = "Role assumed by GitHub Actions via OIDC for Terraform deployments."

  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json
}


# ------------------------------------------------------------
# Permissions for Terraform deployments
# ------------------------------------------------------------

data "aws_iam_policy_document" "github_terraform_deploy_permissions" {

  statement {
    sid     = "ReadEnergyCloudWatchDashboard"
    effect  = "Allow"
    actions = ["cloudwatch:GetDashboard"]
    resources = [
      "arn:aws:cloudwatch::${data.aws_caller_identity.current.account_id}:dashboard/EuropeanEnergyPipeline"
    ]
  }


  statement {
    sid    = "ReadEnergySNSTopic"
    effect = "Allow"
    actions = [
      "sns:GetTopicAttributes",
      "sns:ListTagsForResource",
      "sns:GetSubscriptionAttributes",
      "sns:ListSubscriptionsByTopic"
    ]
    resources = [
      "arn:aws:sns:${var.aws_region}:${data.aws_caller_identity.current.account_id}:european-energy-alerts"
    ]
  }

  # ----------------------------------------------------------
  # Terraform remote state
  # ----------------------------------------------------------

  statement {
    sid    = "TerraformStateBucketAccess"
    effect = "Allow"

    actions = [
      "s3:ListBucket"
    ]

    resources = [
      "arn:aws:s3:::${var.terraform_state_bucket_name}"
    ]
  }

  statement {
    sid    = "TerraformStateObjectAccess"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject"
    ]

    resources = [
      "arn:aws:s3:::${var.terraform_state_bucket_name}/${var.terraform_state_key}"
    ]
  }

  statement {
    sid    = "TerraformStateLockAccess"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]

    resources = [
      "arn:aws:s3:::${var.terraform_state_bucket_name}/${var.terraform_state_key}.tflock"
    ]
  }


  # ----------------------------------------------------------
  # Data Lake S3 infrastructure
  # ----------------------------------------------------------

  statement {
    sid    = "DataLakeBucketManagement"
    effect = "Allow"

    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:GetBucketPolicy",
      "s3:GetBucketAcl",
      "s3:GetBucketCORS",
      "s3:GetBucketWebsite",
      "s3:GetBucketTagging",
      "s3:GetBucketPublicAccessBlock",
      "s3:GetEncryptionConfiguration",
      "s3:GetBucketLogging",
      "s3:GetBucketVersioning",
      "s3:GetBucketRequestPayment",
      "s3:GetBucketObjectLockConfiguration",
      "s3:GetLifecycleConfiguration",
      "s3:GetReplicationConfiguration",
      "s3:GetAccelerateConfiguration",
      "s3:GetBucketNotification",
      "s3:GetBucketOwnershipControls",
      "s3:GetBucketPolicyStatus"
    ]

    resources = [
      "arn:aws:s3:::${var.data_bucket_name}"
    ]
  }


  # ----------------------------------------------------------
  # AWS Glue Data Catalog
  # ----------------------------------------------------------

  statement {
    sid    = "GlueCatalogDatabaseManagement"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTags"
    ]

    resources = [
      "*"
    ]
  }


  # ----------------------------------------------------------
  # Amazon Athena workgroup
  # ----------------------------------------------------------

  statement {
    sid    = "AthenaWorkgroupManagement"
    effect = "Allow"

    actions = [
      "athena:GetWorkGroup",
      "athena:ListWorkGroups",
      "athena:ListTagsForResource"
    ]

    resources = [
      "*"
    ]
  }


  # ----------------------------------------------------------
  # Project IAM managed policies
  # ----------------------------------------------------------

  statement {
    sid    = "ProjectIAMPolicyManagement"
    effect = "Allow"

    actions = [
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:ListPolicyVersions"
    ]

    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${var.s3_policy_name}",
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${var.glue_policy_name}",
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${var.athena_policy_name}"
    ]
  }


  # ----------------------------------------------------------
  # Runtime user policy attachments
  # ----------------------------------------------------------

  statement {
    sid    = "ProjectIAMUserAttachments"
    effect = "Allow"

    actions = [
      "iam:GetUser",
      "iam:ListGroupsForUser",
      "iam:ListAttachedUserPolicies"
    ]

    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:user/${var.runtime_user_name}"
    ]
  }


  # ----------------------------------------------------------
  # Runtime IAM group
  # ----------------------------------------------------------

  statement {
    sid    = "ProjectIAMGroupManagement"
    effect = "Allow"

    actions = [
      "iam:GetGroup",
      "iam:ListAttachedGroupPolicies"
    ]

    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:group/${var.runtime_group_name}"
    ]
  }


}


# ------------------------------------------------------------
# Managed deployment policy
# ------------------------------------------------------------

resource "aws_iam_policy" "github_terraform_deploy" {
  name        = "EuropeanEnergyGitHubTerraformDeploy"
  description = "Least-privilege permissions for GitHub Actions Terraform deployments."

  policy = data.aws_iam_policy_document.github_terraform_deploy_permissions.json
}


# ------------------------------------------------------------
# Attach deployment permissions to the GitHub Actions role
# ------------------------------------------------------------

resource "aws_iam_role_policy_attachment" "github_terraform_deploy" {
  role       = aws_iam_role.github_terraform_deploy.name
  policy_arn = aws_iam_policy.github_terraform_deploy.arn
}

# ------------------------------------------------------------
# Restricted role for manually approved Terraform apply
# ------------------------------------------------------------

resource "aws_iam_role" "github_terraform_apply" {
  name               = "GitHubTerraformApplyRole"
  description        = "Restricted role for manually approved Terraform apply jobs."
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json
}

data "aws_iam_policy_document" "github_terraform_apply_permissions" {

  statement {
    sid    = "ManageEnergyCloudWatchDashboard"
    effect = "Allow"
    actions = [
      "cloudwatch:PutDashboard"
    ]
    resources = [
      "arn:aws:cloudwatch::${data.aws_caller_identity.current.account_id}:dashboard/EuropeanEnergyPipeline"
    ]
  }

  statement {
    sid    = "ManageEnergySNSTopic"
    effect = "Allow"
    actions = [
      "sns:CreateTopic",
      "sns:SetTopicAttributes",
      "sns:Subscribe",
      "sns:GetSubscriptionAttributes"
    ]
    resources = [
      "arn:aws:sns:${var.aws_region}:${data.aws_caller_identity.current.account_id}:european-energy-alerts"
    ]
  }

  source_policy_documents = [
    data.aws_iam_policy_document.github_terraform_deploy_permissions.json
  ]

  statement {
    sid       = "ApplyDataLakeBucketSettings"
    effect    = "Allow"
    actions   = ["s3:PutBucketPublicAccessBlock", "s3:PutEncryptionConfiguration"]
    resources = ["arn:aws:s3:::${var.data_bucket_name}"]
  }

  statement {
    sid     = "ApplyGlueDatabase"
    effect  = "Allow"
    actions = ["glue:CreateDatabase", "glue:UpdateDatabase"]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:database/european_energy_analytics"
    ]
  }

  statement {
    sid       = "ApplyAthenaWorkgroup"
    effect    = "Allow"
    actions   = ["athena:CreateWorkGroup", "athena:UpdateWorkGroup"]
    resources = ["arn:aws:athena:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workgroup/european-energy-analytics"]
  }
}

resource "aws_iam_policy" "github_terraform_apply" {
  name        = "EuropeanEnergyGitHubTerraformApply"
  description = "Restricted permissions for manually approved Terraform apply jobs."
  policy      = data.aws_iam_policy_document.github_terraform_apply_permissions.json
}

resource "aws_iam_role_policy_attachment" "github_terraform_apply" {
  role       = aws_iam_role.github_terraform_apply.name
  policy_arn = aws_iam_policy.github_terraform_apply.arn
}
