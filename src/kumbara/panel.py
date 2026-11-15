"""Streamlit paneli:  kumbara panel   (veya: streamlit run src/kumbara/panel.py)"""

from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from kumbara import UYARI
from kumbara import portfoy as pf
from kumbara.analiz import aylik_ozet, duzenli_odemeler, kategori_aylik, kategori_kirilimi
from kumbara.butce import SabitGider, gelecek_ay_plani, taksit_takvimi
from kumbara.depo import Depo, veri_dizini, yerel_depo
from kumbara.ekstre import EkstreHatasi, oku
from kumbara.gorsel import GORSEL_UZANTILARI
from kumbara.kategori import Kategorilendirici
from kumbara.portfoy import (
    RISKLER,
    VARLIK_SINIFLARI,
    Hedef,
    birikimi_dagit,
    ppf_reel_getiri_guncelle,
    toplam_dagilim,
    varsayimlari_yukle,
)
from kumbara.tahmin import Parametreler

# Sabit sıralı kategorik palet (renk varlığa bağlı, sıraya değil). Gri: "Diğer".
PALET = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
GRI = "#8a8985"
VARLIK_RENK = {kod: PALET[i] for i, kod in enumerate(VARLIK_SINIFLARI)}

st.set_page_config(page_title="kumbara", page_icon="🐷", layout="wide")


def tl(x) -> str:
    return "-" if x is None or pd.isna(x) else (
        f"{x:,.0f}".replace(",", ".") + " TL")


def _yerlesim(fig: go.Figure, baslik: str | None = None, yukseklik: int = 340) -> go.Figure:
    fig.update_layout(title=baslik, height=yukseklik, margin=dict(l=8, r=8, t=40 if baslik else 8, b=8),
                      bargap=0.35, hovermode="x unified",
                      legend=dict(orientation="h", y=-0.15, traceorder="normal"),
                      separators=",.")
    fig.update_layout(barcornerradius=4, bargroupgap=0.08)
    if not any(getattr(t, "orientation", None) == "h" for t in fig.data):
        fig.update_xaxes(type="category")  # "2026-05" ayları tarih gibi yorumlanmasın
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    fig.update_traces(marker_line_width=0)
    return fig


def depo() -> Depo:
    return yerel_depo()  # iş parçacığı başına bağlantı (paylaşılan bağlantı sonuçları bozuyordu)


def kategorilendirici() -> Kategorilendirici:
    return Kategorilendirici.varsayilan(veri_dizini() / "kategoriler.yaml")


@st.cache_data(ttl=900, show_spinner="Piyasa verisi alınıyor…")
def piyasa_ozeti() -> dict:
    from kumbara.piyasa import Piyasa
    p = Piyasa(veri_dizini())
    ozet = p.ozet()
    ozet["_hatalar"] = dict(p.hatalar)
    return ozet


def islemler() -> pd.DataFrame:
    df = depo().islemler()
    if df.empty:
        return df
    df = kategorilendirici().uygula(df)
    return df


# --- Kenar çubuğu: ekstre yükleme --------------------------------------------------------------
with st.sidebar:
    st.header("Ekstre yükle")
    dosyalar = st.file_uploader("CSV / XLSX / PDF / ekran görüntüsü (JPG, PNG)",
                                accept_multiple_files=True,
                                type=["csv", "txt", "xlsx", "xls", "pdf", "jpg", "jpeg", "png",
                                      "webp", "heic"])
    gorsel_var = any(Path(f.name).suffix.lower() in GORSEL_UZANTILARI for f in dosyalar or [])
    mevcut_hesaplar = sorted({h for _, h, _ in depo().kaynaklar()})
    secim = st.selectbox("Hesap", ["(otomatik / yeni)"] + mevcut_hesaplar,
                         help="Dönem içi görüntüsü hangi karta ait? Ekstresiyle eşleşmesi için aynı "
                              "hesabı seçin.")
    hesap = (st.text_input("Yeni hesap adı", placeholder="ör. Garanti Bonus")
             if secim == "(otomatik / yeni)" else secim)
    kart_secilmedi = gorsel_var and not hesap
    if kart_secilmedi:
        st.warning("Ekran görüntüsü hangi karta ait? Yukarıdan kartı seçin (ekstresiyle eşleşmesi "
                   "için ekstrenin yüklendiği adla aynı olmalı).")
    donem_ici = st.checkbox("Görüntüler dönem içi işlemler (henüz ekstreye girmedi)", value=True,
                            disabled=not gorsel_var,
                            help="Ekstre gelince bu işlemler otomatik olarak ekstredekilerle "
                                 "değiştirilir; çift sayılmaz.")
    tur = st.selectbox("Tür", ["otomatik", "hesap", "kart"],
                       help="Kart ekstresinde harcamalar artı yazılır.")
    sifre = st.text_input("PDF şifresi (varsa)", type="password",
                          help="Bazı bankalar ekstre PDF'ini şifreli gönderir.")
    if st.button("Yükle", disabled=not dosyalar or kart_secilmedi, type="primary"):
        kat = kategorilendirici()
        for f in dosyalar:
            with tempfile.TemporaryDirectory() as d:
                ad = Path(f.name)
                gorsel = ad.suffix.lower() in GORSEL_UZANTILARI
                if gorsel:  # telefonlar hep "image.png" adını verebilir: her yükleme ayrı kaynak
                    ad = ad.with_stem(f"{ad.stem}-{datetime.now():%Y%m%d-%H%M%S}")
                yol = Path(d) / ad.name
                yol.write_bytes(f.getvalue())
                try:
                    with st.spinner(f"{f.name} okunuyor…"):
                        df = kat.uygula(oku(yol, hesap=hesap or None, tur=tur,
                                            sifre=sifre or None,
                                            donem_ici=donem_ici if gorsel else None))
                except EkstreHatasi as e:
                    st.error(str(e))
                    if yol.suffix.lower() == ".pdf" or gorsel:
                        from kumbara.gorsel import gorsel_tani
                        from kumbara.pdf_ekstre import tani
                        try:
                            ozet = gorsel_tani(yol, 40) if gorsel else tani(yol, sifre or None, 40)
                        except EkstreHatasi:
                            ozet = None
                        if ozet:
                            with st.expander(f"{f.name}: maskeli düzen (paylaşılabilir)",
                                             expanded=True):
                                st.caption("Rakamlar 9, harfler x ile değiştirildi; isim, kart no "
                                           "ve tutarlar görünmez.")
                                st.code(ozet, language=None)
                    continue
            eklenen = depo().islem_ekle(df)
            r = depo().son_rapor
            ek = [f"{r[k]} {m}" for k, m in (("kesinlesen", "dönem içi işlem ekstreyle kesinleşti"),
                                             ("zaten_ekstrede", "zaten ekstrede, atlandı"),
                                             ("guncellenen", "dönem içi işlem güncellendi")) if r.get(k)]
            st.success(f"{f.name} → {df['hesap'].iat[0]}"
                       f"{' (dönem içi)' if df['donem_ici'].any() else ''}: {eklenen} yeni işlem"
                       + (f" · {'; '.join(ek)}" if ek else ""))
    st.caption(f"Veriler yalnızca bu bilgisayarda: `{depo().yol}`")
    kopyalar = depo().kopya_kaynaklar()
    if kopyalar:
        st.warning("Aynı dosya birden çok hesap adıyla yüklenmiş; işlemleri iki kez sayılıyor: "
                   + "; ".join(f"{k} ({' / '.join(h)})" for k, h in kopyalar.items())
                   + ". Aşağıdan fazla olanı silin.")
    with st.expander("Yüklü dosyalar / sil", expanded=bool(kopyalar)):
        kaynak_listesi = depo().kaynaklar()
        if kaynak_listesi:
            with st.form("hesap_duzelt"):
                st.caption("Hesap adını düzelt (ör. ekran görüntüsünü doğru karta taşı)")
                hangi = st.selectbox("Dosya", kaynak_listesi,
                                     format_func=lambda k: f"{k[1]} · {k[0]} ({k[2]})")
                hesaplar = sorted({h for _, h, _ in kaynak_listesi})
                yeni_hesap = st.selectbox("Yeni hesap", hesaplar)
                if st.form_submit_button("Taşı") and hangi[1] != yeni_hesap:
                    depo().hesap_degistir(hangi[0], hangi[1], yeni_hesap)
                    st.rerun()
        araliklar = {(r.kaynak, r.hesap): f"{r.ilk} → {r.son}"
                     for r in depo().kaynak_ozeti().itertuples()}
        for i, (kaynak, hesap_adi, adet) in enumerate(kaynak_listesi):
            k1, k2 = st.columns([3, 2])
            k1.caption(f"{hesap_adi} · {kaynak} · {adet} işlem · "
                       f"{araliklar.get((kaynak, hesap_adi), '')}")
            if k2.button("Sil", key=f"sil-{i}-{kaynak}-{hesap_adi}"):
                depo().islemleri_sil(kaynak, hesap_adi)
                st.rerun()
    if depo().ornek_var_mi():
        st.warning("Örnek (sentetik) veriler yüklü. Gerçek ekstrelerinizle karışmaması için silin.")
        if st.button("Örnek veriyi sil"):
            depo().ornek_sil()
            st.rerun()
    st.divider()
    cevrimdisi = st.toggle("Çevrimdışı (canlı veri çekme)", value=False)
    enf_elle = st.number_input("Aylık enflasyon varsayımı (%) — 0 = canlı TÜFE", 0.0, 20.0, 0.0,
                               0.1)
    guven = st.slider("Hedefe ulaşma olasılığı hedefi", 50, 95, 80, 5, format="%d%%") / 100

def varlik_degerleme(cevrimdisi_: bool):
    """Varlıkları değerler (15 dk önbellekli), tamamı fiyatlanınca günün kaydını tutar."""
    from kumbara.varlik import Fiyatlayici, degerle
    from kumbara.varlik import ozet as v_ozet
    varliklar = depo().varliklar()
    if not varliklar:
        return None, set()
    anahtar = tuple((v.id, v.tur, v.kod, v.miktar, v.maliyet, v.hedef, v.deger_elle)
                    for v in varliklar)

    @st.cache_data(ttl=900, show_spinner="Varlıklar canlı fiyatla değerleniyor…")
    def _hesapla(anahtar_, cevrimdisi__):
        piyasa_ = None
        if not cevrimdisi__:
            from kumbara.piyasa import Piyasa
            piyasa_ = Piyasa(veri_dizini())
        son = {}
        for detay in depo().varlik_gecmisi()["detay"]:
            son.update(detay.get("fiyatlar") or {})
        f = Fiyatlayici(piyasa_, son_bilinen=son)
        return degerle(depo().varliklar(), f), set(f.eski_fiyatli)

    d, eski = _hesapla(anahtar, cevrimdisi_)
    oz = v_ozet(d)
    if not cevrimdisi_ and not oz["fiyatlanamayan"]:
        depo().varlik_degeri_kaydet(date.today().isoformat(), oz)
    return d, eski


def varliklar_sekmesi(cevrimdisi_: bool) -> None:
    from kumbara.varlik import ALTIN_TURLERI, TURLER, Varlik, sinif_adi
    from kumbara.varlik import ozet as v_ozet
    st.caption("Yatırım hesaplarınızı, fiziki altınınızı, döviz ve TL birikimlerinizi girin. "
               "Kod: fon için TEFAS kodu (AFT), hisse için BIST sembolü (THYAO), altın için "
               f"{', '.join(ALTIN_TURLERI)}, döviz için USD/EUR; nakit ve diğer için serbest ad. "
               "'Diğer' (BES, kripto vb.) için toplam TL değeri 'Elle değer' sütununa yazın.")
    mevcut = depo().varliklar()
    YOK = "(yok)"
    hedef_adlari = [YOK] + [h.ad for h in depo().hedefler()]
    tablo = pd.DataFrame([{"id": v.id, "tur": v.tur, "kod": v.kod, "miktar": v.miktar,
                           "maliyet": v.maliyet, "kurum": v.kurum, "hedef": v.hedef or YOK,
                           "deger_elle": v.deger_elle} for v in mevcut],
                         columns=["id", "tur", "kod", "miktar", "maliyet", "kurum", "hedef",
                                  "deger_elle"])
    duzen = st.data_editor(
        tablo, num_rows="dynamic", hide_index=True, width="stretch", key="varlik_tablo",
        column_config={
            "id": None,
            "tur": st.column_config.SelectboxColumn("Tür", options=list(TURLER), required=True),
            "kod": st.column_config.TextColumn("Kod", required=True),
            "miktar": st.column_config.NumberColumn("Miktar (adet/gram/TL)", min_value=0.0,
                                                    format="%.4f"),
            "maliyet": st.column_config.NumberColumn("Toplam maliyet (TL)", min_value=0.0),
            "kurum": st.column_config.TextColumn("Kurum / yer"),
            "hedef": st.column_config.SelectboxColumn("Bağlı hedef", options=hedef_adlari),
            "deger_elle": st.column_config.NumberColumn("Elle değer (TL)", min_value=0.0)})
    if st.button("Varlıkları kaydet", type="primary"):
        eski_idler = {v.id for v in mevcut}
        kalan = set()
        try:
            for r in duzen.to_dict("records"):
                if not r.get("tur") or not r.get("kod"):
                    continue
                def deger(k, r=r):
                    x = r.get(k)
                    return None if x is None or (isinstance(x, float) and pd.isna(x)) or x == "" else x
                vid = deger("id")
                hedef_ = deger("hedef")
                v = Varlik(r["tur"], r["kod"], float(deger("miktar") or 0), deger("maliyet"),
                           deger("kurum"), None if hedef_ == YOK else hedef_, deger("deger_elle"),
                           int(vid) if vid is not None else None)
                kalan.add(depo().varlik_kaydet(v))
        except ValueError as e:
            st.error(str(e))
        else:
            for vid in eski_idler - kalan:
                depo().varlik_sil(vid)
            st.rerun()
    d, eski = varlik_degerleme(cevrimdisi_)
    if d is None:
        st.info("Henüz varlık yok. Tabloya satır ekleyin ya da terminalde "
                "`kumbara varlik yukle varliklar.csv` kullanın.")
        return
    oz = v_ozet(d)
    m1, m2, m3 = st.columns(3)
    m1.metric("Toplam birikim", tl(oz["toplam"]))
    if oz["maliyet"]:
        m2.metric("Maliyeti girilenler", tl(oz["maliyetli_deger"]),
                  delta=tl(oz["maliyetli_deger"] - oz["maliyet"]),
                  help=f"Toplam maliyet: {tl(oz['maliyet'])}")
    from kumbara.kart import kart_borclari
    tum = islemler()
    borc = float(kart_borclari(tum)["toplam_borc"].sum()) if len(tum) else 0.0
    m3.metric("Net birikim (kart borcu düşülmüş)", tl(oz["toplam"] - borc),
              help=f"Kart borcu {tl(borc)}: dönem içi harcamalar + kalan taksitler; önceki ekstreler "
                   f"ödendi varsayıldı. Hedefe bağlı olmayan: {tl(oz['hedef'].get('', 0))}")
    if oz["fiyatlanamayan"]:
        st.warning(f"{oz['fiyatlanamayan']} varlık fiyatlanamadı (kodu kontrol edin); toplam eksik.")
    if eski:
        st.caption("Canlı fiyatı alınamayıp son bilinen fiyatla değerlenenler: "
                   + ", ".join(sorted(eski)))
    siniflar = sorted(oz["sinif"].items(), key=lambda kv: kv[1])
    if siniflar:
        fig = go.Figure(go.Bar(x=[v for _, v in siniflar], y=[sinif_adi(k) for k, _ in siniflar],
                               orientation="h", marker_color=PALET[0],
                               hovertemplate="%{x:,.0f} TL<extra></extra>"))
        st.plotly_chart(_yerlesim(fig, "Varlık sınıfına göre birikim", 60 + 34 * len(siniflar)),
                        width="stretch")
    gecmis = depo().varlik_gecmisi()
    if len(gecmis) >= 2:
        fig = go.Figure([go.Scatter(x=gecmis["tarih"], y=gecmis["toplam"], name="Toplam değer",
                                    mode="lines+markers", line=dict(width=2, color=PALET[0]),
                                    marker=dict(size=8), hovertemplate="%{y:,.0f} TL")])
        if gecmis["maliyet"].fillna(0).gt(0).any():
            fig.add_scatter(x=gecmis["tarih"], y=gecmis["maliyet"], name="Maliyeti girilenlerin "
                            "maliyeti", mode="lines+markers", line=dict(width=2, color=PALET[1]),
                            marker=dict(size=8), hovertemplate="%{y:,.0f} TL")
        fig.update_xaxes(type="date")
        st.plotly_chart(_yerlesim(fig, "Toplam birikimin seyri", 300), width="stretch")
    else:
        st.caption("Birikim seyri grafiği için her gün değerleme kaydedilir; ikinci kayıttan "
                   "sonra grafik görünür.")
    st.dataframe(d.drop(columns=["id", "sinif", "fiyatlanamadi"]), hide_index=True,
                 width="stretch")


if "tarih_onarimi" not in st.session_state:  # eski sürümlerin OCR tarih hatalarını bir kez onar
    st.session_state["tarih_onarimi"] = depo().donem_ici_tarihlerini_duzelt()
df = islemler()
st.title("kumbara")
_toplamsiz = depo().toplamsiz_kartlar()
if _toplamsiz:
    st.warning("Şu kartların dönem içi işlemleri var ama bankanın ekrandaki toplamı (Güncel Dönem "
               "Borcu / Dönem İçi Harcamalar Toplamı) kayıtlı değil, bu yüzden ekranda görünmeyen "
               f"harcamalar eksik sayılıyor: {', '.join(_toplamsiz)}. Kenar çubuğundaki 'Yüklü "
               "dosyalar / sil' bölümünden bu kartın görüntü kayıtlarını silip, toplamın göründüğü "
               "ekran görüntüsünü yeniden yükleyin.")
if st.session_state["tarih_onarimi"]:
    with st.expander(f"{len(st.session_state['tarih_onarimi'])} dönem içi kaydın yanlış okunmuş "
                     "tarihi düzeltildi (eski sürüm OCR hatası)"):
        st.dataframe(pd.DataFrame(st.session_state["tarih_onarimi"],
                                  columns=["Dosya", "Eski tarih", "Yeni tarih"]), hide_index=True)
if df.empty:
    st.info("Henüz işlem yok. Soldan ekstre yükleyin ya da terminalde `kumbara ornek` çalıştırın. "
            "Aşağıda varlıklarınızı yine de girebilirsiniz.")
    st.subheader("Varlıklar")
    varliklar_sekmesi(cevrimdisi)
    st.stop()

DEGERLEME, _ = varlik_degerleme(cevrimdisi)

ozet_piyasa = {} if cevrimdisi else piyasa_ozeti()
varsayimlari_yukle(veri_dizini() / "varsayimlar.yaml")
PARAM = Parametreler.yukle(veri_dizini() / "parametreler.json")
if PARAM is not None:
    pf.parametreleri_uygula(PARAM)
ppf_reel_getiri_guncelle(ozet_piyasa.get("politika_faizi"), ozet_piyasa.get("tufe_yillik"),
                         ozet_piyasa.get("tufe_son3_yillik"))
if enf_elle:
    aylik_enf = enf_elle / 100
elif ozet_piyasa.get("tufe_aylik") is not None:
    aylik_enf = ozet_piyasa["tufe_aylik"]
else:
    aylik_enf = 0.02

sek_ozet, sek_kat, sek_plan, sek_hedef, sek_varlik, sek_piyasa, sek_islem = st.tabs(
    ["Özet", "Kategoriler", "Gelecek ay", "Hedefler & portföy", "Varlıklar", "Piyasa & KAP",
     "İşlemler"])

# --- Özet --------------------------------------------------------------------------------------
with sek_ozet:
    ao = aylik_ozet(df, depo().gelirler())
    son = ao.iloc[-1]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"Gelir ({ao.index[-1]})", tl(son.gelir))
    k2.metric("Gider", tl(son.gider))
    k3.metric("Net", tl(son.net))
    k4.metric("Birikim oranı", "-" if pd.isna(son.birikim_orani) else f"%{son.birikim_orani*100:.0f}")
    st.caption(f"Ekstrelere göre dönem boyunca biriken nakit (gelir − gider): "
               f"{tl(ao['kumulatif_net'].iloc[-1])}"
               + (f" · Varlıklarınızın bugünkü toplamı: {tl(DEGERLEME['deger'].sum())}"
                  if DEGERLEME is not None else ""))
    x = ao.index.astype(str)
    fig = go.Figure([go.Bar(name="Gelir", x=x, y=ao["gelir"], marker_color=PALET[0],
                            hovertemplate="%{y:,.0f} TL"),
                     go.Bar(name="Gider", x=x, y=ao["gider"], marker_color=PALET[1],
                            hovertemplate="%{y:,.0f} TL")])
    st.plotly_chart(_yerlesim(fig, "Aylık gelir ve gider"), width="stretch")
    fig = go.Figure(go.Scatter(x=x, y=ao["birikim_orani"] * 100, mode="lines+markers",
                               line=dict(width=2, color=PALET[0]), marker=dict(size=8),
                               hovertemplate="%{y:.1f}%", name="Birikim oranı"))
    st.plotly_chart(_yerlesim(fig, "Birikim oranı (%)", 260), width="stretch")

# --- Kategoriler -------------------------------------------------------------------------------
with sek_kat:
    aylar = sorted(pd.to_datetime(df["tarih"]).dt.to_period("M").astype(str).unique())
    secili = st.select_slider("Ay", aylar, value=aylar[-1])
    kir = kategori_kirilimi(df, secili)
    fig = go.Figure(go.Bar(x=kir["tutar"][::-1], y=kir.index[::-1], orientation="h",
                           marker_color=PALET[0], hovertemplate="%{x:,.0f} TL<extra></extra>"))
    st.plotly_chart(_yerlesim(fig, f"{secili} harcama dağılımı", 40 + 28 * len(kir)),
                    width="stretch")
    tablo = kategori_aylik(df)
    ilk = list(tablo.sum().sort_values(ascending=False).index[:7])  # tüm dönemde en büyük 7
    tablo["Diğer kategoriler"] = tablo.drop(columns=ilk).sum(axis=1)
    fig = go.Figure()
    for i, kat in enumerate(ilk + ["Diğer kategoriler"]):
        fig.add_bar(name=kat, x=tablo.index.astype(str), y=tablo[kat],
                    marker_color=PALET[i] if i < 7 else GRI, hovertemplate="%{y:,.0f} TL")
    fig.update_layout(barmode="stack")
    fig.update_traces(marker_line_width=2, marker_line_color="rgba(0,0,0,0)")
    st.plotly_chart(_yerlesim(fig, "Kategori bazında aylık harcama"), width="stretch")
    st.subheader("Düzenli ödemeler")
    st.dataframe(duzenli_odemeler(df), hide_index=True, width="stretch")

# --- Gelecek ay --------------------------------------------------------------------------------
with sek_plan:
    hedefler = depo().hedefler()
    if DEGERLEME is not None:
        from kumbara.varlik import hedeflere_uygula
        hedefler = hedeflere_uygula(hedefler, DEGERLEME)
    gerekli = (sum(p.gerekli_aylik_katki for p in birikimi_dagit(hedefler, guven=guven))
               if hedefler else 0.0)
    c1, c2 = st.columns(2)
    gelir_elle = c1.number_input("Beklenen net gelir (0 = ekstrelerden tahmin)", 0.0, step=1000.0)
    taban = c2.slider("İsteğe bağlı harcamalar en fazla ne kadar kısılabilir?", 0, 100, 50, 5,
                      format="%d%%")
    plan = gelecek_ay_plani(df, depo().sabit_giderler(), gerekli, aylik_enf, gelir_elle or None,
                            zorunlu_kategoriler=kategorilendirici().zorunlu,
                            istege_taban=1 - taban / 100, gelirler=depo().gelirler())
    st.subheader(f"{plan.hedef_ay} bütçesi")
    m = st.columns(5)
    m[0].metric("Beklenen gelir", tl(plan.beklenen_gelir), help=f"Kaynak: {plan.gelir_kaynagi}")
    m[1].metric("Taksitler", tl(plan.taksit_toplam))
    m[2].metric("Sabit/düzenli", tl(plan.sabit_toplam))
    m[3].metric("Değişken limit", tl(plan.degisken_toplam))
    m[4].metric("Birikime", tl(plan.birikim_onerilen + plan.ek_birikim),
                delta=tl(plan.birikim_onerilen + plan.ek_birikim - plan.birikim_hedefi)
                if plan.birikim_hedefi else None)
    for n in plan.notlar:
        st.warning(n)
    st.caption(f"Aylık enflasyon varsayımı: %{aylik_enf*100:.2f}")
    a, b = st.columns(2)
    a.markdown("**Taksitler**")
    a.dataframe(plan.taksitler, hide_index=True, width="stretch")
    b.markdown("**Sabit / düzenli ödemeler**")
    b.dataframe(plan.sabitler, hide_index=True, width="stretch")
    st.markdown("**Değişken harcama limitleri**")
    st.dataframe(plan.degisken, hide_index=True, width="stretch")
    from kumbara.kart import kart_borclari
    kb = kart_borclari(df)
    if len(kb):
        st.markdown("**Kart borçları** — önceki ekstreler ödendi varsayıldı")
        st.dataframe(kb.drop(columns=["donem_ici_var"]).rename(columns={
            "hesap": "Kart", "donem_ici_harcama": "Dönem içi harcama", "donem_ici_iade": "İade",
            "sonraki_taksit": "Sıradaki taksit", "sonraki_ekstre": "Sonraki ekstre ≈",
            "kalan_taksit": "Sonraki aylara kalan taksit", "toplam_borc": "Toplam borç",
            "son_donem_ici": "Son dönem içi işlem"}), hide_index=True, width="stretch")
        st.caption(f"Sonraki ekstreler toplamı {tl(kb['sonraki_ekstre'].sum())}: gelecek ay "
                   "hesabınızdan çıkacak kart ödemesi (bu ayın harcamaları). Yukarıdaki limitler ise "
                   "gelecek ay yapacağınız yeni harcamalar içindir."
                   + ("" if kb["donem_ici_var"].all() else
                      " Dönem içi görüntüsü yüklenmeyen kartlarda yalnızca taksitler görünür."))
    takvim = taksit_takvimi(df, plan.hedef_ay, 12)
    if len(takvim):
        aylar_t = [c for c in takvim.columns if c[:2] == "20"]
        fig = go.Figure(go.Bar(x=aylar_t, y=[takvim[a].sum() for a in aylar_t],
                               marker_color=PALET[1], hovertemplate="%{y:,.0f} TL<extra></extra>"))
        st.plotly_chart(_yerlesim(fig, "Önümüzdeki 12 ayın taksit yükü", 260),
                        width="stretch")
    with st.expander("Düzenli gelirler (maaş, zam)", expanded=not depo().gelirler()):
        st.caption("Zam için aynı adla yeni tutar ve başlangıç ayı girin; o aydan itibaren yeni "
                   "tutar geçerli olur. Ekstrede maaş görünen aylarda ekstredeki tutar kullanılır.")
        with st.form("gelir"):
            g1, g2, g3, g4 = st.columns(4)
            g_ad = g1.text_input("Ad", "Maaş")
            g_tutar = g2.number_input("Aylık net tutar", 0.0, step=1000.0)
            g_bas = g3.text_input("Başlangıç ayı (YYYY-AA, boş = hep)", "")
            g_hesap = g4.text_input("Yattığı hesap", "")
            if st.form_submit_button("Kaydet") and g_ad and g_tutar:
                from kumbara.gelir import SabitGelir, ay_coz
                try:
                    depo().gelir_kaydet(SabitGelir(g_ad, g_tutar, ay_coz(g_bas), None,
                                                   g_hesap or None))
                    st.rerun()
                except ValueError:
                    st.error("Başlangıç ayını YYYY-AA biçiminde girin (ör. 2026-12).")
        for g in depo().gelirler():
            c1, c2 = st.columns([4, 1])
            c1.caption(f"{g.ad}: {tl(g.tutar)}"
                       + (f" · {g.baslangic:%Y-%m} itibarıyla" if g.baslangic else "")
                       + (f" · {g.hesap}" if g.hesap else ""))
            if c2.button("Sil", key=f"gelir-{g.ad}-{g.baslangic}"):
                depo().gelir_sil(g.ad, g.baslangic)
                st.rerun()
    with st.expander("Sabit gider ekle / sil"):
        with st.form("sabit"):
            s1, s2, s3, s4 = st.columns(4)
            ad = s1.text_input("Ad", placeholder="Kira")
            tutar = s2.number_input("Tutar", 0.0, step=500.0)
            kat = s3.text_input("Kategori", "Kira")
            bitis = s4.date_input("Bitiş (isteğe bağlı)", value=None)
            if st.form_submit_button("Kaydet") and ad and tutar:
                depo().sabit_kaydet(SabitGider(ad, tutar, kat, bitis))
                st.rerun()
        for s in depo().sabit_giderler():
            if st.button(f"Sil: {s.ad} ({tl(s.tutar)})", key=f"sabit-{s.ad}"):
                depo().sabit_sil(s.ad)
                st.rerun()

# --- Hedefler & portföy ------------------------------------------------------------------------
with sek_hedef:
    with st.expander("Hedef ekle", expanded=not hedefler), st.form("hedef"):
        h1, h2, h3 = st.columns(3)
        ad = h1.text_input("Hedef", placeholder="Ev peşinatı")
        tutar = h2.number_input("Tutar (bugünün TL'siyle)", 0.0, step=10_000.0)
        tarih = h3.date_input("Hedef tarihi", value=date(date.today().year + 2, 1, 1))
        h4, h5, h6 = st.columns(3)
        mevcut = h4.number_input("Şu an ayrılmış birikim", 0.0, step=1_000.0)
        oncelik = h5.selectbox("Öncelik", [1, 2, 3], index=1)
        risk = h6.selectbox("Risk profili", RISKLER, index=1)
        if st.form_submit_button("Kaydet") and ad and tutar:
            depo().hedef_kaydet(Hedef(ad, tutar, tarih, mevcut, oncelik, risk))
            st.rerun()
    if hedefler:
        planlar = birikimi_dagit(hedefler, plan.birikim_onerilen + plan.ek_birikim, guven=guven)
        if DEGERLEME is not None:
            from kumbara.varlik import planlara_dengeleme_uygula
            planlara_dengeleme_uygula(planlar, DEGERLEME)
        st.caption(f"Getiri/oynaklık kaynağı: {pf.PARAMETRE_KAYNAGI} · katkılar 4.000 senaryoluk Monte "
                   f"Carlo ile %{guven*100:.0f} olasılığa göre")
        satirlar = [{"Hedef": p.hedef.ad, "Vade": p.vade, "Ay": p.ay_sayisi, "Risk": p.hedef.risk,
                     "Tutar": p.hedef.tutar, "Mevcut": p.hedef.mevcut,
                     f"Gerekli aylık (%{guven*100:.0f})": p.gerekli_aylik_katki,
                     "Ortalama getiriyle": p.medyan_katki, "Bu ay ayrılan": p.onerilen_aylik_katki,
                     "Ulaşma olasılığı %": round((p.basari_olasiligi or 0) * 100),
                     "Kötü senaryo (p10)": p.sonuc_araligi.get("p10"),
                     "Orta (p50)": p.sonuc_araligi.get("p50"),
                     "Beklenen reel getiri %": round(p.beklenen_reel_getiri * 100, 1),
                     "Oynaklık %": round(p.beklenen_oynaklik * 100, 1)}
                    for p in planlar]
        st.dataframe(pd.DataFrame(satirlar), hide_index=True, width="stretch")
        fig = go.Figure()
        for kod, vs in VARLIK_SINIFLARI.items():
            fig.add_bar(name=vs.ad, orientation="h", y=[f"{p.hedef.ad} ({p.vade})" for p in planlar],
                        x=[p.dagilim.get(kod, 0) for p in planlar], marker_color=VARLIK_RENK[kod],
                        customdata=[p.katki_dagilimi.get(kod, 0) for p in planlar],
                        hovertemplate="%{x}% · %{customdata:,.0f} TL<extra>" + vs.ad + "</extra>")
        fig.update_layout(barmode="stack", hovermode="closest")
        fig.update_traces(marker_line_width=2, marker_line_color="rgba(0,0,0,0)")
        st.plotly_chart(_yerlesim(fig, "Hedef bazlı model dağılım (%)", 120 + 60 * len(planlar)),
                        width="stretch")
        for p in planlar:
            for u in p.uyarilar:
                st.warning(f"{p.hedef.ad}: {u}")
        toplam = toplam_dagilim(planlar)
        st.markdown("**Bu ay toplam alım dağılımı**")
        st.dataframe(pd.DataFrame([{"Varlık sınıfı": VARLIK_SINIFLARI[k].ad, "Tutar (TL)": v}
                                   for k, v in toplam.items()]), hide_index=True)
        if not cevrimdisi and st.button("TEFAS'tan fon adaylarını getir"):
            from kumbara.piyasa import Piyasa
            pz = Piyasa(veri_dizini())
            for kod in toplam:
                st.markdown(f"*{VARLIK_SINIFLARI[kod].ad}*")
                st.dataframe(pz.fon_adaylari(kod, 5), hide_index=True)
            if pz.hatalar:
                st.error(pz.hatalar)
        sil = st.selectbox("Hedef sil", ["—"] + [h.ad for h in hedefler])
        if sil != "—" and st.button(f"'{sil}' hedefini sil"):
            depo().hedef_sil(sil)
            st.rerun()
    with st.expander("Getiri / oynaklık tahminleri"):
        if PARAM is None:
            st.info("Henüz tahmin yok; uzun vadeli varsayımlar kullanılıyor.")
        else:
            st.dataframe(pd.DataFrame({
                "Varlık sınıfı": [VARLIK_SINIFLARI[k].ad for k in PARAM.reel_getiri],
                "Ay": [PARAM.ay_sayisi.get(k) for k in PARAM.reel_getiri],
                "Tarihsel reel getiri": [PARAM.tarihsel_getiri.get(k) for k in PARAM.reel_getiri],
                "Kullanılan": list(PARAM.reel_getiri.values()),
                "Tarihsel oynaklık": [PARAM.tarihsel_oynaklik.get(k) for k in PARAM.reel_getiri],
                "Kullanılan oynaklık": list(PARAM.oynaklik.values())}), hide_index=True)
            for n in PARAM.notlar:
                st.caption(n)
        if not cevrimdisi and st.button("TEFAS ve TÜFE geçmişinden yeniden tahmin et"):
            from kumbara.piyasa import Piyasa
            from kumbara.tahmin import tahmin_et
            with st.spinner("Fon geçmişleri indiriliyor…"):
                try:
                    tahmin_et(Piyasa(veri_dizini())).kaydet(veri_dizini() / "parametreler.json")
                    st.rerun()
                except RuntimeError as e:
                    st.error(str(e))
    st.caption(UYARI)

# --- Piyasa & KAP ------------------------------------------------------------------------------
with sek_varlik:
    varliklar_sekmesi(cevrimdisi)

with sek_piyasa:
    if cevrimdisi:
        st.info("Çevrimdışı mod açık.")
    else:
        o = ozet_piyasa
        p1, p2, p3, p4, p5 = st.columns(5)
        p1.metric("USD/TRY", o.get("usd_try") or "-")
        p2.metric("EUR/TRY", o.get("eur_try") or "-")
        p3.metric("Gram altın", tl(o.get("gram_altin")))
        p4.metric("Politika faizi", "-" if o.get("politika_faizi") is None
                  else f"%{o['politika_faizi']*100:.2f}")
        p5.metric(f"Yıllık TÜFE ({o.get('tufe_donem') or '-'})", "-" if o.get("tufe_yillik") is None
                  else f"%{o['tufe_yillik']*100:.2f}")
        st.caption(f"Güncelleme: {o.get('zaman')} · TCMB kur tarihi: {o.get('tcmb_kur_tarihi')}")
        if o.get("_hatalar"):
            with st.expander("Alınamayan veriler"):
                st.json(o["_hatalar"])
        if st.button("Yenile"):
            piyasa_ozeti.clear()
            st.rerun()
        semboller = st.text_input("KAP bildirimleri için semboller", "THYAO, ASELS")
        if st.button("Bildirimleri getir"):
            from kumbara.piyasa import Piyasa
            pz = Piyasa(veri_dizini())
            for s in [x.strip() for x in semboller.split(",") if x.strip()]:
                st.markdown(f"**{s.upper()}**")
                st.dataframe(pz.kap_bildirimleri(s, 10), hide_index=True, width="stretch",
                             column_config={"URL": st.column_config.LinkColumn()})
            if pz.hatalar:
                st.error(pz.hatalar)

# --- İşlemler ----------------------------------------------------------------------------------
with sek_islem:
    kategoriler = sorted({k.kategori for k in kategorilendirici().kurallar} | {"Diğer", "Diğer Gelir"}
                         | set(df["kategori"].dropna()))
    k1, k2 = st.columns([3, 2])
    filtre = k1.multiselect("Kategori", kategoriler)
    yeni_kat = k2.text_input("Yeni kategori ekle", placeholder="ör. Spor",
                             help="Listede olmayan bir kategori; ekledikten sonra tabloda seçin.")
    if yeni_kat:
        kategoriler = sorted(set(kategoriler) | {yeni_kat.strip()})
    st.caption("Kategoriyi değiştirip kaydedince, 'kural olarak öğren' açıksa aynı işyerinin "
               "BÜTÜN işlemleri (geçmiş ve gelecek) bu kategoriye geçer.")
    goster = df[df["kategori"].isin(filtre)] if filtre else df
    duzenlenen = st.data_editor(
        goster[["islem_id", "tarih", "aciklama", "tutar", "hesap", "kategori"]].iloc[::-1],
        column_config={"kategori": st.column_config.SelectboxColumn(options=kategoriler),
                       "islem_id": None},
        disabled=["tarih", "aciklama", "tutar", "hesap"], hide_index=True, width="stretch")
    ogren = st.checkbox("Kural olarak öğren (aynı işyerinin tüm işlemlerine uygula)", value=True)
    if st.button("Kategori değişikliklerini kaydet"):
        from kumbara.kategori import kural_ekle
        from kumbara.metin import isyeri_anahtari
        eski = goster.set_index("islem_id")["kategori"]
        aciklamalar = goster.set_index("islem_id")["aciklama"]
        tutarlar = goster.set_index("islem_id")["tutar"]
        degisen = 0
        for r in duzenlenen.itertuples():
            if eski.get(r.islem_id) != r.kategori and r.kategori:
                degisen += 1
                if ogren:
                    kural_ekle(veri_dizini() / "kategoriler.yaml", r.kategori,
                               isyeri_anahtari(aciklamalar[r.islem_id]),
                               "gelir" if tutarlar[r.islem_id] > 0 else "gider")
                else:
                    depo().kategori_ata(r.islem_id, r.kategori)
        if degisen:
            st.rerun()
