# Parsers Platform Backend

FastAPI backend for the multi-user version of the parsers platform.

## What is included now

- user registration and login
- JWT access tokens
- roles: `user`, `admin`
- current user endpoint
- parser job records scoped by user
- Redis/Celery queue for parser jobs
- worker orchestration through the existing parsers hub API
- tariff plans, user subscriptions, and monthly usage limits
- invoices, payment webhook skeleton, and subscription activation
- in-app notifications for users
- admin audit log for important system actions
- Alembic migrations for backend tables

The first registered user becomes `admin`.

## Local run

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
BACKEND_DATABASE_URL="postgresql://parsers:parsers@localhost:5432/parsers" alembic upgrade head
BACKEND_AUTO_CREATE_TABLES=true uvicorn app.main:app --reload
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Main endpoints

- `GET /health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/users/me`
- `GET /api/v1/billing/plans`
- `GET /api/v1/billing/me`
- `POST /api/v1/billing/invoices`
- `GET /api/v1/billing/invoices`
- `GET /api/v1/billing/invoices/{invoice_id}`
- `POST /api/v1/billing/invoices/{invoice_id}/mock-pay`
- `POST /api/v1/billing/webhook`
- `POST /api/v1/billing/admin/plans`
- `GET /api/v1/billing/admin/plans`
- `PATCH /api/v1/billing/admin/plans/{plan_id}`
- `POST /api/v1/billing/admin/users/{user_id}/subscription`
- `GET /api/v1/billing/admin/invoices`
- `POST /api/v1/billing/admin/invoices/{invoice_id}/mark-paid`
- `GET /api/v1/notifications`
- `POST /api/v1/notifications/read-all`
- `POST /api/v1/notifications/{notification_id}/read`
- `GET /api/v1/parser-meta/config`
- `GET /api/v1/parser-meta/2gis/rubrics`
- `GET /api/v1/parser-meta/2gis/cities`
- `GET /api/v1/parser-meta/olx/categories`
- `GET /api/v1/admin/users`
- `GET /api/v1/admin/users/{user_id}`
- `PATCH /api/v1/admin/users/{user_id}`
- `GET /api/v1/admin/users/{user_id}/jobs`
- `GET /api/v1/admin/users/{user_id}/usage`
- `GET /api/v1/admin/audit-logs`
- `POST /api/v1/jobs`
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/results`
- `GET /api/v1/results/fields`
- `GET /api/v1/results/export?format=csv|json|xlsx`

## Docker services

The root `docker-compose.yml` now includes:

- `backend` - FastAPI API
- `backend_worker` - Celery worker
- `redis` - queue broker/result backend

When a user calls `POST /api/v1/jobs`, the API creates a `parser_jobs` record, enqueues a Celery task, and the worker starts the real parser through the existing `parsers_hub` HTTP API.

Before enqueueing, the backend checks the user's active subscription:

- allowed parser sources
- monthly job limit
- monthly reserved records limit

If a user does not have an active subscription, the backend automatically attaches the default `free` plan.

## Payments

The payment layer is provider-agnostic for now:

- `POST /api/v1/billing/invoices` creates an invoice for a selected plan
- `POST /api/v1/billing/invoices/{invoice_id}/mock-pay` marks the invoice paid for local testing
- `POST /api/v1/billing/webhook` accepts signed provider callbacks

Webhook signature header:

```text
X-Payment-Signature: hmac_sha256(raw_body, PAYMENT_WEBHOOK_SECRET)
```

When an invoice is paid, the backend automatically activates the selected subscription plan.

## Audit and notifications

Important actions are written to `audit_logs`:

- registration and login
- parser job creation, completion, cancellation, and failure
- invoice creation and payment callbacks
- admin changes to users, plans, and subscriptions

Users receive in-app notifications in `notifications`. The frontend can poll `GET /api/v1/notifications` to show unread counters and status messages in the cabinet.
