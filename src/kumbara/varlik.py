"""Varlıklar: yatırım hesapları (TEFAS fonu, BIST hissesi), fiziki altın, döviz ve TL nakit.

Her varlık canlı fiyatla değerlenir, varlık sınıfına (portföy modelindeki) eşlenir ve istenirse bir
birikim hedefine bağlanır. Değerlemeler günlük kaydedilir; böylece toplam birikimin zaman içindeki
seyri ("kümülatif birikim") ve yatırılan para ile piyasa getirisi ayrı ayrı izlenir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from .metin import sade
from .portfoy import VARLIK_SINIFLARI

TURLER = ("fon", "hisse", "yabanci", "altin", "doviz", "nakit", "diger")

# kod -> (canlı fiyat anahtarı, saflık çarpanı, açıklama)
ALTIN_TURLERI: dict[str, tuple[str, float, str]] = {
    "gram": ("gram-altin", 1.0, "Gram altın (24 ayar)"),
    "ceyrek": ("ceyrek-altin", 1.0, "Çeyrek altın (adet)"),
    "yarim": ("yarim-altin", 1.0, "Yarım altın (adet)"),
    "tam": ("tam-altin", 1.0, "Tam altın (adet)"),
    "cumhuriyet": ("cumhuriyet-altin", 1.0, "Cumhuriyet altını (adet)"),
    "ata": ("ata-altin", 1.0, "Ata altın (adet)"),
    "22ayar": ("gram-altin", 0.916, "22 ayar altın / bilezik (gram)"),
    "ajda": ("gram-altin", 0.916, "22 ayar ajda bilezik (gram)"),
    "18ayar": ("gram-altin", 0.750, "18 ayar altın (gram)"),
    "14ayar": ("gram-altin", 0.585, "14 ayar altın (gram)"),
    "gumus": ("gram-gumus", 1.0, "Gram gümüş"),
}

# Portföy modelinde olmayan sınıflar (değerlemeye dahil, hedef dağılımda yok)
EK_SINIFLAR = {"doviz": "Döviz (nakit)", "diger": "Diğer (karma/serbest fon vb.)"}


@dataclass
class Varlik:
    tur: str                    # fon | hisse | yabanci | altin | doviz | nakit | diger
    kod: str                    # TEFAS kodu, BIST sembolü, yurt dışı sembol (VOO, LSE:VWRL), altın
                                # türü, döviz kodu; nakit/diğer: ad
    miktar: float               # pay adedi, gram, adet, döviz tutarı; nakit: TL
    maliyet: float | None = None  # toplam alış maliyeti (TL), kâr/zarar için
    kurum: str | None = None    # "İş Yatırım", "Midas", "Ev", "Kiralık kasa"...
    hedef: str | None = None    # bağlı olduğu birikim hedefinin adı
    deger_elle: float | None = None  # "diger" için toplam TL değer
    id: int | None = None

    def __post_init__(self):
        self.tur = self.tur.strip().lower()
        if self.tur not in TURLER:
            raise ValueError(f"Varlık türü {TURLER} içinden olmalı: {self.tur!r}")
        self.kod = str(self.kod).strip()
        if self.tur in ("fon", "hisse", "yabanci", "doviz"):
            self.kod = self.kod.upper()
        if self.tur == "altin":
            self.kod = sade(self.kod).lower().replace(" ", "").replace("altin", "") or "gram"
            if self.kod not in ALTIN_TURLERI:
                raise ValueError(f"Altın türü {list(ALTIN_TURLERI)} içinden olmalı: {self.kod!r}")


def fon_sinifi(fon_adi: str) -> str:
    """TEFAS fon adından portföy modelindeki varlık sınıfı (eşleşmezse 'diger')."""
    ad = sade(fon_adi)
    for kod in ("ppf", "kisa_borc", "eurobond", "altin", "yabanci_hisse", "bist_hisse", "tl_tahvil"):
        vs = VARLIK_SINIFLARI[kod]
        if re.search(vs.tefas_desen, ad) and not (vs.tefas_haric and re.search(vs.tefas_haric, ad)):
            return kod
    return "diger"


def sinif(v: Varlik, fon_adi: str | None = None) -> str:
    return {"hisse": "bist_hisse", "yabanci": "yabanci_hisse", "altin": "altin", "doviz": "doviz",
            "nakit": "ppf", "diger": "diger"}.get(v.tur) or fon_sinifi(fon_adi or "")


KISA_ADLAR = {"ppf": "TL nakit / mevduat / para piyasası", "kisa_borc": "Kısa vadeli borçlanma",
              "tl_tahvil": "TL tahvil / bono", "eurobond": "Eurobond / dolar tahvil",
              "altin": "Altın / gümüş", "bist_hisse": "BIST hisse", "yabanci_hisse": "Yabancı hisse"}


def sinif_adi(kod: str) -> str:
    return KISA_ADLAR.get(kod) or EK_SINIFLAR.get(kod, kod)


class Fiyatlayici:
    """Canlı birim fiyatlar (çalışma boyunca önbellekli). `piyasa` = kumbara.piyasa.Piyasa.

    son_bilinen: önceki değerlemelerden {"tur:kod": fiyat}; canlı fiyat alınamazsa kullanılır.
    """

    def __init__(self, piyasa=None, sabit: dict[tuple[str, str], tuple[float, str]] | None = None,
                 son_bilinen: dict[str, float] | None = None,
                 borsalar: tuple[str, ...] = ("NASDAQ", "NYSE", "AMEX")):
        self.piyasa = piyasa
        self.borsalar = borsalar
        self.kaynak: dict[tuple[str, str], tuple[str, str]] = {}  # yurt dışı: (sembol, para birimi)
        self.onbellek: dict[tuple[str, str], tuple[float | None, str | None]] = dict(sabit or {})
        self.son_bilinen = son_bilinen or {}
        self.eski_fiyatli: set[str] = set()

    def fiyat(self, v: Varlik) -> tuple[float | None, str | None]:
        """(birim fiyat TL, açıklama/fon adı) — alınamazsa (None, hata)."""
        if v.tur == "nakit":
            return 1.0, "TL"
        if v.deger_elle:  # elle girilen toplam değer her türde canlı fiyatın önüne geçer
            return (v.deger_elle / v.miktar if v.miktar else v.deger_elle), f"{v.kod} (elle)"
        if v.tur == "diger":
            return None, v.kod
        anahtar = (v.tur, v.kod)
        if anahtar not in self.onbellek:
            fiyat, aciklama = self._getir(v)
            yedek = self.son_bilinen.get(f"{v.tur}:{v.kod}")
            if fiyat is None and yedek:
                fiyat, aciklama = yedek, f"{aciklama or v.kod} (son bilinen fiyat)"
                self.eski_fiyatli.add(f"{v.tur}:{v.kod}")
            self.onbellek[anahtar] = (fiyat, aciklama)
        return self.onbellek[anahtar]

    def _getir(self, v: Varlik) -> tuple[float | None, str | None]:
        if self.piyasa is None:
            return None, "çevrimdışı"
        p = self.piyasa
        if v.tur == "fon":
            import borsapy as bp
            info = p._dene(f"fon:{v.kod}", lambda: bp.Fund(v.kod).info)
            return (float(info["price"]), info.get("name")) if info and info.get("price") else (
                None, p.hatalar.get(f"fon:{v.kod}", "fon bulunamadı"))
        if v.tur == "hisse":
            h = p.hisse(v.kod) or {}
            return h.get("last_price"), v.kod
        if v.tur == "altin":
            anahtar, carpan, ad = ALTIN_TURLERI[v.kod]
            f = p.anlik(anahtar)
            return (round(f * carpan, 4) if f else None), ad
        if v.tur == "doviz":
            return self._kur(v.kod), f"{v.kod} (TCMB alış)"
        if v.tur == "yabanci":
            q = p.yabanci(v.kod, self.borsalar)
            if not q:
                return None, p.hatalar.get(f"yabanci:{v.kod}", "sembol bulunamadı")
            kur = self._kur(q["para"])
            self.kaynak[(v.tur, v.kod)] = (q["sembol"], q["para"])
            return (round(q["fiyat"] * kur, 4) if kur else None), f"{q['ad']} ({q['sembol']})"
        return None, None

    def _kur(self, para: str) -> float | None:
        """1 birim dövizin TL karşılığı (TCMB alış; yoksa piyasa)."""
        if para == "TRY":
            return 1.0
        kurlar = self.piyasa.tcmb_kurlari() or {}
        return (kurlar.get(para) or {}).get("alis") or self.piyasa.anlik(para)


def degerle(varliklar: list[Varlik], fiyatlayici: Fiyatlayici) -> pd.DataFrame:
    satirlar = []
    for v in varliklar:
        birim, aciklama = fiyatlayici.fiyat(v)
        deger = round(birim * v.miktar, 2) if birim is not None else None
        s = sinif(v, aciklama if v.tur == "fon" else None)
        kar = round(deger - v.maliyet, 2) if deger is not None and v.maliyet else None
        satirlar.append({
            "id": v.id, "tur": v.tur, "kod": v.kod, "ad": aciklama, "miktar": v.miktar,
            "birim_fiyat": birim, "deger": deger, "maliyet": v.maliyet, "kar": kar,
            "kar_orani": round(kar / v.maliyet, 4) if kar is not None else None,
            "sinif": s, "sinif_adi": sinif_adi(s), "kurum": v.kurum, "hedef": v.hedef,
            "fiyatlanamadi": birim is None, "elle": bool(v.deger_elle) and v.tur != "nakit",
            "kaynak_sembol": fiyatlayici.kaynak.get((v.tur, v.kod), (None, None))[0],
            "kaynak_para": fiyatlayici.kaynak.get((v.tur, v.kod), (None, None))[1]})
    return pd.DataFrame(satirlar, columns=[
        "id", "tur", "kod", "ad", "miktar", "birim_fiyat", "deger", "maliyet", "kar", "kar_orani",
        "sinif", "sinif_adi", "kurum", "hedef", "fiyatlanamadi", "elle", "kaynak_sembol",
        "kaynak_para"])


def yabanci_siniflarini_uygula(degerleme: pd.DataFrame, ulke) -> pd.DataFrame:
    """Yurt dışı hisse/ETF'lerin varlık sınıfını seçilen ülkenin yatırımcısına göre belirler
    (ör. VOO ABD'de yerel hisse, Türkiye'de yabancı hisse; BND Türkiye'de döviz tahvil)."""
    from .ulke import yabanci_sinifi
    d = degerleme.copy()
    for i in d.index[d["tur"] == "yabanci"]:
        k = yabanci_sinifi(d.at[i, "kaynak_sembol"] or d.at[i, "kod"], d.at[i, "kaynak_para"], ulke)
        d.at[i, "sinif"], d.at[i, "sinif_adi"] = k, sinif_adi(k)
    return d


def para_birimine_cevir(degerleme: pd.DataFrame, para: str, kur: float | None) -> pd.DataFrame:
    """TL fiyatlı satırları başka bir para birimine çevirir (kur: 1 birim `para` kaç TL).

    Nakit, elle girilen değer ve ülkenin kendi dövizi zaten o para birimindedir (dövizi nakit sayılır).
    Kur yoksa TL fiyatlı satırlar fiyatlanamadı sayılır. Maliyet o para biriminde girilmiş kabul edilir.
    """
    if para == "TRY" or degerleme.empty:
        return degerleme
    d = degerleme.copy()
    kendi = (d["tur"] == "doviz") & (d["kod"] == para)
    yerel = (d["tur"] == "nakit") | d["elle"].astype(bool) | kendi
    d.loc[kendi, "birim_fiyat"] = 1.0
    d.loc[kendi, "deger"] = d.loc[kendi, "miktar"]
    d.loc[kendi, ["sinif", "sinif_adi"]] = ["ppf", sinif_adi("ppf")]
    tl = ~yerel & d["birim_fiyat"].notna()
    if kur:
        d.loc[tl, "birim_fiyat"] = d.loc[tl, "birim_fiyat"] / kur
        d.loc[tl, "deger"] = (d.loc[tl, "deger"] / kur).round(2)
    else:
        d.loc[tl, ["birim_fiyat", "deger"]] = None
        d.loc[tl, "fiyatlanamadi"] = True
    kar = d["deger"] - d["maliyet"]
    d["kar"] = kar.where(d["maliyet"].fillna(0) > 0).round(2)
    d["kar_orani"] = (d["kar"] / d["maliyet"]).round(4)
    return d


def ozet(degerleme: pd.DataFrame) -> dict:
    d = degerleme.dropna(subset=["deger"])
    maliyetli = d.dropna(subset=["maliyet"])
    return {
        "toplam": round(float(d["deger"].sum()), 2),
        "maliyet": round(float(maliyetli["maliyet"].sum()), 2),
        "maliyetli_deger": round(float(maliyetli["deger"].sum()), 2),
        "sinif": {k: round(float(v), 2) for k, v in d.groupby("sinif")["deger"].sum().items()},
        "hedef": {k: round(float(v), 2) for k, v in d.groupby(d["hedef"].fillna(""))["deger"]
                  .sum().items()},
        "fiyatlanamayan": int(degerleme["fiyatlanamadi"].sum()),
        "fiyatlar": {f"{r.tur}:{r.kod}": r.birim_fiyat for r in d.itertuples()
                     if r.tur not in ("nakit", "diger")},
    }


def hedef_mevcutlari(degerleme: pd.DataFrame) -> dict[str, float]:
    """Hedefe bağlı varlıkların güncel değeri (hedef adı -> TL)."""
    d = degerleme.dropna(subset=["deger"])
    d = d[d["hedef"].notna() & (d["hedef"] != "")]
    return {k: round(float(v), 2) for k, v in d.groupby("hedef")["deger"].sum().items()}


def dengeleyerek_dagit(katki: float, mevcut: dict[str, float],
                       hedef_dagilim: dict[str, int]) -> dict[str, float]:
    """Yeni katkıyı, mevcut portföyü hedef dağılıma yaklaştıracak şekilde böler (satış yapmadan).

    Hedef değer_k = ağırlık_k × (mevcut toplam + katkı). Eksik kalan sınıflara öncelik verilir;
    eksikler katkıyı aşarsa orantılı paylaştırılır; artan katkı hedef ağırlıklarla dağıtılır.
    """
    if katki <= 0:
        return {k: 0.0 for k in hedef_dagilim}
    toplam = sum(mevcut.values()) + katki
    eksik = {k: max(0.0, w / 100 * toplam - mevcut.get(k, 0.0)) for k, w in hedef_dagilim.items()}
    eksik_toplam = sum(eksik.values())
    if eksik_toplam >= katki:
        return {k: round(katki * e / eksik_toplam, 2) for k, e in eksik.items()}
    kalan = katki - eksik_toplam
    return {k: round(eksik[k] + kalan * w / 100, 2) for k, w in hedef_dagilim.items()}


def alimi_normallestir(alim: Varlik, tutar: float) -> Varlik:
    from dataclasses import replace
    alim = replace(alim, id=None, maliyet=tutar or None)
    if alim.tur == "nakit" and not alim.miktar:
        alim.miktar = tutar
    if alim.tur == "diger":
        alim.miktar, alim.deger_elle = 1.0, tutar
    return alim


def alimi_birlestir(mevcut: list[Varlik], alim: Varlik, tutar: float) -> Varlik:
    """Alımı mevcut varlıklarla birleştirir: aynı tür + kod + hedef varsa miktar ve maliyet artar,
    yoksa yeni varlık olur. Nakitte miktar ödenen tutardır; "diğer"de elle değer artar.
    Maliyeti girilmemiş eski bir varlığa maliyet eklenmez (yarım maliyet yanıltıcı kâr gösterir)."""
    from dataclasses import replace
    alim = alimi_normallestir(alim, tutar)
    for v in mevcut:
        if (v.tur, v.kod, v.hedef or None) == (alim.tur, alim.kod, alim.hedef or None):
            v = replace(v)
            if alim.tur == "diger":
                v.deger_elle = (v.deger_elle or 0) + tutar
            else:
                v.miktar += alim.miktar
            if v.maliyet is not None:
                v.maliyet += tutar
            return v
    return alim


def csv_oku(yol) -> list[Varlik]:
    """CSV/XLSX'ten varlık listesi. Sütunlar: tur, kod, miktar, [maliyet, kurum, hedef, deger]."""
    from .metin import tutar_cozumle
    yol = str(yol)
    df = pd.read_excel(yol, dtype=str) if yol.lower().endswith((".xlsx", ".xls")) else pd.read_csv(
        yol, sep=None, engine="python", dtype=str, encoding="utf-8-sig")
    df.columns = [sade(c).lower() for c in df.columns]
    varliklar = []
    for _, r in df.iterrows():
        if pd.isna(r.get("tur")) or pd.isna(r.get("kod")):
            continue
        def al(k, r=r):
            x = r.get(k)
            return None if x is None or pd.isna(x) or str(x).strip() == "" else str(x).strip()
        varliklar.append(Varlik(tur=al("tur"), kod=al("kod"), miktar=tutar_cozumle(al("miktar")) or 0,
                                maliyet=tutar_cozumle(al("maliyet")), kurum=al("kurum"),
                                hedef=al("hedef"), deger_elle=tutar_cozumle(al("deger"))))
    return varliklar


def hedeflere_uygula(hedefler: list, degerleme: pd.DataFrame) -> list:
    """Varlık bağlanmış hedeflerin `mevcut` alanını güncel piyasa değeriyle değiştirir."""
    from dataclasses import replace
    mevcut = hedef_mevcutlari(degerleme)
    return [replace(h, mevcut=mevcut[h.ad]) if h.ad in mevcut else h for h in hedefler]


def planlara_dengeleme_uygula(planlar: list, degerleme: pd.DataFrame) -> None:
    """Varlığı olan hedeflerde bu ayki katkıyı, mevcut dağılımı modele yaklaştıracak şekilde böler."""
    d = degerleme.dropna(subset=["deger"])
    for p in planlar:
        bagli = d[d["hedef"] == p.hedef.ad]
        if bagli.empty:
            continue
        mevcut = {k: float(v) for k, v in bagli.groupby("sinif")["deger"].sum().items()}
        p.mevcut_dagilim = {k: round(v, 2) for k, v in mevcut.items()}
        modelde = {k: v for k, v in mevcut.items() if k in p.dagilim}
        p.katki_dagilimi = dengeleyerek_dagit(p.onerilen_aylik_katki, modelde, p.dagilim)
        disarida = set(mevcut) - set(p.dagilim)
        if disarida:
            pay = sum(mevcut[k] for k in disarida) / sum(mevcut.values())
            p.uyarilar.append(
                f"Bu hedefe bağlı {', '.join(sinif_adi(k) for k in sorted(disarida))} "
                f"(%{pay * 100:.0f}) bu hedefin {p.vade} vade dağılımında yok. Değere dahil edildi; "
                "yeni katkı bunlara yönlendirilmiyor."
                + (" Kısa vadeli hedefte oynak varlık, hedef tarihinde değer kaybı riski taşır."
                   if p.vade == "kısa" and disarida & {"altin", "doviz", "bist_hisse", "yabanci_hisse",
                                                        "diger"} else ""))
