"""Türkçe metin, tutar ve tarih ayrıştırma yardımcıları."""

from __future__ import annotations

import math
import re
from datetime import date, datetime


class EkstreHatasi(ValueError):
    """Ekstre okunamadığında kullanıcıya gösterilecek açıklamalı hata."""


_TR_ASCII = str.maketrans(
    {"ç": "c", "Ç": "C", "ğ": "g", "Ğ": "G", "ı": "i", "İ": "I", "ö": "o", "Ö": "O",
     "ş": "s", "Ş": "S", "ü": "u", "Ü": "U", "â": "a", "Â": "A", "î": "i", "û": "u"}
)


def sade(metin: str) -> str:
    """Türkçe karakterleri ASCII'ye çevirip büyük harfe dönüştürür, boşlukları sadeleştirir.

    >>> sade("Migros Ticaret A.Ş. İstanbul")
    'MIGROS TICARET A.S. ISTANBUL'
    """
    if metin is None:
        return ""
    return re.sub(r"\s+", " ", str(metin).translate(_TR_ASCII).upper()).strip()


def tutar_cozumle(deger) -> float | None:
    """'1.234,56', '-1.234,56 TL', '1,234.56', '(123,45)', '123,45-' gibi değerleri sayıya çevirir."""
    if deger is None:
        return None
    if isinstance(deger, (int, float)):
        if math.isnan(deger):
            return None
        return float(deger)
    s = str(deger).strip()
    if not s:
        return None
    negatif = False
    if s.startswith("(") and s.endswith(")"):
        negatif, s = True, s[1:-1]
    s = re.sub(r"(?i)\b(TL|TRY|USD|EUR)\b|[₺$€\s]", "", s)
    if s.endswith("-"):
        negatif, s = True, s[:-1]
    elif s.endswith("+"):
        s = s[:-1]
    if s.startswith("-"):
        negatif, s = True, s[1:]
    elif s.startswith("+"):
        s = s[1:]
    if not s or not re.fullmatch(r"[\d.,]+", s):
        return None
    if "," in s and "." in s:
        ondalik = "," if s.rfind(",") > s.rfind(".") else "."
        binlik = "." if ondalik == "," else ","
        s = s.replace(binlik, "").replace(ondalik, ".")
    elif "," in s:
        # Türkçe bağlamda virgül ondalık ayıracıdır.
        s = s.replace(",", "") if s.count(",") > 1 else s.replace(",", ".")
    elif "." in s and re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        sayi = float(s)
    except ValueError:
        return None
    return -sayi if negatif else sayi


_AYLAR = {
    "OCAK": 1, "SUBAT": 2, "MART": 3, "NISAN": 4, "MAYIS": 5, "HAZIRAN": 6,
    "TEMMUZ": 7, "AGUSTOS": 8, "EYLUL": 9, "EKIM": 10, "KASIM": 11, "ARALIK": 12,
}
_TARIH_BICIMLERI = ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%y", "%d/%m/%y",
                    "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d/%m/%Y %H:%M")


def tarih_cozumle(deger) -> date | None:
    """'12.11.2026', '12/11/26', '2026-11-12', '12 Kasım 2026' gibi tarihleri çözer (gün önce)."""
    if deger is None:
        return None
    if isinstance(deger, datetime):
        return deger.date()
    if isinstance(deger, date):
        return deger
    if hasattr(deger, "to_pydatetime"):  # pandas.Timestamp
        try:
            return deger.to_pydatetime().date()
        except ValueError:
            return None
    s = str(deger).strip()
    if not s or s.lower() in {"nan", "nat", "none"}:
        return None
    for bicim in _TARIH_BICIMLERI:
        try:
            return datetime.strptime(s, bicim).date()
        except ValueError:
            continue
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(\d{4})", s)
    if m and sade(m.group(2)) in _AYLAR:
        try:
            return date(int(m.group(3)), _AYLAR[sade(m.group(2))], int(m.group(1)))
        except ValueError:
            return None
    return None


_TAKSIT_ANAHTAR = re.compile(r"\bTAKS[I]?[TD]|\bTKS\b|\bTAK\b|\d\s*TK\b")  # "(2/3 TK)"  # TAKSİT, TAKSİDİ
_TAKSIT_ORAN = re.compile(r"(?<![\d/.])(\d{1,2})\s*/\s*(\d{1,2})(?![\d/.])")
_TAKSIT_CARPIM = re.compile(r"\d,\d{2}\s*X\s*(\d{1,2})\s*=.*?(\d{1,2})\s*\.\s*TAKS")
_TAKSIT_SIRA = re.compile(r"(\d{1,2})\s*\.\s*TAKS[I]?T\s*(?:/|DAN|NIN|UN)?\s*(?:TOPLAM\s*)?(\d{1,2})")


def taksit_bul(aciklama: str) -> tuple[int, int] | None:
    """Açıklamadan (kaçıncı taksit, toplam taksit) bilgisini çıkarır.

    >>> taksit_bul("TEKNOSA ISTANBUL TAKSİT 3/6")
    (3, 6)
    >>> taksit_bul("MIGROS 12/11 ISTANBUL") is None
    True
    """
    s = sade(aciklama)
    if not _TAKSIT_ANAHTAR.search(s):
        return None
    m = _TAKSIT_CARPIM.search(s)  # Garanti: "1.250,00X4=5.000,00 3.TAKSIT"
    if m and 1 <= int(m.group(2)) <= int(m.group(1)) <= 48:
        return int(m.group(2)), int(m.group(1))
    for desen in (_TAKSIT_SIRA, _TAKSIT_ORAN):
        for m in desen.finditer(s):
            k, n = int(m.group(1)), int(m.group(2))
            if 1 <= k <= n <= 48 and n > 1:
                return k, n
    return None


def isyeri_anahtari(aciklama: str) -> str:
    """Aynı işyerine ait işlemleri gruplamak için kısa bir anahtar üretir.

    Rakamları, taksit ifadelerini ve kısa ekleri atar; ilk iki anlamlı kelimeyi kullanır.
    """
    s = sade(aciklama)
    s = re.sub(r"\bTAKS[I]?T\w*|\bTKS\b", " ", s)
    s = re.sub(r"[^A-Z ]", " ", s)
    kelimeler = [k for k in s.split() if len(k) > 2 and k not in _GURULTU]
    return " ".join(kelimeler[:2]) if kelimeler else s.strip() or "BILINMEYEN"


_GURULTU = {
    "TIC", "TICARET", "SAN", "SANAYI", "LTD", "STI", "PAZ", "PAZARLAMA", "ISTANBUL", "ANKARA",
    "IZMIR", "TURKIYE", "TR", "TRY", "POS", "SATIS", "ISLEM", "ISLEMI", "HARCAMA", "INTERNET",
    "MAGAZA", "MAGAZACILIK", "MAGAZALARI", "SUBE", "SUBESI", "VE", "ILE", "ONLINE", "WWW",
    "COM", "HIZ", "HIZMETLERI", "LIMITED", "ANONIM", "SIRKETI", "KART", "KREDI", "BANKA",
}
