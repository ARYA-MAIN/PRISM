# Database Migrations

This folder contains SQL migration scripts for the PRISM PostgreSQL database.

## Migration 001 — Allow NULL from_location

**File:** `001_allow_null_from_location.sql`

**Purpose:** Allows inventory movements originating outside the warehouse, such as customer returns, to have a `NULL` value in `from_location`.

**Prerequisite:** The `prism_data.movements` table must already exist.

### Applying the migration

From the repository root, run:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d prism_db -f ".\backend\migrations\001_allow_null_from_location.sql"
```

Enter your PostgreSQL password when prompted.

**Note:** Apply this migration only to databases where the change has not already been made.