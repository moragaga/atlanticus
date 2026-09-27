# La instancia WSGI posterga la creación de Flask hasta post_worker_init.
from application.runtime import create_worker_runtime
from atlanticus.web.hosting import WorkerApplication

application = WorkerApplication(create_worker_runtime)
