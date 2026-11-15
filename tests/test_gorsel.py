"""Dönem içi ekran görüntüleri (OCR), ekstreyle eşleştirme ve kart borcu testleri."""

import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from kumbara.depo import Depo
from kumbara.ekstre import normalize, oku
from kumbara.gorsel import ekran_islemleri
from kumbara.kart import kart_borclari
from kumbara.kategori import Kategorilendirici

REF = date(2026, 11, 14)
DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _ozet(islemler):
    return [(s.tarih, s.aciklama.split()[0], s.tutar, s.arti_isaretli) for s in islemler]


# --- Düzen mantığı (OCR'sız) --------------------------------------------------------------------

def test_baslik_duzeni_tarih_ustte():
    satirlar = ["Dönem İçi İşlemler", "Dönem içi harcama 1.520,40 TL", "13 Kasım 2026 Perşembe",
                "MIGROS ISTANBUL -245,90 TL", "SPOTIFY -99,00 TL", "12 Kasım 2026",
                "ÖDEMENİZ İÇİN TEŞEKKÜRLER +5.000,00 TL", "TEKNOSA 3/6 Taksit -1.000,00 TL"]
    assert _ozet(ekran_islemleri(satirlar, REF)) == [
        (date(2026, 11, 13), "MIGROS", 245.90, False), (date(2026, 11, 13), "SPOTIFY", 99.0, False),
        (date(2026, 11, 12), "ÖDEMENİZ", -5000.0, True), (date(2026, 11, 12), "TEKNOSA", 1000.0, False)]


def test_tarih_altta_duzeni():
    satirlar = ["MIGROS ISTANBUL 245,90 TL", "13.11.2026 14:32", "A101 YENI MAGAZACILIK 89,50 TL",
                "12.11.2026 09:10", "SHELL 1.500,00 TL", "10.11.2026 18:45"]
    assert [(d, a, t) for d, a, t, _ in _ozet(ekran_islemleri(satirlar, REF))] == [
        (date(2026, 11, 13), "MIGROS", 245.90), (date(2026, 11, 12), "A101", 89.50),
        (date(2026, 11, 10), "SHELL", 1500.0)]


def test_tek_satir_ve_isyeri_ustte_bugun_dun():
    satirlar = ["Bugün", "STARBUCKS", "185,00 TL", "Dün", "YEMEKSEPETİ.COM", "430,75 TL",
                "11.11.2026 UBER TRIP 212,40"]
    assert _ozet(ekran_islemleri(satirlar, REF)) == [
        (REF, "STARBUCKS", 185.0, False), (date(2026, 11, 13), "YEMEKSEPETİ.COM", 430.75, False),
        (date(2026, 11, 11), "UBER", 212.40, False)]


def test_limit_ve_puan_satirlari_islem_degil():
    satirlar = ["Kullanılabilir Limit 45.000,00 TL", "Toplam 1.234,56 TL", "Kazanılan Bonus 12,34 TL",
                "13 Kasım 2026", "MIGROS 245,90 TL"]
    assert len(ekran_islemleri(satirlar, REF)) == 1


# --- Gerçek OCR (Tesseract) ---------------------------------------------------------------------

def _ekran(yol: Path, satirlar: list[tuple[str, str]], koyu: bool = False) -> Path:
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(str(DEJAVU), 38)
    kucuk = ImageFont.truetype(str(DEJAVU), 30)
    arka, yazi, soluk = ((18, 18, 18), (235, 235, 235), (160, 160, 160)) if koyu else (
        (255, 255, 255), (20, 20, 20), (110, 110, 110))
    img = Image.new("RGB", (1170, 140 + 78 * len(satirlar)), arka)
    d = ImageDraw.Draw(img)
    y = 60
    for sol, sag in satirlar:
        f, renk = (kucuk, soluk) if sol.startswith("~") else (font, yazi)
        d.text((48, y), sol.lstrip("~"), font=f, fill=renk)
        if sag:
            w = d.textlength(sag, font=font)
            d.text((1170 - 48 - w, y), sag, font=font, fill=yazi)
        y += 78
    img.save(yol, quality=92)
    return yol


ocr = pytest.mark.skipif(not (shutil.which("tesseract") and DEJAVU.exists()),
                         reason="Tesseract veya font yok")


@ocr
@pytest.mark.parametrize("koyu", [False, True])
def test_ocr_ekran_goruntusu(tmp_path, koyu):
    pytest.importorskip("pytesseract")
    yol = _ekran(tmp_path / ("koyu.png" if koyu else "acik.jpg"), [
        ("Dönem İçi İşlemler", ""), ("Kullanılabilir Limit", "45.000,00 TL"),
        ("~13 Kasım 2026 Perşembe", ""),
        ("MIGROS TİCARET İSTANBUL", "-245,90 TL"), ("SPOTIFY", "-99,00 TL"),
        ("~12 Kasım 2026 Çarşamba", ""),
        ("ÖDEMENİZ İÇİN TEŞEKKÜRLER", "+5.000,00 TL"), ("TEKNOSA 3/6 Taksit", "-1.000,00 TL")],
        koyu)
    df = Kategorilendirici.varsayilan().uygula(oku(yol, hesap="Yapı Kredi Kart"))
    assert df["donem_ici"].all() and set(df["kaynak_turu"]) == {"kart"}
    tutar = dict(zip(df["aciklama"].str.split().str[0], df["tutar"], strict=False))
    assert tutar["MIGROS"] == -245.90 and tutar["SPOTIFY"] == -99.0
    assert tutar["TEKNOSA"] == -1000.0
    odeme = df[df["tutar"] > 0]
    assert odeme["tutar"].tolist() == [5000.0] and odeme["kategori"].iat[0] == "Transfer"
    assert df.loc[df["aciklama"].str.startswith("TEKNOSA"), "taksit_toplam"].iat[0] == 6
    assert sorted(df["tarih"].unique()) == [date(2026, 11, 12), date(2026, 11, 13)]


# --- Dönem içi ↔ ekstre eşleştirme ve kart borcu ------------------------------------------------

def _islemler(satirlar, hesap, kaynak, donem_ici):
    df = pd.DataFrame(satirlar, columns=["tarih", "aciklama", "tutar"])
    return normalize(df.assign(hesap=hesap, kaynak=kaynak, kaynak_turu="kart", donem_ici=donem_ici))


def test_ekstre_gelince_donem_ici_kesinlesir(tmp_path):
    depo = Depo(tmp_path / "k.db")
    di = _islemler([(date(2026, 11, 13), "MIGROS ISTANBUL", -245.9),
                    (date(2026, 11, 13), "SPOTIFY", -99.0)], "YK Kart", "ekran1.jpg", True)
    assert depo.islem_ekle(di) == 2
    depo.kategori_ata(depo.islemler()["islem_id"].iat[0], "Market")  # elle kategori
    # Yeni ekran görüntüsü: aynı iki işlem (OCR metni farklı) + bir yeni işlem
    di2 = _islemler([(date(2026, 11, 13), "MIGR0S ISTANBUL", -245.9),
                     (date(2026, 11, 13), "SPOTIFY P123", -99.0),
                     (date(2026, 11, 14), "SHELL", -1500.0)], "YK Kart", "ekran2.jpg", True)
    depo.islem_ekle(di2)
    assert depo.son_rapor["guncellenen"] == 2 and len(depo.islemler()) == 3
    # Ekstre geldi: tarihler 1 gün kaymış olabilir, açıklama farklı
    ekstre = _islemler([(date(2026, 11, 14), "MIGROS TICARET A.S.", -245.9),
                        (date(2026, 11, 14), "SPOTIFY.COM", -99.0),
                        (date(2026, 11, 15), "SHELL ATASEHIR", -1500.0)], "YK Kart", "ekstre.pdf", False)
    depo.islem_ekle(ekstre)
    assert depo.son_rapor["kesinlesen"] == 3
    son = depo.islemler()
    assert len(son) == 3 and not son["donem_ici"].any()
    assert (son.loc[son["aciklama"].str.startswith("MIGROS"), "kategori"] == "Market").all()
    # Ekstreye girmiş işlem tekrar dönem içi olarak yüklenirse eklenmez
    depo.islem_ekle(_islemler([(date(2026, 11, 14), "SHELL", -1500.0)], "YK Kart", "ekran3.jpg", True))
    assert depo.son_rapor["zaten_ekstrede"] == 1 and len(depo.islemler()) == 3


def test_kart_borcu_onceki_ekstre_odendi():
    kat = Kategorilendirici.varsayilan()
    ekstre = _islemler([(date(2026, 10, 12), "MIGROS", -1000.0),
                        (date(2026, 10, 18), "TRENDYOL TAKSİT 1/3", -500.0),
                        (date(2026, 10, 20), "HESAPTAN AKTARIM", 9000.0)], "YK Kart", "e.pdf", False)
    donem = _islemler([(date(2026, 11, 2), "SHELL", -1500.0),
                       (date(2026, 11, 5), "IADE ZARA", 200.0),
                       (date(2026, 11, 6), "KREDI KARTI ODEMESI", 3000.0),     # önceki ekstreye
                       (date(2026, 11, 7), "TEKNOSA TAKSİT 1/4", -750.0)], "YK Kart", "d.jpg", True)
    b = kart_borclari(kat.uygula(pd.concat([ekstre, donem], ignore_index=True))).iloc[0]
    assert b.donem_ici_harcama == 2250.0 and b.donem_ici_iade == 200.0
    assert b.sonraki_taksit == 500.0          # TRENDYOL 2/3 (ekstreden)
    assert b.sonraki_ekstre == 2250.0 - 200.0 + 500.0
    assert b.kalan_taksit == 500.0 + 750.0 * 3  # TRENDYOL 3/3 + TEKNOSA 2-4/4
    # Ekstredeki 1.000 TL'lik harcama ve 9.000/3.000 TL ödemeler borca dahil değil (ödendi varsayımı)


def test_ocr_isareti_kaybetse_de_odeme_alacak():
    satirlar = ["13 Kasım 2026", "ÖDEMENİZ İÇİN TEŞEKKÜRLER 5.000,00 TL", "MIGROS 245,90 TL",
                "İADE ZARA 150,00 TL"]
    sonuc = {s.aciklama.split()[0]: (s.tutar, s.arti_isaretli) for s in ekran_islemleri(satirlar, REF)}
    assert sonuc["ÖDEMENİZ"][1] and sonuc["İADE"][1] and not sonuc["MIGROS"][1]


def test_ocr_yildiz_arti_duzeltmesi():
    from kumbara.gorsel import _ocr_duzelt
    assert _ocr_duzelt("*5.000,00") == "+5.000,00" and _ocr_duzelt("*BONUS") == "*BONUS"


def test_kart_borcunda_transfer_harcama_sayilmaz():
    kat = Kategorilendirici.varsayilan()
    donem = _islemler([(date(2026, 11, 2), "SHELL", -1500.0),
                       (date(2026, 11, 6), "ÖDEMENİZ İÇİN TEŞEKKÜRLER", -5000.0)],  # işaret yanlış
                      "YK Kart", "d.jpg", True)
    assert kart_borclari(kat.uygula(donem)).iloc[0].donem_ici_harcama == 1500.0


@ocr
def test_ocr_arti_isaretli_odeme_kucuk_ekran(tmp_path):
    """Az satırlı koyu ekran: '+5.000,00' düşük güvenle okunsa bile ödeme alacak sayılmalı."""
    pytest.importorskip("pytesseract")
    yol = _ekran(tmp_path / "k.png", [("~13 Kasım 2026 Perşembe", ""),
                                      ("MIGROS TİCARET İSTANBUL", "-245,90 TL"),
                                      ("ÖDEMENİZ İÇİN TEŞEKKÜRLER", "+5.000,00 TL")], koyu=True)
    df = Kategorilendirici.varsayilan().uygula(oku(yol, hesap="Kart"))
    assert sorted(df["tutar"].tolist()) == [-245.90, 5000.0]
    assert df.loc[df["tutar"] > 0, "kategori"].iat[0] == "Transfer"


def test_apple_vision_turkce_desteklemezse_ingilizceye_duser(tmp_path, monkeypatch):
    """macOS'ta Vision 'tr-TR' kabul etmezse çökmeden en-US ile okunmalı."""
    import sys
    import types

    from PIL import Image

    from kumbara import gorsel
    desteklenen = {"en-US", "fr-FR", "de-DE"}
    cagrilar = []

    class SahteOCR:
        def __init__(self, yol, language_preference=None):
            self.diller = language_preference
            cagrilar.append(language_preference)

        def recognize(self):
            if self.diller and not set(self.diller) <= desteklenen:
                raise ValueError("Invalid language preference.")
            # (metin, güven, (x, y, w, h)) — normalize, köken sol-alt
            return [("13 Kasim 2026", 0.9, (0.05, 0.80, 0.4, 0.05)),
                    ("MIGROS ISTANBUL", 0.9, (0.05, 0.70, 0.4, 0.05)),
                    ("-245,90 TL", 0.9, (0.70, 0.70, 0.25, 0.05)),
                    ("ODEMENIZ ICIN TESEKKURLER", 0.9, (0.05, 0.60, 0.5, 0.05)),
                    ("5.000,00 TL", 0.2, (0.70, 0.60, 0.25, 0.05))]  # düşük güven, işaretsiz

    sahte = types.ModuleType("ocrmac")
    sahte.ocrmac = types.SimpleNamespace(OCR=SahteOCR)
    monkeypatch.setitem(sys.modules, "ocrmac", sahte)
    monkeypatch.setattr(gorsel.sys, "platform", "darwin")
    yol = tmp_path / "ekran.png"
    Image.new("RGB", (1170, 800), "white").save(yol)
    df = oku(yol, hesap="Kart", referans=REF)
    assert cagrilar[:2] == [["tr-TR", "en-US"], ["en-US"]]
    assert sorted(df["tutar"].tolist()) == [-245.90, 5000.0]   # ödeme alacak, harcama gider
    assert df["tarih"].unique().tolist() == [date(2026, 11, 13)]


def test_apple_vision_tamamen_basarisizsa_tesseracta_doner(tmp_path, monkeypatch):
    import sys
    import types

    from PIL import Image

    from kumbara import gorsel

    class Bozuk:
        def __init__(self, *a, **k):
            pass

        def recognize(self):
            raise RuntimeError("Vision yok")

    sahte = types.ModuleType("ocrmac")
    sahte.ocrmac = types.SimpleNamespace(OCR=Bozuk)
    monkeypatch.setitem(sys.modules, "ocrmac", sahte)
    monkeypatch.setattr(gorsel.sys, "platform", "darwin")
    yol = tmp_path / "e.png"
    Image.new("RGB", (100, 100), "white").save(yol)
    assert gorsel._kelimeler_ocrmac(yol, 100, 100) is None


def test_yilsiz_nokta_tarih_ve_taksit_karismaz():
    satirlar = ["13.11 MIGROS 245,90 TL", "12.11", "TEKNOSA 3/6 Taksit 1.000,00 TL"]
    sonuc = _ozet(ekran_islemleri(satirlar, REF))
    assert sonuc == [(date(2026, 11, 13), "MIGROS", 245.90, False),
                     (date(2026, 11, 12), "TEKNOSA", 1000.0, False)]


def test_tarih_basligi_yukarida_kalmis_liste_devami():
    """Uzun listenin ikinci ekran görüntüsü: ilk satırların tarihi görünmüyor."""
    satirlar = ["A101 YENI MAGAZACILIK 89,50 TL", "SHELL 1.500,00 TL", "10 Kasım 2026",
                "STARBUCKS 185,00 TL"]
    sonuc = _ozet(ekran_islemleri(satirlar, REF))
    assert [s[1] for s in sonuc] == ["A101", "SHELL", "STARBUCKS"]
    assert all(s[0] == date(2026, 11, 10) for s in sonuc)


def test_hic_tarih_yoksa_goruntu_tarihi():
    sonuc = _ozet(ekran_islemleri(["MIGROS 245,90 TL", "SPOTIFY 99,00 TL"], REF))
    assert [s[0] for s in sonuc] == [REF, REF]


def test_islem_okunamazsa_donem_ici_toplami():
    from kumbara.gorsel import donem_ici_toplami
    assert donem_ici_toplami(["Kart Limiti 80.000,00 TL", "Son Ekstre Borcu 31.482,16 TL",
                              "Dönem İçi Harcamalarım", "12.345,67 TL"]) == 12345.67
    assert donem_ici_toplami(["Dönem içi harcama: 8.150,00 TL"]) == 8150.0
    assert donem_ici_toplami(["Son Ekstre Borcu 31.482,16 TL", "Asgari 6.296,43 TL"]) is None


def test_ozet_satiri_ve_ekstre_devralma(tmp_path):
    from kumbara.gorsel import OZET_ACIKLAMA
    depo = Depo(tmp_path / "k.db")
    depo.islem_ekle(_islemler([(date(2026, 11, 5), "MIGROS", -245.9),
                               (date(2026, 11, 6), "SHELL", -1500.0)], "YK Kart", "a.png", True))
    # İşlemleri okunamayan yeni görüntü: toplam satırı eskilerin yerini alır
    depo.islem_ekle(_islemler([(date(2026, 11, 14), OZET_ACIKLAMA, -3000.0)], "YK Kart", "b.png", True))
    assert depo.son_rapor["guncellenen"] == 2
    assert depo.islemler()["tutar"].tolist() == [-3000.0]
    # Ayrıntılı görüntü gelince özet silinir
    depo.islem_ekle(_islemler([(date(2026, 11, 13), "MIGROS", -245.9)], "YK Kart", "c.png", True))
    assert depo.islemler()["aciklama"].tolist() == ["MIGROS"]
    # Ekstre (son tarih 27.11): OCR tutarı yanlış okumuş olsa bile dönem içi kayıt devredilir
    depo.islem_ekle(_islemler([(date(2026, 11, 13), "MIGROS TIC", -254.9)], "YK Kart", "e.pdf", False))
    son = depo.islemler()
    assert len(son) == 1 and not son["donem_ici"].any() and depo.son_rapor["kesinlesen"] == 1
    # Ekstre sonrası tarihli dönem içi kayıt (yeni dönem) korunur
    depo.islem_ekle(_islemler([(date(2026, 11, 29), "A101", -50.0)], "YK Kart", "d.png", True))
    depo.islem_ekle(_islemler([(date(2026, 11, 27), "BIM", -20.0)], "YK Kart", "e2.pdf", False))
    assert "A101" in set(depo.islemler()["aciklama"])


def test_gorselde_kart_secilmezse_anlasilir_hata(tmp_path, monkeypatch):
    from kumbara import gorsel
    from kumbara.ekstre import EkstreHatasi
    from kumbara.pdf_ekstre import Satir
    monkeypatch.setattr(gorsel, "gorsel_islemleri",
                        lambda yol, ref: ([Satir(REF, "MIGROS", 10.0, False)], None))
    yol = tmp_path / "IMG_0015.PNG"
    yol.write_bytes(b"x")
    with pytest.raises(EkstreHatasi, match="hangi karta"):
        oku(yol)
    assert oku(yol, hesap="Yapı Kredi Kart")["hesap"].iat[0] == "Yapı Kredi Kart"


def test_hesap_degistir_tasir_ve_eslestirir(tmp_path):
    depo = Depo(tmp_path / "k.db")
    depo.islem_ekle(_islemler([(date(2026, 10, 20), "MIGROS", -245.9)], "Yapı Kredi Kart",
                              "ekstre.pdf", False))
    depo.islem_ekle(_islemler([(date(2026, 11, 13), "SHELL", -1500.0),
                               (date(2026, 10, 20), "MIGR0S", -245.9)],   # zaten ekstrede
                              "IMG_0015-20261114-161259", "IMG_0015-20261114-161259.PNG", True))
    depo.kategori_ata(depo.islemler().query("aciklama == 'SHELL'")["islem_id"].iat[0], "Yakıt")
    depo.hesap_degistir("IMG_0015-20261114-161259.PNG", "IMG_0015-20261114-161259",
                        "Yapı Kredi Kart")
    son = depo.islemler()
    assert set(son["hesap"]) == {"Yapı Kredi Kart"} and len(son) == 2   # çift sayılmadı
    shell = son[son["aciklama"] == "SHELL"].iloc[0]
    assert shell["kategori"] == "Yakıt" and shell["elle"] == 1 and shell["donem_ici"]


# --- Sol sütunda alt alta tarih düzenleri (gerçek uygulamaları taklit eden sentetik ekranlar) ----

def _sol_sutunlu_ekran(yol: Path, ust: list[tuple[str, str]], islemler: list[dict],
                       turuncu: bool) -> Path:
    """Sol sütunda '12 / Kasım / 2026' ya da '13 / Kas / 17:46', sağda işyeri + tutar."""
    from PIL import Image, ImageDraw, ImageFont
    buyuk = ImageFont.truetype(str(DEJAVU), 44)
    font = ImageFont.truetype(str(DEJAVU), 34)
    img = Image.new("RGB", (920, 260 + 230 * len(islemler) + 80 * len(ust)), (24, 26, 38))
    d = ImageDraw.Draw(img)
    y = 40
    for sol, sag in ust:
        d.text((40, y), sol, font=font, fill=(200, 200, 210))
        if sag:
            d.text((880 - d.textlength(sag, font=font), y), sag, font=font, fill=(240, 240, 240))
        y += 80
    for isl in islemler:
        gun, ay, alt = isl["sol"]
        d.text((40, y), gun, font=buyuk, fill=(240, 240, 240))
        d.text((40, y + 58), ay, font=font, fill=(240, 240, 240))
        d.text((40, y + 108), alt, font=font, fill=(240, 240, 240))
        d.text((200, y + 4), isl["isyeri"], font=font, fill=(235, 235, 235))
        satir = y + 58
        if isl.get("alt_metin"):
            d.text((200, satir), isl["alt_metin"], font=font, fill=(220, 220, 220))
            satir += 50
        renk = (232, 86, 31) if turuncu else (240, 240, 240)
        x = 200 if turuncu else 880 - d.textlength(isl["tutar"], font=font)
        d.text((x, satir), isl["tutar"], font=font, fill=renk)
        if isl.get("puan"):
            d.text((200, satir + 48), isl["puan"], font=font, fill=(160, 160, 170))
        y += 230
    img.save(yol)
    return yol


@ocr
def test_ocr_is_bankasi_duzeni_turuncu_tutarlar(tmp_path):
    pytest.importorskip("pytesseract")
    yol = _sol_sutunlu_ekran(tmp_path / "isb.png", [("Dönem İçi Harcamalar Toplamı", "-4.000,00 TL")], [
        {"sol": ("13", "Kas", "17:46"), "isyeri": "Iyzico/Yemeksepeti Istanbul TR - 17:46",
         "tutar": "-1.642,50 TL", "puan": "Kazanılan MaxiPuan:0,18"},
        {"sol": ("10", "Kas", "00:58"), "isyeri": "Apple.Com/Bill Apple.Com - 00:58",
         "tutar": "-169,99 TL"},
        {"sol": ("8", "Kas", "23:59"), "isyeri": "Ornek Tekstil (2/3 TK) - 23:59",
         "tutar": "-1.215,40 TL (2/3)"},
        {"sol": ("12", "Kas", "18:48"), "isyeri": "Google *Ornek Abonelik", "tutar": "-649.99 TL"}],
        turuncu=True)
    df = oku(yol, hesap="İş Bankası Kart", referans=REF)
    tutar = dict(zip(df["aciklama"].str.split().str[0], -df["tutar"], strict=False))
    assert tutar["Iyzico/Yemeksepeti"] == 1642.5 and tutar["Apple.Com/Bill"] == 169.99
    assert tutar["Ornek"] == 1215.4 and tutar["Google"] == 649.99   # '649.99' noktalı
    assert df.loc[df["aciklama"].str.startswith("Ornek"), "taksit_toplam"].iat[0] == 3
    assert df.loc[df["aciklama"].str.startswith("Iyzico"), "tarih"].iat[0] == date(2026, 11, 13)
    assert df.attrs["ekran_ozeti"]["toplam"] == 4000.0


@ocr
def test_ocr_yapi_kredi_duzeni_ve_banka_toplami(tmp_path):
    pytest.importorskip("pytesseract")
    yol = _sol_sutunlu_ekran(tmp_path / "yk.png", [
        ("Güncel Dönem Borcu", "10.000,00 TL"), ("Kullanılabilir Kart Limiti", "50.000,00 TL"),
        ("Bir Sonraki Hesap Kesim Tarihi", "27/11/2026"), ("Bu Döneme Ait Taksit Tutarı", "3.000,00 TL")], [
        {"sol": ("12", "Kasım", "2026"), "isyeri": "AKVARYUM KAFE ISTANBUL TR", "tutar": "36,00 TL"},
        {"sol": ("08", "Kasım", "2026"), "isyeri": "STRDVRS STRADIVARIUS ISTANBUL TR",
         "alt_metin": "4485 TL'lik işlemin 1/3 taksidi", "tutar": "1.495,00 TL"},
        {"sol": ("08", "Kasım", "2026"), "isyeri": "DECATHLON ISTANBUL TR", "tutar": "1.460,00 TL"}],
        turuncu=False)
    df = Kategorilendirici.varsayilan().uygula(oku(yol, hesap="Yapı Kredi Kart", referans=REF))
    assert sorted((-df["tutar"]).tolist()) == [36.0, 1460.0, 1495.0]
    strad = df[df["aciklama"].str.contains("STRADIVARIUS")].iloc[0]
    assert (strad.taksit_no, strad.taksit_toplam, strad.kategori) == (1, 3, "Giyim")
    oz = df.attrs["ekran_ozeti"]
    assert oz["toplam"] == 10000.0 and oz["taksit_dahil"] and oz["kesim"] == date(2026, 11, 27)
    # Depoya yüklenince görünmeyen kısım ve taksitler banka toplamına tamamlanır
    depo = Depo(tmp_path / "k.db")
    depo.islem_ekle(df)
    di = depo.islemler()
    assert round(-di["tutar"].sum(), 2) == 10000.0
    assert kart_borclari(Kategorilendirici.varsayilan().uygula(di)).iloc[0].sonraki_ekstre == 10000.0


def _sahte_vision(monkeypatch, gozlemler):
    """gozlemler: (metin, x, ust, genislik, yukseklik) — 0..1 arası, üstten ölçülü."""
    import sys
    import types

    from kumbara import gorsel

    class SahteOCR:
        def __init__(self, yol, language_preference=None):
            pass

        def recognize(self):
            return [(m, 0.95, (x, 1 - u - h, w, h)) for m, x, u, w, h in gozlemler]

    sahte = types.ModuleType("ocrmac")
    sahte.ocrmac = types.SimpleNamespace(OCR=SahteOCR)
    monkeypatch.setitem(sys.modules, "ocrmac", sahte)
    monkeypatch.setattr(gorsel.sys, "platform", "darwin")


def test_vision_saatleri_noktali_okursa_subat_olmaz(tmp_path, monkeypatch):
    """Saat '17:02' OCR'da '17.02' gelirse 17 Şubat sanılmamalı (kullanıcı hatası: 'Şubat 2026')."""
    from PIL import Image
    g = [("Dönem İçi Harcamalar", 0.04, 0.10, 0.3, 0.02), ("-1.812,49 TL", 0.75, 0.10, 0.2, 0.02),
         ("Toplamı", 0.04, 0.12, 0.1, 0.02)]
    bloklar = [("13", "17.02", "Iyzico/Yemeksepeti Istanbul TR - 17.02", "-1.642,50 TL"),
               ("10", "00.58", "Apple.Com/Bill Apple.Com - 00.58", "-169,99 TL")]
    for i, (gun, saat, isyeri, tutar) in enumerate(bloklar):
        u = 0.25 + i * 0.15
        g += [(gun, 0.05, u, 0.04, 0.025), (isyeri, 0.15, u, 0.6, 0.022),
              ("Kas", 0.05, u + 0.04, 0.05, 0.022), (tutar, 0.15, u + 0.04, 0.2, 0.022),
              (saat, 0.04, u + 0.08, 0.07, 0.022), ("Kazanılan MaxiPuan:0,18", 0.15, u + 0.08, 0.3, 0.02)]
    _sahte_vision(monkeypatch, g)
    yol = tmp_path / "isb.png"
    Image.new("RGB", (920, 2000), (20, 20, 30)).save(yol)
    df = oku(yol, hesap="İş Bankası Kart", referans=REF)
    assert sorted(df["tarih"].tolist()) == [date(2026, 11, 10), date(2026, 11, 13)]
    assert sorted((-df["tutar"]).tolist()) == [169.99, 1642.5]
    assert df.attrs["ekran_ozeti"]["toplam"] == 1812.49


def test_eski_yolda_saat_tarih_sanilmaz():
    """Sol sütun düzeni olmayan ekranda da '17.02' gibi saatler Şubat yapılmaz."""
    sonuc = ekran_islemleri(["MIGROS 17.02 245,90 TL", "SHELL 21.26 1.500,00 TL"], REF)
    assert all(s.tarih.month == 11 for s in sonuc)


def test_kontrol_komutu_supheli_tarihi_gosterir(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from kumbara.cli import app
    monkeypatch.setenv("KUMBARA_VERI_DIZINI", str(tmp_path))
    depo = Depo()
    depo.islem_ekle(_islemler([(date(2026, 2, 17), "MIGROS", -245.9)], "YK Kart", "IMG_1.PNG", True))
    sonuc = CliRunner().invoke(app, ["kontrol"])
    assert sonuc.exit_code == 0, sonuc.output
    assert "Şüpheli tarih" in sonuc.output and "IMG_1.PNG" in sonuc.output
    assert "banka toplamı yok" in sonuc.output


def test_vision_birlesik_parcalar(tmp_path, monkeypatch):
    """Vision 'Kas' ile tutarı ya da saat ile puan satırını tek parça döndürürse de okunmalı."""
    from PIL import Image
    g = []
    for i, (gun, isyeri, tutar) in enumerate([("13", "Iyzico/Yemeksepeti Istanbul TR", "-1.642,50 TL"),
                                             ("10", "Apple.Com/Bill Apple.Com", "-169,99 TL")]):
        u = 0.25 + i * 0.15
        g += [(gun, 0.05, u, 0.04, 0.025), (isyeri + " - 17:46", 0.15, u, 0.6, 0.022),
              (f"Kas {tutar}", 0.05, u + 0.04, 0.32, 0.022),            # birleşik
              ("17:46 Kazanılan MaxiPuan:0,18", 0.04, u + 0.08, 0.45, 0.02)]
    _sahte_vision(monkeypatch, g)
    yol = tmp_path / "b.png"
    Image.new("RGB", (920, 2000), (20, 20, 30)).save(yol)
    df = oku(yol, hesap="İş Bankası Kart", referans=REF)
    assert sorted(zip(df["tarih"], -df["tutar"], strict=True)) == [(date(2026, 11, 10), 169.99),
                                                       (date(2026, 11, 13), 1642.5)]
    assert df["aciklama"].str.startswith(("Iyzico", "Apple")).all()


def test_eski_yanlis_tarihler_onarilir(tmp_path):
    """Eski sürümün '17.02' → Şubat yaptığı dönem içi kayıtlar görüntü tarihine taşınır."""
    depo = Depo(tmp_path / "k.db")
    depo.islem_ekle(_islemler([(date(2026, 2, 17), "MIGROS", -245.9),
                               (date(2026, 11, 13), "SHELL", -1500.0)],
                              "YK Kart", "IMG_0015-20261114-161259.PNG", True))
    depo.islem_ekle(_islemler([(date(2026, 3, 21), "A101", -50.0), (date(2026, 11, 10), "BIM", -20.0),
                               (date(2026, 11, 12), "SOK", -30.0)], "YK Kart", "ekran.jpg", True))
    depo.islem_ekle(_islemler([(date(2026, 2, 1), "ESKI EKSTRE", -10.0)], "YK Kart", "e.pdf", False))
    onarim = depo.donem_ici_tarihlerini_duzelt()
    assert sorted(onarim) == [("IMG_0015-20261114-161259.PNG", "2026-02-17", "2026-11-14"),
                              ("ekran.jpg", "2026-03-21", "2026-11-12")]
    tarih = dict(zip(depo.islemler()["aciklama"], depo.islemler()["tarih"], strict=True))
    assert tarih["ESKI EKSTRE"] == date(2026, 2, 1)   # ekstre kayıtlarına dokunulmaz
    assert depo.donem_ici_tarihlerini_duzelt() == []  # ikinci çalıştırmada değişiklik yok


def test_toplamsiz_kartlar(tmp_path):
    depo = Depo(tmp_path / "k.db")
    depo.islem_ekle(_islemler([(date(2026, 11, 13), "SHELL", -1500.0)], "YK Kart", "a.png", True))
    assert depo.toplamsiz_kartlar() == ["YK Kart"]
    df = _islemler([(date(2026, 11, 13), "SHELL", -1500.0)], "YK Kart", "b.png", True)
    df.attrs["ekran_ozeti"] = {"toplam": 5000.0}
    df.attrs["ekran_tarihi"] = date(2026, 11, 14)
    depo.islem_ekle(df)
    assert depo.toplamsiz_kartlar() == []
