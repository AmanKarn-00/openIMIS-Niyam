# NIYAM openIMIS Production Runbook

## Current Integration Shape

NIYAM is split into two openIMIS-compatible modules:

- Backend module: `/Users/shuv/Downloads/niyam_openimis`
- Frontend module: `/Users/shuv/Downloads/niyam_fe`

The backend assembly at `/Users/shuv/Downloads/openimis-be_py/openimis.json` includes:

```json
{
  "name": "niyam",
  "pip": "-e ../niyam_openimis"
}
```

The frontend assembly at `/Users/shuv/Downloads/openimis-fe_js/openimis.json` includes:

```json
{
  "name": "NiyamModule",
  "npm": "@openimis/fe-niyam@file:../niyam_fe"
}
```

## Backend Setup

From `/Users/shuv/Downloads/openimis-be_py`:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd script
../.venv/bin/python modules-requirements.py ../openimis.json > ../modules-requirements.txt
cd ..
.venv/bin/python -m pip install -r modules-requirements.txt
```

On macOS 26, `pyminizip==0.2.6` may fail because its vendored zlib source redefines `fdopen`. The local environment was fixed by building the package from a patched temp source. Linux/Docker environments generally avoid this SDK-specific issue.

## Database And Migrations

The repository now has a local `.env` copied from `.env.example`. It targets PostgreSQL on `127.0.0.1:5432` by default.

When Docker Desktop or another Docker daemon is running:

```bash
cd /Users/shuv/Downloads/openimis-be_py
docker compose up -d db
cd openIMIS
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py runserver 0.0.0.0:8000
```

NIYAM adds one migration:

```text
niyam
 [ ] 0001_initial
```

It creates `niyam_validation_log`, an append-only audit table for deterministic validation outcomes.

## Frontend Setup

The NIYAM frontend module builds independently:

```bash
cd /Users/shuv/Downloads/niyam_fe
npm install --legacy-peer-deps --ignore-scripts
npm run build
```

The openIMIS frontend assembly has been generated with NIYAM included in `src/modules.js`. Once the backend is running:

```bash
cd /Users/shuv/Downloads/openimis-fe_js
npm install --legacy-peer-deps
npm run start
```

The frontend proxies `/api` to `http://localhost:8000`, matching the backend runserver command above.

## Verification Completed

Backend:

```text
python manage.py check
System check identified no issues (0 silenced).
```

NIYAM engine:

```text
Ran 3 tests in 0.000s
OK
```

Frontend:

```text
niyam_fe npm run build
✓ built
```

Assembly config:

```text
openimis-fe_js/src/modules.js contains @openimis/fe-niyam
```

## Remaining Local Blocker

Docker is installed but the daemon is not running on this machine:

```text
failed to connect to the docker API at unix:///var/run/docker.sock
```

Until Docker Desktop is started, the official openIMIS database containers cannot be launched, migrations cannot be applied to the real database, and the backend/frontend cannot be opened against live data.
