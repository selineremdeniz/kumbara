"""PDF hesap özeti / kredi kartı ekstresi okuyucu.

Bankaların PDF'leri çok farklıdır. Sırayla iki yöntem denenir; en çok geçerli işlem bulan seçilir:

1. Tablo: PDF'deki çizgili tablolar (pdfplumber) okunur, başlık satırı ("İşlem Tarihi",
   "Açıklama", "Tutar", "Borç/Alacak") Excel'deki gibi tanınır. Sonraki sayfalardaki başlıksız
   devam tabloları aynı sütun düzeniyle okunur.
2. Satır: metin satır satır taranır. Satır başında tarih aranır; tarih şu biçimlerde olabilir:
   12.10.2026, 12/10/26, 12-10-2026, 12 Ekim 2026, 12 EKİ 2026, 2026-10-12, ya da yılsız 12.10
   (yıl, belgedeki tam tarihlerden çıkarılır). Tarihten sonra saat olabilir. Tutar 1.234,56,
   1234,56, (1.234,56), -1.234,56, 1.234,56- ya da 1.234,56 + biçiminde olabilir; yanında TL/₺
   bulunabilir. Tutarı bir sonraki satırlarda olan (bölünmüş) açıklamalar birleştirilir.
   Toplam, devir ve son ödeme gibi özet satırları atlanır.

Kart ekstrelerinde açık "+" işaretli tutarlar (ödeme, iade) alacak kabul edilir.
Şifreli PDF'ler için `sifre` verilir. Okunamayan dosyalar için `tani()`, harfleri ve rakamları
maskelenmiş bir düzen özeti üretir; bu özet kişisel bilgi göstermeden paylaşılabilir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .metin import _TR_ASCII, EkstreHatasi, sade, taksit_bul, tarih_cozumle


class PdfHatasi(EkstreHatasi):
    pass


class PdfSifreHatasi(PdfHatasi):
    pass


_AYLAR = {"OCAK": 1, "SUBAT": 2, "MART": 3, "NISAN": 4, "MAYIS": 5, "HAZIRAN": 6, "TEMMUZ": 7,
          "AGUSTOS": 8, "EYLUL": 9, "EKIM": 10, "KASIM": 11, "ARALIK": 12}
_AY_KISA = {"OCA": 1, "SUB": 2, "MAR": 3, "NIS": 4, "MAY": 5, "HAZ": 6, "TEM": 7, "AGU": 8,
            "EYL": 9, "EKI": 10, "KAS": 11, "ARA": 12}
_AY_DESEN = "|".join(sorted([*_AYLAR, *_AY_KISA], key=len, reverse=True))

# Desenler ASCII'ye çevrilmiş, büyük harfli satır kopyası üzerinde çalışır (konumlar aynıdır).
_TARIH = re.compile(
    r"^\s*(?P<tarih>"
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
    rf"|\d{{1,2}}\s+(?:{_AY_DESEN})\.?\s+\d{{4}}"
    r"|\d{1,2}[./]\d{1,2}"
    r")(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?(?=\s|$)"
)
_TAM_TARIH = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)")
_TUTAR = re.compile(
    r"(?<![\d.,/%])(?P<on>[-+]\s?)?(?:(?:TL|TRY)\s?|₺\s?)?"
    r"(?P<sayi>\(?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}\)?)"
    r"(?P<son>\s?[-+](?=\s|$))?(?:\s?(?:TL|TRY|₺))?(?![\d/])"
)
_OZET = re.compile(r"TOPLAM|ONCEKI DONEM|DONEM BORCU|SON ODEME|ASGARI|HESAP KESIM|DEVREDEN|"
                   r"DEVIR|KULLANILABILIR LIMIT|KART LIMITI|EKSTRE BORCU|GECEN DONEM")


def _ascii(satir: str) -> str:
    """Konumları koruyarak ASCII + büyük harf (tek karakter -> tek karakter)."""
    s = satir.translate(_TR_ASCII)
    u = s.upper()
    return u if len(u) == len(s) else s


@dataclass
class Satir:
    tarih: date
    aciklama: str
    tutar: float          # işaretli; kart ekstresinde artı = harcama
    arti_isaretli: bool   # tutarın yanında açık "+" var mıydı (ödeme/iade)


def _tarih_coz(metin: str, referans: date) -> date | None:
    t = re.sub(r"\s+\d{1,2}:\d{2}(?::\d{2})?$", "", metin.strip())
    m = re.fullmatch(rf"(\d{{1,2}})\s+({_AY_DESEN})\.?\s+(\d{{4}})", t)
    if m:
        ay = _AYLAR.get(m[2]) or _AY_KISA.get(m[2])
        try:
            return date(int(m[3]), ay, int(m[1]))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})", t)
    if m:  # yılsız tarih
        try:
            d = date(referans.year, int(m[2]), int(m[1]))
        except ValueError:
            return None
        return d.replace(year=d.year - 1) if d > referans + timedelta(days=31) else d
    return tarih_cozumle(t)


def _tutar_coz(m: re.Match) -> tuple[float, bool]:
    sayi = m["sayi"]
    negatif = sayi.startswith("(")
    deger = float(sayi.strip("()").replace(".", "").replace(",", "."))
    isaretler = (m["on"] or "").strip() + (m["son"] or "").strip()
    if "-" in isaretler:
        negatif = True
    return (-deger if negatif else deger), "+" in isaretler


def _tutar_sec(aciklama: str, tutarlar: list[re.Match]) -> re.Match:
    """Birden çok tutar varsa: taksitli satırda toplam/taksit çiftinden taksiti, değilse ilkini."""
    if len(tutarlar) > 1:
        taksit = taksit_bul(aciklama)
        if taksit:
            n = taksit[1]
            degerler = [abs(_tutar_coz(t)[0]) for t in tutarlar]
            for i, kucuk in enumerate(degerler):
                if any(abs(buyuk - kucuk * n) <= 0.02 * buyuk + 1 for buyuk in degerler if buyuk > kucuk):
                    return tutarlar[i]
    return tutarlar[0]


class PdfSatiri(str):
    """Metin satırı + her kelimenin satırdaki konumu ve sayfadaki x aralığı."""
    konumlar: list[tuple[int, int, float, float]]  # (başlangıç, bitiş, x0, x1)

    def __new__(cls, kelimeler: list[dict]):
        parcalar, konumlar, i = [], [], 0
        for w in kelimeler:
            if parcalar:
                i += 1
            parcalar.append(w["text"])
            konumlar.append((i, i + len(w["text"]), w["x0"], w["x1"]))
            i += len(w["text"])
        nesne = super().__new__(cls, " ".join(parcalar))
        nesne.konumlar = konumlar
        return nesne

    def x1(self, konum: int) -> float | None:
        """Satırdaki karakter konumunu içeren kelimenin sağ kenarı."""
        for bas, son, _, x1 in getattr(self, "konumlar", []):
            if bas <= konum < son:
                return x1
        return None


_PUAN = re.compile(r"PUAN|BONUS|CHIP|MIL\b|PARAF")
_PUAN_BOLUMU = re.compile(r"(PUAN|BONUS|CHIP)\w*\s*(OZETI|DETAY|BILGI)")


def _islem_basligi_mi(a: str) -> bool:
    """'İşlem Tarihi ... Tutar(TL) ...' gibi başlık satırı mı? (İçinde rakam/tutar olmamalı;
    'İşlem Tutarı: 401,69 TRY' gibi bilgi satırları başlık değildir.)"""
    return ("TUTAR" in a and ("TARIH" in a or "ISLEM" in a) and not _TUTAR.search(a)
            and not re.search(r"\d{2}", a))


def _kolonlari_bul(satir: str, a: str) -> list[tuple[str, float]] | None:
    """İşlem tablosu başlığından sütunların sağ kenarları: [('tutar', x1), ('puan', x1), ...]."""
    konumlar = getattr(satir, "konumlar", None)
    if not konumlar:
        return None
    kolonlar, onceki = [], ""
    for bas, son, _, x1 in konumlar:
        k = a[bas:son]
        if "KALAN" in k or (onceki == "KALAN" and ("TUTAR" in k or "TAKSIT" in k)):
            kolonlar.append(("diger", x1))
        elif _PUAN.search(k):
            kolonlar.append(("puan", x1))
        elif "TUTAR" in k and not any(t == "tutar" for t, _ in kolonlar):
            kolonlar.append(("tutar", x1))
        onceki = k
    return kolonlar if any(t == "tutar" for t, _ in kolonlar) else None


def _tutarlari_kolonla_sec(satir: str, kayma: int, tutarlar: list[re.Match],
                           kolonlar: list[tuple[str, float]] | None) -> list[re.Match] | None:
    """Sütun bilgisi varsa TUTAR sütununa düşen tutarları döndürür.

    None: karar verilemedi (eski yöntem kullanılır); []: satırda yalnızca puan/bonus var.
    """
    if not kolonlar:
        return None
    secilen, puan_var = [], False
    for t in tutarlar:
        x = satir.x1(kayma + t.end() - 1) if isinstance(satir, PdfSatiri) else None
        if x is None:
            return None
        tip = min(kolonlar, key=lambda k: abs(k[1] - x))[0]
        if tip == "tutar":
            secilen.append(t)
        puan_var |= tip == "puan"
    if secilen:
        return secilen
    return [] if puan_var else None


def _taksit_ekle(aciklama: str, satir_a: str) -> str:
    """Taksit bilgisi açıklamada değil satırın başka yerindeyse açıklamaya ekler."""
    if taksit_bul(aciklama):
        return aciklama
    t = taksit_bul(satir_a)
    return f"{aciklama} TAKSİT {t[0]}/{t[1]}" if t else aciklama


def satirlari_ayristir(satirlar: list[str], referans: date | None = None) -> list[Satir]:
    """Metin satırlarından işlemleri çıkarır.

    Bölünmüş açıklamaları birleştirir, alt satırdaki taksit bilgisini ("...TL'lik işlemin 1 / 3
    taksidi") önceki işleme bağlar, puan özeti bölümlerini atlar ve sütun konumu biliniyorsa
    puan/bonus sütunundaki rakamları tutar saymaz.
    """
    referans = referans or date.today()
    sonuc: list[Satir] = []
    bekleyen: tuple[date, str] | None = None
    butce = 0
    kolonlar: list[tuple[str, float]] | None = None
    puan_bolumu = False

    def ekle(tarih, aciklama, tutarlar, satir, kayma, satir_a):
        nonlocal sonuc
        uygun = _tutarlari_kolonla_sec(satir, kayma, tutarlar, kolonlar)
        if uygun == []:
            return  # yalnızca puan/bonus satırı
        aciklama = re.sub(r"\s+", " ", aciklama).strip()
        if not uygun and _PUAN.search(_ascii(aciklama)) and len(tutarlar) == 1 and kolonlar is None:
            return  # "HEDİYE MAXIPUAN 100,00" gibi puan satırı
        secilen = uygun[0] if uygun else _tutar_sec(aciklama, tutarlar)
        tutar, arti = _tutar_coz(secilen)
        sonuc.append(Satir(tarih, _taksit_ekle(aciklama, satir_a), tutar, arti))

    for ham in satirlar:
        satir = ham if isinstance(ham, PdfSatiri) else ham.replace("\xa0", " ").rstrip()
        if not satir.strip():
            continue
        a = _ascii(satir)
        m = _TARIH.match(a)
        if not m and _islem_basligi_mi(a):
            kolonlar, puan_bolumu = _kolonlari_bul(satir, a), False
            continue
        if not m and (_PUAN_BOLUMU.search(a) or (
                "TARIH" in a and _PUAN.search(a) and "TUTAR" not in a and not _TUTAR.search(a))):
            puan_bolumu = True
            continue
        if m:
            bekleyen = None
            if puan_bolumu or _OZET.search(a):
                continue
            tarih = _tarih_coz(m["tarih"], referans)
            if tarih is None:
                continue
            kalan_a, kalan = a[m.end():], satir[m.end():]
            tutarlar = list(_TUTAR.finditer(kalan_a))
            if not tutarlar:
                bekleyen, butce = (tarih, kalan.strip()), 2
                continue
            aciklama = kalan[:tutarlar[0].start()].strip()
            if not aciklama:  # tutar açıklamadan önce yazılmış
                aciklama = kalan[tutarlar[-1].end():].strip()
            ekle(tarih, aciklama, tutarlar, satir, m.end(), a)
        elif bekleyen:
            tutarlar = list(_TUTAR.finditer(a))
            if tutarlar and not _OZET.search(a):
                ek = satir[:tutarlar[0].start()].strip()
                ekle(bekleyen[0], f"{bekleyen[1]} {ek}", tutarlar, satir, 0, a)
                bekleyen = None
            else:
                butce -= 1
                bekleyen = (bekleyen[0], f"{bekleyen[1]} {satir.strip()}") if butce > 0 else None
        elif sonuc and not puan_bolumu and "TAKSI" in a and not taksit_bul(sonuc[-1].aciklama):
            t = taksit_bul(a)  # alt satırdaki taksit bilgisi: "3.300,00 TL'lik işlemin 1 / 3 taksidi"
            if t and not _OZET.search(a):
                sonuc[-1].aciklama += f" TAKSİT {t[0]}/{t[1]}"
    return [s for s in sonuc if s.tutar != 0]


def _sayfa_satirlari(sayfa) -> list[str]:
    """Kelimeleri konumlarıyla satırlara gruplar; konum alınamazsa düz metne döner."""
    try:
        kelimeler = sayfa.extract_words(x_tolerance=1.5, y_tolerance=3)
    except Exception:  # pragma: no cover - bozuk sayfa
        kelimeler = []
    if not kelimeler:
        return (sayfa.extract_text(x_tolerance=1.5, y_tolerance=3) or "").splitlines()
    kelimeler = [w for w in kelimeler if w.get("upright", True)]
    kelimeler.sort(key=lambda w: (w["top"], w["x0"]))
    satirlar, grup, ust = [], [], None
    for w in kelimeler:
        if ust is not None and abs(w["top"] - ust) > 3:
            satirlar.append(PdfSatiri(sorted(grup, key=lambda k: k["x0"])))
            grup = []
        if not grup:
            ust = w["top"]
        grup.append(w)
    if grup:
        satirlar.append(PdfSatiri(sorted(grup, key=lambda k: k["x0"])))
    return satirlar


def _referans_tarih(metin: str) -> date:
    tarihler = []
    for g, a, y in _TAM_TARIH.findall(metin):
        try:
            tarihler.append(date(int(y), int(a), int(g)))
        except ValueError:
            continue
    makul = [t for t in tarihler if date(2000, 1, 1) <= t <= date.today() + timedelta(days=60)]
    return max(makul) if makul else date.today()


def _ac(yol: Path, sifre: str | None):
    import pdfplumber
    try:
        return pdfplumber.open(yol, password=sifre or "")
    except Exception as e:
        zincir, h = [], e
        while h is not None and len(zincir) < 5:  # pdfplumber asıl hatayı sarmalıyor
            zincir.append(f"{type(h).__name__} {h} {' '.join(map(str, getattr(h, 'args', ())))}")
            h = h.__cause__ or h.__context__
        ad = " ".join(zincir).lower()
        if "password" in ad or "encrypt" in ad or "decrypt" in ad:
            raise PdfSifreHatasi(
                f"{yol.name}: PDF şifreli. Bankanın e-postadaki şifresini girin "
                "(çoğu bankada T.C. kimlik no'nun ilk/son haneleri veya doğum tarihi)."
                if not sifre else f"{yol.name}: PDF şifresi yanlış.") from e
        raise PdfHatasi(f"{yol.name}: PDF açılamadı ({type(e).__name__}: {e}).") from e


def _metin_ve_tablolar(yol: Path, sifre: str | None) -> tuple[list[str], list[list[list[str]]]]:
    satirlar: list[str] = []
    tablolar: list[list[list[str]]] = []
    with _ac(yol, sifre) as pdf:
        for sayfa in pdf.pages:
            satirlar.extend(_sayfa_satirlari(sayfa))
            for tablo in sayfa.extract_tables() or []:
                temiz = [[re.sub(r"\s+", " ", str(h or "")).strip() for h in satir]
                         for satir in tablo if satir and any(h for h in satir)]
                if temiz:
                    tablolar.append(temiz)
    return satirlar, tablolar


def _tablolardan(tablolar: list[list[list[str]]], referans: date) -> tuple[list[Satir], bool]:
    """Başlıklı tablolardan işlemler. (satırlar, borç/alacak sütunlu mu)"""
    from .ekstre import _basliklari_eslestir
    from .metin import tutar_cozumle
    sonuc, borc_alacak, eslesme = [], False, None
    for tablo in tablolar:
        bas = None
        for i, satir in enumerate(tablo[:5]):
            e = _basliklari_eslestir(satir)
            if "tarih" in e and ({"tutar", "borc", "alacak"} & e.keys()):
                bas, eslesme, genislik = i, e, len(satir)
                break
        if bas is None:
            if eslesme is None or len(tablo[0]) != genislik:
                continue
            bas = -1  # önceki tablonun devamı
        for satir in tablo[bas + 1:]:
            def h(alan, satir=satir, eslesme=eslesme):
                i = eslesme.get(alan)
                return satir[i] if i is not None and i < len(satir) else ""
            if _OZET.search(_ascii(" ".join(satir))):
                continue
            tarih = _tarih_coz(h("tarih"), referans) if h("tarih") else None
            if tarih is None:
                continue
            arti = "+" in h("tutar")
            if "tutar" in eslesme:
                tutar = tutar_cozumle(h("tutar"))
            else:
                borc_alacak = True
                b, a = tutar_cozumle(h("borc")) or 0, tutar_cozumle(h("alacak")) or 0
                tutar = abs(a) - abs(b)
            if tutar:
                sonuc.append(Satir(tarih, h("aciklama"), float(tutar), arti))
    return sonuc, borc_alacak


# Sıra önemli: banka adları marka adlarından (Bonus, World...) önce denenir.
_BANKALAR = [
    (r"VAKIFBANK|VAKIF KATILIM", "VakıfBank"), (r"DENIZBANK", "DenizBank"),
    (r"YAPI KREDI|YAPI VE KREDI|WORLDCARD|WORLDPUAN", "Yapı Kredi"),
    (r"GARANTI BBVA|GARANTI BANKASI|BONUSFLAS", "Garanti BBVA"),
    (r"ISBANK|IS BANKASI|MAXIMUM|MAXIPUAN", "İş Bankası"), (r"AKBANK|AXESS|CHIP-PARA", "Akbank"),
    (r"ZIRAAT|BANKKART", "Ziraat"), (r"HALKBANK|PARAF", "Halkbank"),
    (r"QNB|FINANSBANK|CARDFINANS", "QNB"), (r"ENPARA", "Enpara"), (r"KUVEYT", "Kuveyt Türk"),
    (r"\bTEB\b|TURK EKONOMI", "TEB"), (r"\bING\b", "ING"), (r"HSBC", "HSBC"),
    (r"ALBARAKA", "Albaraka"), (r"ODEABANK", "Odeabank"), (r"FIBABANKA", "Fibabanka"),
]


def banka_bul(metin: str) -> str | None:
    a = _ascii(metin)
    return next((ad for desen, ad in _BANKALAR if re.search(desen, a)), None)


def pdf_islemleri(yol: str | Path, sifre: str | None = None
                  ) -> tuple[list[Satir], str | None, str | None]:
    """PDF'den işlemleri çıkarır. (işlemler, tür ipucu: 'hesap'/'kart'/None, banka adı)"""
    yol = Path(yol)
    satirlar, tablolar = _metin_ve_tablolar(yol, sifre)
    metin = "\n".join(satirlar)
    if len(metin.strip()) < 20:
        raise PdfHatasi(f"{yol.name}: PDF'de metin yok; taranmış (resim) bir belge. Bankanın "
                        "internet şubesinden Excel/CSV ya da metin içeren PDF indirin.")
    if metin.count("(cid:") > 20:
        raise PdfHatasi(f"{yol.name}: PDF'deki yazı tipi metne çevrilemiyor. Bankanın Excel/CSV "
                        "dökümünü kullanın.")
    referans = _referans_tarih(metin)
    tablo_satirlari, borc_alacak = _tablolardan(tablolar, referans)
    metin_satirlari = satirlari_ayristir(satirlar, referans)
    if len(tablo_satirlari) >= len(metin_satirlari) and tablo_satirlari:
        secilen, ipucu = tablo_satirlari, ("hesap" if borc_alacak else None)
    else:
        secilen, ipucu = metin_satirlari, None
    if not secilen:
        raise PdfHatasi(f"{yol.name}: PDF'de metin var ama işlem satırı tanınamadı. "
                        "`kumbara pdf-tani` ile maskeli düzeni görüp paylaşabilirsiniz.")
    if ipucu is None and any(s.arti_isaretli for s in secilen):
        ipucu = "kart"  # "+" ile işaretli ödemeler kart ekstresine özgü
    return secilen, ipucu, banka_bul(metin)


# --- Tanı ----------------------------------------------------------------------------------------

_KORUNAN = {*_AYLAR, *_AY_KISA, "TARIH", "TARIHI", "ISLEM", "ISLEMLER", "ACIKLAMA", "ACIKLAMASI",
            "TUTAR", "TUTARI", "TL", "TRY", "USD", "EUR", "BORC", "BORCU", "ALACAK", "BAKIYE",
            "TAKSIT", "TAKSITI", "TKS", "ODEME", "ODEMESI", "TOPLAM", "DONEM", "DONEMI", "KESIM",
            "SON", "HARCAMA", "HARCAMALAR", "PUAN", "BONUS", "MAXIPUAN", "WORLDPUAN", "CHIP", "PARA",
            "IADE", "FAIZ", "ASGARI", "LIMIT", "KART", "KREDI", "HESAP", "OZETI", "EKSTRE", "VALOR",
            "DETAY", "ISYERI", "MIKTAR", "ONCEKI", "SAYFA", "NO", "KALAN", "TESEKKUR", "EDERIZ"}


def maskele(satir: str) -> str:
    """Düzeni koruyup içeriği gizler: rakamlar 9, harfler x/X olur; başlık sözcükleri korunur."""
    def kelime(m: re.Match) -> str:
        k = m[0]
        if sade(k).strip(".:") in _KORUNAN:
            return k
        return "".join("X" if c.isupper() else "x" for c in k)
    s = re.sub(r"\d", "9", satir)
    return re.sub(r"[^\W\d_]+", kelime, s)


def tani(yol: str | Path, sifre: str | None = None, en_fazla: int = 60) -> str:
    """Maskeli düzen özeti: kişisel bilgi içermez, hata ayıklamak için paylaşılabilir."""
    yol = Path(yol)
    satirlar, tablolar = _metin_ve_tablolar(yol, sifre)
    metin = "\n".join(satirlar)
    referans = _referans_tarih(metin)
    tablo_s, _ = _tablolardan(tablolar, referans)
    metin_s = satirlari_ayristir(satirlar, referans)
    ozet = [f"# {len(satirlar)} metin satırı, {len(tablolar)} tablo, '(cid:' sayısı "
            f"{metin.count('(cid:')}; tablo yöntemi {len(tablo_s)}, satır yöntemi "
            f"{len(metin_s)} işlem buldu",
            "# Tablo başlıkları: " + " || ".join(" | ".join(maskele(h) for h in t[0])
                                                for t in tablolar[:4])]
    dolu = [s for s in satirlar if s.strip()]
    return "\n".join(ozet + [maskele(s) for s in dolu[:en_fazla]])


# Ekstredeki bankanın kendi toplamı (öncelik sırasıyla). Önceki dönem, asgari, limit hariç.
_TOPLAM_ETIKETLERI = [
    (r"DONEM\s?ICI HARCAMA", "Dönem içi harcamalar"),
    (r"HESAP OZETI BORCU|EKSTRE BORCU", "Hesap özeti borcu"),
    (r"DONEM BORCU", "Dönem borcu"),
    (r"GUNCEL DONEM BORCU|TOPLAM BORC", "Toplam borç"),
]
_TOPLAM_HARIC = re.compile(r"ONCEKI|ASGARI|MINIMUM|LIMIT|SON ODEME|GECEN|PUAN|BONUS|TAKSITLI")


def ekstre_toplami(yol: str | Path, sifre: str | None = None) -> tuple[float, str] | None:
    """PDF ekstrede bankanın yazdığı dönem toplamı: (tutar, etiket) ya da None."""
    satirlar, _ = _metin_ve_tablolar(Path(yol), sifre)
    a = [_ascii(str(s)) for s in satirlar]
    for desen, etiket in _TOPLAM_ETIKETLERI:
        for i, x in enumerate(a):
            m = re.search(desen, x)
            if not m or _TOPLAM_HARIC.search(x):
                continue
            for aday in (x[m.end():], a[i + 1] if i + 1 < len(a) else ""):
                t = list(_TUTAR.finditer(aday))
                if t:
                    return abs(_tutar_coz(t[0])[0]), etiket
    return None
