# Local Setup and Operations Runbook

This runbook describes the existing development environment and safe operational procedures. It does **not** automatically provision a new independent AWS environment. The Terraform backend and several resources are tied to the project's existing AWS account; access and configuration must be reviewed before use.

## Prerequisites

- Windows with PowerShell, Docker Desktop with Docker Compose, Git, Python 3.12, AWS CLI v2 and Terraform >= 1.16.
- Access to the Ember API and the appropriate project AWS account/resources in `eu-central-1`.
- An AWS CLI profile named `energy-pipeline` with the minimum permissions required for the intended action.
- A locally configured `~/.aws` directory; the Airflow Compose file mounts it read-only into the containers.
- Access to any external alert integrations needed to test notifications.

> **Security:** Never commit `.env`, AWS credentials, Terraform state or saved plans. The current Compose configuration includes development-only example authentication values; replace these with secure, environment-specific values before using the deployment outside a trusted local environment. Do not expose the Airflow UI publicly with those values.

## 1. Clone and configure

```powershell
git clone https://github.com/georgeballa7/EuropeanEnergyDataAnalytics.git
cd EuropeanEnergyDataAnalytics
Copy-Item .env.example .env
```

Edit `.env` and set `EMBER_API_KEY` to your own value. Other settings used by runtime integrations must be configured according to the corresponding project code and environment; do not put secrets in tracked files.

Confirm the AWS identity and region **before** any AWS or Terraform operation:

```powershell
aws sts get-caller-identity --profile energy-pipeline
aws configure get region --profile energy-pipeline
```

The project uses `eu-central-1`. If the account or region differs from the intended environment, stop and resolve it first.

## 2. Python dependencies and tests

From the repository root, use an existing Python 3.12 environment (for example, the local `energy` conda environment):

```powershell
python --version
python -m pip install -r requirements.txt
python -m pytest -v
```

The repository's GitHub Actions CI also runs pytest. A passing unit test suite is not proof of successful AWS connectivity or a complete pipeline run.

## 3. Start local Airflow

The Compose configuration is in `airflow/docker-compose.yaml` and builds the image from `airflow/Dockerfile` using `airflow/requirements.txt`. The stack includes PostgreSQL 16, an Airflow API server, scheduler and DAG processor; the web interface is mapped to localhost port 8081.

Run these commands from the repository root:

```powershell
docker compose -f airflow/docker-compose.yaml build
docker compose -f airflow/docker-compose.yaml run --rm airflow-init
docker compose -f airflow/docker-compose.yaml up -d
docker compose -f airflow/docker-compose.yaml ps
```

Open `http://localhost:8081` and sign in with the credentials configured for your local environment. Verify that the project DAG appears in the UI before triggering it.

The scheduled DAG runs monthly on the 10th at 14:00 Europe/Berlin (`catchup=False`). A manual run may call AWS services and incur costs; verify credentials and scope first.

To inspect logs:

```powershell
docker compose -f airflow/docker-compose.yaml logs --tail=100 airflow-scheduler
docker compose -f airflow/docker-compose.yaml logs --tail=100 airflow-dag-processor
docker compose -f airflow/docker-compose.yaml logs --tail=100 airflow-apiserver
```

Stop services without deleting the PostgreSQL volume:

```powershell
docker compose -f airflow/docker-compose.yaml down
```

Avoid `down -v` unless you intentionally want to delete the local Airflow metadata database.

## 4. Validate Terraform safely

Terraform files live in `infra/terraform/`. The S3 backend is configured in `infra/terraform/versions.tf` with encrypted remote state and native S3 locking. The backend bucket and key refer to this project's **existing** environment.

For syntax and formatting checks without backend access:

```powershell
cd infra/terraform
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

An AWS-backed `terraform plan` refreshes remote state and requires appropriate access and variable values. **Do not run `terraform apply` or modify/import state simply to follow this guide.** The GitHub Actions Terraform planning workflow uses OIDC and guards against delete/replacement operations; plan success does not deploy infrastructure.

For a separate deployment, first parameterize and review the backend, account-specific resource identifiers, IAM policies, variables and state ownership. Reusing the existing backend for a new environment risks altering the original infrastructure.

## 5. Check the data pipeline

The documented data flow is:

1. Ember API ingestion → append-only S3 Bronze JSON.
2. Cleaning, merge and validation → S3 Silver Parquet snapshots.
3. Dimensional transformations and integrity checks → S3 Gold Parquet snapshots.
4. Explicit Glue catalog registration for Silver and Gold tables.
5. Athena post-load validation of all nine Gold tables → Power BI Import report.

Before a manual run, check the intended Ember dataset/country scope and the existing S3 incremental ingestion state. Historical backfills are **separate maintenance operations** and should not be substituted for regular incremental ingestion.

After a run, verify that all five Airflow tasks succeeded, especially `validate_persisted_gold`. Check expected new Bronze objects, updated Silver/Gold snapshots, Glue table metadata and Athena validation results. The final task queries the existing `european-energy-analytics` workgroup and fails on empty Gold tables, null required fields, duplicate keys, invalid foreign keys, Athena errors or timeouts. Compare counts, country coverage and source periods with the project's [data-quality rules](../data_quality.md). A successful Airflow run alone does not prove analytical correctness.

## 6. Troubleshooting and recovery

| Symptom | First checks | Safe next action |
| --- | --- | --- |
| Airflow UI unavailable | `docker compose ... ps`; API server and PostgreSQL logs | Restart affected services; preserve PostgreSQL volume |
| DAG missing | DAG processor logs; mounted `airflow/dags` directory | Fix import/configuration errors before rerunning |
| AWS `AccessDenied` | `aws sts get-caller-identity --profile energy-pipeline`; IAM scope | Correct the intended identity or least-privilege policy; do not switch to administrator credentials as a workaround |
| Ember API failure | API key, HTTP response, rate limits and request scope | Retry only after identifying the cause; avoid duplicate backfill loads |
| Data-quality failure | Failed task logs, input schema, keys and source coverage | Correct source/configuration or transformation; do not bypass validations |
| Terraform drift or planned replacement | Plan output, variable values, remote-state ownership and resource taint | Stop; investigate before any apply or state manipulation |
| Athena failure | Workgroup, Glue table schema, S3 paths, query permissions and results location | Inspect `validate_persisted_gold` logs and query execution details; check CloudWatch/SNS where applicable |

For recovery, prefer correcting the root cause and rerunning the relevant validated pipeline stage. Never manually overwrite Bronze history, Silver/Gold snapshots, or Terraform state without a reviewed recovery plan. S3 object versioning and recovery capabilities depend on the actual bucket configuration; verify them before relying on rollback.

## 7. Monitoring and operational boundaries

- Airflow task failures: Slack notifications.
- Athena failed-query metric: CloudWatch alarm and SNS email notification.
- GitHub Actions: Python tests, Terraform validation and guarded Terraform planning.

A successful deployment or configuration check is not equivalent to a tested notification path. Exercise notifications separately if operational assurance is required.

## 8. Reproducibility checklist

- [ ] Clone succeeds and the intended revision is recorded.
- [ ] Local environment and dependencies install.
- [ ] Tests pass.
- [ ] AWS account and region are verified.
- [ ] Airflow services start and the DAG is visible.
- [ ] A controlled run completes with expected Bronze/Silver/Gold outputs.
- [ ] Glue and Athena return expected data; `validate_persisted_gold` succeeds for all nine Gold tables.
- [ ] Terraform validation passes without changing infrastructure.
- [ ] No credentials, state files or saved plans are committed.

See [architecture](../architecture/architecture.md), [architecture decisions](../decisions/architecture_decisions.md) and [data quality](../data_quality.md) for design details.
