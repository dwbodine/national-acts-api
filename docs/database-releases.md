# Database migrations and API releases

The schema is now defined by reviewed Alembic migrations in Git. Production data
exports stay ignored under `seeds/`; neither they nor secret files enter API images.
No migration executes during Flask or Gunicorn startup.

There are three separate things to keep track of:

- **Schema:** the structure of the database, such as tables, columns, and indexes.
  A migration records a change to that structure, and sometimes a required data change.
- **Data:** the customer, event, order, and configuration rows inside those tables.
  Downloading a production backup gives you a snapshot of these rows as well as
  the schema at the time of the backup.
- **Application release:** the exact API code packaged in a Docker image. Each
  release expects a compatible schema, but replacing the API image does not itself
  change the database.

The normal direction is: write a migration locally, test it, publish the code,
apply the migration to production, then start the new API. Copying production data
back to your machine for troubleshooting is a separate operation. It should never
be how schema changes become part of the project.

Commands below use `python` to mean the project's virtual-environment Python.
PowerShell examples show its full path. Local commands run from the repository
root; production commands run on EC2 beside its existing compose file. Commands
with `<digest>` or password placeholders must have those placeholders replaced.

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

   **Purpose:** install Alembic, SQLAlchemy, and the project's development/test
   dependencies into your virtual environment. Alembic runs the migration scripts;
   SQLAlchemy supplies its database connection. Your existing application data
   layer continues to use the MariaDB connector.

   **Consequences:** this changes installed Python packages, not any database.
   In PowerShell, use `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`
   so the packages go into this project's environment rather than another Python
   installation. Continue once installation finishes successfully.
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

   These three commands perform different jobs:

   - **`verify-baseline`: inspect before changing anything.** It compares the
     selected database's table definitions with the committed baseline. It does
     not compare customer rows: two databases can have different orders while
     having the same schema. Success means the structure matches. A mismatch
     names the affected tables; stop and investigate those differences.
   - **`adopt-baseline`: register an already-existing schema.** It verifies again,
     then creates/populates `alembic_version` with `0001_baseline`. That table tells
     future migration runs where to begin. Existing application tables and rows
     stay in place. This is appropriate for your imported production database,
     because it already contains the baseline structure.
   - **`check`: compare recorded revision with this checkout.** It checks that
     the database is at the migration head, meaning the latest migration in this
     code checkout. It does not recheck every table definition or test application
     features. Right now the baseline is the head. Once newer migrations exist,
     adopting a baseline alone will not satisfy `check`; on your local database,
     run `upgrade` to apply those newer revisions first.

   Before running these commands, check that `.env.development` selects your local
   database. The filename is not a safety boundary: connection values determine
   the target. If you previously exported `DB_*` or `MIGRATION_DB_*` variables into
   your shell, they can override that file. `adopt-baseline` is a real database
   write, even though it only writes migration bookkeeping.

3. Commit this implementation. `bash deploy.sh` builds/pushes the commit SHA tag
   and prints the immutable ECR digest. Enable tag immutability on the existing
   ECR API repository. Retain previous release images for the rollback window.

   **Purpose:** make the code and migrations a traceable release. Commit them
   together so a reviewer can see which schema change belongs to which code
   change. Run the checks before publishing; the publisher does not run the test
   suite for you and refuses an uncommitted working tree.

   **Consequences:** `deploy.sh` builds a Docker image locally and uploads it to
   ECR, AWS's container registry. Despite its name, it does not replace the running
   production API or execute a migration. It uses your local
   `deployment_nationalacts` AWS profile, which must have ECR publishing access.
   The Git commit SHA is the image tag. The printed `@sha256:...` digest identifies
   the exact uploaded image contents; use that whole reference on EC2.

   ECR tag immutability is a separate repository setting; the script does not
   enable it. It prevents an existing commit tag being overwritten. Keeping older
   images matters because rollback needs the preceding image to remain available.
4. Copy the updated `aws/docker-compose.yml` and `aws/*api.sh` plus
   `aws/release-common.sh` to the existing EC2 compose directory. Keep its project
   name, existing volume, networks, `.env`, and secrets paths unchanged.

   **Purpose:** install the new release tooling on the server before using it.
   Your API image contains Python and migrations, while these host scripts
   coordinate Docker, backups, and releases on EC2.

   **Consequences:** copying the files changes server configuration/scripts but
   does not start or stop containers. Keep the production compose directory and
   project name the same. Docker Compose uses the project name to identify its
   resources, including the persistent database volume. Running from a new
   directory or changing the project name can select a different, empty volume
   rather than your existing database. Copy into the established deployment
   directory; do not create a new production stack just to install these files.
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

   **Purpose:** separate the account allowed to change schema from the account
   used by ordinary API requests. A migration may need `CREATE`, `ALTER`, or
   `DROP`; the running API generally needs to read and change rows instead.

   **Consequences:** writing this dotenv file does not create a MariaDB user or
   grant permissions. You must provision the user in MariaDB separately, then
   put its real password in the file. Provisioning the account changes production
   access permissions, not application data. Restrict grants to `nationalacts20`
   and the connection origin needed by the migration container. Ensure the
   account can see all objects in that schema so verification is meaningful.

   The compose migration service mounts this file and the container entrypoint
   reads it into its environment. It is separate from `nationalactsapi.env`.
   Adding the new account does not automatically reduce an existing API account's
   privileges; review that account separately. Keep credentials out of Git and
   the image, and restrict access to the secret file on EC2.
6. Take and verify a production backup, then run these commands on EC2 using the
   digest printed by the publisher (these are intentional production setup
   operations; run them only when ready):

   ```bash
   export API_IMAGE='804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/nationalactsapi@sha256:<digest>'
   docker compose --profile migration pull migrate
   docker compose --profile migration run --rm --no-deps migrate python -m tools.migrate verify-baseline
   docker compose --profile migration run --rm --no-deps migrate python -m tools.migrate adopt-baseline
   ```

   A backup restore should be rehearsed on an isolated database before relying on
   it. Never run `upgrade` against an existing unversioned database: it refuses.

   **Purpose:** adopt the existing production schema without trying to create it
   again. This is the production equivalent of the local adoption in step 2.
   The user/password grant changes in step 5 are also intentional production
   writes; the adoption command is the first migration-bookkeeping write here.

   Run these commands in order:

   - **`export API_IMAGE=...`: select the migration-capable image.** This sets a
     variable in the current shell. It changes neither a container nor a database
     and is not a permanent server setting. Replace `<digest>` with the publisher's
     digest, and use the same shell for the following commands.
   - **`docker compose --profile migration pull migrate`: download that image.**
     The migration profile makes the optional migration service available.
     `pull` downloads image files to EC2; it does not run them. Docker must already
     be authenticated to your ECR registry.
   - **`... run --rm --no-deps migrate ... verify-baseline`: inspect production.**
     `run` starts a temporary container, `--rm` removes that container afterwards,
     and `--no-deps` avoids starting/recreating other services. The production
     database must already be running. Successful exit means the structure matches.
   - **`... adopt-baseline`: write production's starting revision.** This again
     verifies the schema, then records `0001_baseline`. It does not deploy the API
     or replace application tables. Repeating it at the same matching baseline is
     supported, but adopting is a one-time setup operation, not a release habit.

   Take a fresh backup before adoption because this is your first use of the new
   process against production. A downloaded file is not enough to establish that
   recovery works: restore it into a separate database and check representative
   tables/rows. If verification fails, do not bypass it with a manual stamp.

## Local development

`docker compose up -d nationalactsdb` now creates an empty schema on a **new** volume.
Existing volumes remain intact. Run `tools.migrate ... upgrade` to create the schema.
For an explicitly requested data import into a new local volume, use
`docker compose -f docker-compose.yml -f docker-compose-data.yml up -d nationalactsdb`,
then verify/adopt the baseline. Initialization scripts execute only on empty volumes.
Do not remove a volume merely to apply a migration.

For a new empty local database, the full schema-creation command is:

```powershell
.\.venv\Scripts\python.exe -m tools.migrate --env-file .env.development upgrade
```

**Purpose:** apply the baseline and any later migrations to the selected database.
**Consequences:** on an empty database it creates application tables; on a versioned
database it executes only pending migrations. It records completed revisions so
running it again does not repeat them. On an existing unversioned database it
refuses, because it cannot safely assume which changes have already happened.
Verify/adopt such a database first.

The Docker volume stores the actual database files. Restarting/rebuilding the
container normally preserves that volume. The optional data compose file mounts
your export as an initialization script, but MariaDB runs that script only when
initializing an empty volume. Adding the mount or restarting an existing database
does not refresh its data. Replacing local troubleshooting data needs a separate,
explicit restore procedure; it is not accomplished by `upgrade`.

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

The `revision` command only creates a new Python file under `migrations/versions`;
it does not connect to or change the database. Its message becomes a description
and filename. Fill in `upgrade()` with the changes you intend to apply. A blank
generated migration does not infer your intended SQL changes.

The following `upgrade` command does execute those changes locally. Check the
result in the database and exercise the affected application feature. For example,
after adding an optional column, confirm that existing rows still work and both
old and new code can run against the updated schema. A `downgrade()` that removes
that column would also remove values subsequently stored in it; being able to
write the opposite SQL does not automatically make it safe.

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

The three staging commands have these effects:

1. **`up -d staging-db`: create/start the rehearsal database in the background.**
   Its data lives in `staging_db_data`, separate from production's volume.
   This uses additional server disk and memory. `-d` lets the command return while
   the container keeps running; it does not mean initialization has finished.
2. **`run ... upgrade`: rehearse the candidate's migrations.** The migration
   service waits for the staging database's health check, then changes only that
   database using staging credentials. With an empty volume this tests creating
   the schema from scratch. With a restored, versioned snapshot it tests upgrading
   an existing schema, which is closer to production.
3. **`run ... check`: verify the recorded staging revision.** It confirms that
   the candidate's migrations reached their head. It cannot tell you whether
   checkout, reports, or other API features behave correctly; test those through
   an API configured for staging as a separate check.

Staging is useful because an `ALTER TABLE` on a populated table can take much
longer than it does on an empty one. A realistic restore helps reveal runtime,
locking, disk-space, and data assumptions before the production release.

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

`BACKUP_S3_PREFIX` selects the folder-like prefix where this release's recovery
backup will be uploaded. Setting it changes only a shell variable. Use a real
bucket/prefix that the EC2 role can upload to and download from; it is independent
of the nightly backup prefix.

`release-api.sh` is the command that actually changes production. Its sequence is:

1. **Pull the candidate and record the current release.** It records the old
   image reference and database revision so recovery has a specific target.
2. **Back up the current database.** It dumps schema and data, checks that the
   compressed file is valid, uploads it, downloads it, and compares the bytes.
   This uses local disk, network transfer, and S3 storage. A failure stops the
   release before migrations begin. Byte equality verifies transfer integrity,
   not application-level correctness or successful restoration.
3. **Apply pending migrations and check the revision.** This changes production's
   schema and possibly data, depending on the scripts you wrote. The old API is
   still running during this step, which is why migrations must support it.
4. **Replace only the API container with the candidate image.** This is when users
   start receiving the new code. Existing database files stay in their volume.
5. **Check HTTP and database access.** On success it records the release as
   successful. These checks establish basic readiness; they do not replace
   feature tests for the change you deployed.

If readiness fails, the script reports failure but does not automatically restore
the old API. Inspect the release record and run `rollback-api.sh` when appropriate.
Likewise, a failed migration stops the rollout but does not undo any DDL already
committed. Identify the failed stage before deciding the recovery action.

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

`rollback-api.sh` takes the previous image from the most recent release's recovery
record, starts it, and checks readiness. It is a one-release application rollback,
not a menu of arbitrary older versions. Repeating it selects that same previous
image. Customer writes made since deployment remain in the database.

That is useful when, for example, a new API release has a bug after adding an
optional column. The older API can ignore that column while retaining all rows.
It will not work if the migration removed a column the older API still needs.
In that situation, restoring old code alone cannot repair the incompatibility.

A schema `downgrade <explicit-revision>` executes the downgrade functions down to
the chosen revision and changes the database itself. Only use it when those
functions were reviewed and tested against the current data. Restoring an older
backup is more consequential: it can replace everything written since that
snapshot. You need a plan for those newer orders and other writes before doing it.

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

The test environment variables identify the disposable database server; they do
not select your ordinary development database. The tests create their own unique
schemas on that server, then remove them. The password must belong to this test
server, whose account needs database-creation privileges.

`-o addopts=''` replaces the project's default pytest options for this invocation,
so this command runs the focused migration checks without the default coverage
configuration. `--basetemp` puts temporary test files inside the workspace to avoid
Windows system-temp permissions. Passing tests are evidence for the migration
runner's behavior; they do not prove every future migration is safe for live data.

GitHub Actions runs the database checks and release-script checks on pushes and
pull requests. It neither publishes an API image nor deploys production. Make
these checks part of the review process before running the publisher and release.

`aws/build-db.sh` and `aws/rebuild-all.sh` are disaster-recovery tools guarded by
`CONFIRM_DATABASE_REBUILD=DELETE_DATABASE_AND_RESTORE`. They are never deployments.

That guard is an explicit opt-in for destructive recovery, not a promise of safety.
`build-db.sh` removes the named database volume; `rebuild-all.sh` tears down the
stack with its volumes before importing a backup. Once a volume is deleted,
restarting its container cannot recover those files. Recovery depends on the
backup and import succeeding. Do not set that variable for ordinary releases,
migrations, or local troubleshooting-data refreshes.
