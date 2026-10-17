# Nibi

Nibi is a website-first personal finance tracker built with Django, server-rendered HTML, and PostgreSQL in production. It supports accounts, transactions, budgets, savings goals, recurring plans, debt tracking, reports, CSV export, change history, and an optional AI assistant. The assistant runs in Python on the server. Every proposed ledger entry requires confirmation.

## Run locally

1. Use Python 3.14, create and activate a virtual environment, then install the pinned dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env`. Keep `.env` private; it is ignored by Git. The OpenAI key is optional for local finance features.
3. Initialize the local SQLite database and run the site:

   ```powershell
   python manage.py migrate
   python manage.py runserver
   ```

4. Visit `http://127.0.0.1:8000/` and create an account. Create an admin account only if you need Django admin access.

## Production configuration

Production configuration is intentionally strict. With `DJANGO_DEBUG=False`, Nibi requires a non-development secret key, an allowed host supplied by the hosting provider or configured explicitly, and a PostgreSQL `DATABASE_URL`; it rejects SQLite and the development server defaults. SMTP settings are required so users can recover their passwords. Start from `.env.production.example`, replace every example value, and enter secrets in the hosting provider’s secret manager rather than committing an environment file.

## Deploy to Render

The repository is prepared for Render's Python web service. Render assigns a free `onrender.com` subdomain and HTTPS certificate; the app reads Render's assigned hostname and URL automatically. You do not need to buy a domain to get started.

1. Push the project to GitHub, then in Render choose **New > PostgreSQL**. Pick a region and a plan that fits your use. For real finance records, use a database plan with ongoing storage and backups; Render's free PostgreSQL databases expire after 30 days.
2. Create a **Web Service** from `Gale-Carl23/budget-tracker`, branch `main`, runtime **Python 3**. The repository root is the service root.
3. Set the build command to `bash build.sh`. On a paid Render web service, set **Pre-Deploy Command** to `python manage.py migrate --noinput` and **Start Command** to `gunicorn --config gunicorn.conf.py config.wsgi:application`. If Pre-Deploy Command is unavailable on your plan, keep the migration in Start Command: `python manage.py migrate --noinput && gunicorn --config gunicorn.conf.py config.wsgi:application`.
4. In Render's **Health Check Path**, set `/healthz/` so unhealthy app processes are detected and restarted.
5. Add the following environment values in the Render service. Use the database's **Internal Database URL** for `DATABASE_URL`; use Render's **Generate** option for `DJANGO_SECRET_KEY`.

   - `DJANGO_DEBUG` = `False`
   - `DJANGO_SECRET_KEY` = generated secret
   - `DATABASE_URL` = internal URL from the PostgreSQL service
   - `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL` = credentials from your transactional email provider
   - `EMAIL_USE_TLS` = `True` (for providers using STARTTLS on port 587)
   - `OPENAI_API_KEY` = optional; leave unset until you want to enable the assistant
   - `SENTRY_DSN` = optional; set this to the DSN for your Sentry Python/Django project to send privacy-filtered error events
   - `SENTRY_ENVIRONMENT` = `production`

Render supplies the app hostname and HTTPS URL automatically, so Nibi fills `ALLOWED_HOSTS`, CSRF trusted origins, and Render's trusted HTTPS proxy setting for the default `onrender.com` address. If you later add a custom domain, add it to `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` in the service settings.

The free web service sleeps after 15 minutes without requests. Render's free web service also cannot send outbound SMTP, which this app needs for password resets; use a paid web service or add an HTTPS email API integration before relying on password recovery. The free PostgreSQL database expires after 30 days and has no backups, so do not store real financial records there. Review Render's current plan and database terms before creating services.

For automatic bill emails, create a Render **Cron Job** from the same repository and branch. Use `bash build.sh` as its build command, `python manage.py send_bill_reminders` as its command, and schedule it daily at `0 0 * * *` UTC (08:00 in the app's default Asia/Shanghai timezone). Add the same `DATABASE_URL`, `DJANGO_SECRET_KEY`, and SMTP environment values used by the web service. Run `python manage.py send_bill_reminders --dry-run` as a one-off job first to preview the reminders. The cron job must use the same PostgreSQL database as the website; check current Render plan pricing before creating it.

## Automated backups and restore checks

The `.github/workflows/postgres-backup.yml` workflow runs daily and on demand. It exports PostgreSQL in custom format, uploads it to S3 with server-side AES-256 encryption, restores it into a short-lived PostgreSQL container, and checks that the application tables can be queried. Configure the repository in GitHub before relying on the workflow:

- Add GitHub Actions secrets `RENDER_DATABASE_URL` (Render's external PostgreSQL URL), `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY`.
- Add repository variables `AWS_REGION` and `BACKUP_S3_BUCKET`; optionally set `POSTGRES_MAJOR` to match the Render database version (default `18`).
- Use a private S3 bucket with Block Public Access enabled. Give the backup identity only the S3 permissions it needs, enable bucket versioning, and add a lifecycle rule for your chosen retention period. The workflow sends a database copy through a temporary GitHub-hosted runner and stores a copy in your AWS account.
- After adding the settings, run the workflow once from GitHub's **Actions** tab and confirm the backup object exists and the restore-check job succeeds. Scheduled runs use UTC at 00:17.

Paid Render Postgres plans also include Render-managed point-in-time recovery. It restores to a separate database instance so you can inspect it before switching services. The recovery window depends on the Render workspace plan; review Render's current [backup and recovery documentation](https://render.com/docs/postgresql-backups).

## Error monitoring and migrations

The application exposes `/healthz/` for Render's service health checks and writes application/runtime errors to standard logs. For searchable exception reports and alerts, create a Sentry Python/Django project and set its DSN as the Render `SENTRY_DSN` secret. The optional integration disables request-body collection, user identifiers, URL/query details, and local-variable capture to avoid sending financial form contents to monitoring. Configure an alert rule in Sentry to email you when a new issue occurs. Without a `SENTRY_DSN`, events stay in Render logs.

Run `python manage.py migrate --noinput` once per deployment in Render's **Pre-Deploy Command** when that setting is available. Render documents pre-deploy commands as the recommended place for migrations; it is available for paid web services. On plans without it, the existing start command still runs migrations before Gunicorn starts. Keep backups available before schema changes and inspect deploy logs after applying migrations.

Render already provides the public load balancer for web services. To handle more simultaneous traffic, start with the service's **Scale** setting and increase its instance count; each instance runs two Gunicorn workers with two I/O threads by default. Set `WEB_CONCURRENCY` and `GUNICORN_THREADS` only after checking CPU and memory use. Manual multiple-instance scaling and autoscaling plan availability depend on the current Render workspace and service plan; autoscaling requires a Pro workspace. Additional instances and larger plans can incur charges. The app uses persistent PostgreSQL connections (`DB_CONN_MAX_AGE=60` by default); keep total web workers/threads and other app connections below the database's connection limit. Render Postgres connection pooling, when enabled on a supported paid database, requires changing `DATABASE_URL` to its pool URL in the Render dashboard.

Required provider settings:

- `DJANGO_SECRET_KEY`: generate a unique random value for this deployment.
- `DJANGO_DEBUG=False`.
- `DJANGO_ALLOWED_HOSTS`: the exact host name(s) serving Nibi.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: the HTTPS origin(s), including scheme.
- `DATABASE_URL`: a managed PostgreSQL connection URL. Database passwords must be URL-encoded when they contain reserved URL characters.
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, and `DEFAULT_FROM_EMAIL`: a transactional SMTP service for password resets.
- `OPENAI_API_KEY`: optional; add it only as a server-side secret to enable live AI. It is deliberately blank in the production example.
- `LOGIN_RATE_LIMIT_ATTEMPTS` and `LOGIN_RATE_LIMIT_WINDOW_SECONDS`: optional; defaults are 8 failed attempts within 15 minutes for a hashed username/client-IP pair. The shared throttle records contain no raw username or IP address.

New signups receive a signed email-verification link that expires after 24 hours. SMTP must be working for signup verification, password resets, and bill reminder emails. Existing accounts are treated as verified during this upgrade. Passwords must be at least 12 characters for new signups and password changes.

Nibi enables HTTPS redirects, secure session and CSRF cookies, and HSTS in production. The default HSTS period is one hour; increase it to one year only after confirming HTTPS works correctly on the final domain. Do not enable HSTS subdomains or preload unless every affected domain is ready for HTTPS. Set `DJANGO_SECURE_PROXY_SSL_HEADER` only when the hosting provider’s trusted proxy sets and protects the configured header.

Sessions expire after one hour of inactivity, are refreshed as the user makes requests, and end when the browser closes. Change the duration with `SESSION_COOKIE_AGE` (seconds). Session and CSRF cookies are HTTP-only where applicable and use `SameSite=Lax`; Django's CSRF middleware remains enabled, and all data-changing browser forms include CSRF tokens and submit with POST. User-owned objects are also scoped in form querysets and checked server-side, so changing a submitted account or category ID cannot select another user's data. Requests with form bodies larger than 2.5 MiB are rejected by default; adjust `DATA_UPLOAD_MAX_MEMORY_SIZE` only if the app later needs larger submissions.

AI usage is capped per user at 10 requests per minute and 100 per day by default; response size is capped at 700 output tokens and provider requests have a 30-second timeout. These limits can be changed with `AI_REQUESTS_PER_MINUTE`, `AI_REQUESTS_PER_DAY`, and `OPENAI_MAX_OUTPUT_TOKENS`. Configure an additional provider-side project budget/alert for the API key.

## Release steps

Use a production WSGI server such as Gunicorn; never use `runserver` on the public internet. The checked-in Gunicorn configuration uses a small threaded worker pool and recycles workers periodically. Run these commands as part of the release process:

```sh
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
```

Serve collected static files through the host or a static-file service. Configure encrypted database backups and verify a restore before onboarding real users. Add host-level monitoring and alerting, and avoid request-body logging on assistant routes. Pin the Python runtime and install from `requirements.lock` for repeatable builds.

## Assistant privacy and behavior

When a user sends an assistant message, Nibi sends the current message, up to ten recent chat messages, account names and types, up to one hundred current-month transactions, active budgets, and preferences the user chose to remember to the configured AI provider. The provider’s privacy and retention terms apply. Nibi keeps conversation history in the user’s account until they delete it. Users can remove chat history and saved preferences, export transactions, and permanently delete their account and associated application records. Deleting chat history does not delete confirmed ledger entries.

The assistant does not continuously train a shared model on users’ finances. It can use only account-specific preferences the user explicitly chooses to save. It never records a proposed transaction without the user’s confirmation.

## Before a public launch

This project now has production-oriented configuration and privacy controls, but deploying a finance app still requires a final security review, domain-specific settings, a privacy/terms review for the intended markets, a tested backup restore, and verification in the selected hosting environment. The app does not connect to banks or move money.
