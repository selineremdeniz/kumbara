from importlib import resources

import pandas as pd
import pytest

from kumbara.ekstre import oku
from kumbara.kategori import Kategorilendirici


@pytest.fixture(autouse=True)
def gecici_veri_dizini(tmp_path, monkeypatch):
    monkeypatch.setenv("KUMBARA_VERI_DIZINI", str(tmp_path / "kumbara"))


def _ornek(ad, hesap, tur):
    with resources.as_file(resources.files("kumbara.veri").joinpath(ad)) as yol:
        return oku(yol, hesap=hesap, tur=tur)


@pytest.fixture
def islemler() -> pd.DataFrame:
    df = pd.concat([_ornek("ornek_hesap.csv", "Vadesiz", "otomatik"),
                    _ornek("ornek_kart.csv", "Kart", "otomatik")], ignore_index=True)
    return Kategorilendirici.varsayilan().uygula(df)
