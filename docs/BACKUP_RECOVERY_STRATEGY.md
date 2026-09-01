# Ra7al Database Backup & Disaster Recovery Strategy

## 1. Overview & Objectives

This document establishes the official operational standard for PostgreSQL database backups, disaster recovery, encryption, and restoration testing for the Ra7al University Bus Management System.

* **Recovery Point Objective (RPO):** Maximum 1 hour (via WAL archiving / daily snapshots).
* **Recovery Time Objective (RTO):** Maximum 30 minutes for database restoration.

---

## 2. Backup Architecture & Storage Isolation

1. **Isolation from Public Web Root:**
   * Database backups must **NEVER** be stored in the web application root, `/app/uploads`, or any directory served by web servers or static file handlers.
   * All backup artifacts are ignored by `.gitignore` (`*.sql`, `*.dump`, `*.backup`, `*.bak`, `backups/`, `dumps/`).

2. **Offsite Cloud Storage:**
   * Production backups are pushed directly to a dedicated, private cloud storage bucket (e.g., AWS S3, Cloudflare R2, Google Cloud Storage).
   * Bucket configuration:
     * **Public Access Blocked:** Enabled unconditionally.
     * **Server-Side Encryption:** Enabled (KMS / AES-256).
     * **Object Lock / WORM (Write Once Read Many):** 30-day retention lock to protect against ransomware or accidental deletion.
     * **Lifecycle Rules:** Automatically transition daily backups to glacier storage after 30 days and delete after 365 days.

---

## 3. Operational Backup Procedure

### Automated Backup Script
Run the automated backup script located at `scripts/backup_db.py`. It loads credentials strictly from the environment or secret manager (`DATABASE_URL`).

```bash
# Example invocation via cron or CI/CD runner
python scripts/backup_db.py --output-dir /secure/backups --encrypt
```

### Manual pg_dump Execution
```bash
# Export compressed custom format dump (excludes secrets from command-line args)
PGPASSWORD="${DB_PASSWORD}" pg_dump -h "${DB_HOST}" -p "${DB_PORT:-5432}" -U "${DB_USER}" -d "${DB_NAME}" -Fc -f "ra7al_backup_$(date +%Y%m%d_%H%M%S).dump"

# Encrypt backup with GPG / OpenSSL before transport
gpg --symmetric --cipher-algo AES256 "ra7al_backup_$(date +%Y%m%d_%H%M%S).dump"
```

---

## 4. Restoration Procedure & Verification

### Step-by-Step Restore Instructions

1. **Decryption:**
   ```bash
   gpg --decrypt ra7al_backup_YYYYMMDD_HHMMSS.dump.gpg > restore_target.dump
   ```

2. **Pre-Restoration Safety Validation:**
   * Verify dump header integrity using `pg_restore --list restore_target.dump`.
   * Create an emergency pre-restore snapshot of the current database state.

3. **Execution:**
   ```bash
   # Restore into clean staging/production database
   PGPASSWORD="${DB_PASSWORD}" pg_restore -h "${DB_HOST}" -p "${DB_PORT:-5432}" -U "${DB_USER}" -d "${DB_NAME}" --clean --if-exists -v restore_target.dump
   ```

4. **Post-Restoration Sanity Checks:**
   ```bash
   # Verify alembic revision matches expected head
   alembic current
   
   # Run verification test suite against staging
   pytest tests/security -v
   ```

---

## 5. Scheduled Restoration Drills

* **Cadence:** Quarterly disaster recovery simulation.
* **Procedure:** Restore the latest production backup into an isolated staging environment and execute the full test suite (`pytest -v`) to prove data integrity and schema compatibility.
