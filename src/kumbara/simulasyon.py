"""Monte Carlo hedef simülasyonu.

- Varlıkların aylık reel log getirileri korelasyonlu, kalın kuyruklu (Student-t, 5 serbestlik
  derecesi) dağılımdan çekilir. Normal dağılım, Türkiye'deki ani kur ve borsa şoklarını
  olduğundan seyrek gösterir. Ortak ki-kare bileşeni, krizlerde varlıkların birlikte
  düşmesini de modeller.
- Portföy her ay hedefe kalan süreye göre yeniden dengelenir (kayan dağılım): hedef
  yaklaştıkça uzun vade dağılımından orta, sonra kısa vade dağılımına geçilir.
- Katkı her ay sonunda yapılır ve reel olarak sabittir (yani nominalde her ay enflasyon kadar
  artar).

Servet katkıya göre doğrusal olduğundan (W = A + c·B) bir güven düzeyi için gereken katkı,
yol başına gereken katkıların kantili olarak tam hesaplanır; deneme-yanılma gerekmez.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import portfoy as pf

SERBESTLIK = 5
YOL_SAYISI = 4000


@dataclass
class SimulasyonSonucu:
    a: np.ndarray  # mevcut birikimin hedef tarihteki değeri (yol başına)
    b: np.ndarray  # aylık 1 TL katkının hedef tarihteki değeri (yol başına)
    hedef_tutar: float

    def gerekli_katki(self, guven: float) -> float:
        yol_basina = np.where(self.b > 0, (self.hedef_tutar - self.a) / self.b, np.inf)
        return round(max(0.0, float(np.quantile(yol_basina, guven))), 2)

    def olasilik(self, katki: float) -> float:
        return float(np.mean(self.a + katki * self.b >= self.hedef_tutar))

    def dagilim(self, katki: float) -> dict[str, float]:
        w = self.a + katki * self.b
        p10, p50, p90 = np.quantile(w, [0.1, 0.5, 0.9])
        return {"p10": round(float(p10), 2), "p50": round(float(p50), 2), "p90": round(float(p90), 2)}


def _parametreler(siniflar: list[str]):
    mu = np.array([np.log1p(pf.VARLIK_SINIFLARI[k].reel_getiri) / 12 for k in siniflar])
    sig = np.array([pf.VARLIK_SINIFLARI[k].oynaklik / np.sqrt(12) for k in siniflar])
    kor = np.array([[pf.korelasyon(i, j) for j in siniflar] for i in siniflar])
    return mu, sig, np.linalg.cholesky(kor + 1e-10 * np.eye(len(siniflar)))


def portfoy_getirileri(risk: str, ay: int, yol: int = YOL_SAYISI, tohum: int = 42) -> np.ndarray:
    """(yol, ay) boyutunda aylık reel portföy getirileri (basit getiri)."""
    siniflar = list(pf.VARLIK_SINIFLARI)
    mu, sig, chol = _parametreler(siniflar)
    agirliklar = {v: np.array([pf.MODEL_DAGILIMLAR[v][risk].get(k, 0) / 100 for k in siniflar])
                  for v in pf.VADELER}
    rng = np.random.default_rng(tohum)
    olcek = np.sqrt((SERBESTLIK - 2) / SERBESTLIK)  # birim varyanslı t
    sonuc = np.empty((yol, ay))
    for t in range(ay):
        z = rng.standard_normal((yol, len(siniflar))) @ chol.T
        z *= (olcek / np.sqrt(rng.chisquare(SERBESTLIK, yol) / SERBESTLIK))[:, None]
        varlik = np.expm1(mu + sig * z)
        sonuc[:, t] = varlik @ agirliklar[pf.vade_sinifi(ay - t)]
    return sonuc


def simule_et(hedef_tutar: float, mevcut: float, risk: str, ay: int,
              yol: int = YOL_SAYISI, tohum: int = 42) -> SimulasyonSonucu:
    r = np.maximum(portfoy_getirileri(risk, ay, yol, tohum), -0.99)
    son_ek = np.cumprod((1 + r)[:, ::-1], axis=1)[:, ::-1]  # son_ek[t] = Π_{s>=t}(1+r_s)
    a = mevcut * son_ek[:, 0]
    # t. ayın sonundaki katkı t+1..son aylarda büyür; son ayın katkısı büyümez.
    b = son_ek[:, 1:].sum(axis=1) + 1.0
    return SimulasyonSonucu(a=a, b=b, hedef_tutar=hedef_tutar)
