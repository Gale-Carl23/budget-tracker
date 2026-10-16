import os


# Render routes public HTTP traffic through its managed load balancer. Each
# Gunicorn worker handles requests locally; threads also cover I/O waits.
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = max(1, int(os.environ.get("WEB_CONCURRENCY", "2")))
worker_class = "gthread"
threads = max(1, int(os.environ.get("GUNICORN_THREADS", "2")))
timeout = max(30, int(os.environ.get("GUNICORN_TIMEOUT", "60")))
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
