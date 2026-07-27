import node_location


def test_parsea_coordenadas_validas_y_rechaza_valores_inseguros():
    assert node_location._parsearCoordenada("37.3891", "latitud", -90, 90) == 37.3891
    assert node_location._parsearCoordenada("texto", "latitud", -90, 90) is None
    assert node_location._parsearCoordenada("190", "longitud", -180, 180) is None


def test_ubicacion_manual_conserva_procedencia(monkeypatch):
    monkeypatch.setattr(node_location, "NODE_LOCATION", "Parque")
    monkeypatch.setattr(node_location, "NODE_LAT", "37.3891")
    monkeypatch.setattr(node_location, "NODE_LON", "-5.9845")

    location = node_location.obtenerUbicacionNodo()

    assert location == {
        "location": "Parque",
        "lat": 37.3891,
        "lon": -5.9845,
        "source": "manual",
    }


def test_ubicacion_manual_no_envia_un_par_incompleto(monkeypatch):
    monkeypatch.setattr(node_location, "NODE_LOCATION", "Parque")
    monkeypatch.setattr(node_location, "NODE_LAT", "37.3891")
    monkeypatch.setattr(node_location, "NODE_LON", "")

    location = node_location.obtenerUbicacionNodo()

    assert location["lat"] is None
    assert location["lon"] is None