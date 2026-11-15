from datetime import date
from importlib import resources

import pytest

from kumbara.depo import Depo
from kumbara.portfoy import Hedef, birikimi_dagit
from kumbara.varlik import (
    Fiyatlayici,
    Varlik,
    csv_oku,
    degerle,
    dengeleyerek_dagit,
    fon_sinifi,
    hedeflere_uygula,
    ozet,
    planlara_dengeleme_uygula,
)

FIYAT = {("fon", "AFT"): (2.0, "AK PORTFÖY YENİ TEKNOLOJİLER YABANCI HİSSE SENEDİ FONU"),
         ("fon", "PPF"): (1.5, "ÖRNEK PORTFÖY PARA PİYASASI (TL) FONU"),
         ("altin", "gram"): (6000.0, "Gram altın"), ("altin", "ceyrek"): (10000.0, "Çeyrek"),
         ("altin", "22ayar"): (5496.0, "22 ayar"), ("doviz", "USD"): (40.0, "USD"),
         ("hisse", "THYAO"): (300.0, "THYAO")}


def test_turler_ve_altin_kodlari():
    assert Varlik("ALTIN", "Çeyrek Altın", 2).kod == "ceyrek"
    assert Varlik("altin", "22 ayar", 10).kod == "22ayar"
    with pytest.raises(ValueError):
        Varlik("kripto", "BTC", 1)
    with pytest.raises(ValueError):
        Varlik("altin", "reşat", 1)


def test_fon_siniflari():
    assert fon_sinifi("AK PORTFÖY YENİ TEKNOLOJİLER YABANCI HİSSE SENEDİ FONU") == "yabanci_hisse"
    assert fon_sinifi("ÖRNEK PORTFÖY PARA PİYASASI (TL) FONU") == "ppf"
    assert fon_sinifi("ÖRNEK ALTIN KATILIM FONU") == "altin"
    assert fon_sinifi("ÖRNEK BIST 30 HİSSE SENEDİ FONU") == "bist_hisse"
    assert fon_sinifi("ÖRNEK DEĞİŞKEN FON") == "diger"


def test_degerleme_ve_ozet():
    varliklar = [Varlik("fon", "AFT", 1000, maliyet=1500, hedef="Ev"),
                 Varlik("altin", "ceyrek", 3, kurum="Ev"), Varlik("nakit", "Mevduat", 50_000, hedef="Acil"),
                 Varlik("diger", "BES", 1, deger_elle=20_000), Varlik("fon", "YOK", 5)]
    d = degerle(varliklar, Fiyatlayici(sabit={**FIYAT, ("fon", "YOK"): (None, "bulunamadı")}))
    assert d.set_index("kod").loc["AFT", "deger"] == 2000 and d.set_index("kod").loc["AFT", "kar"] == 500
    o = ozet(d)
    assert o["toplam"] == 2000 + 30_000 + 50_000 + 20_000 and o["fiyatlanamayan"] == 1
    assert o["sinif"] == {"yabanci_hisse": 2000, "altin": 30_000, "ppf": 50_000, "diger": 20_000}


def test_dengeleyerek_dagit_eksige_oncelik():
    # Model %50 altın / %50 hisse; elde 10.000 altın var, 4.000 katkı -> hepsi hisseye
    assert dengeleyerek_dagit(4_000, {"altin": 10_000}, {"altin": 50, "bist_hisse": 50}) == {
        "altin": 0.0, "bist_hisse": 4_000.0}
    # Eksikler kapanınca artan katkı ağırlıkla paylaşılır
    r = dengeleyerek_dagit(10_000, {"altin": 1_000, "bist_hisse": 0}, {"altin": 50, "bist_hisse": 50})
    assert r == {"altin": 4_500.0, "bist_hisse": 5_500.0} and sum(r.values()) == 10_000


def test_varlik_hedefe_baglanir_ve_katki_dengelenir():
    bugun = date(2026, 11, 12)
    hedef = Hedef("Ev", 2_000_000, date(2033, 1, 1), mevcut=0, oncelik=1, risk="dengeli")
    d = degerle([Varlik("altin", "gram", 50, hedef="Ev")], Fiyatlayici(sabit=FIYAT))  # 300.000 altın
    [h] = hedeflere_uygula([hedef], d)
    assert h.mevcut == 300_000
    [p] = birikimi_dagit([h], aylik_birikim=20_000, bugun=bugun)
    planlara_dengeleme_uygula([p], d)
    assert p.katki_dagilimi["altin"] == 0.0             # altın zaten fazla
    assert sum(p.katki_dagilimi.values()) == pytest.approx(20_000, abs=0.1)
    assert p.mevcut_dagilim == {"altin": 300_000}


def test_depo_ve_gecmis(tmp_path):
    depo = Depo(tmp_path / "k.db")
    i = depo.varlik_kaydet(Varlik("altin", "gram", 10, kurum="Ev"))
    v = depo.varliklar()[0]
    assert v.id == i and v.kod == "gram"
    v.miktar = 12
    depo.varlik_kaydet(v)
    assert depo.varliklar()[0].miktar == 12 and len(depo.varliklar()) == 1
    depo.varlik_degeri_kaydet("2026-11-01", {"toplam": 100, "maliyet": 80, "sinif": {}})
    depo.varlik_degeri_kaydet("2026-11-12", {"toplam": 130, "maliyet": 90, "sinif": {}})
    depo.varlik_degeri_kaydet("2026-11-12", {"toplam": 140, "maliyet": 90, "sinif": {}})  # aynı gün
    g = depo.varlik_gecmisi()
    assert g["toplam"].tolist() == [100, 140]
    assert depo.varlik_sil(i) == 1


def test_sablon_csv_okunur():
    with resources.as_file(resources.files("kumbara.veri").joinpath("varlik_sablonu.csv")) as yol:
        varliklar = csv_oku(yol)
    assert len(varliklar) == 9
    bes = next(v for v in varliklar if v.tur == "diger")
    assert bes.deger_elle == 85_000 and bes.hedef == "Ev / emeklilik"


def test_cli_portfoy_varlikli_hedef(tmp_path, monkeypatch):
    """Hedefte bazı sınıflarda hiç varlık yokken çıktı üretilebilmeli (çevrimdışı)."""
    from typer.testing import CliRunner

    from kumbara.cli import app
    monkeypatch.setenv("KUMBARA_VERI_DIZINI", str(tmp_path))
    depo = Depo()
    depo.hedef_kaydet(Hedef("Ev", 1_000_000, date(2032, 1, 1), risk="dengeli"))
    depo.varlik_kaydet(Varlik("nakit", "Mevduat", 50_000, hedef="Ev"))
    sonuc = CliRunner().invoke(app, ["portfoy", "--birikim", "10000", "--cevrimdisi"])
    assert sonuc.exit_code == 0, sonuc.output
    assert "Bu hedefe bağlı varlıklar" in sonuc.output


def test_is_parcacigi_basina_baglanti(tmp_path, monkeypatch):
    """Panelde eşzamanlı yeniden çalıştırmalar aynı bağlantıyı paylaşmamalı."""
    import sqlite3
    import threading

    from kumbara.depo import yerel_depo
    monkeypatch.setenv("KUMBARA_VERI_DIZINI", str(tmp_path))
    ana = yerel_depo()
    assert yerel_depo() is ana
    ana.hedef_kaydet(Hedef("Ev", 1_000_000, date(2032, 1, 1)))
    hatalar, depolar = [], []

    def calis():
        try:
            d = yerel_depo()
            depolar.append(d)
            for _ in range(200):
                assert all(len(r) == 3 for r in d.kaynaklar())
                assert [h.ad for h in d.hedefler()] == ["Ev"]
        except Exception as e:  # noqa: BLE001
            hatalar.append(e)

    iplikler = [threading.Thread(target=calis) for _ in range(4)]
    for t in iplikler:
        t.start()
    for t in iplikler:
        t.join()
    assert not hatalar, hatalar
    assert len({id(d) for d in depolar}) == 4 and ana not in depolar
    # Bağlantıyı başka iş parçacığından kullanmak artık sessizce bozulmak yerine hata verir.
    sonuc = []

    def paylas():
        try:
            ana.kaynaklar()
            sonuc.append("çalıştı")
        except sqlite3.ProgrammingError:
            sonuc.append("engellendi")

    t = threading.Thread(target=paylas)
    t.start()
    t.join()
    assert sonuc == ["engellendi"]
