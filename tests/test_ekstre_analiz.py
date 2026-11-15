from datetime import date

import pandas as pd
import pytest

from kumbara.analiz import aylik_ozet, duzenli_odemeler, kategori_kirilimi
from kumbara.ekstre import EkstreHatasi, oku
from kumbara.kategori import Kategorilendirici


def test_ornek_dosyalar_okunur(islemler):
    assert {"Vadesiz", "Kart"} == set(islemler["hesap"])
    assert islemler["tarih"].min() == date(2026, 5, 1)
    kart = islemler[islemler["hesap"] == "Kart"]
    # Kart ekstresinde harcamalar artı yazılır; içeride eksiye çevrilmiş olmalı.
    assert (kart.loc[kart["aciklama"].str.contains("MIGROS"), "tutar"] < 0).all()
    assert kart["taksit_toplam"].notna().sum() == 4 + 2


def test_kategoriler(islemler):
    k = dict(zip(islemler["aciklama"], islemler["kategori"], strict=True))
    assert k["MIGROS TİCARET A.Ş. İSTANBUL"] == "Market"
    assert k["NETFLIX.COM"] == "Abonelik"
    assert k["KREDİ KARTI ÖDEMESİ"] == "Transfer"
    assert k["ÖDEMENİZ İÇİN TEŞEKKÜR EDERİZ"] == "Transfer"
    assert k["MAAŞ ÖDEMESİ ÖRNEK TEKNOLOJİ A.Ş."] == "Maaş"
    assert k["İADE TRENDYOL.COM"] == "İade"
    assert k["İGDAŞ DOĞALGAZ FATURA"] == "Fatura"
    assert k["OPET PETROLCÜLÜK"] == "Yakıt"


def test_tekrar_yukleme_ayni_kimlik(islemler):
    assert islemler["islem_id"].is_unique


def test_aylik_ozet_transferleri_saymaz(islemler):
    ozet = aylik_ozet(islemler)
    assert len(ozet) == 6
    mayis = ozet.loc[pd.Period("2026-05", "M")]
    assert mayis["gelir"] == pytest.approx(68_000 + islemler.query(
        "aciklama == 'MEVDUAT FAİZİ' and tarih < @date(2026, 6, 1)")["tutar"].sum())
    # Kart ödemesi (Transfer) gider sayılmamalı: gider < gelir
    assert 0 < mayis["gider"] < mayis["gelir"]


def test_kategori_kirilimi_toplami_bir(islemler):
    k = kategori_kirilimi(islemler, "2026-10")
    assert k["pay"].sum() == pytest.approx(1, abs=1e-3)
    assert "Transfer" not in k.index


def test_duzenli_odemeler(islemler):
    d = duzenli_odemeler(islemler)
    isyerleri = set(d["isyeri"])
    assert {"NETFLIX", "SPOTIFY P"} & isyerleri or any("NETFLIX" in i for i in isyerleri)
    assert any("TURKCELL" in i for i in isyerleri)
    assert not any("TEKNOSA" in i for i in isyerleri)  # taksitler hariç


def test_borc_alacak_sutunlari(tmp_path):
    yol = tmp_path / "hareket.csv"
    yol.write_text("Tarih;Açıklama;Borç;Alacak;Bakiye\n"
                   "01.10.2026;MAAS;;50.000,00;50.000,00\n"
                   "02.10.2026;MIGROS;1.000,00;;49.000,00\n", "utf-8")
    df = oku(yol)
    assert df["tutar"].tolist() == [50_000.0, -1_000.0]


def test_xlsx_ust_bilgi_satirlari(tmp_path):
    yol = tmp_path / "ekstre.xlsx"
    pd.DataFrame([["XYZ BANK", None, None], ["Dönem: Ekim 2026", None, None],
                  ["İşlem Tarihi", "Açıklama", "Tutar (TL)"],
                  ["05.10.2026", "A101 YENI MAGAZACILIK", "-450,50"],
                  ["06.10.2026", "TURKCELL", "-300"]]).to_excel(yol, header=False, index=False)
    df = Kategorilendirici.varsayilan().uygula(oku(yol, tur="hesap"))
    assert df["kategori"].tolist() == ["Market", "Fatura"]


def test_baslik_yoksa_anlasilir_hata(tmp_path):
    yol = tmp_path / "bos.csv"
    yol.write_text("a;b;c\n1;2;3\n", "utf-8")
    with pytest.raises(EkstreHatasi):
        oku(yol)


def test_kullanici_kurallari_once(tmp_path):
    ozel = tmp_path / "kategoriler.yaml"
    ozel.write_text("kurallar:\n  - {kategori: Spor, yon: gider, anahtar: [MACFIT]}\n", "utf-8")
    k = Kategorilendirici.varsayilan(ozel)
    assert k.bul("MACFIT ATASEHIR", -900) == "Spor"
    assert k.bul("MIGROS", -10) == "Market"
    assert k.bul("BILINMEYEN YER", -10) == "Diğer"


@pytest.mark.parametrize("aciklama,beklenen", [
    ("MAVI JEANS TEKIRDAG TR TAKSİT 1/3", "Giyim"),
    ("ASİCS MARLİN HİLLTOWN İSTANBUL TR TAKSİT 1/5", "Giyim"),
    ("ORNEK TEKSTIL ISTANBUL TR TAKSİT 1/3", "Giyim"),
    ("TRENDYOL.COM ISTANBUL TR TAKSİT 1/3", "Online Alışveriş"),
    ("OZDILEK AVM YALOVA YALOVA TR TAKSİT 2/3", "Alışveriş (AVM)"),
    ("ELEKSE/PAYTAX TAKSİ İSTANBUL TR", "Taksi ve Uber"),
    ("MOKAUNİTED/BITAKSI M İSTANBUL TR", "Taksi ve Uber"),
    ("IYZICO/UBER.COM ISTANBUL TR", "Taksi ve Uber"),
    ("UBER EATS YEMEK ISTANBUL TR", "Yeme-İçme"),
    ("WWW.IDO.COM.TR ISTANBUL TR", "Ulaşım"),
    ("ALLIANZ YASAM VE EMEKLILIIZMIR TR", "BES ve Birikim"),
    ("STRDVRS STRADİVARİUS CİTYİSTANBUL TR", "Giyim"),
    ("İLBE RETORANT İSTANBUL TR", "Yeme-İçme"),
    ("PLATİN LOSTRA ÜMİT B İSTANBUL TR", "Kişisel Bakım"),
    ("BARIS TICARET", "Diğer"),   # 'BAR$' tam kelime
])
def test_gercek_isyerleri_kategorileri(aciklama, beklenen):
    assert Kategorilendirici.varsayilan().bul(aciklama, -100) == beklenen


def test_kural_ogrenme(tmp_path):
    from kumbara.kategori import kural_ekle
    dosya = tmp_path / "kategoriler.yaml"
    kural_ekle(dosya, "Market", "MONEYPAY DIJITAL")
    kural_ekle(dosya, "Online Alışveriş", "MONEYPAY DIJITAL")  # fikir değişti: taşınır
    k = Kategorilendirici.varsayilan(dosya)
    assert k.bul("MONEYPAY *DIJITAL PLATISTANBUL TR", -500) == "Online Alışveriş"
    assert k.bul("MIGROS", -10) == "Market"
