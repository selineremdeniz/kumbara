"""Ekran görüntüsü / fotoğraf (JPG, PNG, WEBP, HEIC) ekstreleri: OCR ile okuma.

Tipik kullanım: bankanın mobil uygulamasındaki "dönem içi işlemler" (henüz ekstreye girmemiş
harcamalar) ekranının görüntüsü. OCR tamamen yerelde yapılır, hiçbir yere gönderilmez:
  - macOS: Apple Vision (pip install ocrmac) — ek kurulum gerekmez. Türkçe, macOS sürümü
    destekliyorsa kullanılır; desteklemiyorsa Latin alfabesiyle okunur (tarih/tutar/kategori
    eşleştirmesi Türkçe karakterden bağımsızdır).
  - Diğer / yedek: Tesseract (brew install tesseract tesseract-lang | apt install
    tesseract-ocr tesseract-ocr-tur) + pip install pytesseract.

Düzen bağımsız ayrıştırma: uygulamalar işlemleri farklı gösterir —
  (a) tarih başlığı + altında işlemler, (b) "işyeri  tutar" satırı + altında tarih,
  (c) "tarih  işyeri  tutar" tek satır. Satırlar tarih / tutar / metin olarak sınıflanır,
  tarihsiz tutar satırlarına düzene göre önceki ya da sonraki tarih atanır.
"""

from __future__ import annotations

import contextlib
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .metin import EkstreHatasi
from .pdf_ekstre import (
    _AY_DESEN,
    _OZET,
    _PUAN,
    _TUTAR,
    PdfSatiri,
    Satir,
    _ascii,
    _tarih_coz,
    _tutar_coz,
    _tutar_sec,
)

GORSEL_UZANTILARI = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff"}


class OcrHatasi(EkstreHatasi):
    pass


# --- OCR -----------------------------------------------------------------------------------------

def _resim_ac(yol: Path):
    from PIL import Image, ImageOps, ImageStat
    if yol.suffix.lower() in {".heic", ".heif"}:
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError as e:
            raise OcrHatasi("HEIC için: pip install pillow-heif (ya da görüntüyü JPG/PNG kaydedin)"
                            ) from e
    renkli = ImageOps.exif_transpose(Image.open(yol)).convert("RGB")
    # Gri tonlama renkli yazıyı (koyu zeminde turuncu/kırmızı tutarlar) soldurur; her pikselin
    # en güçlü kanalı (HSV "V") renkli yazıyı koyu zeminden net ayırır.
    r, g, b = renkli.split()
    from PIL import ImageChops
    img = ImageChops.lighter(ImageChops.lighter(r, g), b)
    if ImageStat.Stat(img).mean[0] < 110:  # karanlık mod: ters çevir
        img = ImageOps.invert(img)
    img = ImageOps.autocontrast(img, cutoff=1)
    if img.width < 1400:  # küçük görüntüyü büyüt: OCR doğruluğu artar
        oran = 1400 / img.width
        img = img.resize((1400, int(img.height * oran)))
    return img


def _kelimeler_tesseract(img) -> list[dict]:
    try:
        import pytesseract
    except ImportError as e:
        raise OcrHatasi("Görüntü okumak için OCR gerekli: pip install pytesseract ve Tesseract "
                        "(macOS: brew install tesseract tesseract-lang; macOS'ta alternatif: "
                        "pip install ocrmac)") from e
    try:
        diller = pytesseract.get_languages()
    except Exception as e:  # tesseract ikilisi yok
        raise OcrHatasi("Tesseract bulunamadı. macOS: brew install tesseract tesseract-lang · "
                        "Linux: apt install tesseract-ocr tesseract-ocr-tur") from e
    dil = "tur" if "tur" in diller else "eng"
    # psm 11 (seyrek metin): uygulama ekranlarında sağa yaslı tutarları ve işaretleri daha iyi okur.
    veri = pytesseract.image_to_data(img, lang=dil, config="--psm 11",
                                     output_type=pytesseract.Output.DICT)
    kelimeler = []
    for i, metin in enumerate(veri["text"]):
        metin = _ocr_duzelt((metin or "").strip())
        # Tutara benzeyen kelimeler düşük güvenle bile tutulur (yoksa işlem kaybolur).
        if not metin or (float(veri["conf"][i]) < 20 and not _TUTAR_BENZERI.search(metin)):
            continue
        x, y, w, h = (veri[k][i] for k in ("left", "top", "width", "height"))
        kelimeler.append({"text": metin, "x0": x, "x1": x + w, "top": y, "h": h})
    return kelimeler


_TUTAR_BENZERI = re.compile(r"\d[.,]\d{2}\b")


def _ocr_duzelt(metin: str) -> str:
    """Yaygın OCR hataları: '+' işareti '*', '＋' ya da '÷' okunabilir."""
    return re.sub(r"^[*＋÷](?=\d)", "+", metin)


def _kelimeler_ocrmac(yol: Path, genislik: int, yukseklik: int) -> list[dict] | None:
    if sys.platform != "darwin":
        return None
    try:
        from ocrmac import ocrmac
    except ImportError:
        return None
    # Apple Vision'ın Türkçe desteği macOS sürümüne bağlı; desteklenmiyorsa Latin alfabesi
    # (en-US) ile okunur. Tarih/tutar/ay adları ve kategoriler Türkçe karakterden bağımsız
    # eşleştiği için sonuç etkilenmez; yalnızca açıklamalarda Ş→S gibi sadeleşme olabilir.
    sonuc, hata = None, None
    for diller in (["tr-TR", "en-US"], ["en-US"], None):
        try:
            ocr = (ocrmac.OCR(str(yol), language_preference=diller) if diller
                   else ocrmac.OCR(str(yol)))
            sonuc = ocr.recognize()
            break
        except Exception as e:  # desteklenmeyen dil vb.
            hata = e
    if sonuc is None:  # Vision kullanılamadı: Tesseract'a dön
        import logging
        logging.getLogger(__name__).info("Apple Vision OCR başarısız (%s); Tesseract deneniyor", hata)
        return None
    kelimeler = []
    for metin, guven, (x, y, w, h) in sonuc:  # normalize; köken sol-alt
        metin = _ocr_duzelt(metin.strip())
        if (guven < 0.3 and not _TUTAR_BENZERI.search(metin)) or not metin:
            continue
        kelimeler.append({"text": metin, "x0": x * genislik, "x1": (x + w) * genislik,
                          "top": (1 - y - h) * yukseklik, "h": h * yukseklik})
    return kelimeler


def _nokta_ondalik_duzelt(kelimeler: list[dict]) -> None:
    """Bazı uygulamalar bekleyen işlemleri '-649.99 TL' gibi noktayla yazar. Yanında TL olan
    (binlik ayırıcısız) böyle sayıları '-649,99' yapar; '12.11' gibi tarihler etkilenmez."""
    for i, w in enumerate(kelimeler):
        m = re.fullmatch(r"([-+]?\d{1,3})\.(\d{2})((?:TL|TRY|₺)?)", w["text"])
        if not m:
            continue
        sonraki = kelimeler[i + 1]["text"] if i + 1 < len(kelimeler) else ""
        if m[3] or re.match(r"(TL|TRY|₺)\b", sonraki):
            w["text"] = f"{m[1]},{m[2]}{m[3]}"


def ocr_satirlari(yol: str | Path) -> list[PdfSatiri]:
    """Görüntüdeki metni, aynı yükseklikteki kelimeleri birleştirerek satırlara çevirir."""
    yol = Path(yol)
    img = _resim_ac(yol)
    kelimeler = _kelimeler_ocrmac(yol, img.width, img.height)
    if kelimeler is None:
        kelimeler = _kelimeler_tesseract(img)
    if not kelimeler:
        raise OcrHatasi(f"{yol.name}: görüntüde yazı bulunamadı.")
    kelimeler.sort(key=lambda w: (w["top"], w["x0"]))
    _nokta_ondalik_duzelt(kelimeler)
    satirlar, grup, merkez, yuk = [], [], None, 0
    for w in kelimeler:
        m = w["top"] + w["h"] / 2
        if grup and abs(m - merkez) > max(yuk, w["h"]) * 0.6:
            satirlar.append(PdfSatiri(sorted(grup, key=lambda k: k["x0"])))
            grup = []
        if not grup:
            merkez, yuk = m, w["h"]
        grup.append(w)
    if grup:
        satirlar.append(PdfSatiri(sorted(grup, key=lambda k: k["x0"])))
    return satirlar


# --- Ayrıştırma ----------------------------------------------------------------------------------

_TARIH_HER_YER = re.compile(
    r"(?<![\d.,/])(?P<tarih>"
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
    rf"|\d{{1,2}}\s+(?:{_AY_DESEN})\.?(?:\s+\d{{4}})?"
    r"|\d{1,2}\.\d{2}(?!\s*(?:TAKS|TKS))"  # yılsız 13.11 (yıl referanstan); 3/6 taksittir
    r")(?![\d.,/])"
)
_GORECELI = re.compile(r"\b(BUGUN|DUN|TODAY|YESTERDAY)\b")
_SAAT = re.compile(r"\b\d{1,2}[:.]\d{2}(?::\d{2})?\b")
_GURULTU = re.compile(r"\b(PAZARTESI|SALI|CARSAMBA|PERSEMBE|CUMA|CUMARTESI|PAZAR|TL|TRY|PROVIZYON|"
                      r"ONAYLANDI|BEKLEMEDE|ISLEM|DETAY|TAMAMLANDI)\b")
son_ozet: dict = {}  # son okunan görüntünün banka toplamları (ekstre.oku DataFrame.attrs'a taşır)
_EK_OZET = re.compile(r"LIMIT|BAKIYE|DONEM ICI|DONEM BORC|TOPLAM|ASGARI|SON ODEME|HESAP KESIM|"
                      r"TAKSIT TUTARI|DONEME AIT|"
                      r"KULLANILABILIR|BORCUNUZ|HARCAMA TUTARI")


_ALACAK = re.compile(r"ODEME|TESEKKUR|IADE|IPTAL|AKTARIM|REFUND|CHARGEBACK|HESAPTAN")


@dataclass
class _Kayit:
    sira: int
    aciklama: str
    tutarlar: list
    satir: str
    tarih: date | None


PENCERE_GERI = 62  # dönem içi ekranı en çok ~2 aylık işlem gösterir


def pencerede(d: date | None, referans: date) -> bool:
    """Dönem içi ekranındaki bir tarih makul mü? (görüntü tarihinden en çok ~2 ay önce, en çok
    1 gün sonra). OCR'ın saatleri ('17:02' → '17.02') tarih sanmasını engeller."""
    return d is not None and referans - timedelta(days=PENCERE_GERI) <= d <= referans + timedelta(days=1)


def _tarih_bul(a: str, referans: date) -> tuple[date | None, re.Match | None]:
    g = _GORECELI.search(a)
    if g:
        return (referans if g[1] in ("BUGUN", "TODAY") else referans - timedelta(days=1)), g
    for m in _TARIH_HER_YER.finditer(a):
        metin = m["tarih"]
        if re.fullmatch(rf"\d{{1,2}}\s+(?:{_AY_DESEN})\.?", metin):  # yılsız "12 Kasım"
            gun, ay = metin.split()[0], metin.split()[1].rstrip(".")
            from .pdf_ekstre import _AY_KISA, _AYLAR
            no = _AYLAR.get(ay) or _AY_KISA.get(ay)
            try:
                d = date(referans.year, no, int(gun))
            except (TypeError, ValueError):
                continue
            d = d.replace(year=d.year - 1) if d > referans + timedelta(days=31) else d
            if pencerede(d, referans):
                return d, m
            continue
        d = _tarih_coz(metin, referans)
        if pencerede(d, referans):
            return d, m
    return None, None


def _temiz_metin(satir: str, a: str, cikar: list[tuple[int, int]]) -> str:
    parcalar, son = [], 0
    for bas, bit in sorted(cikar):
        parcalar.append(satir[son:bas])
        son = max(son, bit)
    parcalar.append(satir[son:])
    metin = " ".join(parcalar)
    metin = re.sub(r"[₺|•·>›<‹]", " ", metin)
    kelimeler = [k for k in metin.split() if not _GURULTU.fullmatch(_ascii(k).strip(".,:"))]
    return re.sub(r"\s+", " ", " ".join(kelimeler)).strip(" -–:,.")


_AY_KELIME = re.compile(rf"^(?:{_AY_DESEN})\.?$")
_LIK = re.compile(r"^\s*(?:TL)?\s*'?\s*L[I1]K\b")


def _ay_no(kelime: str) -> int | None:
    from .pdf_ekstre import _AY_KISA, _AYLAR
    k = _ascii(kelime).strip(".,:")
    return _AYLAR.get(k) or _AY_KISA.get(k)


def sol_sutun_islemleri(satirlar: list[str], referans: date | None = None) -> list[Satir] | None:
    """Tarihi sol sütunda alt alta yazan uygulamalar (Yapı Kredi '12 / Kasım / 2026',
    İş Bankası '13 / Kas / 17:46'): satırın en solundaki kelimelerden tarih blokları kurulur,
    blok içindeki ilk satır açıklama, puan satırı dışındaki ilk tutar işlem tutarıdır.
    Bu düzen bulunamazsa None döner."""
    referans = referans or date.today()
    genislik = max((k[3] for s in satirlar for k in getattr(s, "konumlar", [])), default=0)
    if not genislik:
        return None
    # Sol sütunun sağ sınırı: soldaki ay adlarının ("Kas", "Kasım") bittiği yer + pay.
    # Apple Vision yan yana metni tek parça döndürebilir ("Kas -1.642,50 TL"): parçanın İLK
    # kelimesine bakılır, ay kelimesinin bittiği x oranla tahmin edilir.
    def ilk(metin: str) -> str:
        return metin.split()[0] if metin.split() else ""

    ay_sonlari = sorted(x0 + (x1 - x0) * len(ilk(str(s)[b:e])) / max(1, e - b)
                        for s in satirlar for b, e, x0, x1 in getattr(s, "konumlar", [])
                        if x0 < genislik * 0.3 and _ay_no(ilk(str(s)[b:e])))
    if len(ay_sonlari) < 2:
        return None
    sinir = ay_sonlari[len(ay_sonlari) // 2] + genislik * 0.02

    def sol_kelimeler(s) -> list[str]:
        return [ilk(str(s)[b:e]) for b, e, x0, _ in getattr(s, "konumlar", []) if x0 < sinir]

    def sag_parcalar(s) -> list[tuple[int, int]]:
        """Sağ sütundaki metin aralıkları; soldan başlayıp sağa taşan birleşik parçanın ilk
        kelimeden sonrası da dahil."""
        parcalar = []
        for b, e, x0, x1 in getattr(s, "konumlar", []):
            if x0 >= sinir:
                parcalar.append((b, e))
            elif x1 > sinir + genislik * 0.05:
                metin = str(s)[b:e]
                bosluk = metin.find(" ")
                if bosluk > 0:
                    parcalar.append((b + bosluk + 1, e))
        return parcalar

    sollar = [sol_kelimeler(s) for s in satirlar]
    # Çapalar: (satır no, gün) — sonraki 1-2 satırın sol kelimesi ay adı olmalı
    capalar: list[tuple[int, date]] = []
    for i, sol in enumerate(sollar):
        ay = next((_ay_no(k) for k in sol if _ay_no(k)), None)
        if not ay:
            continue
        # Gün, ay satırının 1-2 satır üstünde (arada tek başına '-' gibi satırlar olabilir).
        gun_satiri, gun = None, None
        for j in (i - 1, i - 2):
            if j < 0:
                continue
            gun = next((int(k) for k in sollar[j] if k.isdigit() and 1 <= int(k) <= 31), None)
            if gun is not None:
                gun_satiri = j
                break
        if gun_satiri is None:  # gün okunamadı: işyeri yazan satır bloğun başıdır
            gun_satiri = next((j for j in (i - 1, i - 2) if j >= 0 and len(re.findall(
                r"[A-Za-zÇĞİÖŞÜçğıöşü]", str(satirlar[j]))) >= 6), max(i - 1, 0))
        yil = next((int(k[-4:]) for k in (sollar[i + 1] if i + 1 < len(sollar) else [])
                    if re.fullmatch(r"\d?20\d\d", k)), None)
        if gun is None:  # OCR günü kaçırdıysa: önceki işlemin günü (liste yeniden eskiye)
            gun = capalar[-1][1].day if capalar else referans.day
        try:
            d = date(yil or referans.year, ay, gun)
        except ValueError:
            continue
        if not yil and d > referans + timedelta(days=31):
            d = d.replace(year=d.year - 1)
        if not pencerede(d, referans):  # yanlış okunmuş gün/ay: önceki işlemin tarihi
            d = capalar[-1][1] if capalar else referans
        if capalar and capalar[-1][0] == gun_satiri:
            continue
        capalar.append((gun_satiri, d))
    if len(capalar) < 2:
        return None

    sonuc = []
    sinirlar = [c[0] for c in capalar] + [len(satirlar)]
    for (bas, tarih), son in zip(capalar, sinirlar[1:], strict=True):
        aciklama_parca, tutarlar, blok_metni = [], [], []
        for j in range(bas, son):
            s = str(satirlar[j])
            a = _ascii(s)
            blok_metni.append(a)
            if _PUAN.search(a) or _EK_OZET.search(a) or _OZET.search(a):
                continue
            sag = sag_parcalar(satirlar[j])
            if not sag:
                continue
            bas_k, son_k = sag[0][0], sag[-1][1]
            parca_a, parca = a[bas_k:son_k], s[bas_k:son_k]
            satir_tutar = [t for t in _TUTAR.finditer(parca_a) if not _LIK.match(parca_a[t.end():])]
            saat = [m.span() for m in _SAAT.finditer(parca_a)]
            metin = _temiz_metin(parca, parca_a, saat + [t.span() for t in satir_tutar])
            harf = len(re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]", metin))
            if satir_tutar:
                tutarlar.extend(satir_tutar)
            if harf >= 3 and not tutarlar and len(aciklama_parca) < 2:
                aciklama_parca.append(metin)
        if not tutarlar or not aciklama_parca:
            continue
        aciklama = _ikonsuz(aciklama_parca[0])
        if not aciklama:
            continue
        tutar, arti = _tutar_coz(tutarlar[0])
        aciklama = _taksit_ekle_blok(aciklama, " ".join(blok_metni))
        if not arti and _ALACAK.search(_ascii(aciklama)):
            arti = True
        sonuc.append(Satir(tarih, aciklama, tutar, arti))
    return _isaret_normalle(sonuc)


def _ikonsuz(metin: str) -> str:
    """OCR'ın ikonlardan ürettiği baştaki artıkları ('*X', '&s', '49', '©') atar."""
    kelimeler = metin.split()
    while kelimeler and (len(kelimeler[0]) <= 2 or not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]{2}",
                                                                  kelimeler[0])):
        kelimeler.pop(0)
    return " ".join(kelimeler)


def _taksit_ekle_blok(aciklama: str, blok: str) -> str:
    from .metin import taksit_bul
    if taksit_bul(aciklama):
        return aciklama
    t = taksit_bul(blok)
    return f"{aciklama} TAKSİT {t[0]}/{t[1]}" if t else aciklama


def _tarih_sinirla(sonuc: list[Satir], referans: date) -> list[Satir]:
    """Son güvence: pencere dışında kalan tarih (OCR hatası) görüntü tarihine çekilir."""
    for s in sonuc:
        if not pencerede(s.tarih, referans):
            s.tarih = referans
    return sonuc


def _isaret_normalle(sonuc: list[Satir]) -> list[Satir]:
    """Harcamalar eksi gösteriliyorsa (çoğunluk eksi) kart işaretine çevir: artı = harcama."""
    isaretsiz = [s for s in sonuc if not s.arti_isaretli]
    if isaretsiz and sum(s.tutar < 0 for s in isaretsiz) > len(isaretsiz) / 2:
        for s in sonuc:
            s.tutar = -s.tutar
    return [s for s in sonuc if s.tutar != 0]


def ekran_islemleri(satirlar: list[str], referans: date | None = None) -> list[Satir]:
    """OCR satırlarından işlemleri çıkarır. Dönen tutarlar 'kart ekstresi' işaretindedir:
    artı = harcama; açık '+' ile gösterilenler (ödeme/iade) arti_isaretli=True."""
    referans = referans or date.today()
    sol = sol_sutun_islemleri(satirlar, referans)
    if sol:
        return _tarih_sinirla(sol, referans)
    kayitlar: list[_Kayit] = []
    tarih_satirlari: list[tuple[int, date]] = []
    bekleyen_metin = None
    for i, satir in enumerate(satirlar):
        satir = str(satir)
        a = _ascii(satir)
        if not a.strip() or _PUAN.search(a):
            continue
        tarih, tm = _tarih_bul(a, referans)
        cikar = [tm.span()] if tm else []
        cikar += [s.span() for s in _SAAT.finditer(a)]
        tutarlar = [t for t in _TUTAR.finditer(a)
                    if not any(b <= t.start() < e for b, e in cikar)]
        if tutarlar and (_OZET.search(a) or _EK_OZET.search(a)):
            bekleyen_metin = None
            continue
        metin = _temiz_metin(satir, a, cikar + [t.span() for t in tutarlar])
        harf = len(re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]", metin))
        if tutarlar:
            aciklama = metin if harf >= 3 else (bekleyen_metin or "")
            if not aciklama:
                continue
            kayitlar.append(_Kayit(i, aciklama, tutarlar, a, tarih))
            bekleyen_metin = None
        elif tarih:
            tarih_satirlari.append((i, tarih))
            if harf >= 3 and not _GURULTU.search(_ascii(metin)):
                bekleyen_metin = metin  # "12.11.2026 MIGROS" (tutar alt satırda)
        elif harf >= 3 and not _EK_OZET.search(a):
            bekleyen_metin = metin
    if not kayitlar:
        return []

    # Tarihsiz kayıtlar için düzeni belirle: tarih kaydın üstünde mi (başlık) altında mı?
    tarihsiz = [k for k in kayitlar if k.tarih is None]
    sonra_duzeni = False
    if tarihsiz and tarih_satirlari:
        ilk_kayit, ilk_tarih = kayitlar[0].sira, tarih_satirlari[0][0]
        benzer_sayi = abs(len(tarih_satirlari) - len(tarihsiz)) <= max(1, len(tarihsiz) // 5)
        sonra_duzeni = ilk_kayit < ilk_tarih and benzer_sayi
    siralar = [k.sira for k in kayitlar] + [10**9]
    for j, k in enumerate(kayitlar):
        if k.tarih is not None:
            continue
        if sonra_duzeni:
            sonraki = [t for s, t in tarih_satirlari if k.sira < s < siralar[j + 1]]
            k.tarih = sonraki[0] if sonraki else None
        if k.tarih is None:
            onceki = [t for s, t in tarih_satirlari if s < k.sira]
            k.tarih = onceki[-1] if onceki else None
        if k.tarih is None:
            # Uzun listenin devamı olan görüntüde tarih başlığı yukarıda kalmış olabilir:
            # en yakın sonraki tarihi, o da yoksa görüntünün tarihini (referans) kullan.
            sonraki = [t for s, t in tarih_satirlari if s > k.sira]
            k.tarih = sonraki[0] if sonraki else referans

    sonuc = []
    for k in kayitlar:
        if k.tarih is None:
            continue
        secilen = _tutar_sec(k.aciklama, k.tutarlar)
        tutar, arti = _tutar_coz(secilen)
        # OCR '+' işaretini kaçırabilir: ödeme/iade açıklamalı satırlar her durumda alacaktır.
        if not arti and _ALACAK.search(_ascii(k.aciklama)):
            arti = True
        sonuc.append(Satir(k.tarih, k.aciklama, tutar, arti))
    # Harcamalar eksi gösteriliyorsa (çoğunluk eksi) kart işaretine çevir: artı = harcama.
    isaretsiz = [s for s in sonuc if not s.arti_isaretli]
    if isaretsiz and sum(s.tutar < 0 for s in isaretsiz) > len(isaretsiz) / 2:
        for s in sonuc:
            s.tutar = -s.tutar
    return _tarih_sinirla([s for s in sonuc if s.tutar != 0], referans)


def gorsel_islemleri(yol: str | Path, referans: date | None = None
                     ) -> tuple[list[Satir], str | None]:
    """(işlemler, banka adı). Ekrandaki banka toplamları son_ozet'e yazılır."""
    from .pdf_ekstre import banka_bul
    satirlar = ocr_satirlari(yol)
    son_ozet.clear()
    son_ozet.update(ekran_ozeti(satirlar))
    islemler = ekran_islemleri(satirlar, referans)
    if not islemler:
        toplam = donem_ici_toplami(satirlar)
        if toplam is not None:  # yedek: işlemler okunamadı ama ekrandaki dönem içi toplamı var
            islemler = [Satir(referans or date.today(), OZET_ACIKLAMA, toplam, False)]
    if not islemler:
        raise OcrHatasi(f"{Path(yol).name}: görüntüde ne işlem satırı ne de 'dönem içi harcama' "
                        "toplamı tanınabildi. Aşağıdaki 'maskeli düzen' bölümünün ekran "
                        "görüntüsünü paylaşırsanız okuyucu bankanızın düzenine göre ayarlanabilir.")
    return islemler, banka_bul("\n".join(map(str, satirlar)))


OZET_ACIKLAMA = "DÖNEM İÇİ TOPLAM (özet; işlem detayı okunamadı)"
KALAN_ACIKLAMA = "DÖNEM İÇİ – ekranda görünmeyen işlemler (banka toplamından)"
TAKSIT_ACIKLAMA = "BU DÖNEME AİT TAKSİTLER (banka toplamından)"


def ekran_ozeti(satirlar: list[str]) -> dict:
    """Ekranın üstündeki banka toplamları:
    toplam        : bu dönem şimdiye kadarki borç/harcama (Güncel Dönem Borcu ya da Dönem İçi
                    Harcamalar Toplamı) — önceki ekstreler ödendi varsayımıyla kart borcu
    taksit_dahil  : toplam bu döneme ait taksitleri içeriyor mu ('Bu Döneme Ait Taksit Tutarı')
    kesim         : bir sonraki hesap kesim tarihi
    """
    s = [str(x) for x in satirlar]
    a = [_ascii(x) for x in s]

    def deger(etiket: str) -> float | None:
        for i, x in enumerate(a):
            if re.search(etiket, x):
                for aday in (x, a[i + 1] if i + 1 < len(a) else ""):
                    t = list(_TUTAR.finditer(aday))
                    if t:
                        return abs(_tutar_coz(t[0])[0])
        return None

    ozet = {"guncel_borc": deger(r"GUNCEL DONEM BORC"),
            "donem_ici_toplam": deger(r"DONEM\s?ICI HARCAMA"),
            "donem_taksit": deger(r"DONEME AIT TAKSIT|BU DONEM(IN)? TAKSIT")}
    ozet["toplam"] = ozet["guncel_borc"] or ozet["donem_ici_toplam"]
    ozet["taksit_dahil"] = bool(ozet["guncel_borc"] and ozet["donem_taksit"])
    kesim = next((m for x in a if "HESAP KESIM" in x
                  for m in [re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", x)] if m), None)
    if kesim:
        with contextlib.suppress(ValueError):
            ozet["kesim"] = date(int(kesim[3]), int(kesim[2]), int(kesim[1]))
    return {k: v for k, v in ozet.items() if v is not None}
_TOPLAM_ETIKETI = re.compile(r"DONEM\s?ICI|EKSTRE(YE|LENMEMIS)|HENUZ EKSTRE|GUNCEL DONEM")
_ONCEKI_BORC = re.compile(r"ONCEKI|SON EKSTRE|EKSTRE BORCU|ASGARI|LIMIT|PUAN|BONUS")


def donem_ici_toplami(satirlar: list[str]) -> float | None:
    """Ekrandaki 'Dönem içi harcamalar: 12.345,67 TL' gibi toplamı bulur (etiket ve tutar aynı
    satırda ya da tutar bir alt satırda). Önceki ekstre borcu/asgari/limit kullanılmaz."""
    satirlar = [str(s) for s in satirlar]
    for i, s in enumerate(satirlar):
        a = _ascii(s)
        if not _TOPLAM_ETIKETI.search(a) or _ONCEKI_BORC.search(a):
            continue
        for aday in (a, _ascii(satirlar[i + 1]) if i + 1 < len(satirlar) else ""):
            t = list(_TUTAR.finditer(aday))
            if t:
                return abs(_tutar_coz(t[0])[0])
    return None


def gorsel_tani(yol: str | Path, en_fazla: int = 60) -> str:
    """OCR metninin maskeli hâli (rakamlar 9, harfler x): paylaşılabilir, kişisel bilgi içermez."""
    from .pdf_ekstre import maskele
    satirlar = ocr_satirlari(yol)
    islemler = ekran_islemleri(satirlar)
    ozet = f"# {len(satirlar)} OCR satırı, {len(islemler)} işlem tanındı"
    return "\n".join([ozet] + [maskele(str(s)) for s in satirlar[:en_fazla]])
