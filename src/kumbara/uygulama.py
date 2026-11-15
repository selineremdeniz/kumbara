"""kumbara paneli:  kumbara panel   (eski ayrıntılı panel: kumbara panel --ayrintili)

İki sayfa: "Bu ayın planı" (kart ekstresi + bu ayki gelir → birikim → hedefe göre portföy) ve
"Birikimlerim" (varlıklar, adet/gram, canlı değerleme). Panel dili seçilen ülkeden gelir.
"""

from __future__ import annotations

import streamlit as st

from kumbara import portfoy as pf
from kumbara.depo import veri_dizini
from kumbara.dil import dil_kodu, t
from kumbara.ortak import Baglam, ayar_kaydet, ayarlar
from kumbara.sayfa_birikim import goster as birikim_sayfasi
from kumbara.sayfa_plan import goster as plan_sayfasi
from kumbara.ulke import ULKELER, ulke_uygula

st.set_page_config(page_title="kumbara", page_icon="🐷", layout="wide")
A = ayarlar()
kodlar = list(ULKELER)

with st.sidebar:
    onceki = A.get("ulke", "TR") if A.get("ulke") in ULKELER else "TR"
    ulke_kodu = st.selectbox("🌍", kodlar, index=kodlar.index(onceki), key="ulke",
                             format_func=lambda k: f"{ULKELER[k].ad} ({ULKELER[k].para})",
                             label_visibility="collapsed")
dil = dil_kodu(ulke_kodu)
ulke = ulke_uygula(ulke_kodu)

sayfa = st.navigation([
    st.Page(plan_sayfasi, title=t(dil, "sayfa_plan"), icon="🧮", default=True),
    st.Page(birikim_sayfasi, title=t(dil, "sayfa_birikim"), icon="💰", url_path="birikimlerim"),
])

with st.sidebar:
    st.header(t(dil, "ayarlar"))
    canli = None
    if ulke_kodu == "TR":
        from kumbara.tahmin import Parametreler
        p = Parametreler.yukle(veri_dizini() / "parametreler.json")
        if p is not None:
            pf.parametreleri_uygula(p)
        if st.toggle(t(dil, "canli_tcmb"), value=A.get("canli", True)):
            @st.cache_data(ttl=3600, show_spinner=False)
            def _tcmb() -> dict:
                from kumbara.piyasa import Piyasa
                return Piyasa(veri_dizini()).ozet()
            with st.spinner(t(dil, "veri_aliniyor")):
                canli = _tcmb()
            pf.ppf_reel_getiri_guncelle(canli.get("politika_faizi"), canli.get("tufe_yillik"),
                                        canli.get("tufe_son3_yillik"))
    varsayilan_enf = (canli or {}).get("tufe_yillik") or ulke.enflasyon
    enflasyon = st.number_input(t(dil, "enflasyon"), 0.0, 200.0,
                                float(A.get(f"enf_{ulke_kodu}", round(varsayilan_enf * 100, 1))),
                                0.5, key=f"enf_{ulke_kodu}") / 100
    st.caption(t(dil, "not_tr" if ulke_kodu == "TR" else "not_diger"))
    st.caption(t(dil, "ayrintili"))

ayar_kaydet(ulke=ulke_kodu, canli=canli is not None,
            **{f"enf_{ulke_kodu}": round(enflasyon * 100, 1)})
st.session_state["baglam"] = Baglam(ulke, dil, enflasyon, canli)
sayfa.run()
