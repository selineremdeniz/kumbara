"""Birikim hedefleri ve vadeye (kısa/orta/uzun) göre model portföy dağılımı.

Tüm hesaplar REEL (enflasyondan arındırılmış, bugünün TL'si) yapılır: hedef tutarını bugünün
fiyatlarıyla girersiniz; çıkan aylık katkıyı her ay enflasyon oranında artırmanız gerekir.

VARLIK_SINIFLARI'ndaki getiri/oynaklık değerleri uzun vadeli ÖNSEL varsayımlardır. `kumbara parametre
guncelle` bunları TEFAS fon geçmişi ve TÜFE'den tahmin edip (tahmin.py) bu varsayımlarla harmanlar;
~/.kumbara/varsayimlar.yaml ile de değiştirilebilir. Bu modül yatırım tavsiyesi vermez.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

VADELER = ("kısa", "orta", "uzun")
RISKLER = ("muhafazakar", "dengeli", "agresif")


@dataclass(frozen=True)
class VarlikSinifi:
    kod: str
    ad: str
    reel_getiri: float  # yıllık, reel (TL bazında, enflasyon sonrası) varsayım
    oynaklik: float     # yıllık standart sapma (kaba varsayım)
    tefas_desen: str    # TEFAS fon adında aranacak düzenli ifade (sade() edilmiş ad üzerinde)
    tefas_haric: str = "SERBEST"


VARLIK_SINIFLARI: dict[str, VarlikSinifi] = {v.kod: v for v in [
    VarlikSinifi("ppf", "Para piyasası fonu / vadeli mevduat", 0.01, 0.02, r"PARA PIYASASI"),
    VarlikSinifi("kisa_borc", "Kısa vadeli borçlanma araçları fonu", 0.015, 0.04,
                 r"KISA VADELI BORCLANMA"),
    VarlikSinifi("tl_tahvil", "TL borçlanma araçları (tahvil/bono) fonu", 0.02, 0.10,
                 r"BORCLANMA ARACLARI", r"SERBEST|KISA VADELI|EUROBOND|DIS BORCLANMA|YABANCI|DOVIZ"),
    VarlikSinifi("eurobond", "Eurobond / dış borçlanma araçları fonu (USD)", 0.02, 0.15,
                 r"EUROBOND|DIS BORCLANMA"),
    VarlikSinifi("altin", "Altın / kıymetli madenler fonu", 0.025, 0.18, r"ALTIN|KIYMETLI MADEN"),
    VarlikSinifi("bist_hisse", "BIST hisse senedi fonu / BIST30 BYF", 0.05, 0.30,
                 r"HISSE SENEDI", r"SERBEST|YABANCI"),
    VarlikSinifi("yabanci_hisse", "Yabancı hisse senedi fonu", 0.05, 0.22,
                 r"YABANCI.*HISSE|HISSE.*YABANCI"),
]}

VARSAYILAN_SINIFLAR: dict[str, VarlikSinifi] = dict(VARLIK_SINIFLARI)  # Türkiye önselleri


def varsayilanlara_don() -> None:
    """Varlık sınıflarını (ad, getiri, oynaklık) ve korelasyonları başlangıç hâline döndürür."""
    global KORELASYON, PARAMETRE_KAYNAGI
    VARLIK_SINIFLARI.clear()
    VARLIK_SINIFLARI.update(VARSAYILAN_SINIFLAR)
    KORELASYON, PARAMETRE_KAYNAGI = None, "varsayım"


# Model dağılımlar (%). Satırlar vade, sütunlar risk profili.
MODEL_DAGILIMLAR: dict[str, dict[str, dict[str, int]]] = {
    "kısa": {
        "muhafazakar": {"ppf": 80, "kisa_borc": 20},
        "dengeli": {"ppf": 65, "kisa_borc": 20, "altin": 15},
        "agresif": {"ppf": 50, "kisa_borc": 20, "altin": 15, "eurobond": 15},
    },
    "orta": {
        "muhafazakar": {"ppf": 30, "tl_tahvil": 25, "eurobond": 20, "altin": 20, "bist_hisse": 5},
        "dengeli": {"ppf": 15, "tl_tahvil": 20, "eurobond": 20, "altin": 20, "bist_hisse": 15,
                    "yabanci_hisse": 10},
        "agresif": {"ppf": 5, "tl_tahvil": 15, "eurobond": 15, "altin": 20, "bist_hisse": 25,
                    "yabanci_hisse": 20},
    },
    "uzun": {
        "muhafazakar": {"ppf": 10, "tl_tahvil": 15, "eurobond": 20, "altin": 25,
                        "bist_hisse": 15, "yabanci_hisse": 15},
        "dengeli": {"ppf": 5, "tl_tahvil": 10, "eurobond": 15, "altin": 20, "bist_hisse": 25,
                    "yabanci_hisse": 25},
        "agresif": {"eurobond": 10, "altin": 15, "bist_hisse": 35, "yabanci_hisse": 40},
    },
}


def varsayimlari_yukle(dosya: Path | None) -> None:
    """Kullanıcı varsayım dosyasıyla reel getiri/oynaklık değerlerini günceller.

    Biçim:  reel_getiri: {bist_hisse: 0.04, altin: 0.02}
            oynaklik:    {bist_hisse: 0.35}
    """
    if not dosya or not Path(dosya).exists():
        return
    veri = yaml.safe_load(Path(dosya).read_text("utf-8")) or {}
    for alan in ("reel_getiri", "oynaklik"):
        for kod, deger in (veri.get(alan) or {}).items():
            if kod in VARLIK_SINIFLARI:
                eski = VARLIK_SINIFLARI[kod]
                VARLIK_SINIFLARI[kod] = VarlikSinifi(**{**eski.__dict__, alan: float(deger)})


def ppf_reel_getiri_tahmini(politika_faizi: float | None, yillik_enflasyon: float | None,
                            son3_yillik: float | None = None) -> float | None:
    """Para piyasası için ileriye dönük yıllık reel getiri.

    - Fon getirisi ≈ politika faizi - 3 puan (yönetim ücreti ve stopaj payı, kaba).
    - Beklenen enflasyon = son yıllık TÜFE ile son 3 ayın yıllıklandırılmış TÜFE'sinin ortalaması
      (keyfi bir dezenflasyon varsayımı yerine güncel eğilim).
    """
    if politika_faizi is None or yillik_enflasyon is None:
        return None
    nominal = max(politika_faizi - 0.03, 0.0)
    beklenen_enf = (yillik_enflasyon + son3_yillik) / 2 if son3_yillik is not None else (
        yillik_enflasyon)
    reel = (1 + nominal) / (1 + beklenen_enf) - 1
    return round(max(min(reel, 0.10), -0.10), 4)


def _guncelle(kod: str, **alanlar) -> None:
    eski = VARLIK_SINIFLARI[kod]
    VARLIK_SINIFLARI[kod] = VarlikSinifi(**{**eski.__dict__, **alanlar})


def ppf_reel_getiri_guncelle(politika_faizi: float | None, yillik_enflasyon: float | None,
                             son3_yillik: float | None = None) -> None:
    reel = ppf_reel_getiri_tahmini(politika_faizi, yillik_enflasyon, son3_yillik)
    if reel is None:
        return
    for kod, ek in (("ppf", 0.0), ("kisa_borc", 0.005)):
        _guncelle(kod, reel_getiri=round(reel + ek, 4))


VARSAYILAN_KORELASYON = 0.3
KORELASYON: dict[str, dict[str, float]] | None = None
PARAMETRE_KAYNAGI = "varsayım"


def korelasyon(i: str, j: str) -> float:
    if i == j:
        return 1.0
    if KORELASYON and i in KORELASYON and j in KORELASYON[i]:
        return KORELASYON[i][j]
    return VARSAYILAN_KORELASYON


def parametreleri_uygula(p) -> None:
    """tahmin.Parametreler nesnesindeki tahminleri model varsayımlarının yerine koyar."""
    global KORELASYON, PARAMETRE_KAYNAGI
    for kod in VARLIK_SINIFLARI:
        alanlar = {}
        if kod in p.reel_getiri:
            alanlar["reel_getiri"] = float(p.reel_getiri[kod])
        if kod in p.oynaklik:
            alanlar["oynaklik"] = float(p.oynaklik[kod])
        if alanlar:
            _guncelle(kod, **alanlar)
    KORELASYON = p.korelasyon
    PARAMETRE_KAYNAGI = f"tahmin ({p.tarih})"


def vade_sinifi(ay: int) -> str:
    return "kısa" if ay <= 12 else ("orta" if ay <= 36 else "uzun")


@dataclass
class Hedef:
    ad: str
    tutar: float               # bugünün TL'siyle
    tarih: date
    mevcut: float = 0.0        # bu hedef için ayrılmış mevcut birikim
    oncelik: int = 2           # 1 = en yüksek
    risk: str = "dengeli"

    def ay_sayisi(self, bugun: date | None = None) -> int:
        bugun = bugun or date.today()
        return max(1, (self.tarih.year - bugun.year) * 12 + (self.tarih.month - bugun.month))

    def vade(self, bugun: date | None = None) -> str:
        return vade_sinifi(self.ay_sayisi(bugun))


@dataclass
class HedefPlani:
    hedef: Hedef
    vade: str
    ay_sayisi: int
    dagilim: dict[str, int]
    beklenen_reel_getiri: float
    beklenen_oynaklik: float
    gerekli_aylik_katki: float        # `guven` olasılıkla hedefe ulaştıran katkı (simülasyon)
    medyan_katki: float = 0.0         # beklenen getiriyle (annüite) gereken katkı
    guven: float = 0.8
    onerilen_aylik_katki: float = 0.0
    basari_olasiligi: float | None = None  # önerilen katkıyla hedefe ulaşma olasılığı
    sonuc_araligi: dict[str, float] = field(default_factory=dict)  # hedef tarihteki servet p10/50/90
    katki_dagilimi: dict[str, float] = field(default_factory=dict)
    uyarilar: list[str] = field(default_factory=list)
    mevcut_dagilim: dict[str, float] = field(default_factory=dict)  # hedefe bağlı varlıklar (TL)
    _sim: object = field(default=None, repr=False)

    def sonuclari_guncelle(self) -> None:
        if self._sim is not None:
            self.basari_olasiligi = round(self._sim.olasilik(self.onerilen_aylik_katki), 3)
            self.sonuc_araligi = self._sim.dagilim(self.onerilen_aylik_katki)


def model_dagilim(vade: str, risk: str) -> dict[str, int]:
    if vade not in VADELER:
        raise ValueError(f"vade {VADELER} içinden olmalı")
    if risk not in RISKLER:
        raise ValueError(f"risk {RISKLER} içinden olmalı")
    return dict(MODEL_DAGILIMLAR[vade][risk])


def dagilim_getiri(dagilim: dict[str, int]) -> tuple[float, float]:
    """(beklenen yıllık reel getiri, yıllık oynaklık) — korelasyon matrisiyle."""
    agirlik = {k: v / 100 for k, v in dagilim.items()}
    getiri = sum(w * VARLIK_SINIFLARI[k].reel_getiri for k, w in agirlik.items())
    varyans = 0.0
    for i, wi in agirlik.items():
        for j, wj in agirlik.items():
            si, sj = VARLIK_SINIFLARI[i].oynaklik, VARLIK_SINIFLARI[j].oynaklik
            varyans += wi * wj * si * sj * korelasyon(i, j)
    return round(getiri, 4), round(varyans ** 0.5, 4)


def gerekli_aylik_katki(hedef_tutar: float, mevcut: float, ay: int, yillik_reel: float) -> float:
    """Gelecek değer (annüite) formülüyle aylık reel katkı."""
    r = (1 + yillik_reel) ** (1 / 12) - 1
    gelecek_mevcut = mevcut * (1 + r) ** ay
    kalan = hedef_tutar - gelecek_mevcut
    if kalan <= 0:
        return 0.0
    if abs(r) < 1e-9:
        return round(kalan / ay, 2)
    return round(kalan * r / ((1 + r) ** ay - 1), 2)


def hedef_plani(hedef: Hedef, bugun: date | None = None, guven: float = 0.8,
                simulasyon: bool = True) -> HedefPlani:
    """Hedefin vadesi, dağılımı ve gereken aylık katkısı.

    simulasyon=True: katkı, Monte Carlo ile hedefe `guven` olasılıkla ulaşacak şekilde
    hesaplanır (daha gerçekçi, beklenen getiriden daha temkinli). False: yalnızca annüite.
    """
    vade = hedef.vade(bugun)
    n = hedef.ay_sayisi(bugun)
    dagilim = model_dagilim(vade, hedef.risk)
    getiri, oynaklik = dagilim_getiri(dagilim)
    medyan = gerekli_aylik_katki(hedef.tutar, hedef.mevcut, n, getiri)
    sim = None
    katki = medyan
    if simulasyon:
        from .simulasyon import simule_et
        sim = simule_et(hedef.tutar, hedef.mevcut, hedef.risk, n)
        katki = sim.gerekli_katki(guven)
    uyarilar = []
    if vade == "kısa" and hedef.risk == "agresif":
        uyarilar.append("Kısa vadeli hedefte yüksek risk: hedef tarihte değer düşük olabilir.")
    if n <= 3:
        uyarilar.append("Hedefe 3 aydan az kaldı; birikimi likit (para piyasası) tutun.")
    return HedefPlani(hedef=hedef, vade=vade, ay_sayisi=n, dagilim=dagilim,
                      beklenen_reel_getiri=getiri, beklenen_oynaklik=oynaklik,
                      gerekli_aylik_katki=katki, medyan_katki=medyan, guven=guven,
                      uyarilar=uyarilar, _sim=sim)


def birikimi_dagit(hedefler: list[Hedef], aylik_birikim: float | None = None,
                   bugun: date | None = None, guven: float = 0.8,
                   simulasyon: bool = True) -> list[HedefPlani]:
    """Hedeflerin planlarını çıkarır; aylık birikim kapasitesi verilirse önceliğe göre paylaştırır.

    Önce öncelik 1 hedeflerin gerekli katkısı karşılanır, sonra 2, sonra 3. Bir öncelik grubuna
    para yetmezse grup içinde gerekli katkı oranında bölünür. Artan para, en uzun vadeli hedefe
    eklenir.
    """
    planlar = [hedef_plani(h, bugun, guven, simulasyon) for h in hedefler]
    if aylik_birikim is None:
        for p in planlar:
            p.onerilen_aylik_katki = p.gerekli_aylik_katki
    else:
        kalan = max(0.0, aylik_birikim)
        for oncelik in sorted({p.hedef.oncelik for p in planlar}):
            grup = [p for p in planlar if p.hedef.oncelik == oncelik]
            ihtiyac = sum(p.gerekli_aylik_katki for p in grup)
            oran = 1.0 if ihtiyac <= kalan else (kalan / ihtiyac if ihtiyac else 0)
            for p in grup:
                p.onerilen_aylik_katki = round(p.gerekli_aylik_katki * oran, 2)
                if oran < 1:
                    p.uyarilar.append(
                        f"Birikim kapasitesi yetmiyor: gerekli katkının %{oran * 100:.0f}'i "
                        "ayrılabildi. Hedef tarihini uzatmayı veya tutarı düşürmeyi düşünün.")
            kalan -= sum(p.onerilen_aylik_katki for p in grup)
        if kalan > 0.5 and planlar:
            en_uzun = max(planlar, key=lambda p: p.ay_sayisi)
            en_uzun.onerilen_aylik_katki = round(en_uzun.onerilen_aylik_katki + kalan, 2)
    for p in planlar:
        p.katki_dagilimi = {k: round(p.onerilen_aylik_katki * v / 100, 2)
                            for k, v in p.dagilim.items()}
        p.sonuclari_guncelle()
    return planlar


def toplam_dagilim(planlar: list[HedefPlani]) -> dict[str, float]:
    """Tüm hedeflerin aylık katkılarının varlık sınıfı bazında toplamı (TL)."""
    toplam: dict[str, float] = {}
    for p in planlar:
        for k, v in p.katki_dagilimi.items():
            toplam[k] = round(toplam.get(k, 0.0) + v, 2)
    return dict(sorted(toplam.items(), key=lambda kv: -kv[1]))
