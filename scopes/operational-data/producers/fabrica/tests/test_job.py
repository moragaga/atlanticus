from types import SimpleNamespace

from atlanticus.data_producers.fabrica import FabricaJob, FabricaProducerState
from atlanticus.state import AtomicStateStore


class _Context:
    def __init__(self):
        self.configuration = SimpleNamespace(environment=SimpleNamespace(is_local=True))
        self.iteration_has_work = False
        self.execution_facts = {}
        self.iteration_facts = {}

    def get_execution_fact(self, name):
        return self.execution_facts.get(name)

    def set_execution_fact(self, name, value):
        self.execution_facts[name] = value

    def set_iteration_fact(self, name, value):
        self.iteration_facts[name] = value


def test_empty_catalog_is_noop_without_storage(tmp_path) -> None:
    state = FabricaProducerState(store=AtomicStateStore(volume_path=tmp_path, application='fabrica-planes'))
    context = _Context()
    job = FabricaJob(materializers=(), producer_state=state, idle_seconds=5)
    job.run_iteration(context)
    assert context.iteration_facts['streams_planned'] == 0
    assert context.iteration_facts['partitions_changed'] == 0
    assert context.iteration_facts['outcome'] == 'skipped'
