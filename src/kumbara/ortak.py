"""Panel sayfalarının ortak parçaları: ayarlar, seçilen ülke/dil bağlamı ve birikim değerlemesi."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

from .depo import veri_dizini, yerel_depo
from .dil import kategori_adi, t, yuzde
from .ulke import Ulke, para

PALET = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
AYAR_DOSYASI = veri_dizini() / "hizli.json"


def ayarlar() -> dict:
    try:
        return json.loads(AYAR_DOSYASI.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def ayar_kaydet(**degerler) -> None:
    a = ayarlar()
    if all(a.get(k) == v for k, v in degerler.items()):
        return
    a.update(degerler)
    with contextlib.suppress(OSError):
        AYAR_DOSYASI.write_text(json.dumps(a, ensure_ascii=False, indent=2), "utf-8")


@dataclass
class Baglam:
    ulke: Ulke
    dil: str
    enflasyon: float
    canli: dict | None = None

    def t(self, anahtar: str, **degerler) -> str:
        return t(self.dil, anahtar, **degerler)

    def P(self, x: float | None, ondalik: int = 0) -> str:  # noqa: N802 - kısa para biçimi
        return "-" if x is None or pd.isna(x) else para(x, self.ulke, ondalik)

    def yuzde(self, x: float, ondalik: int = 0) -> str:
        return yuzde(self.dil, x, ondalik)

    def kategori(self, ad: str) -> str:
        return kategori_adi(self.dil, ad)

    def sinif(self, kod: str) -> str:
        return self.t(f"s_{kod}")


def baglam() -> Baglam:
    return st.session_state["baglam"]


# --- Birikim değerlemesi (her iki sayfa kullanır) --------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def _tl_degerleme(anahtar: tuple, borsalar: tuple[str, ...]) -> tuple[pd.DataFrame, list[str]]:
    from .piyasa import Piyasa
    from .varlik import Fiyatlayici, degerle
    son: dict[str, float] = {}
    for detay in yerel_depo().varlik_gecmisi()["detay"]:
        son.update(detay.get("fiyatlar") or {})
    f = Fiyatlayici(Piyasa(veri_dizini()), son_bilinen=son, borsalar=borsalar)
    return degerle(yerel_depo().varliklar(), f), sorted(f.eski_fiyatli)


@st.cache_data(ttl=3600, show_spinner=False)
def _kur(para_birimi: str) -> float | None:
    """1 birim yabancı paranın TL karşılığı (TCMB döviz alış; yoksa piyasa)."""
    from .piyasa import Piyasa
    p = Piyasa(veri_dizini())
    return ((p.tcmb_kurlari() or {}).get(para_birimi) or {}).get("alis") or p.anlik(para_birimi)


def birikim_degerlemesi(b: Baglam) -> tuple[pd.DataFrame | None, list[str], float | None]:
    """(seçilen ülkenin parasıyla değerleme, son bilinen fiyatla değerlenenler, kur)."""
    from .varlik import ozet, para_birimine_cevir, yabanci_siniflarini_uygula
    varliklar = yerel_depo().varliklar()
    if not varliklar:
        return None, [], None
    anahtar = tuple((v.id, v.tur, v.kod, v.miktar, v.maliyet, v.hedef, v.deger_elle)
                    for v in varliklar)
    with st.spinner(b.t("degerleniyor")):
        d_tl, eski = _tl_degerleme(anahtar, b.ulke.borsalar)
        kur = None if b.ulke.para == "TRY" else _kur(b.ulke.para)
    d = yabanci_siniflarini_uygula(para_birimine_cevir(d_tl, b.ulke.para, kur), b.ulke)
    oz = ozet(d)
    if not oz["fiyatlanamayan"]:  # günün kaydı: seyir grafiği ve çevrimdışı yedek fiyatlar (TL)
        yerel_depo().varlik_degeri_kaydet(date.today().isoformat(), dict(
            oz, fiyatlar=ozet(d_tl)["fiyatlar"], para=b.ulke.para))
    return d, eski, kur
