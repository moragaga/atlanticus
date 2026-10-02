# La instancia WSGI posterga la creación de Flask hasta post_worker_init.
from atlanticus.web.hosting import WorkerApplication

from application.runtime import create_worker_runtime

application = WorkerApplication(create_worker_runtime)
