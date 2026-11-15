import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from kumbara import portfoy as pf
from kumbara.simulasyon import simule_et
from kumbara.tahmin import (
    Parametreler,
    aylik_enflasyon_serisi,
    aylik_reel_getiri,
    daralt,
    en_yakin_psd,
    parametreleri_hesapla,
    temsilci_fonlar,
)


@pytest.fixture(autouse=True)
def varsayimlari_koru():
    yedek = dict(pf.VARLIK_SINIFLARI)
    kor, kaynak = pf.KORELASYON, pf.PARAMETRE_KAYNAGI
    yield
    pf.VARLIK_SINIFLARI.clear()
    pf.VARLIK_SINIFLARI.update(yedek)
    pf.KORELASYON, pf.PARAMETRE_KAYNAGI = kor, kaynak


def _enflasyon(aylar, oran=0.03):
    idx = pd.period_range("2021-01", periods=aylar, freq="M")
    return pd.Series(oran, index=idx)


def test_reel_getiri_enflasyonu_dusar():
    enf = _enflasyon(13)
    gunler = pd.date_range("2021-01-31", periods=13, freq="ME")
    fiyat = pd.Series(1.05 ** np.arange(13), index=gunler)  # ayda %5 nominal
    r = aylik_reel_getiri(fiyat, enf)
    assert len(r) == 12
    assert r.iloc[0] == pytest.approx(1.05 / 1.03 - 1)


def test_tufe_tablosu_okunur():
    tufe = pd.DataFrame({"MonthlyInflation": [2.5, 3.0], "YearlyInflation": [40, 38]},
                        index=pd.to_datetime(["2026-09-01", "2026-10-01"]))
    s = aylik_enflasyon_serisi(tufe)
    assert s[pd.Period("2026-10", "M")] == pytest.approx(0.03)


def test_tahmin_gercek_parametreleri_bulur():
    """Bilinen dağılımdan üretilen uzun seride tahmin gerçeğe yakın olmalı.

    (Ortalamanın standart hatası sigma/sqrt(yıl): 5 yıllık veride ~11 puan, 500 yılda ~1 puan.
    Bu yüzden gerçek 5 yıllık veride ortalama varsayıma doğru daraltılır.)"""
    rng = np.random.default_rng(1)
    idx = pd.period_range("1500-01", periods=6000, freq="M")
    gercek_mu, gercek_sig = 0.08, 0.25
    log_r = rng.normal(np.log1p(gercek_mu) / 12, gercek_sig / np.sqrt(12), len(idx))
    p = parametreleri_hesapla({"bist_hisse": pd.Series(np.expm1(log_r), index=idx)}, {})
    assert p.tarihsel_getiri["bist_hisse"] == pytest.approx(gercek_mu, abs=0.03)
    assert p.tarihsel_oynaklik["bist_hisse"] == pytest.approx(gercek_sig, abs=0.02)
    # Uzun veri: kullanılan değer tarihsele yaklaşır ama önsel varsayımla harmanlanır.
    onsel = pf.VARLIK_SINIFLARI["bist_hisse"].reel_getiri
    assert min(onsel, p.tarihsel_getiri["bist_hisse"]) <= p.reel_getiri["bist_hisse"] <= max(
        onsel, p.tarihsel_getiri["bist_hisse"])


def test_kisa_veride_varsayim_agir_basar():
    assert daralt(0.40, 24, 0.05, 120) == pytest.approx(0.05 + 24 / 144 * 0.35)
    assert daralt(None, 0, 0.05, 120) == 0.05


def test_ucuk_tahmin_sinirlanir_ve_ppf_ileriye_donuk():
    idx = pd.period_range("2021-01", periods=600, freq="M")
    p = parametreleri_hesapla({"altin": pd.Series(0.06, index=idx)}, {"ppf": 0.03})
    assert p.reel_getiri["altin"] <= 0.15 and any("sınır" in n for n in p.notlar)
    assert p.reel_getiri["ppf"] == 0.03


def test_korelasyon_matrisi_gecerli():
    k = pd.DataFrame([[1, 0.9, -0.9], [0.9, 1, 0.9], [-0.9, 0.9, 1]], index=list("abc"),
                     columns=list("abc"), dtype=float)
    m = en_yakin_psd(k)
    assert np.all(np.linalg.eigvalsh(m.values) > 0)
    assert np.allclose(np.diag(m.values), 1)


def test_temsilci_fonlar_sadece_en_iyiler_degil():
    liste = pd.DataFrame({"fund_code": [f"F{i}" for i in range(20)],
                          "name": [f"ABC ALTIN FONU {i}" for i in range(20)],
                          "return_5y": np.arange(20.0)})
    secim = temsilci_fonlar(liste, "altin", 5)
    assert secim[0] == "F0" and secim[-1] == "F19" and len(secim) == 5


def test_parametre_kaydet_yukle_uygula(tmp_path):
    idx = pd.period_range("2021-01", periods=60, freq="M")
    p = parametreleri_hesapla({"altin": pd.Series(np.tile([0.03, -0.02], 30), index=idx)}, {})
    yol = tmp_path / "p.json"
    p.kaydet(yol)
    assert json.loads(yol.read_text())["oynaklik"]["altin"] > 0
    q = Parametreler.yukle(yol)
    pf.parametreleri_uygula(q)
    assert pf.VARLIK_SINIFLARI["altin"].oynaklik == q.oynaklik["altin"]
    assert pf.PARAMETRE_KAYNAGI.startswith("tahmin")


def test_simulasyon_guven_arttikca_katki_artar():
    sim = simule_et(200_000, 10_000, "dengeli", 48)
    k50, k80, k95 = (sim.gerekli_katki(g) for g in (0.5, 0.8, 0.95))
    assert k50 < k80 < k95
    assert sim.olasilik(k80) == pytest.approx(0.8, abs=0.01)


def test_simulasyon_oynakliksiz_annuiteye_esit():
    for kod in pf.VARLIK_SINIFLARI:
        pf._guncelle(kod, oynaklik=1e-9, reel_getiri=0.03)
    sim = simule_et(100_000, 0, "muhafazakar", 24, yol=200)
    beklenen = pf.gerekli_aylik_katki(100_000, 0, 24, 0.03)
    assert sim.gerekli_katki(0.8) == pytest.approx(beklenen, rel=1e-3)


def test_plan_olasilik_raporlar():
    bugun = date(2026, 11, 12)
    [p] = pf.birikimi_dagit([pf.Hedef("tatil", 60_000, date(2027, 8, 1), 0, 1, "dengeli")],
                            aylik_birikim=1_000, bugun=bugun)
    assert p.basari_olasiligi < 0.05  # 9 ayda 1.000 TL/ay ile 60.000 TL'ye ulaşılamaz
    assert p.sonuc_araligi["p10"] <= p.sonuc_araligi["p50"] <= p.sonuc_araligi["p90"]
    assert p.gerekli_aylik_katki >= p.medyan_katki * 0.95


def test_aykiri_fon_ayiklanir_ve_medyan():
    from kumbara.tahmin import aykiri_mi, sinif_endeksi
    idx = pd.period_range("2022-01", periods=3, freq="M")
    iyi = [pd.Series([0.02, 0.03, 0.01], index=idx), pd.Series([0.03, 0.02, 0.02], index=idx)]
    bozuk = pd.Series([0.02, -0.8, 0.02], index=idx)
    assert aykiri_mi(bozuk) and not aykiri_mi(iyi[0])
    endeks = sinif_endeksi([*iyi, pd.Series([0.5, 0.5, 0.5], index=idx)])
    assert endeks.iloc[0] == pytest.approx(0.03)  # medyan, uç değerden etkilenmez


def test_ppf_ileriye_donuk():
    assert pf.ppf_reel_getiri_tahmini(0.36, 0.30, 0.28) == pytest.approx(1.33 / 1.29 - 1, abs=1e-4)
    assert pf.ppf_reel_getiri_tahmini(None, 0.3) is None
