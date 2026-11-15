"""Varlık sınıfları için reel getiri, oynaklık ve korelasyonu geçmiş veriden tahmin eder.

Yöntem
------
1. Her varlık sınıfı için TEFAS'ta adı o sınıfa uyan, en az 3-5 yıllık geçmişi olan fonlar
   seçilir. Yalnızca en iyi performanslıları seçmek iyimser sonuç verir; bunu önlemek için
   getiri sıralamasının her diliminden eşit aralıklı en fazla `fon_sayisi` fon alınır.
   Fon fiyatları yönetim ücreti düşülmüş net değerlerdir, yani yatırımcının gerçekten
   aldığı getiriyi gösterir.
2. Fiyatlar ay sonu değerine indirgenir. Aylık getiri TÜFE'nin aylık değişimiyle reele
   çevrilir: (1 + nominal) / (1 + enflasyon) - 1.
3. Bir ayda %40'tan çok düşen ya da %80'den çok yükselen fonlar (pay bölünmesi / veri hatası)
   dışlanır; sınıf endeksi = o aydaki fon getirilerinin medyanı.
4. İstatistikler: yıllık geometrik ortalama reel getiri, aylık log getirilerin standart
   sapması x sqrt(12) ve aylık getiri korelasyonları.
5. Gerçekçilik için daraltma (shrinkage): 5 yıllık ortalama getiri çok gürültülüdür, Türkiye'de
   2021-2023 gibi uç dönemleri de içerir. Bu yüzden tarihsel ortalama uzun vadeli
   varsayımla harmanlanır: ağırlık = N / (N + 120 ay). Oynaklık daha güvenilir ölçüldüğü
   için ağırlığı N / (N + 24) olur. Korelasyonlar sabit 0,3'e doğru aynı oranda daraltılır.
6. Para piyasası ve kısa vadeli borçlanma fonlarında geçmiş reel faiz geleceği temsil etmez,
   çünkü para politikası rejimi değişir. Bunların beklenen getirisi güncel politika faizi
   ve enflasyondan ileriye dönük olarak türetilir; oynaklıkları geçmişten alınır.

Sınırlar: kapanan fonlar listede olmadığından hayatta kalma yanlılığı vardır, geçmiş en
fazla 5 yıldır (TEFAS sınırı) ve vergi/stopaj ayrıca modellenmez.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .metin import sade
from .portfoy import VARLIK_SINIFLARI, ppf_reel_getiri_tahmini

log = logging.getLogger(__name__)
ILERIYE_DONUK = ("ppf", "kisa_borc")
N0_GETIRI = 120
N0_OYNAKLIK = 24
HEDEF_KORELASYON = 0.3
GETIRI_SINIRI = (-0.10, 0.15)


@dataclass
class Parametreler:
    tarih: str
    reel_getiri: dict[str, float]
    oynaklik: dict[str, float]
    korelasyon: dict[str, dict[str, float]]
    tarihsel_getiri: dict[str, float | None] = field(default_factory=dict)
    tarihsel_oynaklik: dict[str, float | None] = field(default_factory=dict)
    ay_sayisi: dict[str, int] = field(default_factory=dict)
    fonlar: dict[str, list[str]] = field(default_factory=dict)
    notlar: list[str] = field(default_factory=list)

    def kaydet(self, yol: Path) -> None:
        yol.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), "utf-8")

    @classmethod
    def yukle(cls, yol: Path) -> Parametreler | None:
        try:
            return cls(**json.loads(Path(yol).read_text("utf-8")))
        except (OSError, ValueError, TypeError):
            return None

    def yas_gun(self, bugun: date | None = None) -> int:
        return ((bugun or date.today()) - date.fromisoformat(self.tarih[:10])).days


# --- Saf hesap fonksiyonları (ağsız test edilebilir) -------------------------------------------

def aylik_enflasyon_serisi(tufe: pd.DataFrame) -> pd.Series:
    """borsapy Inflation().tufe() çıktısından aylık enflasyon (oran) serisi; indeks = Period[M]."""
    s = pd.to_numeric(tufe["MonthlyInflation"], errors="coerce")
    s = s / 100 if s.abs().max() > 1.5 else s
    s.index = pd.to_datetime(tufe.index).to_period("M")
    return s[~s.index.duplicated()].sort_index().dropna()


def aylik_reel_getiri(fiyat: pd.Series, enflasyon: pd.Series) -> pd.Series:
    """Günlük fiyattan aylık reel getiri. Eksik aylar atlanır."""
    fiyat = pd.to_numeric(fiyat, errors="coerce").dropna()
    fiyat = fiyat[fiyat > 0]
    if fiyat.empty:
        return pd.Series(dtype=float)
    fiyat.index = pd.to_datetime(fiyat.index)
    ay_sonu = fiyat.groupby(fiyat.index.to_period("M")).last()
    nominal = ay_sonu.pct_change().dropna()
    nominal = nominal.iloc[:-1] if _yarim_ay(fiyat) else nominal  # devam eden ayı atla
    ortak = nominal.index.intersection(enflasyon.index)
    return ((1 + nominal[ortak]) / (1 + enflasyon[ortak]) - 1).rename(None)


def _yarim_ay(fiyat: pd.Series) -> bool:
    son = fiyat.index.max()
    return son.day < 25 and son.to_period("M") == pd.Timestamp.today().to_period("M")


AYKIRI_AYLIK = (-0.40, 0.80)  # bir ayda bundan büyük hareket: pay bölünmesi / veri hatası


def aykiri_mi(getiri: pd.Series) -> bool:
    alt, ust = AYKIRI_AYLIK
    return bool((getiri < alt).any() or (getiri > ust).any())


def sinif_endeksi(getiriler: list[pd.Series], en_az_fon: int = 1) -> pd.Series:
    """Her ay, fonların getirilerinin MEDYANI (tek bir hatalı fon sonucu bozmasın)."""
    if not getiriler:
        return pd.Series(dtype=float)
    tablo = pd.concat(getiriler, axis=1)
    say = tablo.notna().sum(axis=1)
    return tablo.median(axis=1)[say >= en_az_fon].dropna()


def istatistikler(getiri: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.DataFrame, pd.Series]:
    """(yıllık geometrik reel getiri, yıllık oynaklık, korelasyon, ay sayısı)."""
    log_g = np.log1p(getiri)
    n = getiri.notna().sum()
    ort = np.expm1(log_g.mean() * 12)
    oyn = log_g.std(ddof=1) * math.sqrt(12)
    kor = getiri.corr(min_periods=12)
    return ort, oyn, kor, n


def daralt(tarihsel: float | None, n: int, onsel: float, n0: int) -> float:
    if tarihsel is None or not np.isfinite(tarihsel) or n <= 0:
        return onsel
    w = n / (n + n0)
    return w * tarihsel + (1 - w) * onsel


def korelasyon_daralt(kor: pd.DataFrame, n: pd.Series, siniflar: list[str]) -> pd.DataFrame:
    """Sabit korelasyona doğru daraltır, eksikleri hedefle doldurur ve pozitif yarı tanımlı yapar."""
    k = pd.DataFrame(HEDEF_KORELASYON, index=siniflar, columns=siniflar, dtype=float)
    for i in siniflar:
        for j in siniflar:
            if i == j:
                k.loc[i, j] = 1.0
            elif i in kor.index and j in kor.columns and pd.notna(kor.loc[i, j]):
                m = min(n.get(i, 0), n.get(j, 0))
                w = m / (m + N0_OYNAKLIK)
                k.loc[i, j] = w * kor.loc[i, j] + (1 - w) * HEDEF_KORELASYON
    return en_yakin_psd(k)


def en_yakin_psd(k: pd.DataFrame) -> pd.DataFrame:
    deger, vektor = np.linalg.eigh(k.values)
    deger = np.clip(deger, 1e-6, None)
    m = vektor @ np.diag(deger) @ vektor.T
    d = np.sqrt(np.diag(m))
    m = m / np.outer(d, d)
    return pd.DataFrame(m, index=k.index, columns=k.columns)


def parametreleri_hesapla(sinif_getirileri: dict[str, pd.Series], ileriye_donuk: dict[str, float],
                          fonlar: dict[str, list[str]] | None = None) -> Parametreler:
    """Sınıf bazında aylık reel getiri serilerinden nihai parametreleri üretir."""
    siniflar = list(VARLIK_SINIFLARI)
    tablo = pd.DataFrame({k: v for k, v in sinif_getirileri.items() if len(v)})
    notlar = []
    if tablo.empty:
        ort = oyn = n = pd.Series(dtype=float)
        kor = pd.DataFrame()
        notlar.append("Hiçbir sınıf için geçmiş veri alınamadı; varsayılan değerler kullanıldı.")
    else:
        ort, oyn, kor, n = istatistikler(tablo)
    getiri, oynaklik = {}, {}
    for kod, vs in VARLIK_SINIFLARI.items():
        ay = int(n.get(kod, 0) or 0)
        if kod in ILERIYE_DONUK and kod in ileriye_donuk:
            g = ileriye_donuk[kod]
        else:
            g = daralt(ort.get(kod), ay, vs.reel_getiri, N0_GETIRI)
        alt, ust = GETIRI_SINIRI
        if not alt <= g <= ust:
            notlar.append(f"{kod}: getiri tahmini {g:.1%} sınır dışıydı, [{alt:.0%}, {ust:.0%}] "
                          "aralığına çekildi.")
            g = min(max(g, alt), ust)
        getiri[kod] = round(float(g), 4)
        oynaklik[kod] = round(float(daralt(oyn.get(kod), ay, vs.oynaklik, N0_OYNAKLIK)), 4)
        if ay < 24:
            notlar.append(f"{kod}: yalnızca {ay} aylık veri; ağırlıklı olarak varsayım kullanıldı.")
    k = korelasyon_daralt(kor, n, siniflar)
    return Parametreler(
        tarih=date.today().isoformat(), reel_getiri=getiri, oynaklik=oynaklik,
        korelasyon={i: {j: round(float(k.loc[i, j]), 4) for j in siniflar} for i in siniflar},
        tarihsel_getiri={c: _yuvarla(ort.get(c)) for c in siniflar},
        tarihsel_oynaklik={c: _yuvarla(oyn.get(c)) for c in siniflar},
        ay_sayisi={c: int(n.get(c, 0) or 0) for c in siniflar}, fonlar=fonlar or {}, notlar=notlar)


def _yuvarla(x) -> float | None:
    return None if x is None or not np.isfinite(x) else round(float(x), 4)


def temsilci_fonlar(fon_listesi: pd.DataFrame, sinif: str, adet: int) -> list[str]:
    """Sınıfa uyan, uzun geçmişli fonlardan getiri sıralamasına eşit aralıklarla seçim."""
    vs = VARLIK_SINIFLARI[sinif]
    if fon_listesi.empty or "name" not in fon_listesi:
        return []
    ad = fon_listesi["name"].map(sade)
    maske = ad.str.contains(vs.tefas_desen, regex=True)
    if vs.tefas_haric:
        maske &= ~ad.str.contains(vs.tefas_haric, regex=True)
    aday = fon_listesi[maske]
    for kolon in ("return_5y", "return_3y", "return_1y"):
        if kolon in aday and aday[kolon].notna().sum() >= min(adet, 3):
            aday = aday[aday[kolon].notna()].sort_values(kolon)
            break
    if len(aday) <= adet:
        return aday["fund_code"].tolist()
    secim = np.linspace(0, len(aday) - 1, adet).round().astype(int)
    return aday["fund_code"].iloc[secim].tolist()


# --- Canlı veriyle tahmin ----------------------------------------------------------------------

def tahmin_et(piyasa, fon_sayisi: int = 8, donem: str = "5y") -> Parametreler:
    """TEFAS fon geçmişleri ve TÜFE ile parametreleri hesaplar (ağ gerekir)."""
    import borsapy as bp

    tufe = piyasa._dene("tufe_gecmisi", lambda: bp.Inflation().tufe(limit=120))
    if tufe is None or len(tufe) == 0:
        raise RuntimeError(f"TÜFE geçmişi alınamadı: {piyasa.hatalar.get('tufe_gecmisi')}")
    enf = aylik_enflasyon_serisi(tufe)
    liste = piyasa.fon_listesi()
    if liste.empty:
        raise RuntimeError(f"TEFAS fon listesi alınamadı: {piyasa.hatalar.get('fon_listesi')}")

    sinif_getirileri, fonlar, ayiklanan = {}, {}, []
    for kod in VARLIK_SINIFLARI:
        seriler = []
        kodlar = temsilci_fonlar(liste, kod, fon_sayisi)
        for fon in kodlar:
            gecmis = piyasa._dene(f"gecmis:{fon}", lambda f=fon: bp.Fund(f).history(period=donem))
            if gecmis is not None and len(gecmis) and "Price" in gecmis:
                r = aylik_reel_getiri(gecmis["Price"], enf)
                if len(r) >= 12 and aykiri_mi(r):
                    ayiklanan.append(fon)
                elif len(r) >= 12:
                    seriler.append(r.rename(fon))
        fonlar[kod] = [s.name for s in seriler]
        sinif_getirileri[kod] = sinif_endeksi(seriler)
        log.info("%s: %d fon, %d ay", kod, len(seriler), len(sinif_getirileri[kod]))

    ozet = piyasa.ozet()
    ileri = ppf_reel_getiri_tahmini(ozet.get("politika_faizi"), ozet.get("tufe_yillik"),
                                    ozet.get("tufe_son3_yillik"))
    ileriye_donuk = {"ppf": ileri, "kisa_borc": ileri + 0.005} if ileri is not None else {}
    p = parametreleri_hesapla(sinif_getirileri, ileriye_donuk, fonlar)
    if ayiklanan:
        p.notlar.append(f"Aykırı aylık hareket (olası veri hatası/bölünme) nedeniyle dışlanan fonlar: "
                        f"{', '.join(ayiklanan)}")
    if not ileriye_donuk:
        p.notlar.append("Politika faizi/TÜFE alınamadı; para piyasası için varsayım kullanıldı.")
    return p
