# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| `main` branch | Yes |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

If you discover a security vulnerability, please report it by emailing:

**security@alphatrack.app**

Please include:
- A description of the vulnerability
- Steps to reproduce it
- The potential impact
- Any suggested mitigations if you have them

You will receive a response within 72 hours. We will work with you to understand the issue and coordinate a fix before public disclosure.

## Security Model

AlphaTrack is a **self-hosted** application. You are responsible for:

- Changing all default passwords (`POSTGRES_PASSWORD`, `REDIS_PASSWORD`) before exposing any port to a network
- Setting a strong, randomly generated `SECRET_KEY`
- Restricting network access to the PostgreSQL (5432) and Redis (6379) ports — these should never be publicly accessible
- Running the application behind a reverse proxy (nginx, Caddy) with TLS in production
- Keeping your API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.) secret and out of version control

## Known Limitations

- The pipeline dashboard (port 9000) has no authentication. It should not be exposed publicly.
- The Swagger UI (`/docs`) is disabled in `ENVIRONMENT=production` but enabled in development.
- JWT tokens are stored in `localStorage` on the frontend. This is standard for SPAs but means they are accessible to JavaScript running on the same origin.
