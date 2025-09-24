FROM python:3.11.5-alpine3.18

LABEL maintainer="ibrahimadlani"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY ./requirements.txt /tmp/requirements.txt
WORKDIR /app
COPY . /app

RUN python -m venv /py \
    && /py/bin/pip install --upgrade pip \
    && apk add --update --no-cache postgresql-client \
    && apk add --update --no-cache --virtual .tmp-build-deps \
        build-base postgresql-dev musl-dev \
    && /py/bin/pip install -r /tmp/requirements.txt \
    && rm -rf /tmp \
    && apk del .tmp-build-deps \
    && adduser \
        --disabled-password \
        --no-create-home \
        django-user \
    && chmod +x /app/scripts/entrypoint.sh /app/scripts/migrate.sh \
    && mkdir -p /app/staticfiles \
    && chown -R django-user:django-user /app

ENV PATH="/py/bin:$PATH"

USER django-user

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/app/scripts/entrypoint.sh"]
