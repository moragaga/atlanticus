import logging

from flask import Flask

from atlanticus.web.observability import WebObservability


def test_observability_is_silent_for_successful_requests(caplog):
    logger = logging.getLogger('test.web.success')
    logger.handlers.clear()
    logger.propagate = True
    logger.setLevel(logging.WARNING)
    observability = WebObservability(application='test', logger=logger, json_output=False)
    app = Flask(__name__)
    observability.attach_flask(app)

    @app.get('/ok')
    def ok():
        return {'status': 'ok'}

    with caplog.at_level(logging.WARNING):
        response = app.test_client().get('/ok')

    assert response.status_code == 200
    assert caplog.records == []


def test_observability_reports_unhandled_request_failure(caplog):
    logger = logging.getLogger('test.web.error')
    logger.handlers.clear()
    logger.propagate = True
    logger.setLevel(logging.WARNING)
    observability = WebObservability(application='test', logger=logger, json_output=False)
    app = Flask(__name__)
    app.config['PROPAGATE_EXCEPTIONS'] = False
    observability.attach_flask(app)

    @app.get('/fail')
    def fail():
        raise RuntimeError('boom')

    with caplog.at_level(logging.ERROR):
        response = app.test_client().get('/fail')

    assert response.status_code == 500
    messages = [record.getMessage() for record in caplog.records]
    assert any('event=web.request.failed' in message for message in messages)
    assert any('RuntimeError: boom' in message for message in messages)
