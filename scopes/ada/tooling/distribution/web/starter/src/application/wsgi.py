from atlanticus.web.hosting import WorkerApplication

from application.runtime import create_worker_runtime

application = WorkerApplication(create_worker_runtime)
