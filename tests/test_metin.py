from datetime import date

import pytest

from kumbara.metin import isyeri_anahtari, sade, taksit_bul, tarih_cozumle, tutar_cozumle


@pytest.mark.parametrize("girdi,beklenen", [
    ("1.234,56", 1234.56), ("-1.234,56 TL", -1234.56), ("1,234.56", 1234.56), ("(123,45)", -123.45),
    ("123,45-", -123.45), ("+500,00", 500.0), ("₺2.500", 2500.0), ("12.000", 12000.0),
    ("12.5", 12.5), ("0,99", 0.99), (1500, 1500.0), ("", None), ("abc", None), (None, None),
])
def test_tutar(girdi, beklenen):
    assert tutar_cozumle(girdi) == beklenen


@pytest.mark.parametrize("girdi,beklenen", [
    ("12.11.2026", date(2026, 11, 12)), ("12/11/26", date(2026, 11, 12)),
    ("2026-11-12", date(2026, 11, 12)), ("12 Kasım 2026", date(2026, 11, 12)),
    ("1 Ağustos 2026", date(2026, 8, 1)), ("31.02.2026", None), ("", None),
])
def test_tarih(girdi, beklenen):
    assert tarih_cozumle(girdi) == beklenen


@pytest.mark.parametrize("girdi,beklenen", [
    ("TEKNOSA ISTANBUL TAKSİT 3/6", (3, 6)), ("THY 2/3 TAKSIT", (2, 3)),
    ("ABC MAGAZA 12/11 TAKSİT 4/9", (4, 9)), ("XYZ TKS 1/12", (1, 12)),
    ("MIGROS 12/11 ISTANBUL", None), ("TAKSİT 7/6", None), ("4. TAKSIT / 10 ARCELIK", (4, 10)),
])
def test_taksit(girdi, beklenen):
    assert taksit_bul(girdi) == beklenen


def test_sade_ve_isyeri():
    assert sade("  Şık  Çiçekçi ığdır ") == "SIK CICEKCI IGDIR"
    assert isyeri_anahtari("MIGROS TİCARET A.Ş. İSTANBUL") == isyeri_anahtari("MİGROS TIC AS ISTANBUL 2")
    assert (isyeri_anahtari("TEKNOSA İÇ VE DIŞ TİC. TAKSİT 2/6")
            == isyeri_anahtari("TEKNOSA İÇ VE DIŞ TİC. TAKSİT 3/6"))
