# Phase B — first controlled AWS run (release gate)

> Status: **prepared, not executed**. This playbook is for PR #14 on
> `feature/phase-b-centralize-aws-config`, not for `main`.
> The only completed AWS steps so far were **read-only**. Do not execute the
> write steps without an explicit release decision, verified AWS identity,
> verified backups, and a maintenance window.

## 1. Read-only AWS baseline (verified 2026-11-08)

- Target region: `eu-central-1`; AWS caller's account matched the account
  embedded in the configured project bucket name.
- Project S3 bucket accessible. Default bucket encryption: SSE-S3 (`AES256`).
- **Bucket versioning is not enabled** (`GetBucketVersioning` returned no
  `Status`). No bucket lifecycle or Object Lock configuration exists.
  **Do not assume overwritten Silver objects can be recovered automatically.**
- Bronze: 19 JSON files across five datasets (approximately 38.3 MB):
  generation 4, demand 4, emissions 4, carbon_intensity 4, capacity 3.
- All five current Silver files exist at
  `silver/ember/<dataset>/<dataset>.parquet`. Total size ~0.75 MB.
- All nine legacy Core Gold files exist at
  `gold/<table>/<table>.parquet`. Total size ~0.75 MB.
- Existing Glue database: `european_energy_analytics`; five Silver tables,
  nine Core Gold tables, and four Analytics Gold tables all present.
- All nine Core Gold Glue locations **still use** `gold/<table>/`.
  No `gold_snapshots/` objects and no `control/silver/` manifests were
  present. This is the expected pre-Phase-B baseline.
- Dedicated Athena workgroup `european-energy-analytics` is enabled;
  workgroup configuration is enforced and a result location is configured.

This inventory is a point-in-time baseline, **not** evidence that the
new code has been exercised against AWS. Reconfirm it before any rollout.

## 2. Required release gates — all must pass

1. Check out the exact PR #14 commit; record its SHA. Run
   `python -m pytest -v` (and CI Terraform validation). Review CI results.
2. Agree on a maintenance window; pause the scheduled Airflow DAG and
   ensure **no manual Bronze/Silver/Gold publishers** are running.
   The DAG uses `max_active_runs=1`, which does not prevent a separate
   manually invoked script from racing it.
3. Verify AWS account and region **before every write session**.
   Local `AWS_PROFILE=energy-pipeline` must resolve to the intended principal.
4. Record a complete baseline of the 9 Core Gold Glue table definitions
   and locations, the 5 Silver Glue tables and all 4 Analytics Gold Glue tables. Retain
   baseline Athena counts/quality results if an approved query budget exists.
5. **Back up and verify all five existing Silver Parquet objects** under a
   timestamped, separate S3 backup prefix. Since bucket versioning is absent,
   do not write any Silver object until each backup is verified. Record
   source/destination keys, sizes and ETags.
6. Preserve the nine *legacy* Gold Parquet files. Phase B writes Core Gold
   snapshots under `gold_snapshots/<table>/<run-id>/`, outside the old
   `gold/<table>/` Glue prefixes, so do not delete or move any old files.
7. Confirm the planned AWS principal can read Bronze and Silver, write Silver,
   `control/silver/` manifests and `gold_snapshots/` objects, and
   `GetTable/CreateTable/UpdateTable` the intended Glue tables. Read access
   alone does **not** establish write permissions.

**STOP** on account mismatch, incomplete or unverified Silver backup,
unavailable Glue baseline, concurrent writers, CI failure, or unexpected
metadata/schema differences.

## 3. Backup recipe — illustration only; NOT YET RUN

Run only after explicitly approving S3 writes and confirming permissions
and paths. These commands are tailored to Windows PowerShell from the repo root.
They are *not* part of an automatic GitHub Actions deployment.

```powershell
$env:AWS_PROFILE = "energy-pipeline"
$Bucket = python -c "from config.settings import get_aws_settings; print(get_aws_settings()[0])"
$Region = python -c "from config.settings import get_aws_settings; print(get_aws_settings()[1])"
aws sts get-caller-identity --profile $env:AWS_PROFILE
aws configure get region --profile $env:AWS_PROFILE

$ExpectedAccount = aws sts get-caller-identity --profile $env:AWS_PROFILE --query Account --output text
if ($LASTEXITCODE -ne 0 -or -not $Bucket.Contains($ExpectedAccount) -or $Region -ne "eu-central-1") {
    throw "STOP: AWS identity, bucket, or region mismatch"
}

$Stamp = (Get-Date -Format "yyyyMMddTHHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0,8)
$BackupPrefix = "backups/pre-phase-b/$Stamp"
$BackupDir = Join-Path $HOME "phase-b-baseline-$Stamp"
New-Item -Path (Join-Path $BackupDir "glue") -ItemType Directory -Force | Out-Null

$Silver = @("generation","demand","emissions","carbon_intensity","capacity")
foreach ($Dataset in $Silver) {
    $SourceKey = "silver/ember/$Dataset/$Dataset.parquet"
    $BackupKey = "$BackupPrefix/silver/$Dataset.parquet"
    $SourceSize = aws s3api head-object --bucket $Bucket --key $SourceKey --region $Region --query ContentLength --output text
    if ($LASTEXITCODE -ne 0) { throw "STOP: original Silver object not readable: $Dataset" }
    aws s3api copy-object --bucket $Bucket --copy-source "$Bucket/$SourceKey" --key $BackupKey --region $Region
    if ($LASTEXITCODE -ne 0) { throw "STOP: Silver backup copy failed: $Dataset" }
    $BackupSize = aws s3api head-object --bucket $Bucket --key $BackupKey --region $Region --query ContentLength --output text
    if ($LASTEXITCODE -ne 0 -or $BackupSize -ne $SourceSize) { throw "STOP: Silver backup verification failed: $Dataset" }
}

$Core = @(
 "dim_date","dim_country","dim_energy_series","dim_capacity_series",
 "fact_generation","fact_emissions","fact_demand",
 "fact_carbon_intensity","fact_capacity"
)
$Analytics = @(
 "analytics_generation_demand_summary","analytics_energy_mix_transition_summary",
 "analytics_emissions_carbon_intensity","analytics_installed_solar_wind_capacity"
)
foreach ($Table in ($Silver + $Core + $Analytics)) {
    aws glue get-table --database-name "european_energy_analytics" --name $Table --region $Region |
       Out-File -FilePath (Join-Path $BackupDir "glue/$Table.json") -Encoding utf8
}
```

**Before declaring backup complete:** inspect failures and explicitly
compare the five source-versus-backup object sizes, and confirm all
18 Glue JSON files are nonempty and represent the expected database.
Capture original Glue locations separately. For a future rollback,
Glue's `GetTable` response must be converted to a valid `TableInput`;
do **not** blindly submit the original JSON to `UpdateTable`.
Never store credentials, Terraform state, or sensitive local configuration
in this backup directory or commit the backup directory to GitHub.

## 4. Controlled execution order — requires separate write approval

**Gate A — Silver pilot:** After validated backups and stopped Airflow,
process the smallest representative dataset (`demand`) from the PR
revision using `process_dataset(get_s3_client(), "demand")`.
This **overwrites one Silver Parquet object** and writes its manifest.
Verify: schema, DQ, snapshot ETag, manifest ETag, all recorded Bronze
keys, and no unexpected Glue changes. Stop on any discrepancy.

**Gate B — remaining Silver:** Run the remaining datasets (the full
Silver transformation entrypoint will skip the already checkpointed
dataset). Verify all five datasets have correct manifests, ETags and
stable validated Silver snapshots. A failed manifest write must result
in safe reprocessing, never a falsely committed checkpoint.

**Gate C — Core Gold publication:** Run the Gold transformation *only
after* all Silver gates pass. It validates all nine in-memory tables,
writes nine new Parquet files under unique `gold_snapshots/` prefixes,
and then repoints each corresponding Glue table to its new prefix.
Check **all nine** Glue locations and the common `core_gold_snapshot_id`;
confirm all nine snapshot files exist and schemas agree with the
registered `GOLD_TABLE_SCHEMAS`. The nine Glue updates are **not atomic**;
avoid concurrent Athena/Power BI consumption during the publication
window. If any update fails, the automatic rollback is best-effort,
so verify every Glue table manually.

**Gate D — downstream:** Run Glue schema synchronization, then the
Athena post-load validation of all nine Core Gold tables, and finally
the four Analytics Gold publication tasks. These actions issue AWS
requests and, for Athena, billable queries; execute only with an
approved cost envelope. Verify all nine Core Gold checks pass and
all four reporting marts reference valid published snapshots.

**Gate E — rerun:** Repeat the Silver step with unchanged Bronze and
verify it performs no Bronze JSON downloads and no Silver writes.
Check the Airflow task graph and failure notifications separately.

Do **not** merge PR #14 or turn the full monthly DAG back on until
the gates are documented and accepted.

## 5. Rollback / abort procedure

- **Before Silver write:** abort; the live environment remains unchanged.
- **After Silver write, before Gold publication:** stop writers; inspect
  manifest and Glue pointers. If rollback is required, restore each
  affected Silver object from its verified pre-Phase-B copy. A restored
  Silver ETag must mismatch any newer manifest so the next run
  deliberately rebuilds from Bronze.
- **During/after Glue publication failure:** immediately stop dependent
  jobs and inspect **all nine** Glue locations. The implementation
  attempts reverse-order rollback, but if any table remains changed,
  restore its saved `TableInput` using a reviewed, validated recovery
  procedure. The original legacy Gold Parquet files must remain intact.
- **After downstream Athena/Analytics publication:** include the four
  reporting Glue table definitions in the recovery decision; do not
  assume downstream tables automatically roll back when Core Gold does.
- Never delete source files, manifests, staged snapshots or backup copies
  during incident response. Treat manually changed Glue definitions as
  an incident requiring a new consistency check.

## 6. Scope of this PR

This runbook is a **release plan only**. It does not enable S3
versioning, create backup objects, run pipelines, create/change Glue
tables, execute Athena SQL, apply Terraform, or merge the PR. AWS
metadata preflight may be rerun read-only at any time.
