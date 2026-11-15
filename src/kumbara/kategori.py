"""Kural tabanlı işlem kategorilendirme."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import pandas as pd
import yaml

from .metin import sade

_ODEME = re.compile(r"ODEME|AKTARIM|TESEKKUR|HESAPTAN|VIRMAN|HAVALE|EFT|OTOMATIK TAHSILAT")
DIGER_GIDER = "Diğer"
DIGER_GELIR = "Diğer Gelir"
# Gelir/gider toplamlarına katılmayan kategoriler (para bir hesaptan diğerine geçiyor).
NOTR_KATEGORILER = {"Transfer", "BES ve Birikim"}  # BES katkısı tüketim değil birikimdir
# Gelir sayılmayan girişler.
GELIR_DISI = {"Transfer", "İade"}


@dataclass
class Kural:
    kategori: str
    anahtar: list[str]
    yon: str = "hepsi"
    zorunlu: bool = False
    _desen: re.Pattern = field(init=False, repr=False)

    def __post_init__(self):
        # Sol sınırda kelime başı zorunlu; sağda Türkçe ekler (FAIZ-I, OKUL-U) serbest.
        # Sonu '$' ile biten anahtar TAM KELİMEDİR: 'TAKSI$' TAKSİ'yi yakalar, TAKSİT'i yakalamaz.
        parcalar = []
        for a in sorted({str(a).strip() for a in self.anahtar if str(a).strip()}, key=len,
                        reverse=True):
            tam = a.endswith("$")
            k = re.escape(sade(a.rstrip("$")))
            parcalar.append(k + r"(?![A-Z0-9])" if tam else k)
        self._desen = re.compile(r"(?<![A-Z0-9])(?:" + "|".join(parcalar) + ")")

    def eslesir(self, aciklama_sade: str, tutar: float) -> bool:
        if self.yon == "gider" and tutar >= 0:
            return False
        if self.yon == "gelir" and tutar <= 0:
            return False
        return bool(self._desen.search(aciklama_sade))


def kural_ekle(dosya: Path, kategori: str, anahtar: str, yon: str = "gider",
               zorunlu: bool | None = None) -> None:
    """Kullanıcı kural dosyasının BAŞINA bir kural ekler (varsayılanlardan önce uygulanır).
    Aynı anahtar başka bir kategoride varsa oradan çıkarılır."""
    dosya = Path(dosya)
    veri = (yaml.safe_load(dosya.read_text("utf-8")) if dosya.exists() else None) or {}
    kurallar = veri.get("kurallar") or []
    anahtar_sade = sade(anahtar)
    for k in kurallar:
        k["anahtar"] = [a for a in k.get("anahtar", []) if sade(a) != anahtar_sade]
    kurallar = [k for k in kurallar if k["anahtar"]]
    hedef = next((k for k in kurallar if k["kategori"] == kategori and k.get("yon", "hepsi") == yon),
                 None)
    if hedef:
        hedef["anahtar"].insert(0, anahtar_sade)
    else:
        yeni = {"kategori": kategori, "yon": yon, "anahtar": [anahtar_sade]}
        if zorunlu is not None:
            yeni["zorunlu"] = bool(zorunlu)
        kurallar.insert(0, yeni)
    veri["kurallar"] = kurallar
    dosya.parent.mkdir(parents=True, exist_ok=True)
    dosya.write_text("# kumbara: elle düzeltilen kategorilerden öğrenilen kurallar\n"
                     + yaml.safe_dump(veri, allow_unicode=True, sort_keys=False), "utf-8")


def _kurallari_oku(veri: dict) -> list[Kural]:
    return [
        Kural(kategori=k["kategori"], anahtar=list(k.get("anahtar", [])), yon=k.get("yon", "hepsi"),
              zorunlu=bool(k.get("zorunlu", False)))
        for k in (veri or {}).get("kurallar", [])
    ]


class Kategorilendirici:
    def __init__(self, kurallar: list[Kural]):
        self.kurallar = kurallar
        self.zorunlu = {k.kategori for k in kurallar if k.zorunlu}

    @classmethod
    def varsayilan(cls, kullanici_dosyasi: Path | None = None) -> Kategorilendirici:
        metin = resources.files("kumbara.veri").joinpath("kategoriler.yaml").read_text("utf-8")
        kurallar = _kurallari_oku(yaml.safe_load(metin))
        if kullanici_dosyasi and Path(kullanici_dosyasi).exists():
            ozel = _kurallari_oku(yaml.safe_load(Path(kullanici_dosyasi).read_text("utf-8")))
            kurallar = ozel + kurallar
        return cls(kurallar)

    def bul(self, aciklama: str, tutar: float) -> str:
        s = sade(aciklama)
        # Noktalamasız hâli de denenir: öğrenilen 'MONEYPAY DIJITAL' → 'MONEYPAY *DIJITAL PLAT'
        s2 = re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", s)).strip()
        for kural in self.kurallar:
            if kural.eslesir(s, tutar) or (s2 != s and kural.eslesir(s2, tutar)):
                return kural.kategori
        return DIGER_GELIR if tutar > 0 else DIGER_GIDER

    def uygula(self, df: pd.DataFrame, uzerine_yaz: bool = False) -> pd.DataFrame:
        """'kategori' sütununu doldurur. Elle girilmiş kategoriler korunur (uzerine_yaz=False)."""
        df = df.copy()
        if "kategori" not in df.columns:
            df["kategori"] = None
        bos = df["kategori"].isna() | (df["kategori"].astype(str).str.strip() == "")
        if "elle" in df.columns:  # depodan gelen işlemler: elle atanmamış olanları kurallar belirler
            bos |= df["elle"].fillna(0).astype(int) == 0
        hedef = df.index if uzerine_yaz else df.index[bos]
        df.loc[hedef, "kategori"] = [
            self.bul(a, t) for a, t in zip(df.loc[hedef, "aciklama"], df.loc[hedef, "tutar"], strict=True)
        ]
        # Kart ekstresinde alacak (artı) satır gelir OLAMAZ: ya karta yapılan ödemedir ya iadedir.
        if "kaynak_turu" in df.columns:
            alacak = df.index[(df["kaynak_turu"] == "kart") & (df["tutar"] > 0)
                              & df.index.isin(hedef) & ~df["kategori"].isin(NOTR_KATEGORILER)]
            df.loc[alacak, "kategori"] = [
                "Transfer" if _ODEME.search(sade(a)) else "İade" for a in df.loc[alacak, "aciklama"]]
        df["zorunlu"] = df["kategori"].isin(self.zorunlu)
        return df
