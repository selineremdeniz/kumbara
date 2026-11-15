"""Farklı banka PDF düzenlerini taklit eden sentetik PDF'lerle okuyucu testleri."""

from datetime import date
from pathlib import Path

import pytest

from kumbara.ekstre import EkstreHatasi, oku
from kumbara.pdf_ekstre import PdfSifreHatasi, maskele, satirlari_ayristir, tani

fpdf = pytest.importorskip("fpdf")
DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _pdf(yol: Path, satirlar: list[str], tablo: list[list[str]] | None = None,
         sifre: str | None = None) -> Path:
    pdf = fpdf.FPDF()
    pdf.add_page()
    if DEJAVU.exists():
        pdf.add_font("dv", fname=str(DEJAVU))
        pdf.set_font("dv", size=9)
    else:  # Türkçe karakterleri sadeleştir
        pdf.set_font("Helvetica", size=9)
        from kumbara.metin import _TR_ASCII
        satirlar = [s.translate(_TR_ASCII) for s in satirlar]
        tablo = [[h.translate(_TR_ASCII) for h in r] for r in tablo] if tablo else None
    for s in satirlar:
        pdf.cell(0, 5, s, new_x="LMARGIN", new_y="NEXT")
    if tablo:
        with pdf.table(first_row_as_headings=False) as t:
            for r in tablo:
                row = t.row()
                for h in r:
                    row.cell(h)
    if sifre:
        pdf.set_encryption(owner_password="sahip", user_password=sifre)
    pdf.output(str(yol))
    return yol


SATIR_DUZENI = [
    "XYZ BANK KREDİ KARTI HESAP ÖZETİ",
    "Hesap Kesim Tarihi: 12.11.2026   Son Ödeme Tarihi: 22.11.2026",
    "Kart No: 5555 **** **** 1234",
    "İşlem Tarihi   Açıklama                         Tutar",
    "13.10.2026 MIGROS TİCARET A.Ş. İSTANBUL           1.234,56 TL",
    "14.10.2026 TEKNOSA TAKSİT 2/6        6.000,00     1.000,00",
    "15.10.2026 YEMEKSEPETİ.COM",
    "     İSTANBUL TR                                  245,90",
    "16/10 NETFLIX.COM                                 229,99 TL",
    "17.10.2026 14:32 SHELL ATAŞEHİR                  1500,00",
    "20.10.2026 ÖDEMENİZ İÇİN TEŞEKKÜR EDERİZ         5.000,00 +",
    "21.10.2026 İADE TRENDYOL                         (150,00)",
    "12.11.2026 DÖNEM TOPLAMI                         9.999,99",
    "Sayfa 1 / 1",
]


def test_satir_duzeni_ayristirma():
    islemler = satirlari_ayristir(SATIR_DUZENI, referans=date(2026, 11, 12))
    ozet = {(s.tarih, s.aciklama.split()[0], s.tutar, s.arti_isaretli) for s in islemler}
    assert (date(2026, 10, 13), "MIGROS", 1234.56, False) in ozet
    assert (date(2026, 10, 14), "TEKNOSA", 1000.0, False) in ozet      # toplam değil taksit tutarı
    assert (date(2026, 10, 16), "NETFLIX.COM", 229.99, False) in ozet  # yılsız tarih
    assert (date(2026, 10, 17), "SHELL", 1500.0, False) in ozet        # binliksiz tutar, saatli
    assert (date(2026, 10, 20), "ÖDEMENİZ", 5000.0, True) in ozet      # "+" ödeme
    assert (date(2026, 10, 21), "İADE", -150.0, False) in ozet         # parantez = eksi
    yemek = next(s for s in islemler if s.aciklama.startswith("YEMEKSEPET"))
    assert yemek.tutar == 245.90 and "İSTANBUL" in yemek.aciklama     # bölünmüş açıklama
    assert not any("TOPLAM" in s.aciklama for s in islemler)          # özet satırı atlandı
    assert len(islemler) == 7


def test_yilsiz_tarih_yil_donumu():
    [s] = satirlari_ayristir(["28.12 MIGROS 100,00"], referans=date(2027, 1, 12))
    assert s.tarih == date(2026, 12, 28)


def test_ay_adli_tarihler():
    islemler = satirlari_ayristir(["12 Ekim 2026 MİGROS 1.234,56", "3 KAS 2026 A101 99,90 TL",
                                   "2026-10-05 BİM 45,00"])
    assert [s.tarih for s in islemler] == [date(2026, 10, 12), date(2026, 11, 3), date(2026, 10, 5)]


def test_pdf_kart_satir_duzeni(tmp_path):
    df = oku(_pdf(tmp_path / "Kredi_Karti_Hesap_Ozeti.PDF", SATIR_DUZENI), tur="otomatik")
    tutar = dict(zip(df["aciklama"].str.split().str[0], df["tutar"], strict=False))
    assert tutar["MIGROS"] == -1234.56        # harcama gider oldu
    assert tutar["ÖDEMENİZ"] == 5000.0        # ödeme alacak (sonra Transfer kategorisi)
    assert tutar["İADE"] == 150.0
    assert df["taksit_toplam"].notna().sum() == 1


def test_pdf_tablo_duzeni_borc_alacak(tmp_path):
    tablo = [["İşlem Tarihi", "Açıklama", "Borç", "Alacak"],
             ["01.10.2026", "MAAŞ ÖDEMESİ", "", "50.000,00"],
             ["02.10.2026", "KİRA HAVALE", "20.000,00", ""],
             ["05.10.2026", "ENERJİSA FATURA", "850,40", ""]]
    yol = _pdf(tmp_path / "hesap.pdf", ["VADESİZ HESAP HAREKETLERİ", "Dönem: 01.10.2026 - 31.10.2026"],
               [[*r[:2], r[2] or "-", r[3] or "-"] for r in tablo])
    df = oku(yol)
    assert sorted(df["tutar"].tolist()) == [-20000.0, -850.40, 50000.0]


def test_pdf_tablo_tek_tutar(tmp_path):
    tablo = [["Tarih", "İşlem", "Tutar (TL)"], ["03.10.2026", "A101 YENİ MAĞAZACILIK", "450,50"],
             ["04.10.2026", "TURKCELL", "300,00"]]
    df = oku(_pdf(tmp_path / "Belge.pdf", ["Ekstre"], tablo), tur="kart")
    assert df["tutar"].tolist() == [-450.50, -300.0]


def test_sifreli_pdf(tmp_path):
    yol = _pdf(tmp_path / "document.pdf", SATIR_DUZENI, sifre="1234")
    with pytest.raises(PdfSifreHatasi):
        oku(yol)
    with pytest.raises(PdfSifreHatasi, match="yanlış"):
        oku(yol, sifre="0000")
    assert len(oku(yol, sifre="1234")) == 7


def test_metinsiz_pdf_anlasilir_hata(tmp_path):
    pdf = fpdf.FPDF()
    pdf.add_page()
    pdf.output(str(tmp_path / "bos.pdf"))
    with pytest.raises(EkstreHatasi, match="taranmış"):
        oku(tmp_path / "bos.pdf")


def test_maskeleme_kisisel_bilgiyi_gizler(tmp_path):
    assert maskele("13.10.2026 MIGROS KADIKÖY 1.234,56 TL") == "99.99.9999 XXXXXX XXXXXXX 9.999,99 TL"
    assert maskele("İşlem Tarihi Açıklama Tutar") == "İşlem Tarihi Açıklama Tutar"
    cikti = tani(_pdf(tmp_path / "a.pdf", [*SATIR_DUZENI, "AD SOYAD: AYŞE YILMAZ"]))
    assert "AYŞE" not in cikti and "MIGROS" not in cikti and "1234" not in cikti
    assert "satır yöntemi 7 işlem" in cikti


# --- Sütun konumlu düzenler (puan/bonus sütunu, alt satırda taksit, kart ödemesi) -------------

def _kolonlu_pdf(yol: Path, satirlar: list[tuple]) -> Path:
    """Her satır: (tarih, açıklama, tutar, ek_sutun, puan). Tutar sağa yaslı x=140'ta, ek sütun
    x=170'te, puan x=200'de biter; tek elemanlı satırlar sola yaslı düz metindir."""
    pdf = fpdf.FPDF()
    pdf.add_page()
    if DEJAVU.exists():
        pdf.add_font("dv", fname=str(DEJAVU))
        pdf.set_font("dv", size=8)
    else:
        pdf.set_font("Helvetica", size=8)
    y = 15
    for s in satirlar:
        if not DEJAVU.exists():
            from kumbara.metin import _TR_ASCII
            s = tuple(x.translate(_TR_ASCII) for x in s)
        if len(s) == 1:
            pdf.set_xy(10, y)
            pdf.cell(150, 5, s[0])
        else:
            tarih, aciklama, tutar, ek, puan = s
            pdf.set_xy(10, y)
            pdf.cell(25, 5, tarih)
            pdf.set_xy(36, y)
            pdf.cell(70, 5, aciklama)
            for metin, sag in ((tutar, 140), (ek, 170), (puan, 200)):
                if metin:
                    pdf.set_xy(sag - 30, y)
                    pdf.cell(30, 5, metin, align="R")
        y += 6
    pdf.output(str(yol))
    return yol


def test_puan_sutunu_ve_kart_odemesi(tmp_path):
    satirlar = [
        ("KREDİ KARTI HESAP ÖZETİ",), ("Hesap Kesim Tarihi: 05.11.2026",),
        ("İşlem Tarihi", "Açıklama", "Tutar", "Taksit Bilgisi", "MaxiPuan"),
        ("05/10/2026", "XYZ ORNEK GIDA", "800,00", "", ""),
        ("06/10/2026", "ABC MARKET", "210,40", "", "0,02"),
        ("06/10/2026", "WWW.ORNEKSATICI.COM", "", "", "-128,33"),        # puan kullanımı
        ("08/10/2026", "ÖRNEK TEKSTİL", "1.215,40", "1/3 taksidi", "(3.646,20)"),
        ("09/10/2026", "1111-222222 HESAPTAN AKTARIM", "-6.000,00", "", ""),  # karta ödeme
        ("21/10/2026", "HEDİYE KAMPANYA MAXIPUAN", "", "", "100,00"),      # puan hediyesi
        ("05/11/2026", "FAIZ TUTARI", "64,30", "", ""),
        ("TOPLAM 2.290,10 TL",),
    ]
    from kumbara.kategori import Kategorilendirici
    df = Kategorilendirici.varsayilan().uygula(oku(_kolonlu_pdf(tmp_path / "isb.pdf", satirlar),
                                                   tur="kart"))
    assert round(-df.loc[df.tutar < 0, "tutar"].sum(), 2) == 2290.1   # puanlar tutar sayılmadı
    odeme = df[df.aciklama.str.contains("AKTARIM")]
    assert odeme.tutar.iat[0] == 6000.0 and odeme.kategori.iat[0] == "Transfer"  # gelir değil
    tekstil = df[df.aciklama.str.contains("TEKSTİL|TEKSTIL")].iloc[0]
    assert (tekstil.taksit_no, tekstil.taksit_toplam, tekstil.tutar) == (1, 3, -1215.4)
    assert "Banka Masrafı" in set(df.kategori)


def test_alt_satirda_taksit_ve_puan_bolumu(tmp_path):
    satirlar = [
        ("İşlem Tarihi", "İşlemler", "Tutar(TL)", "Kalan Tutar/Taksit", "Puan"),
        ("11 Ekim 2026", "ÖRNEK JEANS ANKARA TR", "1.100,00", "2.200,00 / 2", "74"),
        ("3.300,00 TL'lik işlemin 1 / 3 taksidi",),
        ("12 Ekim 2026", "ÖRNEK ECZANESI ISTANBUL TR", "74,50", "", ""),
        ("PUAN ÖZETİ",),
        ("İşlem Tarihi İşlem Türü Puan TL Karşılığı",),
        ("21 Ekim 2026", "ÖRNEK SATICI ISTANBUL TR", "-30,72 TL", "", "-6.144"),  # puan harcaması
    ]
    df = oku(_kolonlu_pdf(tmp_path / "yk.pdf", satirlar), tur="kart")
    assert sorted(df.tutar.tolist()) == [-1100.0, -74.50]
    jeans = df[df.aciklama.str.contains("JEANS")].iloc[0]
    assert (jeans.taksit_no, jeans.taksit_toplam) == (1, 3)


def test_garanti_carpim_taksit():
    from kumbara.metin import taksit_bul
    assert taksit_bul("ORNEK SPOR AVM 1.250,00x4=5.000,00 3.Taksit 1.250,00") == (3, 4)
    assert taksit_bul("ORNEK TEKSTIL 1.215,40 1/3 taksidi (3.646,20)") == (1, 3)


def test_kart_alacagi_asla_gelir_degil():
    import pandas as pd

    from kumbara.ekstre import normalize
    from kumbara.kategori import Kategorilendirici
    df = normalize(pd.DataFrame({"tarih": [date(2026, 10, 1)] * 3, "hesap": "k", "kaynak": "k",
                                 "aciklama": ["HESAPTAN AKTARIM", "ABC MAGAZA", "MAAS"],
                                 "tutar": [5000.0, 120.0, 30000.0], "kaynak_turu": "kart"}))
    k = dict(zip(df.aciklama, Kategorilendirici.varsayilan().uygula(df).kategori, strict=True))
    assert k == {"HESAPTAN AKTARIM": "Transfer", "ABC MAGAZA": "İade", "MAAS": "İade"}


def test_ornek_veri_silinir(tmp_path):
    from importlib import resources

    from kumbara.depo import Depo
    from kumbara.portfoy import Hedef
    depo = Depo(tmp_path / "k.db")
    with resources.as_file(resources.files("kumbara.veri").joinpath("ornek_kart.csv")) as yol:
        depo.islem_ekle(oku(yol, hesap="Örnek Kart", tur="kart"))
    depo.hedef_kaydet(Hedef("Acil durum fonu", 90_000, date(2027, 11, 1)))
    depo.hedef_kaydet(Hedef("Acil durum fonu 2", 50_000, date(2027, 11, 1)))  # kullanıcının
    assert depo.ornek_var_mi()
    s = depo.ornek_sil()
    assert s["islem"] > 0 and s["hedef"] == 1 and not depo.ornek_var_mi()
    assert [h.ad for h in depo.hedefler()] == ["Acil durum fonu 2"]


def test_ayni_dosya_iki_hesap_adiyla(tmp_path):
    from kumbara.depo import Depo
    depo = Depo(tmp_path / "k.db")
    yol = _pdf(tmp_path / "Belge.pdf", SATIR_DUZENI)
    depo.islem_ekle(oku(yol, hesap="Belge", tur="kart"))
    depo.islem_ekle(oku(yol, hesap="Garanti BBVA Kart", tur="kart"))
    assert depo.kopya_kaynaklar() == {"Belge.pdf": ["Belge", "Garanti BBVA Kart"]}
    assert depo.islemleri_sil("Belge.pdf", "Belge") == 7
    assert depo.kopya_kaynaklar() == {} and len(depo.islemler()) == 7
