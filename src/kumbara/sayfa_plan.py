"""Sayfa: bu ayın planı — son kart ekstresi + bu ayki gelir → bu ayki birikim → hedefe göre portföy.

Ekstreler kaydedilmez; her hesap yüklenen dosyalardan yeniden yapılır. Portföy kuralları her ülkede
aynıdır (portfoy.py); dil ve varlık adları seçilen ülkeden gelir.
"""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import portfoy as pf
from .depo import veri_dizini, yerel_depo
from .ekstre import EkstreHatasi
from .hizli import birikim_hesapla, ekstre_ozetle
from .kategori import Kategorilendirici
from .ortak import PALET, Baglam, ayar_kaydet, ayarlar, baglam, birikim_degerlemesi
from .portfoy import RISKLER, Hedef, birikimi_dagit, toplam_dagilim
from .varlik import hedef_mevcutlari

# pdf_ekstre / hizli'nin Türkçe toplam etiketleri -> dil anahtarı
BANKA_ETIKETLERI = {"Dönem içi harcamalar": "b_donem_ici", "Hesap özeti borcu": "b_hesap_ozeti",
                    "Dönem borcu": "b_donem_borcu", "Toplam borç": "b_toplam_borc",
                    "Güncel dönem borcu": "b_guncel",
                    "Dönem içi harcamalar toplamı": "b_donem_ici_toplam"}


@st.cache_data(show_spinner=False, max_entries=20)
def _ozetle(icerik: bytes, ad: str, sifre: str | None):
    with tempfile.TemporaryDirectory() as d:
        yol = Path(d) / ad
        yol.write_bytes(icerik)
        kat = Kategorilendirici.varsayilan(veri_dizini() / "kategoriler.yaml")
        return ekstre_ozetle(yol, kat, sifre or None)


def _cubuk(etiketler, degerler, renk) -> go.Figure:
    fig = go.Figure(go.Bar(x=list(degerler), y=list(etiketler), orientation="h", marker_color=renk,
                           hovertemplate="%{x:,.0f}<extra></extra>"))
    fig.update_layout(height=60 + 32 * len(degerler), margin=dict(l=8, r=8, t=8, b=8),
                      barcornerradius=4)
    return fig


def satirdan_hedef(r: dict) -> Hedef | None:
    """Hedef tablosu satırı -> Hedef; adı, tutarı ya da tarihi eksik satır atlanır (None).
    Boş hücreler tablodan None ya da NaN gelebilir."""
    def deger(k):
        x = r.get(k)
        return None if x is None or (not isinstance(x, str) and pd.isna(x)) or x == "" else x
    ad, tutar, tarih = deger("ad"), deger("tutar"), deger("tarih")
    if not ad or not tutar or tarih is None:
        return None
    risk = deger("risk")
    return Hedef(str(ad).strip(), float(tutar), pd.Timestamp(tarih).date(), float(deger("mevcut") or 0),
                 int(deger("oncelik") or 2), risk if risk in RISKLER else "dengeli")


def _yuzde_sayi(x: float) -> str:
    return f"{x * 100:.1f}".rstrip("0").rstrip(".")


def hedef_kalani(p: pf.HedefPlani, enflasyon: float) -> dict[str, float]:
    """Hedefe kalan tutarın ne kadarını beklenen getirinin, ne kadarını sizin katkınızın karşılayacağı.

    kalan = tutar − mevcut; yatırılacak = aylık katkı × ay; getiriden = kalan − yatırılacak
    (mevcut birikimin ve katkıların beklenen reel getirisi). Hepsi bugünün parasıyla.
    """
    kalan = max(0.0, p.hedef.tutar - p.hedef.mevcut)
    yatirilacak = round(p.gerekli_aylik_katki * p.ay_sayisi, 2)
    return {"kalan": round(kalan, 2), "yatirilacak": yatirilacak,
            "getiriden": round(kalan - yatirilacak, 2) if kalan else 0.0,
            "nominal": (1 + p.beklenen_reel_getiri) * (1 + enflasyon) - 1}


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _fon_adaylari(siniflar: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    from .piyasa import Piyasa
    p = Piyasa(veri_dizini())
    sonuc = {k: p.fon_adaylari(k, 3) for k in siniflar}
    if not any(len(v) for v in sonuc.values()):
        raise RuntimeError("TEFAS")  # hata önbelleğe alınmaz; sonraki açılışta yeniden denenir
    return sonuc


def fon_onerileri(b: Baglam, toplam: dict[str, float]) -> None:
    """Alım listesindeki her varlık sınıfı için TEFAS'tan örnek fonlar (Türkiye)."""
    st.markdown(f"**{b.t('fonlar_baslik')}**")
    st.caption(b.t("fonlar_aciklama"))
    try:
        with st.spinner(b.t("veri_aliniyor")):
            adaylar = _fon_adaylari(tuple(toplam))
    except Exception:  # noqa: BLE001 - ağ/kaynak hatası: sayfa çalışmaya devam eder
        st.caption(b.t("fonlar_yok"))
        return

    def y(x):
        return "" if x is None or pd.isna(x) else b.yuzde(round(float(x), 1) + 0.0, 1)
    satirlar = []
    for k, tutar in toplam.items():
        for i, r in enumerate(adaylar.get(k, pd.DataFrame()).to_dict("records")):
            satirlar.append({
                b.t("c_varlik"): pf.VARLIK_SINIFLARI[k].ad if i == 0 else "",
                b.t("c_bu_ay"): b.P(tutar) if i == 0 else "",
                b.t("c_kod"): r.get("fund_code"), b.t("c_fon"): r.get("name"),
                b.t("c_1a"): y(r.get("return_1m")), b.t("c_1y"): y(r.get("return_1y")),
                b.t("c_3y"): y(r.get("return_3y"))})
    if satirlar:
        st.dataframe(pd.DataFrame(satirlar), hide_index=True, width="stretch",
                     column_config={b.t("c_varlik"): st.column_config.TextColumn(width="medium")})


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _etf_getirileri(semboller: tuple[str, ...]) -> dict[str, dict]:
    from concurrent.futures import ThreadPoolExecutor

    from .piyasa import Piyasa
    p = Piyasa(veri_dizini())
    with ThreadPoolExecutor(max_workers=6) as havuz:
        sonuc = dict(zip(semboller, havuz.map(
            lambda x: p._dene(f"getiri:{x}", lambda: p.yabanci_getiri(x), {}), semboller), strict=True))
    if not any(sonuc.values()):
        raise RuntimeError("ETF")  # hata önbelleğe alınmaz
    return sonuc


def etf_onerileri(b: Baglam, toplam: dict[str, float]) -> None:
    """Alım listesindeki her varlık sınıfı için seçilen ülkenin borsasından örnek ETF'ler."""
    st.markdown(f"**{b.t('etf_baslik', borsa=b.ulke.borsa_adi)}**")
    st.caption(b.t("etf_aciklama"))
    liste = {k: b.ulke.etfler.get(k, ()) for k in toplam}
    try:
        with st.spinner(b.t("veri_aliniyor")):
            getiri = _etf_getirileri(tuple(sym for v in liste.values() for sym, _ in v))
    except Exception:  # noqa: BLE001 - ağ/kaynak hatası: liste getirisiz gösterilir
        st.caption(b.t("etf_yok"))
        getiri = {}

    def y(x):
        return "" if x is None or pd.isna(x) else b.yuzde(round(float(x), 1) + 0.0, 1)
    satirlar = []
    for k, tutar in toplam.items():
        for i, (sembol, ad) in enumerate(liste[k]):
            g = getiri.get(sembol) or {}
            satirlar.append({
                b.t("c_varlik"): pf.VARLIK_SINIFLARI[k].ad if i == 0 else "",
                b.t("c_bu_ay"): b.P(tutar) if i == 0 else "",
                b.t("c_kod"): sembol, b.t("c_fon"): ad, b.t("c_1a"): y(g.get("return_1m")),
                b.t("c_1y"): y(g.get("return_1y")), b.t("c_3y"): y(g.get("return_3y"))})
    if satirlar:
        st.dataframe(pd.DataFrame(satirlar), hide_index=True, width="stretch",
                     column_config={b.t("c_varlik"): st.column_config.TextColumn(width="medium")})


def uyarilar(b: Baglam, p: pf.HedefPlani) -> list[str]:
    """Plan uyarıları seçilen dilde (portfoy.py'deki Türkçe metinlerin karşılığı)."""
    u = []
    if p.gerekli_aylik_katki > 0 and p.onerilen_aylik_katki < 0.995 * p.gerekli_aylik_katki:
        u.append(b.t("w_kapasite", p=f"{p.onerilen_aylik_katki / p.gerekli_aylik_katki * 100:.0f}"))
    if p.vade == "kısa" and p.hedef.risk == "agresif":
        u.append(b.t("w_kisa_agresif"))
    if p.ay_sayisi <= 3:
        u.append(b.t("w_3ay"))
    disarida = sorted(set(p.mevcut_dagilim) - set(p.dagilim))
    if disarida:
        u.append(b.t("w_disarida", x=", ".join(b.sinif(k) for k in disarida)))
    return u


def goster() -> None:
    b = baglam()
    A = ayarlar()
    s = b.ulke.sembol
    st.title(b.t("plan_baslik"))
    st.caption(b.t("plan_aciklama"))

    # --- 1. Ekstre ---------------------------------------------------------------------------------
    st.subheader(b.t("adim1"))
    # Yüklenen dosyalar oturumda tutulur: sayfa değiştirince kaybolmaz (diske yazılmaz).
    kayitli: dict[str, bytes] = st.session_state.setdefault("ekstreler", {})
    sayac = st.session_state.setdefault("yukleme_sayac", 0)
    yeni = st.file_uploader(b.t("yukle"), accept_multiple_files=True, key=f"yukleyici_{sayac}",
                            type=["pdf", "jpg", "jpeg", "png", "webp", "heic"])
    if yeni:
        for f in yeni:
            kayitli[f.name] = f.getvalue()
        st.session_state["yukleme_sayac"] = sayac + 1
        st.rerun()
    sifre = st.text_input(b.t("sifre"), type="password",
                          value=st.session_state.get("pdf_sifre", ""))
    st.session_state["pdf_sifre"] = sifre
    ozetler = []
    if kayitli:
        st.caption(b.t("yuklu"))
    for ad in list(kayitli):
        c1, c2 = st.columns([8, 1])
        c1.markdown(f"📄 {ad}")
        if c2.button(b.t("kaldir"), key=f"kaldir_{ad}"):
            del kayitli[ad]
            st.rerun()
        try:
            with st.spinner(b.t("okunuyor", ad=ad)):
                ozetler.append(_ozetle(kayitli[ad], ad, sifre))
        except EkstreHatasi as e:
            st.error(b.t("hata", ad=ad, e=e))

    bes_toplam = sum(o.bes for o in ozetler)
    if ozetler:
        def etiket(o):
            return f" ({b.t(BANKA_ETIKETLERI[o.banka_etiketi])})" if o.banka_etiketi in \
                BANKA_ETIKETLERI else ""
        st.dataframe(pd.DataFrame([{
            b.t("c_dosya"): o.dosya, b.t("c_kart"): o.kart, b.t("c_islem"): len(o.islemler),
            b.t("c_banka"): b.P(o.banka_toplami, 2) + etiket(o),
            b.t("c_okunan"): b.P(o.okunan_harcama, 2), b.t("c_bes"): b.P(o.bes, 2),
            b.t("c_taksit"): b.P(o.sonraki_taksit, 2)} for o in ozetler]),
            hide_index=True, width="stretch")
        for o in ozetler:
            for u in o.uyarilar:
                st.caption(f"{o.dosya}: {b.t(u)}")
        tum = pd.concat([o.islemler for o in ozetler], ignore_index=True)
        with st.expander(b.t("kategori_dokumu")):
            gider = tum[(tum["tutar"] < 0) & (tum["kategori"] != "Transfer")]
            kir = (-gider.groupby("kategori")["tutar"].sum()).sort_values()
            st.plotly_chart(_cubuk([b.kategori(k) for k in kir.index], kir.values, PALET[0]),
                            width="stretch")
            liste = tum[["tarih", "hesap", "aciklama", "tutar", "kategori"]].copy()
            liste["kategori"] = liste["kategori"].map(b.kategori)
            st.dataframe(liste, hide_index=True, width="stretch")

    okunan = sum(o.harcama for o in ozetler)
    anahtar = hashlib.sha1("|".join(f"{o.dosya}{o.harcama}" for o in ozetler).encode()).hexdigest()
    duzeltmeler = st.session_state.setdefault("kart_duzeltme", {})  # elle düzeltme de kalsın
    kart_harcama = st.number_input(b.t("kart_harcama", s=s), 0.0,
                                   value=float(duzeltmeler.get(anahtar, round(okunan, 2))),
                                   step=100.0, help=b.t("kart_harcama_yardim"))
    duzeltmeler[anahtar] = kart_harcama

    # --- 2. Gelir ----------------------------------------------------------------------------------
    st.subheader(b.t("adim2"))
    c1, c2 = st.columns(2)
    gelir = c1.number_input(b.t("gelir", s=s), 0.0, value=float(A.get("gelir", 0.0)), step=1000.0)
    kart_disi = c2.number_input(b.t("kart_disi", s=s), 0.0, value=float(A.get("kart_disi", 0.0)),
                                step=500.0)
    bes_birikim = bes_toplam > 0 and st.checkbox(b.t("bes_say", x=b.P(bes_toplam)), value=True)
    ayar_kaydet(gelir=gelir, kart_disi=kart_disi)

    # --- 3. Birikim --------------------------------------------------------------------------------
    st.subheader(b.t("adim3"))
    if not gelir:
        st.info(b.t("gelir_girin"))
        st.stop()
    bk = birikim_hesapla(gelir, kart_harcama, kart_disi, bes_toplam, bes_birikim)
    m1, m2, m3 = st.columns(3)
    m1.metric(b.t("yatirilabilir"), b.P(bk.yatirilabilir))
    m2.metric(b.t("oran"), "-" if bk.oran is None else b.yuzde(bk.oran * 100))
    m3.metric(b.t("toplam_birikim") + (b.t("bes_dahil") if bes_birikim else ""),
              b.P(bk.toplam_birikim))
    st.caption(b.t("formul", g=b.P(gelir), k=b.P(kart_harcama), d=b.P(kart_disi))
               + (b.t("bes_gitti", x=b.P(bes_toplam)) if bes_birikim else ""))
    taksit = sum(o.sonraki_taksit for o in ozetler)
    if taksit:
        st.caption(b.t("taksit_bilgi", x=b.P(taksit),
                       y=b.P(sum(o.kalan_taksit for o in ozetler))))
    if bk.yatirilabilir <= 0:
        st.warning(b.t("acik"))

    # --- 4. Hedefler -------------------------------------------------------------------------------
    st.subheader(b.t("adim4"))
    depo = yerel_depo()
    hedefler = depo.hedefler()
    tablo = pd.DataFrame([{"ad": h.ad, "tutar": h.tutar, "tarih": h.tarih, "mevcut": h.mevcut,
                           "oncelik": h.oncelik, "risk": h.risk} for h in hedefler],
                         columns=["ad", "tutar", "tarih", "mevcut", "oncelik", "risk"])
    duzen = st.data_editor(tablo, num_rows="dynamic", hide_index=True, width="stretch",
                           key="hedef_tablosu", column_config={
                               "ad": st.column_config.TextColumn(b.t("c_hedef")),
                               "tutar": st.column_config.NumberColumn(b.t("c_tutar", s=s),
                                                                      min_value=0.0),
                               "tarih": st.column_config.DateColumn(b.t("c_tarih"),
                                                                    min_value=date.today()),
                               "mevcut": st.column_config.NumberColumn(b.t("c_mevcut_elle"),
                                                                       min_value=0.0),
                               "oncelik": st.column_config.SelectboxColumn(b.t("c_oncelik"),
                                                                           options=[1, 2, 3]),
                               "risk": st.column_config.SelectboxColumn(
                                   b.t("c_risk"), options=list(RISKLER),
                                   format_func=lambda r: b.t(f"risk_{r}"))})
    if st.button(b.t("hedef_kaydet")):
        for h in hedefler:
            depo.hedef_sil(h.ad)
        for h in filter(None, map(satirdan_hedef, duzen.to_dict("records"))):
            depo.hedef_kaydet(h)
        st.rerun()
    if not hedefler:
        st.info(b.t("hedef_ekle"))
        st.stop()

    degerleme, _, _ = birikim_degerlemesi(b)
    bagli = hedef_mevcutlari(degerleme) if degerleme is not None else {}
    if any(h.ad in bagli for h in hedefler):  # Birikimlerim'de hedefe dahil edilenler eklenir
        hedefler = [replace(h, mevcut=round(h.mevcut + bagli.get(h.ad, 0.0), 2)) for h in hedefler]
        st.caption(b.t("mevcut_varliktan"))

    # --- 5. Portföy --------------------------------------------------------------------------------
    st.subheader(b.t("adim5"))
    # Gereken katkı beklenen (ortalama) getiriyle hesaplanır: hedefe kalanın bir kısmını getiri karşılar.
    planlar = birikimi_dagit(hedefler, max(0.0, bk.yatirilabilir), simulasyon=False)
    if degerleme is not None:
        from .varlik import planlara_dengeleme_uygula
        planlara_dengeleme_uygula(planlar, degerleme)
    kaynak = (pf.PARAMETRE_KAYNAGI if b.ulke.kod == "TR" and pf.PARAMETRE_KAYNAGI != "varsayım"
              else b.t("kaynak_diger"))
    e = f"{b.enflasyon * 100:.1f}".rstrip("0").rstrip(".")
    st.caption(b.t("kaynak_notu", ulke=b.ulke.ad, kaynak=kaynak, e=e))
    satirlar = []
    for p in planlar:
        k = hedef_kalani(p, b.enflasyon)
        satirlar.append({
            b.t("c_hedef"): p.hedef.ad, b.t("c_vade"): b.t(f"vade_{p.vade}"),
            b.t("c_kalan_ay"): p.ay_sayisi, b.t("c_mevcut"): b.P(p.hedef.mevcut),
            b.t("c_kalan"): b.P(k["kalan"]),
            b.t("c_getiri"): b.t("getiri_bicim", n=_yuzde_sayi(k["nominal"]),
                                 r=_yuzde_sayi(p.beklenen_reel_getiri)),
            b.t("c_getiriden"): b.P(k["getiriden"]), b.t("c_yatirilacak"): b.P(k["yatirilacak"]),
            b.t("c_aylik"): b.P(p.gerekli_aylik_katki), b.t("c_ayrilan"): b.P(p.onerilen_aylik_katki)})
    st.dataframe(pd.DataFrame(satirlar), hide_index=True, width="stretch")
    for p in planlar:
        for u in uyarilar(b, p):
            st.warning(f"{p.hedef.ad}: {u}")

    for p in planlar:
        baslik = (f"{p.hedef.ad} ({b.t(f'vade_{p.vade}')}, {b.t(f'risk_{p.hedef.risk}')}) — "
                  f"{b.P(p.onerilen_aylik_katki)}")
        with st.expander(baslik):
            if p.mevcut_dagilim:
                st.caption(b.t("bagli", x=b.P(sum(p.mevcut_dagilim.values()))))
            st.dataframe(pd.DataFrame([{b.t("c_varlik"): pf.VARLIK_SINIFLARI[k].ad,
                                        b.t("c_oran"): b.yuzde(v),
                                        b.t("c_bu_ay"): b.P(p.katki_dagilimi.get(k))}
                                       for k, v in p.dagilim.items()]),
                         hide_index=True, width="stretch")

    toplam = {k: v for k, v in toplam_dagilim(planlar).items() if v >= 1}
    if toplam:
        st.markdown(f"**{b.t('alim_listesi')}**")
        sirali = sorted(toplam.items(), key=lambda kv: kv[1])
        st.plotly_chart(_cubuk([pf.VARLIK_SINIFLARI[k].ad for k, _ in sirali],
                               [v for _, v in sirali], PALET[2]), width="stretch")
        st.dataframe(pd.DataFrame([{b.t("c_varlik"): pf.VARLIK_SINIFLARI[k].ad,
                                    b.t("c_tutar", s=s): b.P(v)}
                                   for k, v in sorted(toplam.items(), key=lambda kv: -kv[1])]),
                     hide_index=True, width="stretch")
        if b.ulke.kod == "TR":
            fon_onerileri(b, toplam)
        elif b.ulke.etfler:
            etf_onerileri(b, toplam)
    from .sayfa_birikim import alimlar_bolumu
    alimlar_bolumu(b, onerilen=sum(p.onerilen_aylik_katki for p in planlar), anahtar="plan_alim")
    st.caption(b.t("uyari"))
