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
        "repo:georgeballa7/EuropeanEnergyDataAnalytics:environment:production"
      ]
    }
  }
}


# ------------------------------------------------------------
# IAM role assumed by GitHub Actions through OIDC
# ------------------------------------------------------------

resource "aws_iam_role" "github_terraform_deploy" {
  name = "GitHubTerraformDeployRole"

  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json

  description = "Role assumed by GitHub Actions via OIDC for Terraform deployments."
}



# ------------------------------------------------------------
# Permissions for Terraform deployments
# ------------------------------------------------------------

data "aws_iam_policy_document" "github_terraform_deploy_permissions" {

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
      "arn:aws:s3:::european-energy-terraform-state-488658242500-eu-central-1"
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
      "arn:aws:s3:::european-energy-terraform-state-488658242500-eu-central-1/european-energy/terraform.tfstate"
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
      "arn:aws:s3:::european-energy-terraform-state-488658242500-eu-central-1/european-energy/terraform.tfstate.tflock"
    ]
  }
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

      "s3:GetBucketPublicAccessBlock",
      "s3:PutBucketPublicAccessBlock",

      "s3:GetEncryptionConfiguration",
      "s3:PutEncryptionConfiguration"
    ]

    resources = [
      aws_s3_bucket.energy_data.arn
    ]
  }




    # ----------------------------------------------------------
  # AWS Glue Data Catalog
  # ----------------------------------------------------------

  statement {
    sid    = "GlueCatalogDatabaseManagement"
    effect = "Allow"

    actions = [
      "glue:CreateDatabase",
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:UpdateDatabase",
      "glue:DeleteDatabase"
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
      "athena:CreateWorkGroup",
      "athena:GetWorkGroup",
      "athena:ListWorkGroups",
      "athena:UpdateWorkGroup"
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
      "iam:ListPolicyVersions",
      "iam:CreatePolicyVersion",
      "iam:SetDefaultPolicyVersion",
      "iam:DeletePolicyVersion"
    ]

    resources = [
      aws_iam_policy.s3_access.arn,
      aws_iam_policy.glue_catalog_access.arn,
      aws_iam_policy.athena_access.arn
    ]
  }



    statement {
    sid    = "ProjectIAMUserAttachments"
    effect = "Allow"

    actions = [
      "iam:GetUser",
      "iam:ListAttachedUserPolicies",
      "iam:AttachUserPolicy",
      "iam:DetachUserPolicy"
    ]

    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:user/energy-pipeline"
    ]
  }



    statement {
    sid    = "ProjectIAMGroupManagement"
    effect = "Allow"

    actions = [
      "iam:GetGroup",
      "iam:ListAttachedGroupPolicies",
      "iam:AttachGroupPolicy",
      "iam:DetachGroupPolicy"
    ]

    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:group/EnergyPipelineUsers"
    ]
  }

  statement {
    sid    = "ProjectIAMGroupMembership"
    effect = "Allow"

    actions = [
      "iam:AddUserToGroup",
      "iam:RemoveUserFromGroup"
    ]

    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:group/EnergyPipelineUsers"
    ]
  }