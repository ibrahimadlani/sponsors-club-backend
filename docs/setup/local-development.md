# Local development setup

Follow these steps to run the Sponsors Club backend locally in a reproducible way.

## 1. Prerequisites
- **Python:** Version 3.11 (matches the Docker base image).
- **Database:** SQLite is bundled by default; no separate service is required.
- **System packages:** `libpq-dev`/PostgreSQL client libraries are only necessary when building the Docker image. For a pure virtual environment install, the standard Python toolchain suffices.

## 2. Clone and create a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.dev.txt
```
`requirements.dev.txt` installs both the production stack (`-r requirements.txt`) and the development extras such as pytest, pytest-django, pytest-cov, coverage, and Ruff.

## 3. Apply migrations
```bash
python manage.py migrate
```
This migrates the default SQLite database located at `db.sqlite3`. If you prefer a clean start, delete the file and re-run migrations.

## 4. (Optional) Create an admin user
```bash
python manage.py createsuperuser
```
Provide an email and password so you can access `/admin/` and authenticate against endpoints that require staff status.

## 5. Run the development server
```bash
python manage.py runserver 0.0.0.0:8000
```
The API becomes available at `http://127.0.0.1:8000/`. Interactive documentation will be served at `/api/docs/` and `/api/redoc/` when `drf-yasg` is installed (it ships with the default requirements file).

## 6. Container workflow (optional)
A production-like container image is defined in the `Dockerfile`. To build and run it locally:
```bash
docker build -t sponsors-club-backend .
docker run --rm -p 8000:8000 \
  -e DJANGO_SUPERUSER_EMAIL=admin@example.com \
  -e DJANGO_SUPERUSER_PASSWORD=Passw0rd! \
  sponsors-club-backend
```
The container entrypoint executes Gunicorn via `scripts/entrypoint.sh`. Run `docker run --rm sponsors-club-backend scripts/migrate.sh` (or invoke the script inside the container) if you need to apply migrations separately before starting the web process.

## 7. Useful environment variables
- `PORT`: overrides the Gunicorn bind port in containerized runs (defaults to `8000`).
- `DJANGO_SUPERUSER_EMAIL` and `DJANGO_SUPERUSER_PASSWORD`: consumed by `scripts/migrate.sh` to create or update a superuser automatically.

Keep `DEBUG=True` in `core/settings.py` for local development. For production, make sure to set appropriate environment overrides and secrets management before deploying.
