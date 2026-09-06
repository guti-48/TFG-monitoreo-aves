from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_mediamtx_uses_one_second_fmp4_hls_segments():
    config = (
        PROJECT_ROOT
        / "tools"
        / "mediamtx"
        / "mediamtx.secure.yml"
    ).read_text(encoding="utf-8")

    assert "hlsAlwaysRemux: true" in config
    assert "hlsVariant: fmp4" in config
    assert "hlsSegmentDuration: 1s" in config
    assert "hlsAddress: 127.0.0.1:8888" in config
    assert "authMethod: http" in config
    assert "rtspTransports: [tcp]" in config
    assert "rtmp: false" in config
    assert "webrtc: false" in config
    assert "srt: false" in config
    assert "moq: false" in config


def test_embedded_player_limits_latency_and_recovers_live_edge():
    dashboard = (PROJECT_ROOT / "frontend" / "js" / "dashboard.js").read_text(
        encoding="utf-8"
    )

    assert "liveSyncDurationCount: LIVE_HLS_TARGET_SEGMENTS" in dashboard
    assert "liveMaxLatencyDurationCount: LIVE_HLS_MAX_SEGMENTS" in dashboard
    assert "maxLiveSyncPlaybackRate: 1.25" in dashboard
    assert "moveLivePlayerToEdge(audio, true)" in dashboard
    assert "visibilitychange" in dashboard


def test_embedded_player_has_a_local_hls_library_fallback():
    dashboard = (PROJECT_ROOT / "frontend" / "js" / "dashboard.js").read_text(
        encoding="utf-8"
    )

    assert "function ensureHlsLibrary()" in dashboard
    assert "/hls.min.js" in dashboard


def test_dashboard_oculta_la_credencial_rtsp_pero_permite_copiarla():
    dashboard = (PROJECT_ROOT / "frontend" / "js" / "dashboard.js").read_text(
        encoding="utf-8"
    )

    assert "function maskRtspCredential(rawUrl)" in dashboard
    assert "rtspLabel.textContent = maskRtspCredential(rtspUrl)" in dashboard
    assert "copyLiveStreamUrl('rtsp')" in dashboard


def test_dashboard_no_depende_de_imagenes_locales_ignoradas():
    dashboard = (PROJECT_ROOT / "frontend" / "js" / "dashboard.js").read_text(
        encoding="utf-8"
    )

    assert "human.png" not in dashboard
    assert "ruido_amb.png" not in dashboard
    assert (PROJECT_ROOT / "frontend" / "assets" / "noise-placeholder.svg").is_file()


def test_dependencias_javascript_del_html_tienen_version():
    html = (PROJECT_ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    assert "npm/chart.js@4.4.9/" in html
    assert 'npm/chart.js\"></script>' not in html
