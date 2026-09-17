# Architecture Decisions

## ELT and Medallion Architecture

Bronze, Silver and Gold separate source preservation, data preparation and analytical modelling. Bronze retains the original API response, while transformation occurs after ingestion into S3.

## JSON → Parquet

Bronze uses JSON to preserve the source response with minimal transformation. Silver and Gold use Parquet because it is column-oriented, storage-efficient and well suited to analytical workloads. With Athena, this also reduces unnecessary data scanning and query cost.

## Incremental Bronze, Snapshot Silver and Gold

Bronze is append-only and stores incremental source loads for traceability. Silver maintains one stable, complete cleaned snapshot per dataset. Gold maintains one stable validated analytical snapshot per dimension or fact table. This keeps downstream consumption simple while retaining raw ingestion history.

## pandas Instead of Spark

The current data volume does not justify distributed processing. pandas keeps the implementation simpler and cheaper while meeting the workload requirements. Spark would become appropriate if data volume or processing complexity exceeded a single-machine workload.

## Explicit Glue Catalog Registration

Silver and Gold schemas are controlled by project code. They are therefore registered explicitly in the Glue Data Catalog instead of being rediscovered with crawlers, improving predictability and reproducibility.

## Athena Instead of an Analytical Database Server

Athena provides serverless SQL directly over Parquet in S3 using Glue metadata. This avoids maintaining an always-running analytical database for a portfolio-scale workload and aligns cost with query usage.

## Dimensional Gold Model

A Fact Constellation / Galaxy model separates generation, emissions, demand, carbon intensity and capacity into fact tables while sharing compatible dimensions. Capacity uses a separate series dimension because its aggregation semantics can differ from generation and emissions.

## Power BI Import Mode

The Gold model is imported into Power BI because the dataset is small enough for fast local interaction. DirectQuery would add source-query latency and repeated Athena queries without a meaningful benefit at the current scale.

## Least-Privilege AWS Access

The pipeline identity receives only the AWS permissions required by the workflow. Destructive S3 permissions are intentionally excluded. Local development uses a named AWS profile; production deployment should use IAM roles and temporary credentials.

## No Iceberg at the Current Scale

Parquet is sufficient for the project's stable snapshot design. Apache Iceberg would provide additional transactional table-management capabilities, but they are not required for the current workload and would add unnecessary complexity.
