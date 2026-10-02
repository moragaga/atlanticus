from atlanticus.web.hosting import (
    close_gunicorn_worker,
    resolve_gunicorn_capacity,
    warmup_gunicorn_worker,
)

_capacity = resolve_gunicorn_capacity()
bind = "0.0.0.0:8000"
workers = _capacity.workers
threads = _capacity.threads
preload_app = False
post_worker_init = warmup_gunicorn_worker


def worker_exit(_server, worker):
    close_gunicorn_worker(worker)
