# Sponsors Club Monorepo

<p align="center">
  <a href="https://github.com/your-github-org/sponsors-club-backend/actions/workflows/ci.yml?query=workflow%3ACI">
    <img src="https://github.com/your-github-org/sponsors-club-backend/actions/workflows/ci.yml/badge.svg?branch=main&job=build" alt="Statut du build" />
  </a>
  <a href="https://github.com/your-github-org/sponsors-club-backend/actions/workflows/ci.yml?query=workflow%3ACI">
    <img src="https://github.com/your-github-org/sponsors-club-backend/actions/workflows/ci.yml/badge.svg?branch=main&job=lint" alt="Statut du lint" />
  </a>
  <a href="https://github.com/your-github-org/sponsors-club-backend/actions/workflows/ci.yml?query=workflow%3ACI">
    <img src="https://github.com/your-github-org/sponsors-club-backend/actions/workflows/ci.yml/badge.svg?branch=main&job=tests" alt="Statut des tests" />
  </a>
  <a href="https://github.com/your-github-org/sponsors-club-backend/actions/workflows/ci.yml?query=workflow%3ACI">
    <img src="https://github.com/your-github-org/sponsors-club-backend/actions/workflows/ci.yml/badge.svg?branch=main&job=containerize" alt="Statut du packaging Docker" />
  </a>
</p>

> Remplacez `your-github-org` par votre organisation ou votre nom d'utilisateur GitHub si nécessaire.

This repository now hosts both the historical Django backend and a brand new Next.js + Tailwind frontend scaffold.

- [`backend/`](backend/README.md) contains the existing Django project.
- [`frontend/`](frontend/README.md) contains a JavaScript Next.js starter ready for styling with Tailwind CSS.

Use the provided `docker-compose.yml` to launch the backend together with a PostgreSQL database for local development.
