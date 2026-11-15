"""Harcama analizi: aylık özet, kategori kırılımı, düzenli (tekrarlayan) ödemeler."""

from __future__ import annotations

import pandas as pd

from .gelir import SabitGelir, tanimli_gelir
from .kategori import GELIR_DISI, NOTR_KATEGORILER
from .metin import isyeri_anahtari


def _hazirla(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ay"] = pd.to_datetime(df["tarih"]).dt.to_period("M")
    return df[~df["kategori"].isin(NOTR_KATEGORILER)]


def aylik_ozet(df: pd.DataFrame, gelirler: list[SabitGelir] | None = None) -> pd.DataFrame:
    """Ay bazında gelir, gider, net ve birikim oranı.

    gelirler: tanımlı düzenli gelirler (maaş vb.). Ekstrede o ay "Maaş" görünüyorsa ekstre
    kullanılır; görünmüyorsa (ör. yalnızca kart ekstresi yüklendiyse) tanımlı gelir eklenir.
    """
    d = _hazirla(df)
    gelir = d[(d["tutar"] > 0) & ~d["kategori"].isin(GELIR_DISI)].groupby("ay")["tutar"].sum()
    maasli_aylar = set(d.loc[(d["tutar"] > 0) & (d["kategori"] == "Maaş"), "ay"])
    # İadeler giderden düşülür.
    iade = d[(d["tutar"] > 0) & (d["kategori"] == "İade")].groupby("ay")["tutar"].sum()
    gider = -d[d["tutar"] < 0].groupby("ay")["tutar"].sum()
    ozet = pd.DataFrame({"gelir": gelir, "gider": gider.sub(iade, fill_value=0)}).fillna(0)
    ozet["gelir_kaynagi"] = "ekstre"
    if gelirler:
        for ay in ozet.index:
            ek = tanimli_gelir(gelirler, ay)
            if ek and ay not in maasli_aylar:
                ozet.loc[ay, "gelir"] += ek
                ozet.loc[ay, "gelir_kaynagi"] = "tanımlı" if ozet.loc[ay, "gelir"] == ek else (
                    "ekstre + tanımlı")
    ozet["net"] = ozet["gelir"] - ozet["gider"]
    ozet["birikim_orani"] = (ozet["net"] / ozet["gelir"]).where(ozet["gelir"] > 0)
    ozet = ozet.sort_index()
    ozet["kumulatif_net"] = ozet["net"].cumsum()  # ekstrelere göre biriken nakit (gelir - gider)
    return ozet.round({"gelir": 2, "gider": 2, "net": 2, "birikim_orani": 4, "kumulatif_net": 2})


def kategori_kirilimi(df: pd.DataFrame, ay: str | pd.Period | None = None) -> pd.DataFrame:
    """Harcamaların kategoriye göre dağılımı (ay verilmezse tüm dönem)."""
    d = _hazirla(df)
    d = d[d["tutar"] < 0]
    if ay is not None:
        d = d[d["ay"] == pd.Period(ay, "M")]
    t = (-d.groupby("kategori")["tutar"].sum()).sort_values(ascending=False)
    sonuc = pd.DataFrame({"tutar": t, "pay": t / t.sum() if t.sum() else 0})
    return sonuc.round({"tutar": 2, "pay": 4})


def kategori_aylik(df: pd.DataFrame) -> pd.DataFrame:
    """Satırlar ay, sütunlar kategori olan harcama tablosu."""
    d = _hazirla(df)
    d = d[d["tutar"] < 0]
    return (-d.pivot_table(index="ay", columns="kategori", values="tutar", aggfunc="sum")
            ).fillna(0).round(2)


# Doğası gereği değişken olan kategoriler: her ay görülseler de "sabit ödeme" sayılmaz,
# değişken bütçe limitine girerler.
DEGISKEN_KATEGORILER = {"Market", "Yeme-İçme", "Yakıt", "Ulaşım", "Online Alışveriş", "Giyim",
                        "Elektronik", "Eğlence", "Nakit Çekim", "Seyahat", "Sağlık",
                        "Banka Masrafı"}


def duzenli_odemeler(df: pd.DataFrame, en_az_ay: int = 3, pencere_ay: int = 4,
                     max_sapma: float = 0.25, ayda_en_fazla: float = 2.0) -> pd.DataFrame:
    """Son `pencere_ay` ayın en az `en_az_ay` ayında benzer tutarla görülen ödemeler
    (kira, fatura, abonelik, sigorta, düzenli havale...).

    Taksitler ve doğası gereği değişken kategoriler (market, yakıt...) hariç tutulur; ayda
    ortalama `ayda_en_fazla` işlemden sık görülen işyerleri de düzenli ödeme sayılmaz.
    """
    d = _hazirla(df)
    d = d[(d["tutar"] < 0) & d["taksit_toplam"].isna()
          & ~d["kategori"].isin(DEGISKEN_KATEGORILER)].copy()
    if d.empty:
        return pd.DataFrame(columns=["isyeri", "kategori", "tipik_tutar", "ay_sayisi", "son_tarih"])
    son_ay = d["ay"].max()
    d = d[d["ay"] > son_ay - pencere_ay]
    d["isyeri"] = d["aciklama"].map(isyeri_anahtari)
    aylik = d.groupby(["isyeri", "ay"]).agg(tutar=("tutar", "sum"), kategori=("kategori", "first"),
                                            son_tarih=("tarih", "max"), adet=("tutar", "size")
                                            ).reset_index()
    satirlar = []
    for isyeri, g in aylik.groupby("isyeri"):
        if g["ay"].nunique() < en_az_ay or g["adet"].mean() > ayda_en_fazla:
            continue
        tutarlar = -g["tutar"]
        sapma = tutarlar.std(ddof=0) / tutarlar.mean() if tutarlar.mean() else 1
        if sapma > max_sapma:
            continue
        satirlar.append({"isyeri": isyeri, "kategori": g["kategori"].mode().iat[0],
                         "tipik_tutar": round(float(tutarlar.median()), 2),
                         "ay_sayisi": int(g["ay"].nunique()), "son_tarih": g["son_tarih"].max()})
    sonuc = pd.DataFrame(satirlar, columns=["isyeri", "kategori", "tipik_tutar", "ay_sayisi",
                                            "son_tarih"])
    return sonuc.sort_values("tipik_tutar", ascending=False).reset_index(drop=True)


def en_cok_harcanan_yerler(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    d = _hazirla(df)
    d = d[d["tutar"] < 0].copy()
    d["isyeri"] = d["aciklama"].map(isyeri_anahtari)
    g = d.groupby("isyeri").agg(toplam=("tutar", "sum"), adet=("tutar", "size"),
                                kategori=("kategori", "first"))
    g["toplam"] = -g["toplam"]
    return g.sort_values("toplam", ascending=False).head(n).round(2)
