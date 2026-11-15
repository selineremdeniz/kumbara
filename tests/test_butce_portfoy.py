from datetime import date

import pandas as pd
import pytest

from kumbara.butce import SabitGider, gelecek_ay_plani, taksit_takvimi
from kumbara.portfoy import (
    MODEL_DAGILIMLAR,
    Hedef,
    birikimi_dagit,
    dagilim_getiri,
    gerekli_aylik_katki,
    hedef_plani,
    toplam_dagilim,
)

KASIM = pd.Period("2026-11", "M")


def test_taksitler_gelecek_ay(islemler):
    plan = gelecek_ay_plani(islemler, aylik_enflasyon=0.02)
    assert plan.hedef_ay == KASIM
    t = plan.taksitler.set_index("isyeri")
    teknosa = next(i for i in t.index if "TEKNOSA" in i)
    thy = next(i for i in t.index if "THY" in i)
    assert t.loc[teknosa, "taksit"] == "5/6" and t.loc[teknosa, "tutar"] == 5_000
    assert t.loc[thy, "taksit"] == "3/3" and t.loc[thy, "kalan_borc"] == 4_000
    assert plan.taksit_toplam == 9_000


def test_taksit_takvimi_biter(islemler):
    takvim = taksit_takvimi(islemler, KASIM, 4)
    toplam = {a: takvim[a].sum() for a in ["2026-11", "2026-12", "2027-01", "2027-02"]}
    assert toplam == {"2026-11": 9_000, "2026-12": 5_000, "2027-01": 0, "2027-02": 0}


def test_kira_cift_sayilmaz(islemler):
    plan = gelecek_ay_plani(islemler, [SabitGider("Kira", 25_000, "Kira")], aylik_enflasyon=0.0)
    assert plan.sabitler["kategori"].tolist().count("Kira") == 1
    assert "Kira" not in set(plan.degisken.loc[plan.degisken["tahmin"] > 0, "kategori"])


def test_limitler_butceye_sigar(islemler):
    plan = gelecek_ay_plani(islemler, [SabitGider("Kira", 25_000, "Kira")],
                            birikim_hedefi=15_000, aylik_enflasyon=0.02)
    harcanan = plan.taksit_toplam + plan.sabit_toplam + plan.degisken_toplam
    assert harcanan + plan.birikim_onerilen + plan.ek_birikim == pytest.approx(
        plan.beklenen_gelir + plan.acik, abs=1)
    zorunlu = plan.degisken[plan.degisken["zorunlu"]]
    assert (zorunlu["onerilen"] == zorunlu["tahmin"]).all()


def test_yetersiz_gelirde_istege_bagli_kisilir(islemler):
    plan = gelecek_ay_plani(islemler, birikim_hedefi=50_000, beklenen_gelir=60_000,
                            aylik_enflasyon=0.0)
    istege = plan.degisken[~plan.degisken["zorunlu"]]
    assert (istege["onerilen"] <= istege["tahmin"]).all()
    assert plan.birikim_onerilen <= 50_000
    assert plan.notlar


@pytest.mark.parametrize("vade", MODEL_DAGILIMLAR)
def test_model_dagilimlar_yuzde_yuz(vade):
    for risk, d in MODEL_DAGILIMLAR[vade].items():
        assert sum(d.values()) == 100, (vade, risk)


def test_risk_vade_ile_artar():
    _, kisa = dagilim_getiri(MODEL_DAGILIMLAR["kısa"]["dengeli"])
    _, uzun = dagilim_getiri(MODEL_DAGILIMLAR["uzun"]["dengeli"])
    assert kisa < uzun


def test_annuite():
    assert gerekli_aylik_katki(12_000, 0, 12, 0.0) == 1_000
    assert gerekli_aylik_katki(12_000, 12_000, 12, 0.05) == 0
    assert gerekli_aylik_katki(100_000, 0, 60, 0.05) < 100_000 / 60


def test_vade_siniflari():
    bugun = date(2026, 11, 12)
    assert Hedef("a", 1, date(2027, 6, 1)).vade(bugun) == "kısa"
    assert Hedef("b", 1, date(2028, 11, 1)).vade(bugun) == "orta"
    assert Hedef("c", 1, date(2035, 1, 1)).vade(bugun) == "uzun"
    assert hedef_plani(Hedef("d", 1000, date(2026, 12, 1)), bugun).uyarilar


def test_oncelikli_dagitim():
    bugun = date(2026, 11, 12)
    hedefler = [Hedef("acil", 60_000, date(2027, 11, 1), 0, 1, "muhafazakar"),
                Hedef("ev", 2_000_000, date(2038, 1, 1), 0, 3, "dengeli")]
    planlar = birikimi_dagit(hedefler, aylik_birikim=6_000, bugun=bugun)
    acil, ev = planlar
    assert acil.onerilen_aylik_katki == pytest.approx(acil.gerekli_aylik_katki)
    assert ev.onerilen_aylik_katki == pytest.approx(6_000 - acil.onerilen_aylik_katki, abs=0.05)
    assert ev.uyarilar  # yetersiz kapasite uyarısı
    assert sum(toplam_dagilim(planlar).values()) == pytest.approx(6_000, abs=0.1)


def test_acik_durumunda_denge_korunur(islemler):
    plan = gelecek_ay_plani(islemler, [SabitGider("Kira", 60_000, "Kira")],
                            birikim_hedefi=10_000, beklenen_gelir=70_000, aylik_enflasyon=0.0)
    harcanan = plan.taksit_toplam + plan.sabit_toplam + plan.degisken_toplam
    assert plan.birikim_onerilen == 0 and plan.acik > 0
    assert harcanan + plan.birikim_onerilen + plan.ek_birikim == pytest.approx(
        plan.beklenen_gelir + plan.acik, abs=1)
    assert (plan.degisken.loc[~plan.degisken["zorunlu"], "onerilen"] == 0).all()


def test_maas_ve_zam():
    from kumbara.gelir import SabitGelir, ay_coz, tanimli_gelir
    gelirler = [SabitGelir("Maaş", 60_000), SabitGelir("Maaş", 66_000, ay_coz("2026-12"))]
    assert tanimli_gelir(gelirler, "2026-11") == 60_000
    assert tanimli_gelir(gelirler, "2026-12") == 66_000
    assert tanimli_gelir(gelirler, "2027-06") == 66_000
    bitti = [SabitGelir("Burs", 5_000, None, ay_coz("2026-11"))]
    assert tanimli_gelir(bitti, "2026-12") == 0


def test_tanimli_gelir_plana_ve_ozete_girer(islemler):
    from kumbara.analiz import aylik_ozet
    from kumbara.gelir import SabitGelir, ay_coz
    kart = islemler[islemler.hesap == "Kart"]  # yalnızca kart ekstresi: maaş görünmüyor
    gelirler = [SabitGelir("Maaş", 60_000), SabitGelir("Maaş", 66_000, ay_coz("2026-12"))]
    plan = gelecek_ay_plani(kart, gelirler=gelirler, hedef_ay="2026-12", aylik_enflasyon=0)
    assert plan.beklenen_gelir == 66_000 and plan.gelir_kaynagi == "tanımlı"
    ozet = aylik_ozet(kart, gelirler)
    assert ozet.loc[pd.Period("2026-10", "M"), "gelir"] == 60_000
    # Maaşın ekstrede göründüğü aylarda tanımlı gelir EKLENMEZ (çift sayım yok).
    tam = aylik_ozet(islemler, gelirler)
    assert tam.loc[pd.Period("2026-10", "M"), "gelir"] < 80_000
    assert set(tam["gelir_kaynagi"]) == {"ekstre"}
