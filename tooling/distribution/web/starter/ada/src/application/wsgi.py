from application.runtime import create_worker_runtime
from atlanticus.web.hosting import WorkerApplication

application = WorkerApplication(create_worker_runtime)
