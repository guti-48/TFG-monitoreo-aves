from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_mediamtx_uses_one_second_fmp4_hls_segments():
    config = (PROJECT_ROOT / "tools" / "mediamtx" / "mediamtx.yml").read_text(
        encoding="utf-8"
    )

    assert "hlsAlwaysRemux: true" in config
    assert "hlsVariant: fmp4" in config
    assert "hlsSegmentDuration: 1s" in config


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