# Local Setup and Operations Runbook

This runbook describes the existing development environment and safe operational procedures. It does **not** automatically provision a new independent AWS environment. The Terraform backend and several resources are tied to the project's existing AWS account; access and configuration must be reviewed before use.

## Prerequisites

- Windows with PowerShell, Docker Desktop with Docker Compose, Git, Python 3.12, AWS CLI v2 and Terraform >= 1.16.
- Access to the Ember API and the appropriate project AWS account/resources in `eu-central-1`.
- An AWS CLI profile named `energy-pipeline` with the minimum permissions required for the intended action.
- A locally configured `~/.aws` directory; the Airflow Compose file mounts it read-only into the containers.
- Access to any external alert integrations needed to test notifications.

> **Security:** Never commit `.env`, AWS credentials, Terraform state or saved plans. Compose now requires locally supplied `AIRFLOW_JWT_SECRET` and `AIRFLOW_POSTGRES_PASSWORD`. The UI binds to `127.0.0.1:8081`; do not expose it publicly. The local Airflow simple-auth administrator is for trusted development only.

## 1. Clone and configure

```powershell
git clone https://github.com/georgeballa7/EuropeanEnergyDataAnalytics.git
cd EuropeanEnergyDataAnalytics
Copy-Item .env.example .env
```

Edit `.env` and set `EMBER_API_KEY`, `AIRFLOW_JWT_SECRET` (random, at least 64 characters), and `AIRFLOW_POSTGRES_PASSWORD` (for an existing PostgreSQL volume, use the **current unchanged database password**; for a fresh installation, choose a strong random alphanumeric value). The latter is interpolated into a PostgreSQL connection URI; avoid URI-reserved characters unless URL-encoded. Never commit `.env` or actual credentials.

**Existing PostgreSQL volume:** Do not rotate the database password as part of this configuration-only change. Set `AIRFLOW_POSTGRES_PASSWORD` to the password already used by the existing PostgreSQL role. Docker Compose environment variables do not change passwords stored in an initialized PostgreSQL volume. Do **not** run `docker compose down -v`: it deletes local Airflow metadata.

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
docker compose --env-file .env -f airflow/docker-compose.yaml build
docker compose --env-file .env -f airflow/docker-compose.yaml run --rm airflow-init
docker compose --env-file .env -f airflow/docker-compose.yaml up -d
docker compose --env-file .env -f airflow/docker-compose.yaml ps
```

Open `http://localhost:8081` and sign in with the credentials configured for your local environment. Verify that the project DAG appears in the UI before triggering it.

The scheduled DAG runs monthly on the 10th at 14:00 Europe/Berlin (`catchup=False`). A manual run may call AWS services and incur costs; verify credentials and scope first.

To inspect logs:

```powershell
docker compose --env-file .env -f airflow/docker-compose.yaml logs --tail=100 airflow-scheduler
docker compose --env-file .env -f airflow/docker-compose.yaml logs --tail=100 airflow-dag-processor
docker compose --env-file .env -f airflow/docker-compose.yaml logs --tail=100 airflow-apiserver
```

Stop services without deleting the PostgreSQL volume:

```powershell
docker compose --env-file .env -f airflow/docker-compose.yaml down
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
2. Cleaning, merge and validation → S3 Silver Parquet snapshot; a post-write checkpoint records processed Bronze objects and the Silver ETag.
3. Dimensional transformations, integrity checks and versioned Core Gold Parquet snapshots → controlled Glue publication with best-effort rollback.
4. Silver Glue schema synchronization; Core Gold registrations retain the published snapshot locations.
5. Athena post-load validation of all nine Core Gold tables.
6. Analytics Gold publication of four additional Parquet reporting marts and Glue tables. Existing Power BI Import reporting can use the unchanged Core Gold model; the four additive Analytics Gold tables are available separately for reporting.

Before a manual run, check the intended Ember dataset/country scope (**41 markets** for the four core monthly datasets; **13 configured markets** for capacity), the **2010-01** configured historical request start and the existing S3 incremental ingestion state. Actual historical availability is dataset-specific. Historical backfills are **separate maintenance operations** and should not be substituted for regular incremental ingestion.

After a run, verify that all six Airflow tasks succeeded, especially `validate_persisted_gold` and `publish_analytics_gold`. Check expected new Bronze objects, updated Silver/Gold snapshots, Glue table metadata and Athena validation results. The fifth task, `validate_persisted_gold`, queries the existing `european-energy-analytics` workgroup and fails on empty Core Gold tables, null required fields, duplicate keys, invalid foreign keys, Athena errors or timeouts. The sixth task, `publish_analytics_gold`, prepares or skips reporting marts based on their fingerprints. Compare counts, country coverage and source periods with the project's [data-quality rules](../data_quality.md). A successful Airflow run alone does not prove analytical correctness.

### Phase B: Silver checkpoint and Core Gold publication

Silver now lists all Bronze object metadata but reads and cleans **only new** JSON objects when the `control/silver/<dataset>.json` manifest matches the live Silver snapshot ETag. The manifest is written **after** the validated Parquet snapshot is stored. A missing, stale or invalid manifest, a replaced Bronze object or a removed Bronze object triggers a complete deterministic rebuild from Bronze. New historical backfill objects are recognized even though they do not update the ingestion state. If Silver writing or manifest writing fails, retry the Silver task; never manually advance the manifest. Do not modify Bronze or Silver objects while processing.

Core Gold first validates the full nine-table in-memory model, writes **all nine** Parquet files under unique `gold_snapshots/<table>/<run-id>/` prefixes, outside the legacy `gold/<table>/` prefixes, then updates the nine Glue table locations. If S3 staging fails, previously published tables stay unchanged. If a Glue update fails, the publisher attempts to restore every affected table definition in reverse order. **Glue changes across tables are not atomic**: consumers may briefly see a mixture during publication, and rollback itself can fail. Inspect the failed task, each Glue table location, and the rollback error before retrying. Legacy Core Gold tables continue reading from `gold/<table>/` until their Glue location switches, so staging cannot accidentally mix old and new Parquet files. Old and incomplete snapshots are deliberately retained for diagnosis and recovery; do not delete them without proving that no Glue table references them. S3 bucket versioning is not a replacement for this staged publication process.

The Airflow DAG limits concurrent runs to one (`max_active_runs=1`); avoid running standalone Silver or Gold publishers concurrently with the DAG. Unit tests and CI mock AWS. **The real feature-branch Silver and Core Gold publishing steps were exercised manually against AWS on 2026-11-09**, with independent S3/Glue/Athena verification; see the [integration record](phase_b_validation_2026_11_09.md). The Airflow DAG itself has **not** been run end to end or validated for unattended operation.

### Analytics Gold publication and retry behavior

The checked-in Bronze profile CSV is a historical initial sample (20 core countries / 12 capacity countries), not a current coverage check. The publisher prepares and validates all four reporting marts before updating any final Glue table. The initial reporting validation on 2026-10-14 yielded 38, 38, 38 and 10 rows; Athena independently reconfirmed those counts on **2026-11-09**. On the November validation, all four Analytics marts returned `skipped=True` because data-derived fingerprints were unchanged; a changed-result republish was not live-tested. The project covers 41 markets overall, but comparison-year completeness and capacity-source coverage limit the reporting result sets.

For unchanged reporting SQL and result rows, the fingerprint stored on each final Glue table causes the publisher to skip a new snapshot. If any final Glue update fails, the publisher attempts to restore the previous table definitions for all touched marts in reverse order. Inspect the exception, the rollback results and the four current Glue locations before retrying. On a clean retry, unchanged marts are skipped based on fingerprints. Do not run concurrent publishers. Prepared or failed snapshots may remain unreferenced; do not delete them without confirming they are not referenced by Glue. If the Compose SQL mount was added after container creation, recreate Airflow services with `docker compose --env-file .env -f airflow/docker-compose.yaml up -d --force-recreate airflow-apiserver airflow-scheduler airflow-dag-processor` (without `down -v`).

### Verified feature-branch rollout (2026-11-09)

A controlled manual rollout from PR #14 is complete: all five Silver
checkpoints were inspected (19 Bronze source objects), nine Core Gold
versioned snapshots were published, and all nine Athena Core Gold quality
queries passed. The four existing Analytics Gold tables remained at their
valid previously published snapshots; fingerprint checks correctly
returned `skipped=True`, and four live Athena count queries returned
38, 38, 38 and 10 rows.

Before any Silver write, five original Silver Parquet files and all
18 Glue table definitions were backed up under
`backups/pre-phase-b/20261108T223846Z-b91ad8ee8b5b/` in the project
S3 bucket. The **application data bucket does not have versioning enabled**;
do not confuse it with the separate versioned Terraform state bucket.
Never delete these backups or the legacy Gold objects without an
explicit retention and restore decision.

**Still not exercised:** the complete Airflow DAG, new scheduled Ember
ingestion, end-to-end Slack alerting and changed-result Analytics Gold
UNLOAD/republication. These are separate operational acceptance tests.
The precise results and commands are in the
[Phase B AWS validation record](phase_b_validation_2026_11_09.md).

## 6. Troubleshooting and recovery

| Symptom | First checks | Safe next action |
| --- | --- | --- |
| Airflow UI unavailable | `docker compose ... ps`; API server and PostgreSQL logs | Restart affected services; preserve PostgreSQL volume |
| DAG missing | DAG processor logs; mounted `airflow/dags` directory | Fix import/configuration errors before rerunning |
| AWS `AccessDenied` | `aws sts get-caller-identity --profile energy-pipeline`; IAM scope | Correct the intended identity or least-privilege policy; do not switch to administrator credentials as a workaround |
| Ember API failure | API key, HTTP response, rate limits and request scope | Retry only after identifying the cause; avoid duplicate backfill loads |
| Data-quality failure | Failed task logs, input schema, keys and source coverage | Correct source/configuration or transformation; do not bypass validations |
| Silver checkpoint inconsistency | `control/silver/<dataset>.json`, Bronze keys/ETags, Silver ETag | Allow complete Bronze rebuild; do not manually advance manifest |
| Core Gold publication failed | Snapshot staging logs, nine Glue table locations and rollback report | Verify restoration to old snapshots before retrying; never delete referenced snapshots |
| Terraform drift or planned replacement | Plan output, variable values, remote-state ownership and resource taint | Stop; investigate before any apply or state manipulation |
| Analytics Gold failure | Confirm SQL exists under the **project-relative** `sql/analytics/` directory (mounted at `/opt/airflow/project/sql/analytics/` only inside Airflow), Athena query status, Glue `string` column types and staging table cleanup | Pull the current SQL-path fix; rerun only the failed mart-publisher task when safe. Completed marts with unchanged fingerprints are skipped. Do not delete Glue-referenced snapshots |
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
- [ ] Glue and Athena return expected data; `validate_persisted_gold` succeeds for all nine Core Gold tables.
- [ ] `publish_analytics_gold` succeeds; four `analytics_*` Glue tables are queryable in Athena.
- [ ] A repeated Analytics Gold run with unchanged results returns `skipped: True` and unchanged snapshot locations.
- [ ] Terraform validation passes without changing infrastructure.
- [ ] No credentials, state files or saved plans are committed.

See [architecture](../architecture/architecture.md), [architecture decisions](../decisions/architecture_decisions.md), [data quality](../data_quality.md), and the [Phase B AWS integration record](phase_b_validation_2026_11_09.md) for design and verified release evidence.
