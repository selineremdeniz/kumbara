import httpx
import pytest

from kumbara.piyasa import Piyasa, _oran

ORNEK_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<Tarih_Date Tarih="12.11.2026" Date="11/12/2026" Bulten_No="2026/215">
  <Currency CrossOrder="0" Kod="USD" CurrencyCode="USD"><Unit>1</Unit>
    <ForexBuying>42.1000</ForexBuying><ForexSelling>42.1800</ForexSelling></Currency>
  <Currency CrossOrder="9" Kod="JPY" CurrencyCode="JPY"><Unit>100</Unit>
    <ForexBuying>27.5000</ForexBuying><ForexSelling>27.7000</ForexSelling></Currency>
</Tarih_Date>"""


def test_oran():
    assert _oran(39.5) == pytest.approx(0.395)
    assert _oran("%33,29") == pytest.approx(0.3329)
    assert _oran(0.42) == 0.42
    assert _oran(None) is None


def test_tcmb_kurlari_ayristirma(monkeypatch, tmp_path):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(
        200, content=ORNEK_XML, request=httpx.Request("GET", a[0])))
    kurlar = Piyasa(tmp_path).tcmb_kurlari()
    assert kurlar["_tarih"] == "12.11.2026"
    assert kurlar["USD"]["satis"] == pytest.approx(42.18)
    assert kurlar["JPY"]["alis"] == pytest.approx(0.275)  # 100 birim -> 1 birim


def test_ag_hatasi_cokertmez(monkeypatch, tmp_path):
    def hata(*a, **k):
        raise httpx.ConnectError("engellendi")
    monkeypatch.setattr(httpx, "get", hata)
    p = Piyasa(tmp_path)
    assert p.tcmb_kurlari() is None
    assert "tcmb_kurlari" in p.hatalar


# --- Canlı kaynak testleri: pytest -m ag ---------------------------------------------------------

@pytest.mark.ag
def test_canli_tcmb(tmp_path):
    assert Piyasa(tmp_path).tcmb_kurlari()["USD"]["satis"] > 0


@pytest.mark.ag
def test_canli_ozet(tmp_path):
    p = Piyasa(tmp_path)
    ozet = p.ozet()
    print(ozet, p.hatalar)
    assert ozet["politika_faizi"] and ozet["tufe_yillik"], p.hatalar


@pytest.mark.ag
def test_canli_kap(tmp_path):
    p = Piyasa(tmp_path)
    df = p.kap_bildirimleri("THYAO", 3)
    assert len(df), p.hatalar


@pytest.mark.ag
def test_canli_tefas(tmp_path):
    p = Piyasa(tmp_path)
    assert len(p.fon_adaylari("ppf")), p.hatalar


@pytest.mark.ag
def test_canli_parametre_tahmini(tmp_path):
    from kumbara.tahmin import tahmin_et
    p = tahmin_et(Piyasa(tmp_path), fon_sayisi=3)
    print(p)
    assert sum(p.ay_sayisi.values()) > 0
