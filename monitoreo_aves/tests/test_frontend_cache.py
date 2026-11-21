def test_frontend_se_revalida(client):
    for ruta in ("/", "/index.html", "/css/mobile.css", "/js/science.js"):
        r = client.get(ruta)
        assert r.status_code == 200, ruta
        assert r.headers["cache-control"] == "no-cache", ruta
    assert "cache-control" not in client.get("/health").headers
