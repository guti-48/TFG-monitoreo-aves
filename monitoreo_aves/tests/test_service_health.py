import io
import json

import pytest

from scripts.verify_service import wait_for_backend


HEALTH = dict(status='ok', network_configured=True, security='required',
              security_configured=True, stream_security='required', stream_security_configured=True)


def test_health_waits_for_cold_start_and_preserves_configuration_checks():
    class Opener:
        calls = 0
        def open(self, url, timeout):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionRefusedError('arrancando')
            if self.calls == 2:
                return io.StringIO(json.dumps({**HEALTH, 'network_configured': False}))
            return io.StringIO(json.dumps(HEALTH))
    opener = Opener()
    clock = iter([0,1,1,2,2])
    assert wait_for_backend('http://127.0.0.1:8000/health',10,opener=opener,
                            clock=lambda: next(clock),sleep=lambda _: None) == HEALTH
    assert opener.calls == 3


def test_failed_health_reports_the_actual_connection_error():
    class Opener:
        def open(self, url, timeout):
            raise ConnectionRefusedError('conexion rechazada')
    clock = iter([0,20])
    with pytest.raises(RuntimeError, match='127.0.0.1:8000/health: conexion rechazada'):
        wait_for_backend('http://127.0.0.1:8000/health',10,opener=Opener(),clock=lambda: next(clock))
