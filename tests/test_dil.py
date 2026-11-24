"""Panel dili: her dilde aynı anahtarlar, ülke -> dil, ajda ve kur çevirisi."""

import pandas as pd
import pytest

from kumbara.dil import METINLER, ULKE_DILI, dil_kodu, kategori_adi, t, yuzde
from kumbara.ulke import ULKELER, para
from kumbara.varlik import ALTIN_TURLERI, Fiyatlayici, Varlik, degerle, para_birimine_cevir


def test_tum_diller_ayni_anahtarlar():
    tr = set(METINLER["tr"])
    for dil, metinler in METINLER.items():
        assert set(metinler) == tr, dil
    for kod in ALTIN_TURLERI:                       # her altın türünün her dilde adı var
        assert all(f"a_{kod}" in m for m in METINLER.values())


def test_ulke_dili_ve_bicimler():
    assert set(ULKE_DILI) == set(ULKELER)
    assert dil_kodu("TR") == "tr" and dil_kodu("US") == "en" and dil_kodu("DE") == "de"
    assert t("en", "adim2") == "2 · This month's income"
    assert t("tr", "adim2") == "2 · Bu ayki geliriniz"
    assert t("de", "okunuyor", ad="x.pdf") == "x.pdf wird gelesen…"
    assert kategori_adi("en", "Market") == "Groceries" and kategori_adi("en", "Benim") == "Benim"
    assert yuzde("tr", 80) == "%80" and yuzde("en", 80) == "80%" and yuzde("de", 80) == "80 %"


def test_ajda_22_ayar_fiyatlanir():
    v = Varlik("altin", "ajda", 20)
    assert v.kod == "ajda" and "ajda" in ALTIN_TURLERI[v.kod][2]
    f = Fiyatlayici(sabit={("altin", "ajda"): (3000 * 0.916, "ajda")})
    assert degerle([v], f)["deger"].iat[0] == pytest.approx(20 * 3000 * 0.916)


def test_kur_cevirisi():
    vs = [Varlik("altin", "gram", 10), Varlik("nakit", "Banka", 500),
          Varlik("doviz", "USD", 100), Varlik("diger", "ETF", 1, deger_elle=2000, maliyet=1500)]
    f = Fiyatlayici(sabit={("altin", "gram"): (4000.0, "g"), ("doviz", "USD"): (40.0, "USD")})
    d = para_birimine_cevir(degerle(vs, f), "USD", 40.0)
    deger = dict(zip(d["kod"], d["deger"], strict=True))
    assert deger == {"gram": 1000.0, "Banka": 500.0, "USD": 100.0, "ETF": 2000.0}
    assert d.loc[d["kod"] == "USD", "sinif"].iat[0] == "ppf"       # kendi dövizi = nakit
    assert d.loc[d["kod"] == "ETF", "kar"].iat[0] == 500.0
    yok = para_birimine_cevir(degerle(vs, f), "USD", None)
    assert bool(yok.loc[yok["kod"] == "gram", "fiyatlanamadi"].iat[0])
    assert pd.isna(yok.loc[yok["kod"] == "gram", "deger"].iat[0])


def test_birikim_tablosu_satiri():
    pytest.importorskip("streamlit")
    from kumbara.sayfa_birikim import YOK, satirdan_varlik
    v = satirdan_varlik({"varlik": "altin:ajda", "kod": None, "miktar": 12.5, "hedef": YOK})
    assert (v.tur, v.kod, v.miktar, v.hedef) == ("altin", "ajda", 12.5, None)
    v = satirdan_varlik({"varlik": "diger", "kod": "BES", "miktar": None, "deger_elle": 5000.0,
                         "hedef": "Ev"})
    assert v.miktar == 1.0 and v.deger_elle == 5000.0 and v.hedef == "Ev"
    assert satirdan_varlik({"varlik": None}) is None
    with pytest.raises(ValueError):
        satirdan_varlik({"varlik": "fon", "kod": ""})


def test_alim_birlesir_ve_geri_alinir(tmp_path):
    from kumbara.depo import Depo
    d = Depo(tmp_path / "k.db")
    d.varlik_kaydet(Varlik("altin", "ajda", 10, maliyet=30_000, hedef="Ev"))
    v = d.alim_ekle(Varlik("altin", "ajda", 5, hedef="Ev"), 16_000)
    assert (v.miktar, v.maliyet) == (15, 46_000) and len(d.varliklar()) == 1
    d.alim_ekle(Varlik("altin", "ajda", 2), 6_000)               # başka hedef: ayrı varlık
    d.alim_ekle(Varlik("nakit", "nakit", 0), 5_000)              # nakitte miktar = tutar
    d.alim_ekle(Varlik("diger", "BES", 0), 2_000)                 # diğer: elle değer
    vs = {(x.tur, x.hedef): x for x in d.varliklar()}
    assert vs[("nakit", None)].miktar == 5_000 and vs[("diger", None)].deger_elle == 2_000
    for i in d.alimlar()["id"]:
        d.alim_sil(int(i))
    assert [(x.kod, x.miktar, x.maliyet) for x in d.varliklar()] == [("ajda", 10, 30_000)]


def test_hedefe_kalan_getiri_ve_katki():
    pytest.importorskip("streamlit")
    from datetime import date as dt

    from kumbara.portfoy import Hedef, birikimi_dagit
    from kumbara.sayfa_plan import hedef_kalani
    p = birikimi_dagit([Hedef("Araba", 600_000, dt(2029, 11, 1), 50_000, risk="dengeli")],
                       28_000, bugun=dt(2026, 11, 15), simulasyon=False)[0]
    k = hedef_kalani(p, 0.30)
    assert k["kalan"] == 550_000
    assert k["getiriden"] > 0 and k["yatirilacak"] + k["getiriden"] == pytest.approx(550_000)
    assert k["nominal"] == pytest.approx((1 + p.beklenen_reel_getiri) * 1.30 - 1)


class _SahtePiyasa:
    hatalar: dict = {}

    def yabanci(self, kod, borsalar):
        return {"VOO": {"sembol": "AMEX:VOO", "fiyat": 600.0, "para": "USD", "ad": "Vanguard S&P 500"},
                "LSE:VWRL": {"sembol": "LSE:VWRL", "fiyat": 130.0, "para": "GBP", "ad": "All-World"},
                "NASDAQ:BND": {"sembol": "NASDAQ:BND", "fiyat": 70.0, "para": "USD", "ad": "BND"}}.get(kod)

    def tcmb_kurlari(self):
        return {"USD": {"alis": 40.0}, "GBP": {"alis": 50.0}}

    def anlik(self, _):
        return None


def test_yurt_disi_hisse_etf_ulkeye_gore():
    from kumbara.ulke import ULKELER
    from kumbara.varlik import yabanci_siniflarini_uygula
    vs = [Varlik("yabanci", "voo", 2), Varlik("yabanci", "LSE:VWRL", 10), Varlik("yabanci", "NASDAQ:BND", 1)]
    d_tl = degerle(vs, Fiyatlayici(_SahtePiyasa()))
    assert list(d_tl["deger"]) == [48_000.0, 65_000.0, 2_800.0]          # TL'ye çevrildi
    tr = dict(zip(d_tl["kod"], yabanci_siniflarini_uygula(d_tl, ULKELER["TR"])["sinif"], strict=True))
    assert tr == {"VOO": "yabanci_hisse", "LSE:VWRL": "yabanci_hisse", "NASDAQ:BND": "eurobond"}
    us = yabanci_siniflarini_uygula(para_birimine_cevir(d_tl, "USD", 40.0), ULKELER["US"])
    assert list(us["deger"]) == [1_200.0, 1_625.0, 70.0]                 # dolar fiyatına geri döndü
    assert dict(zip(us["kod"], us["sinif"], strict=True)) == {
        "VOO": "bist_hisse", "LSE:VWRL": "yabanci_hisse", "NASDAQ:BND": "tl_tahvil"}


def test_hedef_satiri_bos_hucreler():
    pytest.importorskip("streamlit")
    from datetime import date as dt

    from kumbara.sayfa_plan import satirdan_hedef
    nan = float("nan")
    h = satirdan_hedef({"ad": " Ev ", "tutar": 1e6, "tarih": dt(2030, 1, 1), "mevcut": nan,
                        "oncelik": nan, "risk": nan})
    assert (h.ad, h.mevcut, h.oncelik, h.risk) == ("Ev", 0.0, 2, "dengeli")
    assert satirdan_hedef({"ad": "Ev", "tutar": nan, "tarih": dt(2030, 1, 1)}) is None
    assert satirdan_hedef({"ad": None, "tutar": 5.0, "tarih": pd.NaT}) is None


def test_negatif_para_bicimi():
    assert para(-1234.5, ULKELER["US"]) == "-$1,234" or para(-1234.5, ULKELER["US"]) == "-$1,235"
    assert para(-1234.5, ULKELER["TR"], 2) == "-1.234,50 ₺"
    assert para(-0.4, ULKELER["US"]) == "$0"


def test_masaustu_bos_port():
    import socket

    from kumbara.masaustu import bos_port
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        dolu = s.getsockname()[1]
        assert bos_port(dolu) != dolu
