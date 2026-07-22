import sys
from pathlib import Path


HARDWARE_DIR = Path(__file__).resolve().parents[1] / "hardware" / "raspberry_pi"
if str(HARDWARE_DIR) not in sys.path:
    sys.path.insert(0, str(HARDWARE_DIR))

import node_location


def test_parsea_coordenadas_validas_y_rechaza_valores_inseguros():
    assert node_location._parsearCoordenada("37.3891", "latitud", -90, 90) == 37.3891
    assert node_location._parsearCoordenada("texto", "latitud", -90, 90) is None
    assert node_location._parsearCoordenada("190", "longitud", -180, 180) is None
