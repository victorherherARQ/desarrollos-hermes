"""Tests para el validador de sorteos."""
from datetime import date
import pytest
from src.downloader.sources import validar_sorteo, ValidationError


class TestValidarSorteo:
    def test_sorteo_valido_basico(self):
        s = validar_sorteo(date(2024, 1, 1), 1, 2, 3, 4, 5, 1, 2)
        assert s["n1"] == 1
        assert s["n5"] == 5

    def test_sorteo_valido_desordenado_se_normaliza(self):
        s = validar_sorteo(date(2024, 1, 1), 50, 49, 48, 47, 46, 12, 11)
        assert s["n1"] == 46
        assert s["n5"] == 50
        assert s["e1"] == 11
        assert s["e2"] == 12

    def test_rechaza_numero_fuera_de_rango(self):
        with pytest.raises(ValidationError, match="fuera de rango"):
            validar_sorteo(date(2024, 1, 1), 0, 2, 3, 4, 5, 1, 2)

    def test_rechaza_numero_mayor_50(self):
        with pytest.raises(ValidationError, match="fuera de rango"):
            validar_sorteo(date(2024, 1, 1), 51, 2, 3, 4, 5, 1, 2)

    def test_rechaza_estrella_fuera_de_rango(self):
        with pytest.raises(ValidationError, match="Estrella fuera de rango"):
            validar_sorteo(date(2024, 1, 1), 1, 2, 3, 4, 5, 0, 2)

    def test_rechaza_estrella_mayor_12(self):
        with pytest.raises(ValidationError, match="Estrella fuera de rango"):
            validar_sorteo(date(2024, 1, 1), 1, 2, 3, 4, 5, 1, 13)

    def test_rechaza_numeros_repetidos(self):
        with pytest.raises(ValidationError, match="Numeros repetidos"):
            validar_sorteo(date(2024, 1, 1), 5, 5, 3, 4, 5, 1, 2)

    def test_rechaza_estrellas_repetidas(self):
        with pytest.raises(ValidationError, match="Estrellas repetidas"):
            validar_sorteo(date(2024, 1, 1), 1, 2, 3, 4, 5, 3, 3)

    def test_rechaza_fecha_anterior_a_inicio(self):
        with pytest.raises(ValidationError, match="anterior al inicio"):
            validar_sorteo(date(2004, 2, 12), 1, 2, 3, 4, 5, 1, 2)

    def test_rechaza_fecha_futura(self):
        with pytest.raises(ValidationError, match="futura"):
            validar_sorteo(date(2030, 1, 1), 1, 2, 3, 4, 5, 1, 2)

    def test_acepta_fecha_2004_02_13_primer_sorteo(self):
        s = validar_sorteo(date(2004, 2, 13), 16, 29, 32, 36, 41, 7, 9)
        assert s["fecha"] == "2004-02-13"
        assert s["n1"] == 16

    def test_acepta_sorteo_real_2024(self):
        # Sorteo real del 2024-06-21: 9,16,17,29,35 + 3,11
        s = validar_sorteo(date(2024, 6, 21), 9, 16, 17, 29, 35, 3, 11)
        assert s["n5"] == 35
        assert s["e2"] == 11

    def test_rechaza_tipo_incorrecto(self):
        with pytest.raises(ValidationError):
            validar_sorteo("2024-01-01", "1", 2, 3, 4, 5, 1, 2)

    def test_rechaza_4_numeros_distintos(self):
        # 5 nums pero hay repetido (4 distintos) -> debe rechazar
        with pytest.raises(ValidationError, match="Numeros repetidos"):
            validar_sorteo(date(2024, 1, 1), 1, 2, 3, 4, 4, 1, 2)

    def test_acepta_input_como_string(self):
        s = validar_sorteo("2024-06-21", 9, 16, 17, 29, 35, 3, 11)
        assert s["fecha"] == "2024-06-21"
