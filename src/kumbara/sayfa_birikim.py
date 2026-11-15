"""Sayfa: Birikimlerim — varlıklar adet/gram olarak girilir, canlı fiyatla değerlenir.

Fon (TEFAS), hisse (BIST), fiziki altın (gram, çeyrek, 22 ayar, ajda bilezik…), döviz ve nakit.
Türk piyasası fiyatları TL'dir; başka ülke seçiliyse TCMB kuruyla o ülkenin parasına çevrilir.
Bir hedefe bağlanan varlıkların değeri, plan sayfasında o hedefin mevcut birikimi olur.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .depo import yerel_depo
from .ortak import PALET, baglam, birikim_degerlemesi
from .varlik import ALTIN_TURLERI, Varlik

YOK = "—"
KODLU = ("fon", "hisse", "yabanci", "doviz")
_ALTINLAR = [f"altin:{k}" for k in ALTIN_TURLERI]
SECENEKLER = ["fon", "hisse", "yabanci", *_ALTINLAR, "doviz", "nakit", "diger"]


def secenekler(ulke_kodu: str) -> list[str]:
    """Varlık türü listesi; Türkiye dışında yurt dışı hisse/ETF başa gelir."""
    if ulke_kodu == "TR":
        return SECENEKLER
    return ["yabanci", "nakit", "doviz", *_ALTINLAR, "fon", "hisse", "diger"]


def secenek(v: Varlik) -> str:
    return f"altin:{v.kod}" if v.tur == "altin" else v.tur


def secenek_adi(b, s: str) -> str:
    return b.t(f"a_{s[6:]}") if s.startswith("altin:") else b.t(f"t_{s}")


def _bos(x) -> bool:
    return x is None or x == "" or (isinstance(x, float) and pd.isna(x))


def satirdan_varlik(r: dict) -> Varlik | None:
    """Tablo satırı -> Varlik (boş satır: None). Eksik kodda ValueError."""
    s = r.get("varlik")
    if _bos(s):
        return None
    tur, _, altin = str(s).partition(":")
    kod = altin if tur == "altin" else ("" if _bos(r.get("kod")) else str(r["kod"]).strip())
    if tur in KODLU and not kod:
        raise ValueError(tur)
    miktar = 0.0 if _bos(r.get("miktar")) else float(r["miktar"])
    elle = None if _bos(r.get("deger_elle")) else float(r["deger_elle"])
    if elle and not miktar:
        miktar = 1.0
    hedef = r.get("hedef")
    return Varlik(tur, kod or tur, miktar, None if _bos(r.get("maliyet")) else float(r["maliyet"]),
                  None if _bos(r.get("kurum")) else str(r["kurum"]),
                  None if _bos(hedef) or hedef == YOK else str(hedef), elle,
                  None if _bos(r.get("id")) else int(r["id"]))


def alimlar_bolumu(b, onerilen: float | None = None, anahtar: str = "alim") -> None:
    """'Bu ay aldıklarım': alımı Birikimlerim'e işler, bu ayın alımlarını listeler/geri alır."""
    depo = yerel_depo()
    s = b.ulke.sembol
    st.subheader(b.t("alim_baslik"))
    st.caption(b.t("alim_aciklama"))
    mesaj = st.session_state.pop(f"{anahtar}_mesaj", None)
    if mesaj:
        st.success(mesaj)
    hedefler = [YOK] + [h.ad for h in depo.hedefler()]
    with st.form(f"{anahtar}_form", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 3])
        secim = c1.selectbox(b.t("bk_tur"), secenekler(b.ulke.kod),
                             format_func=lambda x: secenek_adi(b, x))
        kod = c2.text_input(b.t("bk_kod"), help=b.t("bk_kod_yardim"))
        miktar = c3.number_input(b.t("bk_miktar"), 0.0, step=1.0)
        tutar = c4.number_input(b.t("alim_tutar", s=s), 0.0, step=100.0)
        hedef = c5.selectbox(b.t("bk_hedef"), hedefler, index=1 if len(hedefler) == 2 else 0,
                             format_func=lambda h: b.t("bk_yok") if h == YOK else h)
        if st.form_submit_button(b.t("alim_ekle"), type="primary"):
            try:
                v = satirdan_varlik({"varlik": secim, "kod": kod, "miktar": miktar, "hedef": hedef})
            except ValueError:
                st.error(b.t("bk_kod_yardim"))
            else:
                if (v.tur == "diger" and not tutar) or (v.tur == "nakit" and not (tutar or miktar)) \
                        or (v.tur not in ("diger", "nakit") and not miktar):
                    st.error(b.t("alim_eksik"))
                else:
                    depo.alim_ekle(v, tutar)
                    st.session_state[f"{anahtar}_mesaj"] = b.t(
                        "alim_eklendi", x=f"{secenek_adi(b, secim)} · {b.P(tutar)}")
                    st.rerun()

    bu_ay = depo.alimlar(date.today().replace(day=1))
    if bu_ay.empty:
        return
    st.markdown(f"**{b.t('alim_liste')}**")
    tablo = pd.DataFrame({
        b.t("c_tarih_alim"): bu_ay["tarih"],
        b.t("bk_tur"): [secenek_adi(b, f"altin:{k}" if t == "altin" else t)
                        + (f" · {k}" if t in KODLU else "") for t, k in zip(bu_ay["tur"], bu_ay["kod"],
                                                                             strict=True)],
        b.t("bk_miktar"): bu_ay["miktar"], b.t("alim_tutar", s=s): bu_ay["tutar"].map(b.P),
        b.t("bk_hedef"): bu_ay["hedef"].fillna("")})
    secili = st.dataframe(tablo, hide_index=True, width="stretch", on_select="rerun",
                          selection_mode="single-row", key=f"{anahtar}_liste")
    toplam = float(bu_ay["tutar"].sum())
    st.caption(b.t("alim_toplam", x=b.P(toplam), y=b.P(onerilen)) if onerilen is not None
               else b.t("alim_toplam", x=b.P(toplam), y="-"))
    satir = (secili.selection.rows or [None])[0] if secili else None
    if satir is not None and satir < len(bu_ay) and st.button(b.t("alim_sil"), key=f"{anahtar}_sil"):
        depo.alim_sil(int(bu_ay["id"].iat[satir]))
        st.rerun()


def goster() -> None:
    b = baglam()
    s = b.ulke.sembol
    depo = yerel_depo()
    st.title(b.t("bk_baslik"))
    st.caption(b.t("bk_aciklama"))
    alimlar_bolumu(b)
    st.subheader(b.t("bk_baslik"))

    mevcut = depo.varliklar()
    hedefler = [YOK] + [h.ad for h in depo.hedefler()]
    tablo = pd.DataFrame([{
        "id": v.id, "varlik": secenek(v), "kod": "" if v.tur == "altin" or v.kod == v.tur else v.kod,
        "miktar": v.miktar, "maliyet": v.maliyet, "kurum": v.kurum,
        "hedef": v.hedef if v.hedef in hedefler else YOK, "deger_elle": v.deger_elle}
        for v in mevcut],
        columns=["id", "varlik", "kod", "miktar", "maliyet", "kurum", "hedef", "deger_elle"])
    duzen = st.data_editor(
        tablo, num_rows="dynamic", hide_index=True, width="stretch", key="varlik_tablo",
        column_config={
            "id": None,
            "varlik": st.column_config.SelectboxColumn(
                b.t("bk_tur"), options=secenekler(b.ulke.kod), required=True, width="medium",
                format_func=lambda x: secenek_adi(b, x)),
            "kod": st.column_config.TextColumn(b.t("bk_kod"), help=b.t("bk_kod_yardim")),
            "miktar": st.column_config.NumberColumn(b.t("bk_miktar"), min_value=0.0),
            "maliyet": st.column_config.NumberColumn(b.t("bk_maliyet", s=s), min_value=0.0,
                                                     help=b.t("bk_maliyet_yardim")),
            "kurum": st.column_config.TextColumn(b.t("bk_yer")),
            "hedef": st.column_config.SelectboxColumn(
                b.t("bk_hedef"), options=hedefler, default=hedefler[1] if len(hedefler) == 2 else YOK,
                format_func=lambda h: b.t("bk_yok") if h == YOK else h),
            "deger_elle": st.column_config.NumberColumn(b.t("bk_elle", s=s), min_value=0.0,
                                                        help=b.t("bk_elle_yardim"))})
    if st.button(b.t("bk_kaydet"), type="primary"):
        try:
            yeni = [v for v in map(satirdan_varlik, duzen.to_dict("records")) if v is not None]
        except ValueError:
            st.error(b.t("bk_kod_yardim"))
        else:
            kalan = {depo.varlik_kaydet(v) for v in yeni}
            for v in mevcut:
                if v.id not in kalan:
                    depo.varlik_sil(v.id)
            st.rerun()

    d, eski, kur = birikim_degerlemesi(b)
    if d is None:
        st.info(b.t("bk_bos"))
        return
    from .varlik import ozet
    oz = ozet(d)
    m1, m2, m3 = st.columns(3)
    m1.metric(b.t("bk_toplam"), b.P(oz["toplam"]))
    if oz["maliyet"]:
        m2.metric(b.t("bk_maliyetli"), b.P(oz["maliyetli_deger"]),
                  delta=b.P(oz["maliyetli_deger"] - oz["maliyet"]),
                  help=b.t("bk_maliyet_toplam", x=b.P(oz["maliyet"])))
    m3.metric(b.t("bk_net"), b.P(oz["hedef"].get("", 0.0)))
    if oz["fiyatlanamayan"]:
        st.warning(b.t("bk_fiyatsiz", n=oz["fiyatlanamayan"]))
    if eski:
        st.caption(b.t("bk_eski", x=", ".join(eski)))
    tl_fiyatli = d["tur"].isin(["fon", "hisse", "altin"]) | (
        (d["tur"] == "doviz") & (d["kod"] != b.ulke.para))
    if b.ulke.para != "TRY" and (tl_fiyatli & ~d["elle"].astype(bool)).any():
        st.caption(b.t("bk_kur", para=b.ulke.para, kur=f"{kur:.2f}") if kur else b.t("bk_kur_yok"))

    siniflar = sorted(oz["sinif"].items(), key=lambda kv: kv[1])
    if siniflar:
        st.markdown(f"**{b.t('bk_sinif')}**")
        fig = go.Figure(go.Bar(x=[v for _, v in siniflar], y=[b.sinif(k) for k, _ in siniflar],
                               orientation="h", marker_color=PALET[0],
                               hovertemplate="%{x:,.0f}<extra></extra>"))
        fig.update_layout(height=60 + 34 * len(siniflar), margin=dict(l=8, r=8, t=8, b=8),
                          barcornerradius=4)
        st.plotly_chart(fig, width="stretch")

    gecmis = depo.varlik_gecmisi()
    gecmis = gecmis[gecmis["detay"].map(lambda x: x.get("para", "TRY")) == b.ulke.para]
    st.markdown(f"**{b.t('bk_seyir')}**")
    if len(gecmis) >= 2:
        fig = go.Figure(go.Scatter(x=gecmis["tarih"], y=gecmis["toplam"], mode="lines+markers",
                                   line=dict(width=2, color=PALET[0]), marker=dict(size=8),
                                   hovertemplate="%{y:,.0f}<extra></extra>"))
        fig.update_xaxes(type="date")
        fig.update_layout(height=280, margin=dict(l=8, r=8, t=8, b=8))
        st.plotly_chart(fig, width="stretch")
    else:
        st.caption(b.t("bk_seyir_bilgi"))

    with st.expander(b.t("bk_detay")):
        satirlar = []
        for r in d.itertuples():
            v = Varlik(r.tur, r.kod, r.miktar)
            ad = secenek_adi(b, secenek(v))
            if r.tur in KODLU or (r.tur in ("nakit", "diger") and r.kod != r.tur):
                ad += f" · {r.kod}"
            satirlar.append({
                b.t("c_varlik"): ad, b.t("bk_miktar"): r.miktar,
                b.t("c_birim"): b.P(r.birim_fiyat, 2), b.t("c_deger"): b.P(r.deger),
                b.t("c_kar"): b.P(r.kar) if pd.notna(r.kar) else "",
                b.t("c_sinif"): b.sinif(r.sinif), b.t("bk_yer"): r.kurum or "",
                b.t("bk_hedef"): r.hedef or ""})
        st.dataframe(pd.DataFrame(satirlar), hide_index=True, width="stretch")
