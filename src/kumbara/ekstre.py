"""Banka hesap hareketi ve kredi kartı ekstrelerini (CSV, XLSX, PDF) ortak biçime çevirir.

Ortak biçim (pandas.DataFrame):
    islem_id, tarih (date), aciklama (str), tutar (float; eksi = gider, artı = gelir),
    hesap (str), kaynak (dosya adı), taksit_no, taksit_toplam (Int64, taksitli değilse boş),
    kaynak_turu ("kart" | "hesap")
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pandas as pd

from .metin import EkstreHatasi, sade, taksit_bul, tarih_cozumle, tutar_cozumle

__all__ = ["EkstreHatasi", "oku", "normalize", "SUTUNLAR"]

SUTUNLAR = ["islem_id", "tarih", "aciklama", "tutar", "hesap", "kaynak", "taksit_no",
            "taksit_toplam", "kaynak_turu", "donem_ici"]

# Başlık eş anlamlıları (sade() ile normalize edilmiş). Sıra tercih sırasıdır.
ES_ANLAMLI = {
    "tarih": ["ISLEM TARIHI", "TARIH", "ISLEM ZAMANI", "DATE", "TRANSACTION DATE", "VALOR"],
    "aciklama": ["ACIKLAMA", "ISLEM ACIKLAMASI", "ISLEM DETAYI", "DETAY", "ISYERI", "ISYERI ADI",
                 "DESCRIPTION", "ISLEM"],
    "tutar": ["ISLEM TUTARI", "TUTAR", "TUTAR (TL)", "TUTAR TL", "TL TUTAR", "AMOUNT", "MIKTAR"],
    "borc": ["BORC", "BORC TUTARI", "CIKAN", "CEKILEN", "DEBIT"],
    "alacak": ["ALACAK", "ALACAK TUTARI", "GIREN", "YATAN", "CREDIT"],
}


def _basliklari_eslestir(hucreler: list) -> dict[str, int]:
    adlar = [sade(h) for h in hucreler]
    eslesme: dict[str, int] = {}
    for tam in (True, False):  # önce tam eşleşme, sonra önek
        for alan, adaylar in ES_ANLAMLI.items():
            if alan in eslesme:
                continue
            for aday in adaylar:
                for i, ad in enumerate(adlar):
                    if i in eslesme.values() or not ad:
                        continue
                    if (ad == aday) if tam else ad.startswith(aday):
                        eslesme[alan] = i
                        break
                if alan in eslesme:
                    break
    return eslesme


def _baslik_satiri_bul(ham: pd.DataFrame, sinir: int = 40) -> tuple[int, dict[str, int]]:
    for i in range(min(sinir, len(ham))):
        eslesme = _basliklari_eslestir(list(ham.iloc[i].values))
        if "tarih" in eslesme and ({"tutar", "borc", "alacak"} & eslesme.keys()):
            return i, eslesme
    raise EkstreHatasi(
        "Başlık satırı bulunamadı. Dosyada 'Tarih' ve 'Tutar' (veya 'Borç/Alacak') sütunları "
        "olmalı; yoksa kolonlar={'tarih': ..., 'aciklama': ..., 'tutar': ...} verin."
    )


def _ayirici_bul(satirlar: list[str]) -> str:
    """Satırların çoğunu aynı sayıda parçaya bölen ayırıcıyı seçer (';' öncelikli)."""
    puanlar = {}
    for ayirici in (";", "\t", "|", ","):
        sayilar = [s.count(ayirici) for s in satirlar if s.strip()]
        sayilar = [c for c in sayilar if c > 0]
        if not sayilar:
            continue
        mod = max(set(sayilar), key=sayilar.count)
        puanlar[ayirici] = sayilar.count(mod)
    if not puanlar:
        return ","
    en_iyi = max(puanlar.values())
    # Tutarlardaki ondalık virgül ',' puanını şişirebilir; yakın puanda diğerlerini tercih et.
    return next(a for a in (";", "\t", "|", ",") if puanlar.get(a, 0) >= 0.8 * en_iyi)


def _csv_oku(yol: Path) -> pd.DataFrame:
    import csv
    import io

    ham = yol.read_bytes()
    for kodlama in ("utf-8-sig", "cp1254", "iso-8859-9"):
        try:
            metin = ham.decode(kodlama)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise EkstreHatasi(f"{yol.name}: karakter kodlaması çözülemedi.")
    satirlar = metin.splitlines()
    ayirici = _ayirici_bul(satirlar[:60])
    kayitlar = list(csv.reader(io.StringIO(metin), delimiter=ayirici, quotechar='"'))
    genislik = max((len(k) for k in kayitlar), default=0)
    return pd.DataFrame([k + [None] * (genislik - len(k)) for k in kayitlar], dtype=object)


def _gorsel_oku(yol: Path, tur: str, referans) -> tuple[pd.DataFrame, str | None]:
    """Ekran görüntüsünü OCR ile okuyup başlıklı ham tabloya çevirir; bkz. gorsel."""
    from .gorsel import gorsel_islemleri, son_ozet
    islemler, banka = gorsel_islemleri(yol, referans)
    _gorsel_oku.ozet = dict(son_ozet)
    satirlar = []
    for s in islemler:
        tutar = s.tutar
        if s.arti_isaretli and tur in ("kart", "otomatik"):
            tutar = -abs(tutar)  # "+" = ödeme/iade (alacak)
        satirlar.append([s.tarih, s.aciklama, tutar])
    return pd.DataFrame([["Tarih", "Açıklama", "Tutar"], *satirlar], dtype=object), banka


def _pdf_oku(yol: Path, sifre: str | None, tur: str) -> tuple[pd.DataFrame, str | None, str | None]:
    """PDF'i (tablo veya satır yöntemiyle) okuyup başlıklı ham tabloya çevirir; bkz. pdf_ekstre."""
    from .pdf_ekstre import pdf_islemleri
    islemler, ipucu, banka = pdf_islemleri(yol, sifre)
    kart_olabilir = tur == "kart" or (tur == "otomatik" and ipucu != "hesap")
    satirlar = []
    for s in islemler:
        tutar = s.tutar
        if s.arti_isaretli and kart_olabilir:
            tutar = -abs(tutar)  # kart ekstresinde "+" = ödeme/iade (alacak)
        satirlar.append([s.tarih, s.aciklama, tutar])
    return pd.DataFrame([["Tarih", "Açıklama", "Tutar"], *satirlar], dtype=object), ipucu, banka


def oku(yol: str | Path, hesap: str | None = None, tur: str = "otomatik",
        kolonlar: dict[str, str] | None = None, sifre: str | None = None,
        donem_ici: bool | None = None, referans: date | None = None) -> pd.DataFrame:
    """Bir ekstre dosyasını ortak biçime çevirir.

    tur: "hesap" (eksi = para çıkışı), "kart" (artı = harcama; işaret ters çevrilir) veya
         "otomatik" (Borç/Alacak sütunu varsa hesap; tutarların çoğu artıysa kart).
    kolonlar: başlık otomatik bulunamazsa {"tarih": "İşlem Tarihi", "aciklama": ..., "tutar": ...}
    sifre: şifreli PDF'ler için.
    donem_ici: henüz ekstreye girmemiş işlemler mi? Boşsa: görüntüler (ekran görüntüsü) evet,
        PDF/CSV/XLSX hayır. Dönem içi işlemler ekstre yüklenince onunla değiştirilir.
    referans: görüntülerdeki "Bugün/Dün" ve yılsız tarihler için tarih (boşsa bugün).
    """
    from .gorsel import GORSEL_UZANTILARI
    yol = Path(yol)
    uzanti = yol.suffix.lower()
    if uzanti in {".xlsx", ".xlsm", ".xls"}:
        ham, banka = pd.read_excel(yol, header=None, dtype=object), None
    elif uzanti in {".csv", ".txt", ".tsv"}:
        ham, banka = _csv_oku(yol), None
    elif uzanti == ".pdf":
        ham, ipucu, banka = _pdf_oku(yol, sifre, tur)
        if tur == "otomatik" and ipucu:
            tur = ipucu
    elif uzanti in GORSEL_UZANTILARI:
        ham, banka = _gorsel_oku(yol, tur, referans)
        if not hesap and not banka:
            raise EkstreHatasi(
                f"{yol.name}: görüntünün hangi karta ait olduğu anlaşılamadı. Kartı seçin "
                "(panelde 'Hesap', komut satırında --hesap \"Yapı Kredi Kart\"); ekstresiyle "
                "eşleşmesi için ekstrenin yüklendiği adla aynı olmalı.")
        if tur == "otomatik":
            tur = "kart"  # dönem içi ekranları kredi kartı içindir; hesap için tur="hesap" verin
    else:
        raise EkstreHatasi(f"Desteklenmeyen dosya türü: {uzanti}")
    ham = ham.dropna(how="all").reset_index(drop=True)

    if kolonlar:
        baslik_i = _kolon_satiri(ham, kolonlar)
        if baslik_i is None:
            raise EkstreHatasi(f"Verilen kolon adları dosyada bulunamadı: {list(kolonlar.values())}")
        basliklar = [sade(h) for h in ham.iloc[baslik_i].values]
        eslesme = {alan: basliklar.index(sade(ad)) for alan, ad in kolonlar.items()}
    else:
        baslik_i, eslesme = _baslik_satiri_bul(ham)

    govde = ham.iloc[baslik_i + 1:]

    def sutun(alan):
        return govde.iloc[:, eslesme[alan]] if alan in eslesme else None

    tarih = sutun("tarih").map(tarih_cozumle)
    aciklama = (sutun("aciklama") if "aciklama" in eslesme else pd.Series("", index=govde.index))
    aciklama = aciklama.fillna("").astype(str).str.strip()
    if "tutar" in eslesme:
        tutar = sutun("tutar").map(tutar_cozumle)
    else:
        borc = sutun("borc").map(tutar_cozumle) if "borc" in eslesme else 0
        alacak = sutun("alacak").map(tutar_cozumle) if "alacak" in eslesme else 0
        borc = pd.Series(borc, index=govde.index).fillna(0).abs()
        alacak = pd.Series(alacak, index=govde.index).fillna(0).abs()
        tutar = alacak - borc

    df = pd.DataFrame({"tarih": tarih, "aciklama": aciklama, "tutar": tutar})
    df = df.dropna(subset=["tarih", "tutar"])
    df = df[df["tutar"] != 0]
    if df.empty:
        raise EkstreHatasi(f"{yol.name}: geçerli işlem satırı bulunamadı.")

    if tur == "otomatik":
        tur = "hesap" if {"borc", "alacak"} & eslesme.keys() else (
            "kart" if (df["tutar"] > 0).mean() > 0.7 else "hesap")
    if tur == "kart":
        df["tutar"] = -df["tutar"]
    elif tur != "hesap":
        raise EkstreHatasi("tur 'hesap', 'kart' veya 'otomatik' olmalı.")

    if not hesap and banka:  # dosya adı yerine (ad soyad içerebilir) bankayı kullan
        hesap = f"{banka} {'Kart' if tur == 'kart' else 'Hesap'}"
    df["hesap"] = hesap or yol.stem
    df["kaynak"] = yol.name
    df["kaynak_turu"] = tur
    df["donem_ici"] = (uzanti in GORSEL_UZANTILARI) if donem_ici is None else bool(donem_ici)
    sonuc = normalize(df)
    if uzanti in GORSEL_UZANTILARI:  # ekrandaki banka toplamları (depo kalan satırlarını kurar)
        sonuc.attrs["ekran_ozeti"] = getattr(_gorsel_oku, "ozet", {})
        sonuc.attrs["ekran_tarihi"] = referans or date.today()
    return sonuc


def _kolon_satiri(ham: pd.DataFrame, kolonlar: dict[str, str]) -> int | None:
    istenen = {sade(v) for v in kolonlar.values()}
    for i in range(min(40, len(ham))):
        if istenen <= {sade(h) for h in ham.iloc[i].values}:
            return i
    return None


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Taksit bilgisini ve kararlı işlem kimliğini ekler (aynı dosya iki kez yüklenirse tekrar
    etmez; aynı gün aynı tutarlı iki gerçek işlem ise ayrı kalır)."""
    df = df.copy()
    df["tarih"] = pd.to_datetime(df["tarih"]).dt.date
    df["tutar"] = df["tutar"].astype(float).round(2)
    if "kaynak_turu" not in df.columns:
        df["kaynak_turu"] = "hesap"
    df["donem_ici"] = df["donem_ici"].fillna(False).astype(bool) if "donem_ici" in df else False
    taksit = df["aciklama"].map(taksit_bul)
    df["taksit_no"] = pd.array([t[0] if t else None for t in taksit], dtype="Int64")
    df["taksit_toplam"] = pd.array([t[1] if t else None for t in taksit], dtype="Int64")
    anahtar = (df["hesap"].astype(str) + "|" + df["tarih"].astype(str) + "|"
               + df["aciklama"].map(sade) + "|" + df["tutar"].map(lambda t: f"{t:.2f}"))
    sira = anahtar.groupby(anahtar).cumcount().astype(str)
    df["islem_id"] = (anahtar + "|" + sira).map(
        lambda s: hashlib.sha1(s.encode("utf-8")).hexdigest()[:16])
    return df[SUTUNLAR].sort_values("tarih").reset_index(drop=True)
