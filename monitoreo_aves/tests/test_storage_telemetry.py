from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import requests

from hardware.raspberry_pi.node import storage_telemetry as telemetry
from hardware.raspberry_pi.node.node_delivery import Target


def report(name):
    return dict(device_name=name, measured_at=datetime.now(timezone.utc).isoformat(),
                total_bytes=128_000_000_000, free_bytes=100_000_000_000,
                recordings_bytes=5_000_000_000, recordings_count=900)


def test_recordings_measurement_excludes_links_and_other_files(tmp_path):
    (tmp_path / 'first.wav').write_bytes(b'1234')
    (tmp_path / 'ignore.png').write_bytes(b'123456')
    nested = tmp_path / 'campaign'
    nested.mkdir()
    (nested / 'second.WAV').write_bytes(b'12')
    (nested / 'loop').symlink_to(tmp_path, target_is_directory=True)
    (tmp_path / 'link.wav').symlink_to(tmp_path / 'first.wav')
    assert telemetry.recordings_usage(tmp_path) == (6, 2)


def test_incomplete_measurement_is_unknown_not_zero(tmp_path):
    assert telemetry.recordings_usage(tmp_path / 'missing') == (None, None)
    (tmp_path / 'test.wav').touch()
    clock = iter([0, 3])
    assert telemetry.recordings_usage(tmp_path, clock=lambda: next(clock)) == (None, None)
    (tmp_path / 'test.wav').unlink()
    assert telemetry.recordings_usage(tmp_path) == (0, 0)


def test_report_reaches_second_server_when_first_is_offline_and_is_throttled(monkeypatch):
    targets = [Target('mac', 'http://100.92.197.59:8000', 'mac-token'),
               Target('windows', 'http://100.98.248.58:8000', 'win-token')]
    calls = []
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            assert self.trust_env is False
            assert kwargs['allow_redirects'] is False
            assert kwargs['timeout'] == (3, 3)
            calls.append(url)
            if url.startswith(targets[0].url):
                raise requests.ConnectionError('offline')
            return SimpleNamespace(status_code=200)
    monkeypatch.setattr(telemetry, '_last_report', None)
    monkeypatch.setattr(telemetry, 'enabled', lambda: True)
    monkeypatch.setenv('BIRDMONITOR_INGEST_TARGETS_FILE', 'unused')
    monkeypatch.setattr(telemetry, 'load_targets', lambda path: targets)
    monkeypatch.setattr(telemetry, 'collect_storage', lambda: report('birdmonitor'))
    monkeypatch.setattr(telemetry.requests, 'Session', Session)
    telemetry.report_storage(clock=lambda: 0)
    telemetry.report_storage(clock=lambda: 299)
    assert calls == [t.url + '/node/storage' for t in targets]
    telemetry.report_storage(clock=lambda: 300)
    assert len(calls) == 4


def test_latest_storage_survives_new_requests_and_older_reports_cannot_replace_it(client):
    name = 'storage-' + uuid4().hex
    client.post('/devices/', json={'name': name, 'location': 'test'}).raise_for_status()
    payload = report(name)
    assert client.post('/node/storage', json=payload).status_code == 200
    older = {**payload, 'measured_at': (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(), 'free_bytes': 1}
    assert client.post('/node/storage', json=older).status_code == 200
    response = client.get('/node/storage')
    assert response.headers['cache-control'] == 'no-store'
    stored = next(n for n in response.json()['nodes'] if n['device_name'] == name)
    assert stored['free_bytes'] == payload['free_bytes']
    assert stored['stale'] is False
    assert stored['measured_at'].endswith('+00:00')


def test_stale_and_unknown_recordings_are_explicit(client):
    name = 'storage-' + uuid4().hex
    client.post('/devices/', json={'name': name, 'location': 'test'})
    payload = {**report(name), 'measured_at': (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
               'recordings_bytes': None, 'recordings_count': None}
    assert client.post('/node/storage', json=payload).status_code == 200
    stored = next(n for n in client.get('/node/storage').json()['nodes'] if n['device_name'] == name)
    assert stored['stale'] is True
    assert stored['recordings_bytes'] is None


@pytest.mark.parametrize('change', [{'free_bytes': -1}, {'free_bytes': 2**63}, {'total_bytes': 1},
                                   {'recordings_count': None}, {'free_bytes': '100'},
                                   {'measured_at': '2026-01-01T00:00:00'},
                                   {'measured_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}])
def test_invalid_storage_is_rejected(client, change):
    assert client.post('/node/storage', json={**report('unknown'), **change}).status_code == 422


def test_storage_requires_authentication_and_ingest_token_cannot_read(client, monkeypatch):
    from backend.app.core.security import hash_node_token, hash_admin_password
    name = 'storage-' + uuid4().hex
    client.post('/devices/', json={'name': name, 'location': 'test'})
    monkeypatch.setenv('BIRDMONITOR_SECURITY_MODE', 'required')
    monkeypatch.setenv('BIRDMONITOR_ADMIN_USERNAME', 'admin')
    monkeypatch.setenv('BIRDMONITOR_ADMIN_PASSWORD_HASH', hash_admin_password('test-admin-password'))
    monkeypatch.setenv('BIRDMONITOR_SESSION_SECRET', 's' * 48)
    monkeypatch.setenv('BIRDMONITOR_NODE_TOKEN_HASH', hash_node_token('n' * 32))
    monkeypatch.setenv('BIRDMONITOR_INGEST_TOKEN_HASH', hash_node_token('i' * 32))
    client.cookies.clear()
    assert client.get('/node/storage').status_code == 401
    assert client.post('/node/storage', json=report(name)).status_code == 401
    for token in ('n' * 32, 'i' * 32):
        headers = {'Authorization': 'Bearer ' + token}
        assert client.post('/node/storage', json=report(name), headers=headers).status_code == 200
        assert client.get('/node/storage', headers=headers).status_code == 403
