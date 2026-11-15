"""Hızlı plan: son ayın kart ekstresi + o ayın geliri → bu ayki birikim → hedefe göre portföy.

Ekstreler veritabanına yazılmaz; her hesap yüklenen dosyalardan yeniden yapılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from .ekstre import EkstreHatasi, oku
from .kategori import Kategorilendirici


@dataclass
class EkstreOzeti:
    dosya: str
    kart: str
    islemler: pd.DataFrame
    okunan_harcama: float                 # okunan işlemlerden: harcama − iade (ödemeler hariç)
    banka_toplami: float | None = None    # bankanın ekstrede/ekranda yazdığı toplam
    banka_etiketi: str | None = None
    bes: float = 0.0                      # BES / birikim niteliğindeki ödemeler
    sonraki_taksit: float = 0.0           # gelecek ekstreye girecek taksitler (bu ekstreden)
    kalan_taksit: float = 0.0             # daha sonraki aylara kalan taksitler
    uyarilar: list[str] = field(default_factory=list)  # dil.py anahtarları: u_fark, u_fark_gorsel…

    @property
    def harcama(self) -> float:
        """Önerilen ay harcaması: bankanın toplamı varsa o, yoksa okunan işlemler."""
        return self.banka_toplami if self.banka_toplami is not None else self.okunan_harcama


def ekstre_ozetle(yol: str | Path, kategorilendirici: Kategorilendirici | None = None,
                  sifre: str | None = None, referans: date | None = None) -> EkstreOzeti:
    from .gorsel import GORSEL_UZANTILARI
    from .kart import kart_borclari
    from .pdf_ekstre import ekstre_toplami
    yol = Path(yol)
    kat = kategorilendirici or Kategorilendirici.varsayilan()
    gorsel = yol.suffix.lower() in GORSEL_UZANTILARI
    try:
        df = oku(yol, tur="kart", sifre=sifre, referans=referans)
    except EkstreHatasi as e:
        if "hangi karta" not in str(e):
            raise
        df = oku(yol, hesap=yol.stem, tur="kart", sifre=sifre, referans=referans)
    ekran = dict(df.attrs.get("ekran_ozeti") or {})
    df = kat.uygula(df)
    transfer = df["kategori"] == "Transfer"
    harcama = float(-df.loc[(df["tutar"] < 0) & ~transfer, "tutar"].sum())
    iade = float(df.loc[(df["tutar"] > 0) & ~transfer, "tutar"].sum())
    oz = EkstreOzeti(dosya=yol.name, kart=str(df["hesap"].iat[0]), islemler=df,
                     okunan_harcama=round(harcama - iade, 2),
                     bes=round(max(0.0, float(-df.loc[(df["kategori"] == "BES ve Birikim")
                                                      & (df["tutar"] < 0), "tutar"].sum())), 2))
    if gorsel:
        if ekran.get("toplam"):
            oz.banka_toplami = ekran["toplam"]
            oz.banka_etiketi = ("Güncel dönem borcu" if ekran.get("guncel_borc")
                                else "Dönem içi harcamalar toplamı")
    else:
        bulunan = ekstre_toplami(yol, sifre)
        if bulunan:
            oz.banka_toplami, oz.banka_etiketi = bulunan
    kb = kart_borclari(df)
    if len(kb):
        oz.sonraki_taksit = float(kb["sonraki_taksit"].sum())
        oz.kalan_taksit = float(kb["kalan_taksit"].sum())
    if oz.banka_toplami is not None and oz.okunan_harcama and abs(
            oz.banka_toplami - oz.okunan_harcama) > max(50, 0.02 * oz.banka_toplami):
        oz.uyarilar.append("u_fark_gorsel" if gorsel else "u_fark")
    if oz.banka_toplami is None:
        oz.uyarilar.append("u_toplam_yok")
    return oz


@dataclass
class Birikim:
    gelir: float
    kart_harcama: float
    kart_disi: float
    bes: float
    yatirilabilir: float      # bu ay yatırıma ayrılabilecek nakit
    toplam_birikim: float     # yatırılabilir + (birikim sayılırsa) BES
    oran: float | None


def birikim_hesapla(gelir: float, kart_harcama: float, kart_disi: float = 0.0, bes: float = 0.0,
                    bes_birikim: bool = True) -> Birikim:
    """Kart harcaması BES ödemesini de içerir (karttan çıkmıştır); BES'i birikim saymak, onu
    toplam birikime geri ekler ama yatırıma ayrılabilecek nakdi artırmaz."""
    yatirilabilir = gelir - kart_harcama - kart_disi
    toplam = yatirilabilir + (bes if bes_birikim else 0.0)
    return Birikim(gelir, kart_harcama, kart_disi, bes, round(yatirilabilir, 2), round(toplam, 2),
                   round(toplam / gelir, 4) if gelir > 0 else None)
