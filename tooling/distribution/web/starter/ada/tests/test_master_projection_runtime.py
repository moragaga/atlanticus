from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest


@pytest.fixture(scope='module')
def generated_starter(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = Path(__file__).resolve().parents[6]
    destination = tmp_path_factory.mktemp('master-projection-runtime') / 'ada'
    generated = subprocess.run(
        [sys.executable, '-I', str(root / 'tooling/distribution/web/generate_starter.py'),
         '--profile', 'ada', '--destination', str(destination)],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert generated.returncode == 0, generated.stdout + generated.stderr
    return destination


def _exercise_generated_runtime(starter: Path, source: str) -> None:
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(starter / 'src')
    result = subprocess.run(
        [sys.executable, '-c', dedent(source)],
        cwd=starter, env=environment, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_local_run_uses_the_same_master_aware_runtime_as_wsgi(generated_starter):
    _exercise_generated_runtime(generated_starter, '''
        from types import SimpleNamespace
        from application import runtime

        events = []
        application = object()
        worker = SimpleNamespace(
            application=application,
            close=lambda: events.append('closed'),
        )
        runtime.create_worker_runtime = lambda: worker
        runtime.run_web_application = lambda actual: events.append(('served', actual))
        runtime.run_application()
        assert events == [('served', application), 'closed']
    ''')


def test_local_run_closes_connections_after_server_error(generated_starter):
    _exercise_generated_runtime(generated_starter, '''
        from types import SimpleNamespace
        from application import runtime

        events = []
        worker = SimpleNamespace(application=object(), close=lambda: events.append('closed'))
        runtime.create_worker_runtime = lambda: worker

        def failed_server(_application):
            raise RuntimeError('test-stop')

        runtime.run_web_application = failed_server
        try:
            runtime.run_application()
        except RuntimeError as error:
            assert str(error) == 'test-stop'
        else:
            raise AssertionError('Expected the server to raise')
        assert events == ['closed']
    ''')
