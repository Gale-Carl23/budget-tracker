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
3. Set the build command to `bash build.sh` and the start command to `python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`.
4. Add the following environment values in the Render service. Use the database's **Internal Database URL** for `DATABASE_URL`; use Render's **Generate** option for `DJANGO_SECRET_KEY`.

   - `DJANGO_DEBUG` = `False`
   - `DJANGO_SECRET_KEY` = generated secret
   - `DATABASE_URL` = internal URL from the PostgreSQL service
   - `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL` = credentials from your transactional email provider
   - `EMAIL_USE_TLS` = `True` (for providers using STARTTLS on port 587)
   - `OPENAI_API_KEY` = optional; leave unset until you want to enable the assistant

Render supplies the app hostname and HTTPS URL automatically, so Nibi fills `ALLOWED_HOSTS`, CSRF trusted origins, and Render's trusted HTTPS proxy setting for the default `onrender.com` address. If you later add a custom domain, add it to `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` in the service settings.

The free web service sleeps after 15 minutes without requests. Render's free web service also cannot send outbound SMTP, which this app needs for password resets; use a paid web service or add an HTTPS email API integration before relying on password recovery. The free PostgreSQL database expires after 30 days and has no backups, so do not store real financial records there. Review Render's current plan and database terms before creating services.

Required provider settings:

- `DJANGO_SECRET_KEY`: generate a unique random value for this deployment.
- `DJANGO_DEBUG=False`.
- `DJANGO_ALLOWED_HOSTS`: the exact host name(s) serving Nibi.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: the HTTPS origin(s), including scheme.
- `DATABASE_URL`: a managed PostgreSQL connection URL. Database passwords must be URL-encoded when they contain reserved URL characters.
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, and `DEFAULT_FROM_EMAIL`: a transactional SMTP service for password resets.
- `OPENAI_API_KEY`: optional; add it only as a server-side secret to enable live AI. It is deliberately blank in the production example.

Nibi enables HTTPS redirects, secure session and CSRF cookies, and HSTS in production. The default HSTS period is one hour; increase it to one year only after confirming HTTPS works correctly on the final domain. Do not enable HSTS subdomains or preload unless every affected domain is ready for HTTPS. Set `DJANGO_SECURE_PROXY_SSL_HEADER` only when the hosting provider’s trusted proxy sets and protects the configured header.

AI usage is capped per user at 10 requests per minute and 100 per day by default; response size is capped at 700 output tokens and provider requests have a 30-second timeout. These limits can be changed with `AI_REQUESTS_PER_MINUTE`, `AI_REQUESTS_PER_DAY`, and `OPENAI_MAX_OUTPUT_TOKENS`. Configure an additional provider-side project budget/alert for the API key.

## Release steps

Use a production WSGI server such as Gunicorn; never use `runserver` on the public internet. A typical Linux start command is `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`. Run these commands as part of the release process:

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
