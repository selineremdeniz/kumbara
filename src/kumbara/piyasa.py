"""Canlı piyasa verisi: TCMB kurları ve faiz, TÜFE, altın, BIST, TEFAS fonları, KAP bildirimleri.

Kaynaklar ve erişilen sunucular:
    TCMB günlük kurlar (resmi XML)     www.tcmb.gov.tr
    TCMB politika faizi, TÜFE           www.tcmb.gov.tr                 (borsapy)
    EVDS seriler (isteğe bağlı anahtar) evds3.tcmb.gov.tr               (borsapy, EVDS_API_KEY)
    Altın / anlık döviz                 a.canlidoviz.com                (borsapy)
    BIST fiyatları                      data.tradingview.com (WebSocket, ~15 dk gecikmeli)
    Şirket finansalları                 www.isyatirim.com.tr            (borsapy)
    Yatırım fonları                     www.tefas.gov.tr                (borsapy)
    KAP bildirimleri                    www.kap.org.tr, kap.org.tr      (borsapy)

Her çağrı hata durumunda None/boş tablo döndürür; araç çevrimdışıyken de çalışmaya devam eder.
"""

from __future__ import annotations

import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from .metin import sade
from .portfoy import VARLIK_SINIFLARI

log = logging.getLogger(__name__)
TZ = ZoneInfo("Europe/Istanbul")
TCMB_KUR_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"
_UA = "kumbara/0.1 (kisisel finans araci)"


def _oran(deger) -> float | None:
    """'%39,5', 39.5 veya 0.395 -> 0.395"""
    if deger is None:
        return None
    try:
        x = float(str(deger).replace("%", "").replace(",", ".").strip())
    except ValueError:
        return None
    return x / 100 if abs(x) > 1.5 else x


class Onbellek:
    def __init__(self, dizin: Path):
        self.dosya = Path(dizin) / "piyasa_onbellek.json"
        try:
            self.veri = json.loads(self.dosya.read_text("utf-8"))
        except (OSError, ValueError):
            self.veri = {}

    def al(self, anahtar: str, ttl: int):
        kayit = self.veri.get(anahtar)
        if kayit and time.time() - kayit["t"] < ttl:
            return kayit["v"]
        return None

    def koy(self, anahtar: str, deger) -> None:
        self.veri[anahtar] = {"t": time.time(), "v": deger}
        try:
            self.dosya.parent.mkdir(parents=True, exist_ok=True)
            self.dosya.write_text(json.dumps(self.veri, ensure_ascii=False, default=str), "utf-8")
        except OSError as e:
            log.debug("önbellek yazılamadı: %s", e)


class Piyasa:
    def __init__(self, veri_dizini: Path, zaman_asimi: float = 20.0):
        self.onbellek = Onbellek(veri_dizini)
        self.zaman_asimi = zaman_asimi
        self.hatalar: dict[str, str] = {}

    def _dene(self, ad: str, fn, varsayilan=None):
        try:
            return fn()
        except Exception as e:  # ağ, ayrıştırma, kaynak değişikliği...
            self.hatalar[ad] = f"{type(e).__name__}: {e}"[:300]
            log.info("%s alınamadı: %s", ad, e)
            return varsayilan

    # --- TCMB ---------------------------------------------------------------------------------
    def tcmb_kurlari(self) -> dict[str, dict[str, float]] | None:
        """TCMB'nin resmi günlük gösterge kurları (döviz alış/satış)."""
        onb = self.onbellek.al("tcmb_kur", 3600)
        if onb:
            return onb

        def getir():
            r = httpx.get(TCMB_KUR_URL, timeout=self.zaman_asimi, headers={"User-Agent": _UA})
            r.raise_for_status()
            kok = ET.fromstring(r.content)
            kurlar = {"_tarih": kok.attrib.get("Tarih")}
            for c in kok.findall("Currency"):
                kod = c.attrib.get("CurrencyCode") or c.attrib.get("Kod")
                birim = float(c.findtext("Unit") or 1)

                def oku(etiket, c=c, birim=birim):
                    t = (c.findtext(etiket) or "").strip()
                    return round(float(t) / birim, 6) if t else None
                kurlar[kod] = {"alis": oku("ForexBuying"), "satis": oku("ForexSelling")}
            return kurlar

        kurlar = self._dene("tcmb_kurlari", getir)
        if kurlar:
            self.onbellek.koy("tcmb_kur", kurlar)
        return kurlar

    def politika_faizi(self) -> float | None:
        """TCMB 1 hafta repo (politika) faizi: geçmiş tablosundaki EN SON tarihli değer.

        Not: borsapy 0.11'in policy_rate() fonksiyonu tablonun ilk (2010) satırını döndürüyor;
        bu yüzden geçmiş tablosu tarihe göre sıralanıp son satır alınır.
        """
        import borsapy as bp

        def getir():
            gecmis = bp.TCMB().history("policy")
            seri = pd.to_numeric(gecmis["lending"], errors="coerce").dropna()
            seri.index = pd.to_datetime(seri.index)
            return _oran(seri.sort_index().iloc[-1])
        return self._dene("politika_faizi", getir)

    def enflasyon(self) -> dict | None:
        """Son TÜFE: {'donem', 'yillik', 'aylik'} (oran olarak, 0.33 = %33)."""
        import borsapy as bp

        def getir():
            tufe = bp.Inflation().tufe(limit=3).sort_index()
            son = tufe.iloc[-1]
            aylik = [_oran(x) for x in tufe["MonthlyInflation"]]
            son3 = None
            if len(aylik) == 3 and all(a is not None for a in aylik):
                son3 = (1 + aylik[0]) * (1 + aylik[1]) * (1 + aylik[2])
                son3 = son3 ** 4 - 1
            return {"donem": son.get("YearMonth"), "yillik": _oran(son["YearlyInflation"]),
                    "aylik": _oran(son["MonthlyInflation"]), "son3_yillik": son3}
        return self._dene("enflasyon", getir)

    # --- Döviz / altın / BIST -------------------------------------------------------------------
    def anlik(self, varlik: str) -> float | None:
        """'USD', 'EUR', 'gram-altin' gibi varlıkların anlık fiyatı."""
        import borsapy as bp
        return self._dene(f"anlik:{varlik}", lambda: float(bp.FX(varlik).current["last"]))

    # --- Yurt dışı borsalar (TradingView: NASDAQ, NYSE, AMEX, LSE, XETR…) -----------------------
    def _borsa_ara(self, sembol: str, borsalar: tuple[str, ...]) -> list[str]:
        """Sembolün işlem gördüğü borsalar (tercih sırasıyla); arama kapalıysa boş liste."""
        def ara():
            from borsapy._providers.tradingview_search import get_search_provider
            sonuc = get_search_provider().search(sembol, limit=20)
            bulunan = {r.get("exchange", "").upper() for r in sonuc
                       if str(r.get("symbol", "")).upper() == sembol}
            return [b for b in borsalar if b in bulunan] + sorted(bulunan - set(borsalar))
        return self._dene(f"ara:{sembol}", ara, []) or []

    def yabanci(self, kod: str, borsalar: tuple[str, ...] = ("NASDAQ", "NYSE", "AMEX")) -> dict | None:
        """Yurt dışı hisse/ETF: {'sembol': 'AMEX:VOO', 'fiyat', 'para', 'ad'} ya da None.

        kod "BORSA:SEMBOL" (LSE:VWRL) ya da yalnızca sembol olabilir; yalnızca sembolse borsa,
        TradingView aramasıyla ya da `borsalar` sırasıyla denenerek bulunur. Peni (GBX) → GBP.
        """
        from borsapy._providers.tradingview import get_tradingview_provider
        tv = get_tradingview_provider()
        kod = kod.strip().upper()
        if ":" in kod:
            borsa, sembol = kod.split(":", 1)
            adaylar = [borsa]
        else:
            sembol = kod
            adaylar = self._borsa_ara(sembol, borsalar) or list(borsalar)
        for borsa in adaylar:
            q = self._dene(f"yabanci:{borsa}:{sembol}",
                           lambda b=borsa: tv.get_quote(sembol, b))
            if q and q.get("last"):
                fiyat, para = float(q["last"]), str(q.get("currency") or "USD").upper()
                if para in ("GBX", "GBPENCE"):
                    fiyat, para = fiyat / 100, "GBP"
                return {"sembol": f"{borsa}:{sembol}", "fiyat": fiyat, "para": para,
                        "ad": q.get("description") or sembol}
        return None

    def yabanci_getiri(self, sembol_tam: str) -> dict[str, float | None]:
        """Yurt dışı hisse/ETF'nin 1 ay, 1 yıl ve 3 yıllık getirisi (%)."""
        from datetime import timedelta

        from borsapy._providers.tradingview import get_tradingview_provider
        borsa, sembol = sembol_tam.split(":", 1)
        h = get_tradingview_provider().get_history(
            sembol, interval="1d", start=datetime.now() - timedelta(days=3 * 365 + 10), exchange=borsa)
        kapanis = h["Close"].dropna()
        if kapanis.empty:
            raise ValueError(f"{sembol_tam} için geçmiş yok")
        son, tarih = float(kapanis.iloc[-1]), kapanis.index[-1]

        def once(gun: int) -> float | None:
            eski = kapanis[kapanis.index <= tarih - pd.Timedelta(days=gun)]
            return round((son / float(eski.iloc[-1]) - 1) * 100, 2) if len(eski) else None
        return {"return_1m": once(30), "return_1y": once(365), "return_3y": once(3 * 365)}

    def hisse(self, sembol: str) -> dict | None:
        import borsapy as bp

        def getir():
            info = bp.Ticker(sembol.upper()).info  # fast_info sözlük gibi davranmıyor
            son = info.get("last")
            if son is None:
                raise ValueError(f"{sembol} için fiyat yok")
            return {"last_price": float(son), "previous_close": info.get("prev_close"),
                    "day_high": info.get("high"), "day_low": info.get("low"),
                    "volume": info.get("volume")}
        return self._dene(f"hisse:{sembol}", getir)

    # --- KAP --------------------------------------------------------------------------------------
    def kap_bildirimleri(self, sembol: str, adet: int = 10) -> pd.DataFrame:
        import borsapy as bp

        def getir():
            df = bp.Ticker(sembol.upper()).news
            return df.head(adet).assign(Sembol=sembol.upper())
        return self._dene(f"kap:{sembol}", getir, pd.DataFrame(columns=["Date", "Title", "URL"]))

    # --- TEFAS ------------------------------------------------------------------------------------
    def fon_listesi(self, fon_turu: str = "YAT") -> pd.DataFrame:
        """TEFAS'taki fonlar ve dönemsel getirileri (24 saat önbellekli)."""
        anahtar = f"tefas:{fon_turu}"
        onb = self.onbellek.al(anahtar, 24 * 3600)
        if onb:
            return pd.DataFrame(onb)
        import borsapy as bp
        df = self._dene("fon_listesi", lambda: bp.screen_funds(fund_type=fon_turu, limit=5000),
                        pd.DataFrame())
        if df is not None and len(df):
            self.onbellek.koy(anahtar, df.to_dict(orient="records"))
        return df if df is not None else pd.DataFrame()

    def fon_adaylari(self, sinif: str, adet: int = 3, fon_turu: str = "YAT") -> pd.DataFrame:
        """Bir varlık sınıfına uyan TEFAS fonları; 1 yıllık getiriye göre sıralı.

        Geçmiş getiri gelecek getirinin göstergesi değildir; liste yalnızca araştırma başlangıcıdır.
        Masraf oranı, fon büyüklüğü ve içtüzüğü mutlaka kontrol edin.
        """
        vs = VARLIK_SINIFLARI[sinif]
        df = self.fon_listesi(fon_turu)
        if df.empty or "name" not in df.columns:
            return pd.DataFrame(columns=["fund_code", "name", "return_1y"])
        ad = df["name"].map(sade)
        maske = ad.str.contains(vs.tefas_desen, regex=True)
        if vs.tefas_haric:
            maske &= ~ad.str.contains(vs.tefas_haric, regex=True)
        secim = df[maske].copy()
        if "return_1y" in secim.columns:
            secim = secim.sort_values("return_1y", ascending=False, na_position="last")
        kolonlar = [c for c in ("fund_code", "name", "return_1m", "return_1y", "return_3y")
                    if c in secim.columns]
        return secim[kolonlar].head(adet).reset_index(drop=True)

    # --- Toplu özet -------------------------------------------------------------------------------
    def ozet(self) -> dict:
        kurlar = self.tcmb_kurlari() or {}
        enf = self.enflasyon() or {}
        ozet = {
            "zaman": datetime.now(TZ).isoformat(timespec="seconds"),
            "usd_try": (kurlar.get("USD") or {}).get("satis") or self.anlik("USD"),
            "eur_try": (kurlar.get("EUR") or {}).get("satis") or self.anlik("EUR"),
            "gram_altin": self.anlik("gram-altin"),
            "politika_faizi": self.politika_faizi(),
            "tufe_yillik": enf.get("yillik"),
            "tufe_aylik": enf.get("aylik"),
            "tufe_donem": enf.get("donem"),
            "tufe_son3_yillik": enf.get("son3_yillik"),
            "tcmb_kur_tarihi": kurlar.get("_tarih"),
        }
        return ozet
