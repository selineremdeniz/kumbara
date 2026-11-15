"""Hızlı plan: ekstre toplamı, birikim hesabı ve ülke profilleri."""

from datetime import date
from pathlib import Path

import pytest

from kumbara import portfoy as pf
from kumbara.hizli import birikim_hesapla, ekstre_ozetle
from kumbara.ulke import ULKELER, para, ulke_uygula

fpdf = pytest.importorskip("fpdf")
DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


@pytest.fixture(autouse=True)
def turkiyeye_don():
    yield
    pf.varsayilanlara_don()


def _pdf(yol, satirlar):
    pdf = fpdf.FPDF()
    pdf.add_page()
    if DEJAVU.exists():
        pdf.add_font("dv", fname=str(DEJAVU))
        pdf.set_font("dv", size=9)
    else:
        from kumbara.metin import _TR_ASCII
        pdf.set_font("Helvetica", size=9)
        satirlar = [s.translate(_TR_ASCII) for s in satirlar]
    for s in satirlar:
        pdf.cell(0, 5, s, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(yol))
    return yol


def test_ekstre_toplami_banka_rakami_kullanilir(tmp_path):
    yol = _pdf(tmp_path / "e.pdf", [
        "XYZ BANK KREDİ KARTI HESAP ÖZETİ", "Önceki Dönem Hesap Özeti Borcu : 5.000,00 TL",
        "Dönem Borcu : 3.245,90 TL", "Ödenmesi Gereken Asgari Tutar : 649,18 TL",
        "Kart Limiti : 50.000,00 TL",
        "12.10.2026 MIGROS ISTANBUL 1.245,90", "15.10.2026 ALLIANZ YASAM VE EMEKLILIK 2.000,00",
        "20.10.2026 ÖDEMENİZ İÇİN TEŞEKKÜRLER 5.000,00 +"])
    o = ekstre_ozetle(yol, referans=date(2026, 11, 14))
    assert o.banka_toplami == 3245.90 and o.banka_etiketi == "Dönem borcu"
    assert o.okunan_harcama == 3245.90 and o.harcama == 3245.90   # ödeme harcama sayılmadı
    assert o.bes == 2000.0 and not o.uyarilar


def test_toplam_yoksa_okunan_islemler_ve_uyari(tmp_path):
    yol = _pdf(tmp_path / "e.pdf", ["12.10.2026 MIGROS ISTANBUL 1.245,90", "13.10.2026 SHELL 500,00"])
    o = ekstre_ozetle(yol, referans=date(2026, 11, 14))
    assert o.banka_toplami is None and o.harcama == 1745.90 and o.uyarilar


def test_birikim_hesabi():
    b = birikim_hesapla(gelir=70_000, kart_harcama=50_000, kart_disi=0, bes=8_000, bes_birikim=True)
    assert b.yatirilabilir == 20_000 and b.toplam_birikim == 28_000 and b.oran == pytest.approx(0.4)
    b2 = birikim_hesapla(70_000, 50_000, 0, 8_000, bes_birikim=False)
    assert b2.toplam_birikim == 20_000


def test_ulke_profilleri_kurallar_ayni_adlar_degisir():
    ulke_uygula("US")
    assert "S&P 500" in pf.VARLIK_SINIFLARI["bist_hisse"].ad
    abd = pf.model_dagilim("uzun", "dengeli")
    getiri_abd, _ = pf.dagilim_getiri(abd)
    ulke_uygula("TR")
    assert pf.model_dagilim("uzun", "dengeli") == abd                 # kurallar aynı
    assert "BIST" in pf.VARLIK_SINIFLARI["bist_hisse"].ad
    assert pf.dagilim_getiri(abd)[0] != getiri_abd                    # varsayımlar farklı
    for kod in ULKELER:                                                # her ülke tam tanımlı
        ulke_uygula(kod)
        assert set(pf.VARLIK_SINIFLARI) == set(pf.VARSAYILAN_SINIFLAR)


def test_para_bicimi():
    assert para(12345.6, ULKELER["TR"]) == "12.346 ₺"
    assert para(12345.6, ULKELER["US"]) == "$12,346"
    assert para(12345.6, ULKELER["DE"], 2) == "12.345,60 €"
    assert para(12345.6, ULKELER["GB"]) == "£12,346"
