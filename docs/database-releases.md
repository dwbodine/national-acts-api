# Database migrations and API releases

The schema is now defined by reviewed Alembic migrations in Git. Production data
exports stay ignored under `seeds/`; neither they nor secret files enter API images.
No migration executes during Flask or Gunicorn startup.

## One-time adoption

The initial migration captures the 45 tables, indexes, constraints, column defaults,
and auto-increment column attributes from the October 5, 2026 production export.
It contains no rows, no `DROP TABLE`, no database selection, and no production
auto-increment counters. `baseline-schema.json` records normalized `SHOW CREATE
TABLE` output from that migration on MariaDB 12.2.2. Baseline verification ignores
only changing table auto-increment counters. It rejects missing/extra/changed
tables, views, triggers, routines, and events that the export did not capture.
Use the same MariaDB version and ordinary `sql_mode`; a mismatch requires review,
not blindly stamping or editing the recorded baseline to hide drift.

1. Install dependencies: `python -m pip install -r requirements-dev.txt`.
2. For your existing local imported database:

   ```powershell
   .\.venv\Scripts\python.exe -m tools.migrate --env-file .env.development verify-baseline
   .\.venv\Scripts\python.exe -m tools.migrate --env-file .env.development adopt-baseline
   .\.venv\Scripts\python.exe -m tools.migrate --env-file .env.development check
   ```

   `adopt-baseline` repeats verification and writes only Alembic's version table.
   It never recreates tables or imports data. Exported environment variables take
   precedence over dotenv values. Connection settings are `DB_HOST`, `DB_PORT`
   (default 3306), `DB_DB`, `DB_USER`, and `DB_PASSWORD`.

3. Commit this implementation. `bash deploy.sh` builds/pushes the commit SHA tag
   and prints the immutable ECR digest. Enable tag immutability on the existing
   ECR API repository. Retain previous release images for the rollback window.
4. Copy the updated `aws/docker-compose.yml` and `aws/*api.sh` plus
   `aws/release-common.sh` to the existing EC2 compose directory. Keep its project
   name, existing volume, networks, `.env`, and secrets paths unchanged.
5. Create `secrets/nationalactsapi_migrations.env` on EC2 (never commit it):

   ```dotenv
   DB_HOST=nationalactsdb
   DB_DB=nationalacts20
   DB_USER=nationalacts_migrator
   DB_PASSWORD=<separately-created-migration-user-password>
   ```

   Provision this dedicated MariaDB user with schema-scoped DDL and DML privileges
   needed by reviewed migrations and access to schema metadata. Runtime API users
   should have only the DML privileges they need. `MIGRATION_DB_*` settings are also
   supported and take precedence over corresponding `DB_*` settings. Do not grant
   migration credentials to the API container. Test metadata visibility with the
   migration account before adoption; a restricted account must not hide objects.
6. Take and verify a production backup, then run these commands on EC2 using the
   digest printed by the publisher (these are the first intentional production
   writes; run them only when ready):

   ```bash
   export API_IMAGE='804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/nationalactsapi@sha256:<digest>'
   docker compose --profile migration pull migrate
   docker compose --profile migration run --rm --no-deps migrate python -m tools.migrate verify-baseline
   docker compose --profile migration run --rm --no-deps migrate python -m tools.migrate adopt-baseline
   ```

   A backup restore should be rehearsed on an isolated database before relying on
   it. Never run `upgrade` against an existing unversioned database: it refuses.

## Local development

`docker compose up -d nationalactsdb` now creates an empty schema on a **new** volume.
Existing volumes remain intact. Run `tools.migrate ... upgrade` to create the schema.
For an explicitly requested data import into a new local volume, use
`docker compose -f docker-compose.yml -f docker-compose-data.yml up -d nationalactsdb`,
then verify/adopt the baseline. Initialization scripts execute only on empty volumes.
Do not remove a volume merely to apply a migration.

The baseline creates no reference or demo rows. For development against an empty
schema, provide synthetic fixtures; the application may require lookup/configuration
rows before feature flows work. Keep legitimate, required reference-data changes
in reviewed migrations and customer/test fixtures separate.

Create a migration alongside its application change:

```powershell
.\.venv\Scripts\python.exe -m tools.migrate revision "add optional event field"
.\.venv\Scripts\python.exe -m tools.migrate --env-file .env.development upgrade
```

Edit the generated `upgrade()` explicitly using Alembic operations or `op.execute`.
There is no ORM metadata or schema autogeneration. The default `downgrade()` refuses
until replaced with a reviewed safe implementation. Never edit an applied migration;
add a correction. Avoid importing application modules into migrations.

## Release and application rollback

For an isolated rehearsal database on EC2, `aws/docker-compose-staging.yml` uses
its own Compose project, network, and volume, with no public database port. Create
separate staging root and migration password files at the paths declared there,
plus `secrets/nationalactsapi_staging.env` with `DB_HOST=staging-db`,
`DB_DB=nationalacts_stage`, `DB_USER=nationalacts_migrator`, and `DB_PASSWORD`
matching the staging migration password. Set `API_IMAGE` to the candidate digest:

```bash
docker compose -f docker-compose-staging.yml up -d staging-db
docker compose -f docker-compose-staging.yml --profile migration run --rm migrate python -m tools.migrate upgrade
docker compose -f docker-compose-staging.yml --profile migration run --rm migrate python -m tools.migrate check
```

For realistic data rehearsals, restore only a sanitized backup into this separate
database, verify/adopt the baseline if unversioned, then upgrade. No production
data is automatically copied into staging, and this file does not deploy a staging
API or website. Application feature checks need an API instance configured to use
the staging database. Do not merge this compose file into production compose.

On EC2, authenticate Docker to ECR as usual and set an S3 destination the instance
role can read and write. Scripts require Bash, `flock`, Docker Compose v2, AWS CLI,
gzip, sha256sum, and cmp. Run beside the production compose file:

```bash
export BACKUP_S3_PREFIX=s3://your-existing-backup-bucket/pre-deploy
bash release-api.sh '804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/nationalactsapi@sha256:<digest>'
# If the newly deployed application needs to be rolled back:
bash rollback-api.sh
```

`build-api.sh` now delegates to `release-api.sh` and requires the same image argument.
The release script pulls the immutable image, records the preceding image and schema
revision, takes a logical backup including routines/events/triggers, verifies gzip,
uploads to S3, downloads it and compares bytes, runs migrations, checks revision,
deploys only the API, and checks HTTP and database access. The other websites and
database container remain running. Recreating the single API container can briefly
interrupt requests; this is not a zero-downtime deployment system.

Release records and local backups are in `.releases/` with restricted directory
permissions. Keep this directory and retain the corresponding S3 backups and ECR
images. Establish a retention policy appropriate to your rollback window and disk
capacity. `release-common.sh` reuses its recorded current image. If running Docker
Compose manually, explicitly set `API_IMAGE` from `.releases/current-image`; bare
Compose retains the legacy `latest` default for compatibility.

Host `flock` serializes deployments; a MariaDB advisory lock serializes migration
runners. A migration failure stops before replacing the application, but MariaDB
DDL can already have committed. Inspect the database and release status before
retrying; never stamp a failed revision simply to suppress the error. Backup
verification checks transfer integrity, not the ability to restore or the semantics
of transformed data. Keep periodic restore rehearsals. All baseline tables use
InnoDB; reassess backup consistency if adding nontransactional tables. Do not run
other schema changes while taking the backup.

**Every normal release must preserve compatibility with the preceding application.**
Add optional columns/tables first, backfill separately with resumable jobs, switch
reads/writes, and remove old structures only after the rollback window closes.
During renames/replacements, keep old and new writes consistent. A destructive
cleanup is a separate maintenance release with a specifically reviewed recovery
plan; the application rollback script cannot make incompatible schemas compatible.

Application rollback redeploys the preceding exact image and retains schema and
live data. It does not restore a backup or run `downgrade`. For an explicitly tested,
data-preserving schema rollback, use the migration-capable image with
`python -m tools.migrate downgrade <explicit-revision>` after assessing application
compatibility. Baseline teardown is always refused. Database disaster recovery must
account for writes since the backup; importing a snapshot into live production is
not an ordinary rollback.

## Verification

GitHub Actions runs migration tests on isolated MariaDB 12.2.2. Locally, point tests
only at a disposable server whose root account can create/drop temporary databases:

```powershell
$env:TEST_MARIADB_PORT='33316'
$env:TEST_MARIADB_PASSWORD='<disposable-server-password>'
.\.venv\Scripts\python.exe -m pytest -o addopts='' --basetemp=test_runtime/migrations test/integration/test_migrations.py
```

Tests create uniquely named `migration_ci_*` schemas and delete only those schemas.
They cover empty creation, repeat upgrades, preserving rows during adoption,
schema mismatch rejection, concurrent-runner exclusion, a reversible next migration,
refusal of baseline deletion, and partial DDL failure. Before releases that add
migrations, also rehearse upgrading a sanitized production-sized restore and run
the old and new application feature checks against the resulting schema.

`aws/build-db.sh` and `aws/rebuild-all.sh` are disaster-recovery tools guarded by
`CONFIRM_DATABASE_REBUILD=DELETE_DATABASE_AND_RESTORE`. They are never deployments.
