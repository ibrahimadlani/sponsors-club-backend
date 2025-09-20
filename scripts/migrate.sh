#!/bin/sh

# Fail fast if any command errors to avoid applying partial migrations.
set -e

# Run commands from the Django project root inside the container.
cd /app/

# Collect static files if the deployment requires it. Disabled by default to
# keep the script lean for environments that manage static assets separately.
# /py/bin/python manage.py collectstatic --noinput

# Generate any new migration files and apply outstanding migrations.
/py/bin/python manage.py makemigrations
/py/bin/python manage.py migrate --noinput

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
