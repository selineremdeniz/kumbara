"""Kredi kartı borçları — VARSAYIM: kesinleşmiş (ekstresi kesilmiş) dönemlerin borcu ödendi.

Böylece bir kartın kalan borcu:
  sonraki ekstre ≈ dönem içi harcamalar (henüz ekstreye girmemiş; ekran görüntüsünden)
                   − dönem içi iadeler
                   + ekstrelerdeki taksitli alışverişlerin sıradaki taksiti
  sonraki aylara kalan taksit = taksitli alışverişlerin daha sonraki taksitleri
Dönem içinde karta yapılan ödemeler önceki ekstrenin ödemesi sayılır ve hesaba katılmaz.
"""

from __future__ import annotations

import pandas as pd

from .gorsel import TAKSIT_ACIKLAMA
from .metin import isyeri_anahtari

KOLONLAR = ["hesap", "donem_ici_harcama", "donem_ici_iade", "sonraki_taksit", "sonraki_ekstre",
            "kalan_taksit", "toplam_borc", "son_donem_ici", "donem_ici_var"]


def _taksit_planlari(kart: pd.DataFrame) -> pd.DataFrame:
    """Her taksitli alışverişin son görülen satırı (hesap, işyeri, toplam taksit, tutar)."""
    t = kart[kart["taksit_toplam"].notna() & (kart["tutar"] < 0)].copy()
    if t.empty:
        return t
    t["isyeri"] = t["aciklama"].map(isyeri_anahtari)
    t["tutar_y"] = (-t["tutar"]).round(0)
    t = t.sort_values(["tarih", "taksit_no"])
    return t.groupby(["hesap", "isyeri", "taksit_toplam", "tutar_y"], as_index=False).last()


def kart_borclari(df: pd.DataFrame) -> pd.DataFrame:
    """Kart başına kalan borç tahmini (önceki ekstreler ödendi varsayımıyla)."""
    if df.empty or "kaynak_turu" not in df.columns:
        return pd.DataFrame(columns=KOLONLAR)
    kart = df[df["kaynak_turu"] == "kart"].copy()
    if kart.empty:
        return pd.DataFrame(columns=KOLONLAR)
    if "donem_ici" not in kart.columns:
        kart["donem_ici"] = False
    kategori = kart["kategori"] if "kategori" in kart.columns else pd.Series("", index=kart.index)
    planlar = _taksit_planlari(kart)
    satirlar = []
    for hesap, g in kart.groupby("hesap"):
        di = g[g["donem_ici"]]
        notr = kategori.loc[di.index] == "Transfer"  # karta ödeme asla harcama değil (BES sayılır)
        harcama = float(-di.loc[(di["tutar"] < 0) & ~notr, "tutar"].sum())
        iade = float(di.loc[(di["tutar"] > 0) & (kategori.loc[di.index] != "Transfer"),
                            "tutar"].sum())
        di_isyerleri = {(isyeri_anahtari(a), round(-t)) for a, t in zip(di["aciklama"], di["tutar"],
                                                                         strict=True)}
        sonraki, kalan = 0.0, 0.0
        # Banka ekranındaki toplam bu dönemin taksitlerini içeriyorsa (Yapı Kredi 'Bu Döneme Ait
        # Taksit Tutarı'), ekstrelerden tahmin edilen sıradaki taksit ayrıca eklenmez.
        taksit_dahil = (di["aciklama"] == TAKSIT_ACIKLAMA).any()
        for p in planlar[planlar["hesap"] == hesap].itertuples():
            k, n, tutar = int(p.taksit_no), int(p.taksit_toplam), float(-p.tutar)
            if p.donem_ici:  # yeni taksitli alışveriş dönem içinde: ilk taksiti harcamada sayıldı
                kalan += tutar * (n - k)
                continue
            if k >= n:
                continue
            if taksit_dahil or (p.isyeri, round(tutar)) in di_isyerleri:  # zaten dönem içinde
                kalan += tutar * (n - k - 1)
                continue
            sonraki += tutar
            kalan += tutar * (n - k - 1)
        sonraki_ekstre = harcama - iade + sonraki
        satirlar.append({
            "hesap": hesap, "donem_ici_harcama": round(harcama, 2), "donem_ici_iade": round(iade, 2),
            "sonraki_taksit": round(sonraki, 2), "sonraki_ekstre": round(sonraki_ekstre, 2),
            "kalan_taksit": round(kalan, 2), "toplam_borc": round(sonraki_ekstre + kalan, 2),
            "son_donem_ici": di["tarih"].max() if len(di) else None, "donem_ici_var": bool(len(di))})
    return pd.DataFrame(satirlar, columns=KOLONLAR)
