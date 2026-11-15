"""Örnek (tamamen sentetik) hesap ve kart ekstreleri üretir.

    python scripts/ornek_veri_uret.py   ->  src/kumbara/veri/ornek_{hesap,kart}.csv
"""

import random
from datetime import date
from pathlib import Path

HEDEF = Path(__file__).resolve().parents[1] / "src" / "kumbara" / "veri"
AYLAR = [(2026, m) for m in range(5, 11)]  # Mayıs-Ekim 2026
rnd = random.Random(42)


def tr(x: float) -> str:
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def gun(y, m, d):
    return date(y, m, d).strftime("%d.%m.%Y")


def hesap():
    satirlar, bakiye = [], 40_000.0
    for i, (y, m) in enumerate(AYLAR):
        maas = 68_000 if i < 3 else 74_000  # Ağustos'ta zam
        kalemler = [
            (1, "MAAŞ ÖDEMESİ ÖRNEK TEKNOLOJİ A.Ş.", maas),
            (2, "KİRA ÖDEMESİ EV SAHİBİ HAVALE", -25_000),
            (5, "ENERJİSA ELEKTRİK FATURA ÖDEMESİ", -round(rnd.uniform(900, 1400), 2)),
            (6, "İGDAŞ DOĞALGAZ FATURA", -round([600, 450, 400, 420, 700, 1500][i], 2)),
            (7, "TURKCELL FATURA ÖDEMESİ", -449.90),
            (8, "SÜPERONLİNE İNTERNET FATURA", -549.00),
            (12, "KREDİ KARTI ÖDEMESİ", -round(rnd.uniform(18_000, 24_000), 2)),
            (15, "ATM PARA ÇEKME", -2_000),
            (20, "ANADOLU HAYAT SİGORTA PRİMİ", -1_150),
            (28, "MEVDUAT FAİZİ", round(rnd.uniform(250, 400), 2)),
        ]
        for d, a, t in kalemler:
            bakiye += t
            satirlar.append(f"{gun(y, m, d)};{a};{tr(t)};{tr(bakiye)}")
    baslik = ["HESAP HAREKETLERİ", "Hesap No: TR00 0000 0000 0000 0000 0000 00;;;",
              "İşlem Tarihi;Açıklama;Tutar;Bakiye"]
    (HEDEF / "ornek_hesap.csv").write_text("\n".join(baslik + satirlar) + "\n", "utf-8")


def kart():
    satirlar = []
    for i, (y, m) in enumerate(AYLAR):
        for hafta in range(4):
            satirlar.append((gun(y, m, 3 + hafta * 7), "MIGROS TİCARET A.Ş. İSTANBUL",
                             round(rnd.uniform(1_400, 2_600), 2)))
            satirlar.append((gun(y, m, 5 + hafta * 7), rnd.choice(["A101 YENİ MAĞAZACILIK",
                                                                   "BİM BİRLEŞİK MAĞAZALAR"]),
                             round(rnd.uniform(300, 900), 2)))
        for _ in range(rnd.randint(3, 6)):
            satirlar.append((gun(y, m, rnd.randint(1, 28)), "YEMEKSEPETİ.COM",
                             round(rnd.uniform(350, 750), 2)))
        for _ in range(rnd.randint(4, 8)):
            satirlar.append((gun(y, m, rnd.randint(1, 28)), "STARBUCKS KADIKÖY",
                             round(rnd.uniform(140, 220), 2)))
        satirlar += [(gun(y, m, 9), "NETFLIX.COM", 229.99), (gun(y, m, 11), "SPOTIFY P1234", 99.00),
                     (gun(y, m, 14), "APPLE.COM/BILL ICLOUD", 39.99),
                     (gun(y, m, 4), "OPET PETROLCÜLÜK", round(rnd.uniform(1_500, 2_100), 2)),
                     (gun(y, m, 19), "SHELL ATAŞEHİR", round(rnd.uniform(1_500, 2_100), 2)),
                     (gun(y, m, 16), "TRENDYOL.COM", round(rnd.uniform(500, 2_500), 2))]
        if i in (1, 4):
            satirlar.append((gun(y, m, 22), "LC WAIKIKI MAĞAZACILIK", round(rnd.uniform(1_200, 3_000), 2)))
        if i in (0, 3, 5):
            satirlar.append((gun(y, m, 24), "ÖZEL ECZANE", round(rnd.uniform(200, 600), 2)))
        if i == 2:
            satirlar.append((gun(y, m, 17), "İADE TRENDYOL.COM", -650.00))
        if i >= 2:  # Temmuz'da 6 taksitli laptop
            satirlar.append((gun(y, m, 10), f"TEKNOSA İÇ VE DIŞ TİC. TAKSİT {i - 1}/6", 5_000.00))
        if i >= 4:  # Eylül'de 3 taksitli uçak bileti
            satirlar.append((gun(y, m, 10), f"THY TÜRK HAVA YOLLARI {i - 3}/3 TAKSİT", 4_000.00))
        satirlar.append((gun(y, m, 12), "ÖDEMENİZ İÇİN TEŞEKKÜR EDERİZ", -20_000.00))
    satirlar.sort(key=lambda s: s[0][6:] + s[0][3:5] + s[0][:2])
    metin = ["Tarih,İşlem,Tutar"] + [f'{t},{a},"{tr(x)}"' for t, a, x in satirlar]
    (HEDEF / "ornek_kart.csv").write_text("\n".join(metin) + "\n", "utf-8")


if __name__ == "__main__":
    hesap()
    kart()
    print("örnek ekstreler yazıldı:", HEDEF)
