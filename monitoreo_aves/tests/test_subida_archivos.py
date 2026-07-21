def test_subida_archivos_guarda_wav_y_png_en_carpetas_configuradas(client, tmp_path, monkeypatch):
    from backend.app import uploads

    records_dir = tmp_path / "records"
    spectrograms_dir = tmp_path / "spectrograms"
    records_dir.mkdir()
    spectrograms_dir.mkdir()

    monkeypatch.setattr(uploads, "SERVER_AUDIO_DIR", records_dir)
    monkeypatch.setattr(uploads, "SPECTOGRAM_DIR", spectrograms_dir)

    response = client.post(
        "/upload/",
        files={
            "audio": ("record_test.wav", b"audio-test", "audio/wav"),
            "specto": ("record_test.png", b"png-test", "image/png"),
        },
    )

    assert response.status_code == 200
    assert response.json()["files"] == ["record_test.wav", "record_test.png"]
    assert (records_dir / "record_test.wav").read_bytes() == b"audio-test"
    assert (spectrograms_dir / "record_test.png").read_bytes() == b"png-test"


def test_subida_archivos_rechaza_extensiones_no_permitidas(client, tmp_path, monkeypatch):
    from backend.app import uploads

    records_dir = tmp_path / "records"
    spectrograms_dir = tmp_path / "spectrograms"
    records_dir.mkdir()
    spectrograms_dir.mkdir()

    monkeypatch.setattr(uploads, "SERVER_AUDIO_DIR", records_dir)
    monkeypatch.setattr(uploads, "SPECTOGRAM_DIR", spectrograms_dir)

    response = client.post(
        "/upload/",
        files={
            "audio": ("record_test.mp3", b"audio-test", "audio/mpeg"),
        },
    )

    assert response.status_code == 400
    assert not list(records_dir.iterdir())
    assert not list(spectrograms_dir.iterdir())