# Sponsors Club Frontend

This Next.js application provides a Tailwind CSS starter for building the Sponsors Club user interface.

## Configuration

Set `NEXT_PUBLIC_API_BASE_URL` to the base URL of the Sponsors Club API (defaults to `http://localhost:8000/api`).

```bash
export NEXT_PUBLIC_API_BASE_URL="https://api.sponsorsclub.com/api"
```

## Getting started

```bash
cd frontend
npm install
npm run dev
```

The development server runs on [http://localhost:3000](http://localhost:3000).

## Production-ready authentication flows

- `/login` authenticates users against `/api/users/login/` and persists the returned JWT pair in `localStorage`.
- `/register` lets agents and collaborators create accounts through `/api/users/register/` with client-side validation and rich error feedback.
