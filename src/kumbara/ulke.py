"""Ülke profilleri: para birimi, enflasyon varsayımı ve varlık sınıflarının o ülkedeki karşılıkları.

Portföy kuralları (vade × risk model dağılımları, Monte Carlo) her ülkede AYNIDIR; değişen,
her varlık sınıfının yerel karşılığı (örnek araç, panel dilinde) ve uzun vadeli reel getiri/oynaklık
varsayımlarıdır. Türkiye için canlı TCMB/TEFAS verisi kullanılabilir; diğer ülkelerde değerler
uzun vadeli tarihsel ortalamalara dayanan VARSAYIMLARDIR (panelde değiştirilebilir enflasyon).

Yeni ülke eklemek için ULKELER sözlüğüne bir Ulke girmek yeterlidir.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from . import portfoy as pf


@dataclass(frozen=True)
class Ulke:
    kod: str
    ad: str
    para: str
    sembol: str
    enflasyon: float  # yıllık, varsayılan (panelde değiştirilebilir)
    # sınıf kodu -> (yerel ad / örnek araç, yıllık reel getiri, yıllık oynaklık); None: Türkiye önseli
    siniflar: dict[str, tuple[str, float, float]] | None
    borsa_adi: str = ""
    # yurt dışı hisse/ETF fiyatı aranırken denenecek borsalar (TradingView adlarıyla), sırayla
    borsalar: tuple[str, ...] = ("NASDAQ", "NYSE", "AMEX")
    # varlık sınıfı -> örnek ETF'ler ("BORSA:SEMBOL", ad); Türkiye'de TEFAS fonları kullanılır
    etfler: dict[str, tuple[tuple[str, str], ...]] | None = None


ULKELER: dict[str, Ulke] = {u.kod: u for u in [
    Ulke("TR", "Türkiye", "TRY", "₺", 0.30, None, "Borsa İstanbul"),
    Ulke("US", "United States", "USD", "$", 0.025, {
        "ppf": ("Money market fund / high-yield savings account", 0.005, 0.01),
        "kisa_borc": ("Short-term Treasury bill ETF", 0.008, 0.02),
        "tl_tahvil": ("US Treasury / total bond market ETF", 0.015, 0.06),
        "eurobond": ("Global bond ETF (currency-hedged)", 0.012, 0.05),
        "altin": ("Gold ETF", 0.01, 0.15),
        "bist_hisse": ("US equity index ETF (S&P 500 / total market)", 0.05, 0.16),
        "yabanci_hisse": ("International developed + emerging equity ETF", 0.045, 0.17),
    }, "NYSE / Nasdaq", ("NASDAQ", "NYSE", "AMEX"), {
        "ppf": (("AMEX:BIL", "SPDR Bloomberg 1-3 Month T-Bill ETF"),),
        "kisa_borc": (("NASDAQ:SHY", "iShares 1-3 Year Treasury Bond ETF"),),
        "tl_tahvil": (("NASDAQ:BND", "Vanguard Total Bond Market ETF"),
                      ("AMEX:AGG", "iShares Core US Aggregate Bond ETF")),
        "eurobond": (("NASDAQ:BNDX", "Vanguard Total International Bond ETF"),),
        "altin": (("AMEX:GLD", "SPDR Gold Shares"), ("AMEX:IAU", "iShares Gold Trust")),
        "bist_hisse": (("AMEX:VOO", "Vanguard S&P 500 ETF"),
                       ("AMEX:VTI", "Vanguard Total Stock Market ETF")),
        "yabanci_hisse": (("NASDAQ:VXUS", "Vanguard Total International Stock ETF"),
                          ("AMEX:VEA", "Vanguard FTSE Developed Markets ETF")),
    }),
    Ulke("DE", "Deutschland", "EUR", "€", 0.022, {
        "ppf": ("Tagesgeld / Festgeld / Geldmarkt-ETF", 0.0, 0.01),
        "kisa_borc": ("Kurzlaufende Euro-Staatsanleihen-ETF", 0.003, 0.02),
        "tl_tahvil": ("Euro-Staatsanleihen-ETF", 0.01, 0.06),
        "eurobond": ("Globale Anleihen-ETF (USD, Währungsrisiko)", 0.01, 0.09),
        "altin": ("Gold (physisch besicherter ETC)", 0.015, 0.15),
        "bist_hisse": ("Europa- / Eurozonen-Aktien-ETF", 0.045, 0.18),
        "yabanci_hisse": ("Welt-Aktien-ETF (MSCI World / ACWI)", 0.045, 0.15),
    }, "Xetra", ("XETR", "NASDAQ", "NYSE", "AMEX"), {
        "ppf": (("XETR:XEON", "Xtrackers II EUR Overnight Rate Swap UCITS ETF"),),
        "kisa_borc": (("XETR:DBXP", "Xtrackers II Eurozone Government Bond 1-3 UCITS ETF"),),
        "tl_tahvil": (("XETR:EUNH", "iShares Core EUR Govt Bond UCITS ETF"),),
        "eurobond": (("XETR:EUNA", "iShares Core Global Aggregate Bond UCITS ETF EUR Hedged"),),
        "altin": (("XETR:4GLD", "Xetra-Gold"),),
        "bist_hisse": (("XETR:EUNK", "iShares Core MSCI Europe UCITS ETF"),),
        "yabanci_hisse": (("XETR:EUNL", "iShares Core MSCI World UCITS ETF"),
                          ("XETR:VWCE", "Vanguard FTSE All-World UCITS ETF (Acc)")),
    }),
    Ulke("GB", "United Kingdom", "GBP", "£", 0.028, {
        "ppf": ("Easy-access savings / money market fund (in an ISA)", 0.005, 0.01),
        "kisa_borc": ("Short-dated gilt ETF", 0.008, 0.02),
        "tl_tahvil": ("UK government bond (gilt) ETF", 0.012, 0.08),
        "eurobond": ("Global bond ETF (currency-hedged)", 0.01, 0.05),
        "altin": ("Gold ETC", 0.015, 0.15),
        "bist_hisse": ("UK equity ETF (FTSE All-Share)", 0.045, 0.15),
        "yabanci_hisse": ("Global equity ETF (FTSE All-World)", 0.045, 0.14),
    }, "London Stock Exchange", ("LSE", "NASDAQ", "NYSE", "AMEX"), {
        "ppf": (("LSE:CSH2", "Amundi Smart Overnight Return UCITS ETF GBP"),),
        "kisa_borc": (("LSE:IGLS", "iShares UK Gilts 0-5yr UCITS ETF"),),
        "tl_tahvil": (("LSE:IGLT", "iShares Core UK Gilts UCITS ETF"),),
        "eurobond": (("LSE:AGBP", "iShares Core Global Aggregate Bond UCITS ETF GBP Hedged"),),
        "altin": (("LSE:SGLN", "iShares Physical Gold ETC"),),
        "bist_hisse": (("LSE:VUKE", "Vanguard FTSE 100 UCITS ETF"),),
        "yabanci_hisse": (("LSE:VWRL", "Vanguard FTSE All-World UCITS ETF"),),
    }),
]}


# ETF sembolü -> (listelendiği ülke, o ülkeye göre varlık sınıfı); hem "AMEX:VOO" hem "VOO"
ETF_SINIFI: dict[str, tuple[str, str]] = {}
for _u in ULKELER.values():
    for _sinif, _liste in (_u.etfler or {}).items():
        for _sembol, _ in _liste:
            ETF_SINIFI[_sembol] = ETF_SINIFI[_sembol.split(":")[1]] = (_u.kod, _sinif)


def yabanci_sinifi(sembol: str | None, kaynak_para: str | None, ulke: Ulke) -> str:
    """Yurt dışı hisse/ETF'nin, seçilen ülkenin yatırımcısı için varlık sınıfı.

    Listedeki ETF'ler kendi ülkelerinin sınıfını taşır; başka ülkenin yatırımcısı için hisseler
    yabancı hisse, tahvil/nakit ETF'leri döviz tahvil olur. Listede olmayan sembol hissedir: para
    birimi seçilen ülkeninkiyse yerel, değilse yabancı hisse.
    """
    eslesme = ETF_SINIFI.get(sembol or "") or ETF_SINIFI.get((sembol or "").split(":")[-1])
    if eslesme is None:
        return "bist_hisse" if kaynak_para == ulke.para else "yabanci_hisse"
    etf_ulke, sinif = eslesme
    if etf_ulke == ulke.kod:
        return sinif
    return {"bist_hisse": "yabanci_hisse", "yabanci_hisse": "yabanci_hisse",
            "altin": "altin"}.get(sinif, "eurobond")


def ulke_uygula(kod: str) -> Ulke:
    """Seçilen ülkenin varlık sınıfı adlarını ve varsayımlarını portföy modeline uygular."""
    ulke = ULKELER[kod]
    pf.varsayilanlara_don()
    if ulke.siniflar:
        for sinif, (ad, getiri, oynaklik) in ulke.siniflar.items():
            pf.VARLIK_SINIFLARI[sinif] = replace(pf.VARLIK_SINIFLARI[sinif], ad=ad,
                                                 reel_getiri=getiri, oynaklik=oynaklik)
        pf.PARAMETRE_KAYNAGI = "long-run historical averages"
    return ulke


def para(x: float | None, ulke: Ulke, ondalik: int = 0) -> str:
    if x is None:
        return "-"
    isaret = "-" if round(x, ondalik) < 0 else ""
    metin = f"{abs(x):,.{ondalik}f}"
    if ulke.kod == "TR" or ulke.para == "EUR":  # 1.234,56
        metin = metin.replace(",", "_").replace(".", ",").replace("_", ".")
    return (f"{isaret}{ulke.sembol}{metin}" if ulke.para in ("USD", "GBP")
            else f"{isaret}{metin} {ulke.sembol}")
