"""Gelecek ay bütçesi: taksitler, sabit/zorunlu giderler, değişken harcama tahmini ve limitler."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .analiz import _hazirla, duzenli_odemeler
from .gelir import SabitGelir, tanimli_gelir
from .kategori import GELIR_DISI
from .metin import isyeri_anahtari


@dataclass
class SabitGider:
    """Kullanıcının tanımladığı sabit ödeme (kira, kredi taksiti, aidat, okul taksiti...)."""
    ad: str
    tutar: float
    kategori: str = "Kira"
    bitis: date | None = None  # bu aydan sonra ödenmeyecekse


@dataclass
class ButcePlani:
    hedef_ay: pd.Period
    beklenen_gelir: float
    taksitler: pd.DataFrame
    sabitler: pd.DataFrame
    degisken: pd.DataFrame
    birikim_hedefi: float
    birikim_onerilen: float
    ek_birikim: float
    acik: float
    notlar: list[str] = field(default_factory=list)
    gelir_kaynagi: str = "ekstre"

    @property
    def taksit_toplam(self) -> float:
        return round(float(self.taksitler["tutar"].sum()), 2) if len(self.taksitler) else 0.0

    @property
    def sabit_toplam(self) -> float:
        return round(float(self.sabitler["tutar"].sum()), 2) if len(self.sabitler) else 0.0

    @property
    def degisken_toplam(self) -> float:
        return round(float(self.degisken["onerilen"].sum()), 2) if len(self.degisken) else 0.0


def taksit_planlari(df: pd.DataFrame) -> pd.DataFrame:
    """Her taksitli alışverişin son görülen durumunu döndürür."""
    d = df[df["taksit_toplam"].notna() & (df["tutar"] < 0)].copy()
    cols = ["hesap", "isyeri", "aciklama", "tutar", "taksit_no", "taksit_toplam", "son_ay"]
    if d.empty:
        return pd.DataFrame(columns=cols)
    d["isyeri"] = d["aciklama"].map(isyeri_anahtari)
    d["tutar_yuvarlak"] = (-d["tutar"]).round(0)
    d["ay"] = pd.to_datetime(d["tarih"]).dt.to_period("M")
    d = d.sort_values(["tarih", "taksit_no"])
    son = d.groupby(["hesap", "isyeri", "taksit_toplam", "tutar_yuvarlak"], as_index=False).last()
    son["tutar"] = -son["tutar"]
    son = son.rename(columns={"ay": "son_ay"})
    return son[cols].reset_index(drop=True)


def taksit_takvimi(df: pd.DataFrame, baslangic: pd.Period, ay_sayisi: int = 12) -> pd.DataFrame:
    """Önümüzdeki aylarda ödenecek taksitler (satır = plan, sütun = ay)."""
    planlar = taksit_planlari(df)
    aylar = [baslangic + i for i in range(ay_sayisi)]
    satirlar = []
    for _, p in planlar.iterrows():
        satir = {"isyeri": p["isyeri"], "hesap": p["hesap"], "taksit_tutari": p["tutar"],
                 "toplam_taksit": int(p["taksit_toplam"])}
        for ay in aylar:
            sira = int(p["taksit_no"]) + (ay - p["son_ay"]).n
            satir[str(ay)] = p["tutar"] if 1 <= sira <= int(p["taksit_toplam"]) and ay > p["son_ay"] \
                else 0.0
        if any(satir[str(a)] for a in aylar):
            satirlar.append(satir)
    return pd.DataFrame(satirlar, columns=["isyeri", "hesap", "taksit_tutari", "toplam_taksit",
                                           *map(str, aylar)])


def _ay_taksitleri(df: pd.DataFrame, hedef_ay: pd.Period) -> pd.DataFrame:
    planlar = taksit_planlari(df)
    satirlar = []
    for _, p in planlar.iterrows():
        if hedef_ay <= p["son_ay"]:
            continue
        sira = int(p["taksit_no"]) + (hedef_ay - p["son_ay"]).n
        toplam = int(p["taksit_toplam"])
        if 1 <= sira <= toplam:
            satirlar.append({"isyeri": p["isyeri"], "hesap": p["hesap"], "tutar": p["tutar"],
                             "taksit": f"{sira}/{toplam}", "kalan_taksit": toplam - sira,
                             "kalan_borc": round(p["tutar"] * (toplam - sira + 1), 2)})
    return pd.DataFrame(satirlar, columns=["isyeri", "hesap", "tutar", "taksit", "kalan_taksit",
                                           "kalan_borc"])


def _tam_aylar(d: pd.DataFrame) -> list[pd.Period]:
    """Analizde kullanılacak tamamlanmış aylar (son ay ayın 25'inden önce bitiyorsa yarım sayılır)."""
    aylar = sorted(d["ay"].unique())
    if len(aylar) > 1:
        son_tarih = pd.to_datetime(d["tarih"]).max()
        if son_tarih.day < 25:
            aylar = aylar[:-1]
    return aylar


def gelecek_ay_plani(df: pd.DataFrame, sabit_giderler: list[SabitGider] | None = None,
                     birikim_hedefi: float = 0.0, aylik_enflasyon: float = 0.02,
                     beklenen_gelir: float | None = None, hedef_ay: pd.Period | str | None = None,
                     gecmis_ay: int = 3,
                     zorunlu_kategoriler: set[str] | None = None,
                     istege_taban: float = 0.5,
                     gelirler: list[SabitGelir] | None = None) -> ButcePlani:
    """Son `gecmis_ay` ayın verisinden gelecek ayın bütçesini çıkarır.

    - Taksitler: ekstrelerdeki 'TAKSİT k/n' ifadelerinden.
    - Sabitler: kullanıcının tanımladıkları + düzenli olarak tespit edilen ödemeler.
    - Değişken: kategori bazında son ayların medyanı x enflasyon düzeltmesi.
    - Limitler: gelir - taksit - sabit - birikim hedefi bütçesine sığacak şekilde; sığmazsa önce
      isteğe bağlı kategoriler en fazla `istege_taban` oranına kadar kısılır, yine sığmazsa
      birikim hedefi düşürülür, o da yetmezse isteğe bağlı harcamalar sıfırlanır.
    """
    notlar: list[str] = []
    d = _hazirla(df)
    if d.empty:
        raise ValueError("Analiz için işlem yok. Önce ekstre yükleyin.")
    son_ay = d["ay"].max()
    hedef_ay = pd.Period(hedef_ay, "M") if hedef_ay is not None else son_ay + 1
    aylar = _tam_aylar(d)[-gecmis_ay:]
    if len(aylar) < 2:
        notlar.append("2 aydan az tamamlanmış veri var; tahminler kaba olacaktır.")
    pencere = d[d["ay"].isin(aylar)]

    # 1) Taksitler
    taksitler = _ay_taksitleri(df, hedef_ay)

    # 2) Sabit giderler
    sabit_satirlar = []
    for s in sabit_giderler or []:
        if s.bitis and pd.Period(s.bitis, "M") < hedef_ay:
            continue
        sabit_satirlar.append({"ad": s.ad, "kategori": s.kategori, "tutar": float(s.tutar),
                               "kaynak": "tanımlı"})
    duzenli = duzenli_odemeler(df)
    for _, r in duzenli.iterrows():
        cakisan = any(x["kategori"] == r["kategori"]
                      and abs(x["tutar"] - r["tipik_tutar"]) <= 0.15 * max(x["tutar"], 1)
                      for x in sabit_satirlar)
        if not cakisan:
            sabit_satirlar.append({"ad": r["isyeri"], "kategori": r["kategori"],
                                   "tutar": float(r["tipik_tutar"]), "kaynak": "tespit"})
    sabitler = pd.DataFrame(sabit_satirlar, columns=["ad", "kategori", "tutar", "kaynak"])
    if len(sabitler):
        # Tanımlı tutarlar sözleşmeyle sabittir; tespit edilen faturalar enflasyonla artar.
        tespit = sabitler["kaynak"] == "tespit"
        sabitler.loc[tespit, "tutar"] = (sabitler.loc[tespit, "tutar"] * (1 + aylik_enflasyon)
                                         ).round(2)

    # 3) Değişken harcamalar (taksit ve düzenli ödemeler hariç)
    duzenli_isyerleri = set(duzenli["isyeri"])
    gider = pencere[(pencere["tutar"] < 0) & pencere["taksit_toplam"].isna()].copy()
    gider["isyeri"] = gider["aciklama"].map(isyeri_anahtari)
    gider = gider[~gider["isyeri"].isin(duzenli_isyerleri)]
    tablo = (-gider.pivot_table(index="ay", columns="kategori", values="tutar", aggfunc="sum")
             ).reindex(aylar).fillna(0)
    if zorunlu_kategoriler is None:
        zorunlu_kategoriler = (set(df.loc[df["zorunlu"].astype(bool), "kategori"])
                               if "zorunlu" in df.columns else set())
    carpan = (1 + aylik_enflasyon) ** 2  # son ayların ortası hedef aydan ~2 ay önce
    tahmin = tablo.median() * carpan if len(tablo.columns) else pd.Series(dtype=float)
    # Tanımlı sabit giderler zaten ekstrede görünüyorsa (ör. kira havalesi) çift sayma.
    for kat, tutar in sabitler[sabitler["kaynak"] == "tanımlı"].groupby("kategori")["tutar"].sum(
            ).items():
        if kat in tahmin.index:
            tahmin[kat] = max(0.0, tahmin[kat] - tutar)
    degisken = pd.DataFrame({"kategori": tahmin.index, "tahmin": tahmin.round(2).values})
    degisken["zorunlu"] = degisken["kategori"].isin(zorunlu_kategoriler)
    degisken = degisken[degisken["tahmin"] > 0].sort_values(
        ["zorunlu", "tahmin"], ascending=[False, False]).reset_index(drop=True)

    # 4) Gelir: elle girilen > tanımlı düzenli gelir (zamlar dahil) > ekstrelerin medyanı
    gelir_kaynagi = "elle"
    if beklenen_gelir is None and gelirler and tanimli_gelir(gelirler, hedef_ay):
        beklenen_gelir, gelir_kaynagi = tanimli_gelir(gelirler, hedef_ay), "tanımlı"
    if beklenen_gelir is None:
        gelir_kaynagi = "ekstre"
        gelir = pencere[(pencere["tutar"] > 0) & ~pencere["kategori"].isin(GELIR_DISI)]
        aylik_gelir = gelir.groupby("ay")["tutar"].sum().reindex(aylar).fillna(0)
        beklenen_gelir = float(aylik_gelir.median()) if len(aylik_gelir) else 0.0
        if beklenen_gelir == 0:
            notlar.append("Ekstrelerde gelir bulunamadı. Maaşınızı tanımlayın: "
                          "kumbara gelir ekle Maaş 60000 (veya panelde 'Düzenli gelirler').")

    # 5) Limitler
    taksit_t = float(taksitler["tutar"].sum()) if len(taksitler) else 0.0
    sabit_t = float(sabitler["tutar"].sum()) if len(sabitler) else 0.0
    kullanilabilir = beklenen_gelir - taksit_t - sabit_t - birikim_hedefi
    zorunlu_t = float(degisken.loc[degisken["zorunlu"], "tahmin"].sum())
    istege_t = float(degisken.loc[~degisken["zorunlu"], "tahmin"].sum())
    degisken["onerilen"] = degisken["tahmin"]
    birikim_onerilen, ek_birikim, acik = birikim_hedefi, 0.0, 0.0

    istege = ~degisken["zorunlu"]

    def istege_olcekle(oran: float) -> None:
        degisken.loc[istege, "onerilen"] = (degisken.loc[istege, "tahmin"] * oran).round(2)

    if kullanilabilir >= zorunlu_t + istege_t:
        ek_birikim = kullanilabilir - zorunlu_t - istege_t
    elif kullanilabilir >= zorunlu_t + istege_taban * istege_t:
        oran = (kullanilabilir - zorunlu_t) / istege_t if istege_t else 0
        istege_olcekle(oran)
        notlar.append(f"Birikim hedefine ulaşmak için isteğe bağlı harcamalar %{(1 - oran) * 100:.0f} "
                      "kısıldı.")
    else:
        # İsteğe bağlı harcamalar en fazla tabana kadar kısılır; kalan açık birikimden düşülür.
        istege_kalan = istege_taban * istege_t
        eksik = zorunlu_t + istege_kalan - kullanilabilir
        birikim_onerilen = max(0.0, birikim_hedefi - eksik)
        notlar.append(f"Gelir; zorunlu giderler, taksitler ve birikim hedefinin tamamına yetmiyor. "
                      f"İsteğe bağlı harcamalar %{(1 - istege_taban) * 100:.0f} kısıldı, bu ay "
                      f"birikime {_tl(birikim_onerilen)} ayrılabiliyor.")
        kalan_eksik = max(0.0, eksik - birikim_hedefi)
        if kalan_eksik:
            # Birikim sıfırlandı ama hâlâ açık var: isteğe bağlıyı tamamen kes.
            kesinti = min(istege_kalan, kalan_eksik)
            istege_kalan -= kesinti
            acik = kalan_eksik - kesinti
            notlar.append("İsteğe bağlı harcamalar da sıfırlanmak zorunda kaldı.")
        istege_olcekle(istege_kalan / istege_t if istege_t else 0)
        if acik:
            notlar.append(f"Gelecek ay yaklaşık {_tl(acik)} açık bekleniyor.")

    return ButcePlani(hedef_ay=hedef_ay, beklenen_gelir=round(beklenen_gelir, 2),
                      gelir_kaynagi=gelir_kaynagi,
                      taksitler=taksitler, sabitler=sabitler, degisken=degisken,
                      birikim_hedefi=round(birikim_hedefi, 2),
                      birikim_onerilen=round(birikim_onerilen, 2), ek_birikim=round(ek_birikim, 2),
                      acik=round(acik, 2), notlar=notlar)


def _tl(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".") + " TL"
