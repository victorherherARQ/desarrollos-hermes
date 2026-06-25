"""Tests de integracion: pipeline completo + DB."""
import pytest
from datetime import date
from src.db.repository import SorteoRepository
from src.downloader.scraper import parsear_csv, cargar_en_db


@pytest.fixture
def repo(tmp_path):
    db_path = tmp_path / "test.db"
    return SorteoRepository(str(db_path))


class TestRepository:
    def test_init_creates_schema(self, repo):
        # Si llego aqui sin error, schema OK
        assert repo.count() == 0

    def test_insert_sorteo(self, repo):
        rid = repo.insert_sorteo(date(2024, 6, 21), 9, 16, 17, 29, 35, 3, 11)
        assert rid is not None
        assert repo.count() == 1

    def test_insert_duplicado_no_inserta(self, repo):
        repo.insert_sorteo(date(2024, 6, 21), 9, 16, 17, 29, 35, 3, 11)
        rid2 = repo.insert_sorteo(date(2024, 6, 21), 1, 2, 3, 4, 5, 6, 7)
        assert rid2 is None
        assert repo.count() == 1

    def test_get_all_ordenado_por_fecha(self, repo):
        repo.insert_sorteo(date(2024, 6, 21), 9, 16, 17, 29, 35, 3, 11)
        repo.insert_sorteo(date(2024, 6, 18), 1, 2, 3, 4, 5, 6, 7)
        all_data = repo.get_all()
        assert len(all_data) == 2
        assert all_data[0]["fecha"] < all_data[1]["fecha"]

    def test_freq_numeros(self, repo):
        repo.insert_sorteo(date(2024, 6, 21), 1, 2, 3, 4, 5, 1, 2)
        repo.insert_sorteo(date(2024, 6, 18), 1, 2, 3, 6, 7, 3, 4)
        freq = repo.get_freq_numeros()
        assert freq[1] == 2
        assert freq[2] == 2
        assert freq[3] == 2
        assert freq[4] == 1
        assert freq[5] == 1
        assert freq[6] == 1
        assert freq[7] == 1

    def test_train_test_split(self, repo):
        for year in [2019, 2020, 2021, 2022, 2023]:
            repo.insert_sorteo(date(year, 6, 15), 1, 2, 3, 4, 5, 1, 2)
        train, test = repo.get_train_test_split(2021)
        assert len(train) == 2  # 2019, 2020
        assert len(test) == 3   # 2021, 2022, 2023


class TestPipelineIntegration:
    """Tests que requieren el CSV real descargado."""

    def test_cargar_csv_real(self, repo):
        try:
            sorteos = parsear_csv("data/raw/results.csv")
        except FileNotFoundError:
            pytest.skip("CSV no descargado, skip")
        cargar_en_db(repo, sorteos)
        assert repo.count() >= 1900

    def test_csv_real_cubre_desde_2004(self, repo):
        try:
            sorteos = parsear_csv("data/raw/results.csv")
        except FileNotFoundError:
            pytest.skip("CSV no descargado, skip")
        cargar_en_db(repo, sorteos)
        mn, mx = repo.get_date_range()
        assert mn <= date(2004, 2, 13)
        assert mx >= date(2025, 1, 1)
