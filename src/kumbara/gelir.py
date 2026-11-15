"""Düzenli gelirler (maaş, kira geliri, burs...) ve zamlar.

Aynı ada birden çok kayıt girilebilir; her ay için o aya kadar başlamış EN SON kayıt geçerlidir.
Örnek: "Maaş 60.000" (başlangıçsız) + "Maaş 66.000, 2026-12'den itibaren"
       -> Kasım 2026: 60.000, Aralık 2026 ve sonrası: 66.000.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass
class SabitGelir:
    ad: str
    tutar: float
    baslangic: date | None = None  # bu aydan itibaren (boşsa: hep)
    bitis: date | None = None      # bu aydan sonra yok (ör. sözleşme bitişi)
    hesap: str | None = None       # yattığı hesap (bilgi amaçlı, ör. "Yapı Kredi")


def ay_coz(metin: str | date | None) -> date | None:
    """'2026-12', '2026-12-01' veya date -> ayın ilk günü."""
    if metin in (None, ""):
        return None
    if isinstance(metin, date):
        return metin.replace(day=1)
    p = pd.Period(str(metin)[:7], "M")
    return date(p.year, p.month, 1)


def tanimli_gelir(gelirler: list[SabitGelir], ay: pd.Period | str) -> float:
    """Bir ayda geçerli düzenli gelirlerin toplamı."""
    ay = pd.Period(ay, "M")
    toplam = 0.0
    for ad in {g.ad for g in gelirler}:
        gecerli = [g for g in gelirler if g.ad == ad
                   and (g.baslangic is None or pd.Period(g.baslangic, "M") <= ay)]
        if not gecerli:
            continue
        son = max(gecerli, key=lambda g: g.baslangic or date.min)
        if son.bitis is None or pd.Period(son.bitis, "M") >= ay:
            toplam += son.tutar
    return round(toplam, 2)
