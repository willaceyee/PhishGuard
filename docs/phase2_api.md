# Phase 2 API Guide

All management endpoints use JSON. Except for health, bootstrap, and login, requests require this header:

```text
Authorization: Bearer <access_token>
```

## Database setup

1. Create a PostgreSQL database named `phishguard`.
2. Copy `backend/.env.example` to `backend/.env`.
3. Replace the example database password and secret keys.
4. From `backend`, run `flask --app run.py init-db`.

Automated tests use an isolated in-memory SQLite database and do not modify PostgreSQL.

## Authentication

### Create the first administrator

`POST /api/auth/bootstrap`

```json
{
  "name": "System Admin",
  "email": "admin@example.com",
  "password": "use-a-strong-password"
}
```

This endpoint stops accepting registrations after the first administrator exists.

### Log in

`POST /api/auth/login`

```json
{
  "email": "admin@example.com",
  "password": "use-a-strong-password"
}
```

The response contains a one-hour JWT access token. `GET /api/auth/me` returns the authenticated administrator.

### Change administrator password

`POST /api/auth/change-password`

This endpoint requires an administrator bearer token.

```json
{
  "current_password": "current-password",
  "new_password": "a-new-password-of-at-least-12-characters"
}
```

## Users

- `GET /api/users`
- `POST /api/users`
- `PATCH /api/users/<user_id>`
- `DELETE /api/users/<user_id>`

Create example:

```json
{
  "name": "Aisha Tan",
  "email": "aisha@example.com",
  "department": "Finance",
  "role": "employee"
}
```

## Email templates

- `GET /api/templates`
- `POST /api/templates`
- `PATCH /api/templates/<template_id>`
- `DELETE /api/templates/<template_id>`

Create example:

```json
{
  "template_name": "Password reset",
  "subject": "Password expiry warning",
  "body": "Review your account immediately.",
  "category": "credential"
}
```

Templates cannot be deleted while a campaign uses them.

## Campaigns

- `GET /api/campaigns`
- `POST /api/campaigns`
- `PATCH /api/campaigns/<campaign_id>`
- `DELETE /api/campaigns/<campaign_id>`

Create example:

```json
{
  "campaign_name": "August awareness exercise",
  "template_id": 1,
  "scheduled_date": "2026-08-25T09:00:00+08:00",
  "status": "draft"
}
```
