def test_subida_archivos_guarda_wav_y_png_en_carpetas_configuradas(client, tmp_path, monkeypatch):
    from backend.app.features.uploads import routes as uploads

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
    from backend.app.features.uploads import routes as uploads

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


def test_failed_upload_preserves_existing_file(client, tmp_path, monkeypatch):
    from backend.app.features.uploads import routes as uploads

    monkeypatch.setattr(uploads, "SERVER_AUDIO_DIR", tmp_path)
    monkeypatch.setattr(uploads, "MAX_AUDIO_BYTES", 3)
    existing = tmp_path / "existing.wav"
    existing.write_bytes(b"original")
    response = client.post("/upload/", files={"audio": ("existing.wav", b"too-large", "audio/wav")})
    assert response.status_code == 413
    assert existing.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [existing]


def test_upload_is_not_visible_until_complete(tmp_path):
    import asyncio
    from backend.app.features.uploads.routes import guardar_upload_seguro

    destination = tmp_path / "record.wav"

    class Upload:
        filename = "record.wav"
        calls = 0
        closed = False

        async def read(self, size):
            assert not destination.exists()
            self.calls += 1
            return b"chunk" if self.calls <= 2 else b""

        async def close(self):
            self.closed = True

    upload = Upload()
    asyncio.run(guardar_upload_seguro(upload, tmp_path, {".wav"}, 100))
    assert destination.read_bytes() == b"chunkchunk"
    assert upload.closed
    assert list(tmp_path.iterdir()) == [destination]