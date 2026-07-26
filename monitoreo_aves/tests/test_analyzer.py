import analyzer
import node_config


def test_birdnet_usa_ubicacion_del_nodo_y_umbral_mas_bajo(monkeypatch):
    captured = {}

    class FakeAnalyzer:
        model_name = "BirdNET-Analyzer"
        version = "2.4"
        model_path = "/models/BirdNET_GLOBAL_6K_V2.4_Model_FP32.tflite"

        def __init__(self, version):
            captured["requested_version"] = version

    class FakeRecording:
        def __init__(self, engine, audio_path, **kwargs):
            captured.update(engine=engine, audio_path=audio_path, kwargs=kwargs)
            self.detections = []

        def analyze(self):
            captured["analyzed"] = True

    monkeypatch.setattr(analyzer, "Analyzer", FakeAnalyzer)
    monkeypatch.setattr(analyzer, "Recording", FakeRecording)

    brain = analyzer.BirdAnalyzer(lat=37.3891, lon=-5.9845)
    assert brain.predict("sample.wav") == []

    assert captured["requested_version"] == node_config.BIRDNET_MODEL_VERSION
    assert captured["kwargs"]["lat"] == 37.3891
    assert captured["kwargs"]["lon"] == -5.9845
    assert captured["kwargs"]["min_conf"] == min(
        node_config.UMBRAL_AVES,
        node_config.UMBRAL_HUMANOS,
        node_config.UMBRAL_MOTORES,
    )
    assert captured["analyzed"] is True