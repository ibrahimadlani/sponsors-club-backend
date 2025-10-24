#!/bin/sh

# Fail fast if any command errors to avoid applying partial migrations.
set -e

# Run commands from the Django project root inside the container.
cd /app/

# Ensure the database is available before running migrations.
/py/bin/python manage.py wait_for_db

# Generate any new migration files and apply outstanding migrations.
/py/bin/python manage.py makemigrations
/py/bin/python manage.py migrate --noinput

# Ensure static assets are available for WhiteNoise/Gunicorn by collecting them
# into STATIC_ROOT on every container boot. This is idempotent and keeps admin
# and API docs assets accessible when running inside Docker.
/py/bin/python manage.py collectstatic --noinput

# Optionally create or update a superuser using environment-provided
# credentials. This block is idempotent and safe to run multiple times.
/py/bin/python manage.py shell <<'PYTHON'
from django.contrib.auth import get_user_model
import os

User = get_user_model()
email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
first_name = "Admin"
last_name = "User"

if email and password:
    if not User.objects.filter(email=email).exists():
        User.objects.create_superuser(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        print("Superuser created.")
    else:
        user = User.objects.get(email=email)
        user.set_password(password)
        user.first_name = first_name
        user.last_name = last_name
        user.save()
        print("Superuser already exists. Updating password.")
else:
    print("DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD must be set to create a superuser.")
PYTHON
