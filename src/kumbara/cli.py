"""Komut satırı arayüzü:  kumbara --help"""

from __future__ import annotations

import os
import time
from datetime import date
from importlib import resources
from pathlib import Path

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from . import UYARI
from .analiz import aylik_ozet, duzenli_odemeler, en_cok_harcanan_yerler, kategori_kirilimi
from .butce import SabitGider, gelecek_ay_plani, taksit_takvimi
from .depo import ORNEK_HESAPLAR, Depo, veri_dizini
from .ekstre import EkstreHatasi, oku
from .kategori import Kategorilendirici
from .portfoy import (
    RISKLER,
    VARLIK_SINIFLARI,
    Hedef,
    birikimi_dagit,
    ppf_reel_getiri_guncelle,
    toplam_dagilim,
    varsayimlari_yukle,
)
from .varlik import (
    ALTIN_TURLERI,
    TURLER,
    Fiyatlayici,
    Varlik,
    degerle,
    hedeflere_uygula,
    planlara_dengeleme_uygula,
    sinif_adi,
)
from .varlik import csv_oku as varlik_csv_oku
from .varlik import ozet as varlik_ozeti

app = typer.Typer(help="kumbara: gelir-gider takibi, gelecek ay bütçesi ve hedef bazlı portföy.",
                  no_args_is_help=True)
hedef_app = typer.Typer(help="Birikim hedefleri", no_args_is_help=True)
sabit_app = typer.Typer(help="Sabit/zorunlu giderler (kira, kredi, aidat...)", no_args_is_help=True)
app.add_typer(hedef_app, name="hedef")
app.add_typer(sabit_app, name="sabit")
gelir_app = typer.Typer(help="Düzenli gelirler (maaş vb.) ve zamlar", no_args_is_help=True)
app.add_typer(gelir_app, name="gelir")
con = Console()
VARSAYILAN_AYLIK_ENFLASYON = 0.02


def tl(x: float | None) -> str:
    if x is None or pd.isna(x):
        return "-"
    x = 0.0 if abs(x) < 0.005 else x  # "-0,00" yazmasın
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") + " TL"


def yuzde(x: float | None) -> str:
    return "-" if x is None or pd.isna(x) else f"%{x * 100:.1f}".replace(".", ",")


def _tablo(baslik: str, kolonlar: list[str], satirlar) -> Table:
    t = Table(title=baslik, title_justify="left", header_style="bold")
    for k in kolonlar:
        t.add_column(k)
    for s in satirlar:
        t.add_row(*[str(x) for x in s])
    return t


def _kategorili(depo: Depo) -> pd.DataFrame:
    df = depo.islemler()
    if depo.ornek_var_mi() and set(df["hesap"]) - set(ORNEK_HESAPLAR):
        con.print("[yellow]Uyarı: gerçek verilerinizle birlikte ÖRNEK (sentetik) veriler de var; "
                  "sonuçlar karışık. Temizlemek için: kumbara ornek --sil[/]")
    if df.empty:
        con.print("[yellow]Henüz işlem yok. `kumbara yukle ekstre.xlsx` veya `kumbara ornek` "
                  "ile başlayın.[/]")
        raise typer.Exit(1)
    kat = Kategorilendirici.varsayilan(veri_dizini() / "kategoriler.yaml")
    df = kat.uygula(df)
    depo.kategorileri_guncelle(df)
    return df


@app.command()
def yukle(dosyalar: list[Path] = typer.Argument(..., exists=True,
                                               help="CSV/XLSX/PDF ekstreler, JPG/PNG ekran görüntüleri"),
          hesap: str = typer.Option(None, help="Hesap adı (ör. 'Yapı Kredi Kart')"),
          tur: str = typer.Option("otomatik", help="hesap | kart | otomatik"),
          sifre: str = typer.Option(None, help="Şifreli PDF'ler için şifre"),
          donem_ici: bool = typer.Option(None, "--donem-ici/--kesin",
                                         help="Henüz ekstreye girmemiş işlemler mi? (varsayılan: "
                                              "görüntüler dönem içi, PDF/CSV kesin)")):
    """Hesap özeti / kart ekstresi / dönem içi ekran görüntüsü yükler.

    Dönem içi işlemler, aynı kartın ekstresi yüklenince otomatik olarak ekstre satırlarıyla
    değiştirilir (çift sayılmaz). Görüntülerde hangi kart olduğunu --hesap ile belirtin:

    kumbara yukle donem_ici.jpg --hesap "Yapı Kredi Kart"
    """
    depo = Depo()
    kat = Kategorilendirici.varsayilan(veri_dizini() / "kategoriler.yaml")
    for dosya in dosyalar:
        try:
            df = kat.uygula(oku(dosya, hesap=hesap, tur=tur, sifre=sifre, donem_ici=donem_ici))
        except EkstreHatasi as e:
            con.print(f"[red]{e}[/]")
            con.print(f"[dim]Düzeni görmek için: kumbara pdf-tani \"{dosya}\"[/]")
            continue
        eklenen = depo.islem_ekle(df)
        con.print(f"[green]{dosya.name}[/] ({df['hesap'].iat[0]}"
                  f"{', dönem içi' if df['donem_ici'].any() else ''}): {len(df)} işlem okundu, "
                  f"{eklenen} yeni eklendi ({df['tarih'].min()} → {df['tarih'].max()})."
                  + _rapor_metni(depo.son_rapor))


def _rapor_metni(r: dict) -> str:
    parcalar = []
    if r.get("kesinlesen"):
        parcalar.append(f"{r['kesinlesen']} dönem içi işlem ekstreyle kesinleşti")
    if r.get("zaten_ekstrede"):
        parcalar.append(f"{r['zaten_ekstrede']} işlem zaten ekstrede olduğu için atlandı")
    if r.get("guncellenen"):
        parcalar.append(f"{r['guncellenen']} dönem içi işlem güncellendi")
    return (" " + "; ".join(parcalar) + ".") if parcalar else ""


@app.command("kart")
def kart_komutu():
    """Kart borçları: önceki ekstreler ÖDENDİ varsayılır; kalan = dönem içi + taksitler."""
    from .kart import kart_borclari
    b = kart_borclari(_kategorili(Depo()))
    if b.empty:
        con.print("Kart işlemi yok.")
        return
    _kart_tablosu(b)


def _kart_tablosu(b: pd.DataFrame) -> None:
    con.print(_tablo("Kart borçları (önceki ekstreler ödendi varsayıldı)",
                     ["Kart", "Dönem içi harcama", "İade", "Sıradaki taksit", "Sonraki ekstre ≈",
                      "Sonraki aylara kalan taksit", "Toplam borç"],
                     [(r.hesap, tl(r.donem_ici_harcama) if r.donem_ici_var else "yüklenmedi",
                       tl(r.donem_ici_iade), tl(r.sonraki_taksit), tl(r.sonraki_ekstre),
                       tl(r.kalan_taksit), tl(r.toplam_borc)) for r in b.itertuples()]))
    con.print(f"[bold]Toplam: sonraki ekstreler {tl(b['sonraki_ekstre'].sum())}, toplam kart borcu "
              f"{tl(b['toplam_borc'].sum())}[/]")
    if not b["donem_ici_var"].all():
        con.print("[dim]Dönem içi yüklenmeyen kartlarda yalnızca taksitler görünür. Mobil "
                  "uygulamadaki 'dönem içi işlemler' ekranının görüntüsünü yükleyin: "
                  "kumbara yukle ekran.jpg --hesap \"<kart adı>\"[/]")


varlik_app = typer.Typer(help="Yatırım hesapları, fiziki altın, döviz: toplam birikim",
                         no_args_is_help=True)
app.add_typer(varlik_app, name="varlik")


def _varlik_degerle(depo: Depo, cevrimdisi: bool = False, kaydet: bool = True):
    """Varlıkları canlı fiyatla değerler; tamamı fiyatlanabildiyse günün kaydını tutar."""
    varliklar = depo.varliklar()
    if not varliklar:
        return None
    piyasa_ = None
    if not cevrimdisi:
        from .piyasa import Piyasa
        piyasa_ = Piyasa(veri_dizini())
    gecmis = depo.varlik_gecmisi()
    son_bilinen = {}
    for detay in gecmis["detay"]:
        son_bilinen.update(detay.get("fiyatlar") or {})
    fiyatlayici = Fiyatlayici(piyasa_, son_bilinen=son_bilinen)
    d = degerle(varliklar, fiyatlayici)
    if fiyatlayici.eski_fiyatli:
        con.print(f"[yellow]Canlı fiyatı alınamayıp son bilinen fiyatla değerlenenler: "
                  f"{', '.join(sorted(fiyatlayici.eski_fiyatli))}[/]")
    oz = varlik_ozeti(d)
    if oz["fiyatlanamayan"]:
        con.print(f"[yellow]{oz['fiyatlanamayan']} varlık fiyatlanamadı; toplam eksik olabilir"
                  + (" (çevrimdışı)." if cevrimdisi else ".") + "[/]")
    elif kaydet and not cevrimdisi:
        depo.varlik_degeri_kaydet(date.today().isoformat(), oz)
    return d


def _yazi(x) -> str:
    return "-" if x is None or (isinstance(x, float) and pd.isna(x)) or x == "" else str(x)


def _sayi(x) -> str:
    """Birim fiyat: Türkçe biçim, gereksiz sıfırsız (6.439,675 / 0,8993)."""
    if x is None or pd.isna(x):
        return "-"
    metin = f"{x:,.4f}".rstrip("0").rstrip(".")
    return metin.replace(",", "_").replace(".", ",").replace("_", ".")


@varlik_app.command("ekle")
def varlik_ekle(tur: str = typer.Argument(..., help=" | ".join(TURLER)),
                kod: str = typer.Argument(..., help="Fon kodu (AFT), hisse (THYAO), altın türü "
                                          f"({', '.join(ALTIN_TURLERI)}), döviz (USD); nakit: ad"),
                miktar: float = typer.Argument(..., help="Pay adedi / gram / adet / döviz / TL"),
                maliyet: float = typer.Option(None, help="Toplam alış maliyeti (TL)"),
                kurum: str = typer.Option(None, help="Ör. 'İş Yatırım', 'Ev'"),
                hedef: str = typer.Option(None, help="Bağlanacak birikim hedefinin adı"),
                deger: float = typer.Option(None, help="'diger' türü için toplam TL değer")):
    """Varlık ekler. Örnekler:

    kumbara varlik ekle fon AFT 12500 --kurum "İş Yatırım" --hedef "Ev peşinatı"

    kumbara varlik ekle altin ceyrek 4 --kurum Ev --maliyet 32000

    kumbara varlik ekle altin 22ayar 35 --kurum Ev   (bilezik, gram)

    kumbara varlik ekle altin ajda 20 --kurum Ev      (22 ayar ajda bilezik, gram)

    kumbara varlik ekle doviz USD 1500 --hedef "Acil durum fonu"
    """
    try:
        v = Varlik(tur, kod, miktar, maliyet, kurum, hedef, deger)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    depo = Depo()
    if hedef and hedef not in {h.ad for h in depo.hedefler()}:
        con.print(f"[yellow]'{hedef}' adlı bir hedef yok; varlık yine de kaydedildi.[/]")
    con.print(f"Kaydedildi (id {depo.varlik_kaydet(v)}): {v.tur} {v.kod} {v.miktar}")


@varlik_app.command("liste")
def varlik_liste(cevrimdisi: bool = typer.Option(False)):
    """Varlıkları canlı fiyatla değerler, toplam birikimi gösterir ve günün kaydını tutar."""
    depo = Depo()
    d = _varlik_degerle(depo, cevrimdisi)
    if d is None:
        con.print("Varlık yok: `kumbara varlik ekle ...` veya `kumbara varlik yukle dosya.csv`")
        raise typer.Exit(1)
    con.print(_tablo("Varlıklar", ["id", "Tür", "Kod", "Ad", "Miktar", "Birim fiyat", "Değer",
                                   "Kâr/zarar", "Sınıf", "Kurum", "Hedef"],
                     [(r.id, r.tur, r.kod, (r.ad or "")[:34], f"{r.miktar:g}",
                       _sayi(r.birim_fiyat),
                       tl(r.deger), "-" if pd.isna(r.kar) else f"{tl(r.kar)} ({yuzde(r.kar_orani)})",
                       r.sinif_adi, _yazi(r.kurum), _yazi(r.hedef)) for r in d.itertuples()]))
    oz = varlik_ozeti(d)
    con.print(f"[bold]Toplam birikim: {tl(oz['toplam'])}[/]"
              + (f"  ·  maliyeti girilenler: {tl(oz['maliyet'])} → {tl(oz['maliyetli_deger'])}"
                 if oz["maliyet"] else ""))
    con.print(_tablo("Varlık sınıfına göre", ["Sınıf", "Değer", "Pay"],
                     [(sinif_adi(k), tl(v), yuzde(v / oz["toplam"])) for k, v in
                      sorted(oz["sinif"].items(), key=lambda kv: -kv[1])] if oz["toplam"] else []))
    hedef_adlari = {h.ad for h in depo.hedefler()}
    atanmamis = oz["hedef"].get("", 0)
    con.print(_tablo("Hedefe göre", ["Hedef", "Değer"],
                     [(k or "(hedefe bağlı değil)", tl(v)) for k, v in oz["hedef"].items()]))
    if atanmamis and hedef_adlari:
        con.print(f"[dim]{tl(atanmamis)} hiçbir hedefe bağlı değil. Bağlamak için: "
                  "kumbara varlik guncelle <id> --hedef \"<hedef adı>\"[/]")
    bilinmeyen = {k for k in oz["hedef"] if k and k not in hedef_adlari}
    if bilinmeyen:
        con.print(f"[yellow]Böyle bir hedef yok: {', '.join(bilinmeyen)}[/]")


@varlik_app.command("guncelle")
def varlik_guncelle(varlik_id: int, miktar: float = typer.Option(None),
                    maliyet: float = typer.Option(None), kurum: str = typer.Option(None),
                    hedef: str = typer.Option(None, help="Boş bağlantı için: --hedef ''"),
                    deger: float = typer.Option(None)):
    """Bir varlığın miktarını, maliyetini, kurumunu veya bağlı hedefini değiştirir."""
    depo = Depo()
    v = next((x for x in depo.varliklar() if x.id == varlik_id), None)
    if v is None:
        raise typer.BadParameter(f"id {varlik_id} bulunamadı")
    for alan, deger_ in (("miktar", miktar), ("maliyet", maliyet), ("kurum", kurum),
                         ("hedef", hedef), ("deger_elle", deger)):
        if deger_ is not None:
            setattr(v, alan, (deger_ or None) if alan == "hedef" else deger_)
    depo.varlik_kaydet(v)
    con.print(f"Güncellendi: {v}")


@varlik_app.command("sil")
def varlik_sil(varlik_id: int):
    con.print(f"{Depo().varlik_sil(varlik_id)} varlık silindi.")


@varlik_app.command("yukle")
def varlik_yukle(dosya: Path = typer.Argument(..., exists=True)):
    """CSV/XLSX'ten toplu varlık ekler. Sütunlar: tur;kod;miktar;maliyet;kurum;hedef;deger
    (ilk üçü zorunlu). Şablon: src/kumbara/veri/varlik_sablonu.csv"""
    depo = Depo()
    try:
        varliklar = varlik_csv_oku(dosya)
    except ValueError as e:
        con.print(f"[red]{e}[/]")
        raise typer.Exit(1) from e
    for v in varliklar:
        depo.varlik_kaydet(v)
    con.print(f"{len(varliklar)} varlık eklendi. Değerlemek için: kumbara varlik liste")


@varlik_app.command("gecmis")
def varlik_gecmis():
    """Kaydedilmiş günlük değerlemeler: toplam birikimin seyri."""
    g = Depo().varlik_gecmisi()
    if g.empty:
        con.print("Henüz kayıt yok; `kumbara varlik liste` her çalıştığında günün değeri kaydedilir.")
        return
    ilk = g["toplam"].iat[0]
    con.print(_tablo("Toplam birikim (kümülatif)", ["Tarih", "Toplam", "Maliyet", "Başlangıca göre"],
                     [(r.tarih, tl(r.toplam), tl(r.maliyet) if r.maliyet else "-",
                       tl(r.toplam - ilk)) for r in g.itertuples()]))


@app.command("sil")
def islem_sil(kaynak: str = typer.Option(None, help="Yalnızca bu dosyadan gelen işlemler"),
              hesap: str = typer.Option(None, help="--kaynak ile: yalnızca bu hesap adıyla yüklenen"),
              hepsi: bool = typer.Option(False, "--hepsi", help="Tüm işlemleri sil"),
              evet: bool = typer.Option(False, "--evet", help="Onay sorma")):
    """Yüklenmiş işlemleri siler (ekstreyi yeniden yüklemeden önce). Hedefler ve sabit giderler
    kalır. Seçenek verilmezse yüklü dosyaları listeler."""
    depo = Depo()
    if not kaynak and not hepsi:
        con.print(_tablo("Yüklü dosyalar", ["Dosya", "Hesap", "İşlem", "İlk", "Son", "Gider"],
                         [(r.kaynak, r.hesap, r.adet, r.ilk, r.son, tl(r.gider))
                          for r in depo.kaynak_ozeti().itertuples()]))
        for k, h in depo.kopya_kaynaklar().items():
            con.print(f"[yellow]{k} iki kez yüklenmiş ({' / '.join(h)}); fazla olanı silin: "
                      f'kumbara sil --kaynak "{k}" --hesap "{h[0]}"[/]')
        con.print("Silmek için: kumbara sil --kaynak <dosya>  veya  kumbara sil --hepsi")
        return
    hedef = (f"{kaynak} ({hesap})" if hesap else kaynak) or "TÜM işlemler"
    if not evet and not typer.confirm(f"{hedef} silinsin mi?"):
        raise typer.Exit(1)
    con.print(f"{depo.islemleri_sil(kaynak, hesap)} işlem silindi.")


@app.command("hesap-degistir")
def hesap_degistir(kaynak: str = typer.Option(..., help="Dosya adı (kumbara sil ile görün)"),
                   eski: str = typer.Option(..., help="Şu anki hesap adı"),
                   yeni: str = typer.Option(..., help="Yeni hesap adı, ör. 'Yapı Kredi Kart'")):
    """Bir dosyadan gelen işlemleri başka bir hesaba taşır."""
    depo = Depo()
    con.print(f"{depo.hesap_degistir(kaynak, eski, yeni)} işlem '{yeni}' hesabına taşındı."
              + _rapor_metni(depo.son_rapor))


@app.command("kontrol")
def kontrol():
    """Teşhis: sürüm, OCR motoru, ayların kaynaklara göre dökümü, şüpheli kayıtlar.
    Çıktıda tutarlar vardır ama isim/kart numarası yoktur."""
    import importlib.util
    import subprocess
    import sys

    from .gorsel import KALAN_ACIKLAMA, OZET_ACIKLAMA, TAKSIT_ACIKLAMA
    depo = Depo()
    for kaynak, eski, yeni in depo.donem_ici_tarihlerini_duzelt():
        con.print(f"[green]Tarih düzeltildi:[/] {kaynak}: {eski} → {yeni}")
    try:
        surum = subprocess.run(["git", "log", "-1", "--format=%h %cs %s"], capture_output=True,
                               text=True, cwd=Path(__file__).parent, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        surum = ""
    con.print(f"[bold]Sürüm:[/] {surum or 'bilinmiyor (git yok)'}")
    ocr = []
    if sys.platform == "darwin" and importlib.util.find_spec("ocrmac"):
        ocr.append("Apple Vision")
    if importlib.util.find_spec("pytesseract"):
        import shutil
        ocr.append("Tesseract" + ("" if shutil.which("tesseract") else " (program kurulu değil)"))
    con.print(f"[bold]OCR:[/] {', '.join(ocr) or 'yok — görüntüler okunamaz'}")
    df = depo.islemler()
    if df.empty:
        con.print("İşlem yok.")
        return
    df = Kategorilendirici.varsayilan(veri_dizini() / "kategoriler.yaml").uygula(df)
    df["ay"] = pd.to_datetime(df["tarih"]).dt.to_period("M").astype(str)
    yardimci = df["aciklama"].isin((KALAN_ACIKLAMA, TAKSIT_ACIKLAMA, OZET_ACIKLAMA))
    df["kaynak_tipi"] = "ekstre/hesap"
    df.loc[df["donem_ici"], "kaynak_tipi"] = "dönem içi (görüntü)"
    df.loc[yardimci, "kaynak_tipi"] = "banka toplamından tamamlama"
    gider = df[(df["tutar"] < 0) & ~df["kategori"].isin({"Transfer", "BES ve Birikim"})]
    tablo = (-gider.pivot_table(index="ay", columns="kaynak_tipi", values="tutar", aggfunc="sum")
             ).fillna(0).round(2)
    tablo["TOPLAM GİDER"] = tablo.sum(axis=1)
    con.print(_tablo("Aylara göre gider (kaynağına göre)", ["Ay", *tablo.columns],
                     [(ay, *[tl(v) for v in r]) for ay, r in tablo.iterrows()]))
    oz = pd.read_sql_query("SELECT * FROM kart_ozetleri ORDER BY hesap, tarih", depo.bag)
    if len(oz):
        con.print(_tablo("Kayıtlı banka ekran toplamları", ["Kart", "Tarih", "Toplam", "Taksit",
                                                            "Taksit dahil", "Kesim"],
                         [(r.hesap, r.tarih, tl(r.toplam), tl(r.taksit), "evet" if r.taksit_dahil
                           else "hayır", r.kesim or "-") for r in oz.itertuples()]))
    else:
        con.print("[yellow]Kayıtlı banka ekran toplamı yok: dönem içi görüntülerinin üstündeki "
                  "'Güncel Dönem Borcu' / 'Dönem İçi Harcamalar Toplamı' okunamamış ya da eski "
                  "sürümle yüklenmiş. Görüntüleri silip yeniden yükleyin.[/]")
    uyarilar = []
    bugun = date.today()
    tuhaf = df[(pd.to_datetime(df["tarih"]) > pd.Timestamp(bugun) + pd.Timedelta(days=1))
               | (df["donem_ici"] & (pd.to_datetime(df["tarih"])
                                     < pd.Timestamp(bugun) - pd.Timedelta(days=75)))]
    for r in tuhaf.itertuples():
        uyarilar.append(f"Şüpheli tarih: {r.tarih} {r.aciklama[:40]} {tl(r.tutar)} — dosya "
                        f"'{r.kaynak}' ({'dönem içi' if r.donem_ici else 'ekstre'})")
    for k, h in depo.kopya_kaynaklar().items():
        uyarilar.append(f"Aynı dosya iki hesapla yüklenmiş: {k} ({' / '.join(h)})")
    if depo.ornek_var_mi():
        uyarilar.append("Örnek (sentetik) veri yüklü: kumbara ornek --sil")
    kart_di = df[(df["kaynak_turu"] == "kart") & df["donem_ici"] & ~yardimci]
    for hesap in sorted(set(kart_di["hesap"]) - set(oz["hesap"] if len(oz) else [])):
        uyarilar.append(f"{hesap}: dönem içi işlemler var ama banka toplamı yok; görünmeyen "
                        "işlemler eksik sayılıyor olabilir.")
    for u in uyarilar[:30]:
        con.print(f"[yellow]• {u}[/]")
    if not uyarilar:
        con.print("[green]Şüpheli bir şey bulunamadı.[/]")
    con.print("[dim]Yüklü dosyaların tarih aralıkları için: kumbara sil[/]")


@app.command("pdf-tani")
def pdf_tani(dosya: Path = typer.Argument(..., exists=True),
             sifre: str = typer.Option(None), satir: int = typer.Option(60)):
    """PDF'in veya ekran görüntüsünün (OCR) düzenini MASKELİ gösterir (rakamlar 9, harfler x):
    kişisel bilgi içermez, okunamayan ekstreleri hata bildirimi için paylaşabilirsiniz."""
    from .gorsel import GORSEL_UZANTILARI, gorsel_tani
    from .pdf_ekstre import tani
    try:
        metin = (gorsel_tani(dosya, satir) if dosya.suffix.lower() in GORSEL_UZANTILARI
                 else tani(dosya, sifre, satir))
        con.print(metin, markup=False, highlight=False)
    except EkstreHatasi as e:
        con.print(f"[red]{e}[/]")
        raise typer.Exit(1) from e


@app.command()
def ornek(sil: bool = typer.Option(False, "--sil", help="Örnek verileri temizle")):
    """Örnek (sentetik) ekstreleri yükler; aracı denemek için. Gerçek verinize geçmeden önce
    `kumbara ornek --sil` ile temizleyin."""
    depo = Depo()
    if sil:
        s = depo.ornek_sil()
        con.print(f"Silindi: {s['islem']} örnek işlem, {s['hedef']} örnek hedef, "
                  f"{s['sabit']} örnek sabit gider.")
        return
    kat = Kategorilendirici.varsayilan()
    for ad, hesap, tur in (("ornek_hesap.csv", "Örnek Vadesiz", "hesap"),
                           ("ornek_kart.csv", "Örnek Kart", "kart")):
        with resources.as_file(resources.files("kumbara.veri").joinpath(ad)) as yol:
            df = kat.uygula(oku(yol, hesap=hesap, tur=tur))
        con.print(f"{ad}: {depo.islem_ekle(df)} yeni işlem.")
    if not depo.hedefler():
        bugun = date.today()
        depo.hedef_kaydet(Hedef("Acil durum fonu", 90_000, date(bugun.year + 1, bugun.month, 1), 20_000, 1,
                                "muhafazakar"))
        depo.hedef_kaydet(Hedef("Araba peşinatı", 400_000, date(bugun.year + 3, 6, 1), 0, 2,
                                "dengeli"))
        depo.hedef_kaydet(Hedef("Ev / emeklilik", 3_000_000, date(bugun.year + 12, 1, 1), 50_000, 3,
                                "agresif"))
    if not depo.sabit_giderler():
        depo.sabit_kaydet(SabitGider("Kira", 25_000, "Kira"))
    con.print("Örnek hedefler ve sabit gider eklendi. Şimdi: [bold]kumbara analiz[/], "
              "[bold]kumbara plan[/]\n[yellow]Gerçek ekstrelerinizi yüklemeden önce "
              "`kumbara ornek --sil` ile örnek veriyi temizleyin; yoksa ikisi karışır.[/]")


@app.command()
def analiz(ay: str = typer.Option(None, help="YYYY-AA; boşsa son ay"),
           aylar: int = typer.Option(6, help="Özette gösterilecek ay sayısı")):
    """Aylık gelir-gider özeti, kategori kırılımı ve düzenli ödemeler."""
    depo = Depo()
    df = _kategorili(depo)
    ozet = aylik_ozet(df, depo.gelirler()).tail(aylar)
    con.print(_tablo("Aylık özet", ["Ay", "Gelir", "Gider", "Net", "Birikim oranı"],
                     [(str(i), tl(r.gelir), tl(r.gider), tl(r.net), yuzde(r.birikim_orani))
                      for i, r in ozet.iterrows()]))
    hedef_ay = ay or str(pd.to_datetime(df["tarih"]).max().to_period("M"))
    kir = kategori_kirilimi(df, hedef_ay)
    con.print(_tablo(f"{hedef_ay} kategori kırılımı", ["Kategori", "Tutar", "Pay"],
                     [(k, tl(r.tutar), yuzde(r.pay)) for k, r in kir.iterrows()]))
    duz = duzenli_odemeler(df)
    if len(duz):
        con.print(_tablo("Düzenli ödemeler (tespit)", ["İşyeri", "Kategori", "Tipik tutar", "Ay"],
                         [(r.isyeri, r.kategori, tl(r.tipik_tutar), r.ay_sayisi)
                          for r in duz.itertuples()]))
    yer = en_cok_harcanan_yerler(df, 8)
    con.print(_tablo("En çok harcanan yerler (tüm dönem)", ["İşyeri", "Kategori", "Toplam", "Adet"],
                     [(i, r.kategori, tl(r.toplam), r.adet) for i, r in yer.iterrows()]))
    diger = df[(df["kategori"] == "Diğer")]
    if len(diger):
        con.print(f"[dim]{len(diger)} işlem 'Diğer' kategorisinde. `kumbara islemler --kategori "
                  "Diğer` ile görüp `kumbara kategori <id> <kategori>` ile düzeltebilir ya da "
                  f"{veri_dizini() / 'kategoriler.yaml'} dosyasına kural ekleyebilirsiniz.[/]")


@app.command()
def islemler(kategori: str = typer.Option(None), son: int = typer.Option(30)):
    """İşlemleri listeler."""
    df = _kategorili(Depo())
    if kategori:
        df = df[df["kategori"] == kategori]
    df = df.tail(son)
    con.print(_tablo("İşlemler", ["id", "Tarih", "Açıklama", "Tutar", "Kategori", "Taksit"],
                     [(r.islem_id, r.tarih, r.aciklama[:40], tl(r.tutar), r.kategori,
                       f"{r.taksit_no}/{r.taksit_toplam}" if pd.notna(r.taksit_toplam) else "")
                      for r in df.itertuples()]))


@app.command("kategori")
def kategori_ata(islem_id: str, kategori: str,
                 kural: bool = typer.Option(True, "--kural/--tek",
                                            help="Aynı işyerinin tüm işlemleri için kural kaydet")):
    """Bir işlemin kategorisini değiştirir. Varsayılan olarak aynı işyerinin tüm işlemlerine
    uygulanan bir kural öğrenilir (~/.kumbara/kategoriler.yaml); --tek yalnızca bu işlemi değiştirir."""
    depo = Depo()
    df = depo.islemler()
    satir = df[df["islem_id"] == islem_id]
    if satir.empty:
        raise typer.BadParameter(f"{islem_id} bulunamadı (kumbara islemler ile bakın)")
    if kural:
        from .kategori import kural_ekle
        from .metin import isyeri_anahtari
        anahtar = isyeri_anahtari(satir["aciklama"].iat[0])
        kural_ekle(veri_dizini() / "kategoriler.yaml", kategori, anahtar,
                   "gelir" if satir["tutar"].iat[0] > 0 else "gider")
        con.print(f"Kural öğrenildi: '{anahtar}' → {kategori} (tüm işlemlerine uygulanır)")
    else:
        depo.kategori_ata(islem_id, kategori)
        con.print(f"{islem_id} → {kategori}")


@hedef_app.command("ekle")
def hedef_ekle(ad: str, tutar: float = typer.Argument(..., help="Bugünün TL'siyle hedef tutar"),
               tarih: str = typer.Argument(..., help="YYYY-AA-GG"),
               mevcut: float = typer.Option(0.0, help="Bu hedef için şu an ayrılmış birikim"),
               oncelik: int = typer.Option(2, min=1, max=3),
               risk: str = typer.Option("dengeli", help=" | ".join(RISKLER))):
    """Birikim hedefi ekler/günceller."""
    if risk not in RISKLER:
        raise typer.BadParameter(f"risk {RISKLER} içinden olmalı")
    h = Hedef(ad, tutar, date.fromisoformat(tarih), mevcut, oncelik, risk)
    Depo().hedef_kaydet(h)
    con.print(f"Hedef kaydedildi: {ad} ({h.vade()} vade, {h.ay_sayisi()} ay)")


@hedef_app.command("liste")
def hedef_liste():
    hedefler = Depo().hedefler()
    con.print(_tablo("Hedefler", ["Ad", "Tutar", "Tarih", "Mevcut", "Öncelik", "Risk", "Vade"],
                     [(h.ad, tl(h.tutar), h.tarih, tl(h.mevcut), h.oncelik, h.risk, h.vade())
                      for h in hedefler]))


@hedef_app.command("sil")
def hedef_sil(ad: str):
    Depo().hedef_sil(ad)


@gelir_app.command("ekle")
def gelir_ekle(ad: str = typer.Argument(..., help="Ör. Maaş"),
               tutar: float = typer.Argument(..., help="Aylık net tutar"),
               baslangic: str = typer.Option(None, help="Bu aydan itibaren (YYYY-AA), zam için"),
               bitis: str = typer.Option(None, help="Son ay (YYYY-AA)"),
               hesap: str = typer.Option(None, help="Yattığı hesap, ör. 'Yapı Kredi'")):
    """Düzenli gelir ekler. Zam için aynı adla yeni tutar ve --baslangic girin:

    kumbara gelir ekle Maaş 60000 --hesap "Yapı Kredi"

    kumbara gelir ekle Maaş 66000 --baslangic 2026-12
    """
    from .gelir import SabitGelir, ay_coz
    Depo().gelir_kaydet(SabitGelir(ad, tutar, ay_coz(baslangic), ay_coz(bitis), hesap))
    con.print(f"Kaydedildi: {ad} {tl(tutar)}" + (f" ({baslangic} itibarıyla)" if baslangic else ""))


@gelir_app.command("liste")
def gelir_liste():
    from .gelir import tanimli_gelir
    depo = Depo()
    gelirler = depo.gelirler()
    con.print(_tablo("Düzenli gelirler", ["Ad", "Tutar", "Başlangıç", "Bitiş", "Hesap"],
                     [(g.ad, tl(g.tutar), g.baslangic or "-", g.bitis or "-", g.hesap or "-")
                      for g in gelirler]))
    bu_ay = pd.Timestamp.today().to_period("M")
    con.print(" | ".join(f"{bu_ay + i}: {tl(tanimli_gelir(gelirler, bu_ay + i))}" for i in range(4)))


@gelir_app.command("sil")
def gelir_sil(ad: str, baslangic: str = typer.Option(None, help="Yalnızca bu başlangıçlı kayıt")):
    from .gelir import ay_coz
    con.print(f"{Depo().gelir_sil(ad, ay_coz(baslangic))} kayıt silindi.")


@sabit_app.command("ekle")
def sabit_ekle(ad: str, tutar: float, kategori: str = typer.Option("Kira"),
               bitis: str = typer.Option(None, help="Son ödeme ayı YYYY-AA-GG (kredi vb.)")):
    """Kira, kredi taksiti, aidat gibi sabit ödemeyi tanımlar."""
    Depo().sabit_kaydet(SabitGider(ad, tutar, kategori, date.fromisoformat(bitis) if bitis else None))
    con.print(f"Sabit gider kaydedildi: {ad} {tl(tutar)}")


@sabit_app.command("liste")
def sabit_liste():
    con.print(_tablo("Sabit giderler", ["Ad", "Tutar", "Kategori", "Bitiş"],
                     [(s.ad, tl(s.tutar), s.kategori, s.bitis or "-")
                      for s in Depo().sabit_giderler()]))


@sabit_app.command("sil")
def sabit_sil(ad: str):
    Depo().sabit_sil(ad)


PARAMETRE_DOSYASI = "parametreler.json"


def _parametreleri_yukle() -> None:
    from . import portfoy as pf
    from .tahmin import Parametreler
    varsayimlari_yukle(veri_dizini() / "varsayimlar.yaml")
    p = Parametreler.yukle(veri_dizini() / PARAMETRE_DOSYASI)
    if p is None:
        con.print("[yellow]Getiri/oynaklık tahmini yok; uzun vadeli varsayımlar kullanılıyor. "
                  "Gerçek veriden tahmin için: `kumbara parametre guncelle`[/]")
        return
    pf.parametreleri_uygula(p)
    if p.yas_gun() > 31:
        con.print(f"[yellow]Parametre tahmini {p.yas_gun()} günlük; `kumbara parametre guncelle` "
                  "ile yenileyin.[/]")


def _piyasa_baglami(cevrimdisi: bool, enflasyon: float | None) -> tuple[float, dict]:
    _parametreleri_yukle()
    ozet: dict = {}
    if not cevrimdisi:
        from .piyasa import Piyasa
        p = Piyasa(veri_dizini())
        ozet = p.ozet()
        ozet["_hatalar"] = p.hatalar
        ppf_reel_getiri_guncelle(ozet.get("politika_faizi"), ozet.get("tufe_yillik"),
                                 ozet.get("tufe_son3_yillik"))
    if enflasyon is not None:
        aylik = enflasyon
    elif ozet.get("tufe_aylik") is not None:
        aylik = ozet["tufe_aylik"]
    elif ozet.get("tufe_yillik") is not None:
        aylik = (1 + ozet["tufe_yillik"]) ** (1 / 12) - 1
    else:
        aylik = VARSAYILAN_AYLIK_ENFLASYON
        con.print(f"[yellow]Canlı TÜFE alınamadı; aylık enflasyon {yuzde(aylik)} varsayıldı "
                  "(--enflasyon ile değiştirin).[/]")
    return aylik, ozet


@app.command()
def plan(gelir: float = typer.Option(None, help="Gelecek ay beklenen net gelir"),
         enflasyon: float = typer.Option(None, help="Aylık enflasyon varsayımı (0.025 = %2,5)"),
         cevrimdisi: bool = typer.Option(False, help="Canlı veri çekme"),
         fon: bool = typer.Option(False, help="Her varlık sınıfı için TEFAS fon adaylarını göster"),
         guven: float = typer.Option(0.8, min=0.5, max=0.99,
                                     help="Hedefe ulaşma olasılığı hedefi (katkı buna göre hesaplanır)")):
    """Gelecek ay: taksitler, zorunlu giderler, harcama limitleri ve hedeflere göre portföy."""
    depo = Depo()
    df = _kategorili(depo)
    aylik_enf, ozet = _piyasa_baglami(cevrimdisi, enflasyon)
    degerleme = _varlik_degerle(depo, cevrimdisi)
    hedefler = depo.hedefler()
    if degerleme is not None:
        hedefler = hedeflere_uygula(hedefler, degerleme)
    gerekli = (sum(p.gerekli_aylik_katki for p in birikimi_dagit(hedefler, guven=guven))
               if hedefler else 0.0)
    kat = Kategorilendirici.varsayilan(veri_dizini() / "kategoriler.yaml")
    b = gelecek_ay_plani(df, depo.sabit_giderler(), gerekli, aylik_enf, gelir,
                         zorunlu_kategoriler=kat.zorunlu, gelirler=depo.gelirler())

    con.rule(f"[bold]{b.hedef_ay} bütçe planı")
    con.print(f"Beklenen gelir: [bold]{tl(b.beklenen_gelir)}[/] ({b.gelir_kaynagi})   "
              f"Aylık enflasyon varsayımı: {yuzde(aylik_enf)}")
    if len(b.taksitler):
        con.print(_tablo(f"Taksitler — toplam {tl(b.taksit_toplam)}",
                         ["İşyeri", "Hesap", "Tutar", "Taksit", "Kalan borç"],
                         [(r.isyeri, r.hesap, tl(r.tutar), r.taksit, tl(r.kalan_borc))
                          for r in b.taksitler.itertuples()]))
    if len(b.sabitler):
        con.print(_tablo(f"Sabit / düzenli ödemeler — toplam {tl(b.sabit_toplam)}",
                         ["Ad", "Kategori", "Tutar", "Kaynak"],
                         [(r.ad, r.kategori, tl(r.tutar), r.kaynak) for r in b.sabitler.itertuples()]))
    con.print(_tablo(f"Değişken harcama limitleri — toplam {tl(b.degisken_toplam)}",
                     ["Kategori", "Zorunlu", "Tahmin", "Önerilen limit"],
                     [(r.kategori, "evet" if r.zorunlu else "", tl(r.tahmin), tl(r.onerilen))
                      for r in b.degisken.itertuples()]))
    con.print(f"Hedefler için gereken birikim: {tl(b.birikim_hedefi)}  |  "
              f"Ayrılabilen: [bold]{tl(b.birikim_onerilen)}[/]  |  Ek birikim: {tl(b.ek_birikim)}")
    for n in b.notlar:
        con.print(f"[yellow]• {n}[/]")

    from .kart import kart_borclari
    kb = kart_borclari(df)
    if len(kb):
        _kart_tablosu(kb)
        con.print("[dim]Sonraki ekstre tutarları gelecek ay hesabınızdan çıkacak ödemelerdir "
                  "(bu ayın harcamaları). Yukarıdaki harcama limitleri ise gelecek ay yapacağınız "
                  "yeni harcamalar içindir.[/]")
    takvim = taksit_takvimi(df, b.hedef_ay, 6)
    if len(takvim):
        aylar = [c for c in takvim.columns if c[:2] == "20"]
        con.print(_tablo("Önümüzdeki 6 ayın taksit yükü", ["Ay", "Toplam"],
                         [(a, tl(takvim[a].sum())) for a in aylar]))

    if hedefler:
        planlar = birikimi_dagit(hedefler, b.birikim_onerilen + b.ek_birikim, guven=guven)
        if degerleme is not None:
            planlara_dengeleme_uygula(planlar, degerleme)
        _portfoy_yazdir(planlar, ozet, fon)
    else:
        con.print("Hedef tanımlı değil: `kumbara hedef ekle 'Tatil' 60000 2027-07-01`")


def _portfoy_yazdir(planlar, ozet: dict, fon: bool):
    from . import portfoy as pf
    con.rule("[bold]Hedef bazlı portföy önerisi")
    con.print(f"[dim]Getiri/oynaklık kaynağı: {pf.PARAMETRE_KAYNAGI}. Katkılar {4000} senaryoluk "
              "Monte Carlo simülasyonuyla (kalın kuyruklu, korelasyonlu) hesaplandı.[/]")
    if ozet:
        con.print(f"Piyasa: USD/TRY {ozet.get('usd_try') or '-'} | gram altın "
                  f"{tl(ozet.get('gram_altin'))} | politika faizi {yuzde(ozet.get('politika_faizi'))}"
                  f" | yıllık TÜFE {yuzde(ozet.get('tufe_yillik'))} ({ozet.get('tufe_donem') or '-'})")
        if ozet.get("_hatalar"):
            con.print(f"[dim]Alınamayan veriler: {', '.join(ozet['_hatalar'])}[/]")
    for vade in ("kısa", "orta", "uzun"):
        grup = [p for p in planlar if p.vade == vade]
        if not grup:
            continue
        con.print(f"\n[bold underline]{vade.capitalize()} vade[/]")
        for p in grup:
            con.print(f"[bold]{p.hedef.ad}[/] — hedef {tl(p.hedef.tutar)} ({p.hedef.tarih}, "
                      f"{p.ay_sayisi} ay, {p.hedef.risk}); beklenen reel getiri "
                      f"{yuzde(p.beklenen_reel_getiri)}/yıl, oynaklık ~{yuzde(p.beklenen_oynaklik)}")
            con.print(f"  Gerekli aylık katkı: %{p.guven * 100:.0f} olasılıkla "
                      f"{tl(p.gerekli_aylik_katki)} (ortalama getiriyle {tl(p.medyan_katki)})")
            con.print(f"  Bu ay ayrılan: [bold]{tl(p.onerilen_aylik_katki)}[/] (her ay enflasyon kadar "
                      f"artırın) → hedefe ulaşma olasılığı [bold]{yuzde(p.basari_olasiligi)}[/]")
            if p.sonuc_araligi:
                a = p.sonuc_araligi
                con.print(f"  Hedef tarihte birikim (bugünün TL'si): kötü senaryo {tl(a['p10'])} · "
                          f"orta {tl(a['p50'])} · iyi {tl(a['p90'])}")
            if p.mevcut_dagilim:
                toplam_m = sum(p.mevcut_dagilim.values())
                con.print(f"  Bu hedefe bağlı varlıklar: {tl(toplam_m)} — bu ayki katkı, dağılımı "
                          "hedefe yaklaştıracak şekilde bölündü (satış gerekmez):")
            for kod, oran in p.dagilim.items():
                mevcut_k = p.mevcut_dagilim.get(kod)
                simdi = (f"  (şu an %{(mevcut_k or 0) / sum(p.mevcut_dagilim.values()) * 100:.0f})"
                         if p.mevcut_dagilim and sum(p.mevcut_dagilim.values()) else "")
                con.print(f"    %{oran:>3}  {VARLIK_SINIFLARI[kod].ad:<48} "
                          f"{tl(p.katki_dagilimi.get(kod))}{simdi}")
            for u in p.uyarilar:
                con.print(f"  [yellow]! {u}[/]")
    toplam = toplam_dagilim(planlar)
    con.print(_tablo("Bu ay toplam alım dağılımı", ["Varlık sınıfı", "Tutar"],
                     [(VARLIK_SINIFLARI[k].ad, tl(v)) for k, v in toplam.items()]))
    if fon:
        from .piyasa import Piyasa
        p = Piyasa(veri_dizini())
        for kod in toplam:
            adaylar = p.fon_adaylari(kod)
            if len(adaylar):
                con.print(_tablo(f"TEFAS adayları: {VARLIK_SINIFLARI[kod].ad}",
                                 list(adaylar.columns), adaylar.values.tolist()))
    con.print(f"\n[dim]{UYARI}[/]")


@app.command()
def portfoy(birikim: float = typer.Option(None, help="Aylık ayırabileceğiniz tutar"),
            cevrimdisi: bool = typer.Option(False), fon: bool = typer.Option(False),
            guven: float = typer.Option(0.8, min=0.5, max=0.99)):
    """Yalnızca hedef bazlı portföy önerisi (bütçe hesaplamadan)."""
    depo = Depo()
    hedefler = depo.hedefler()
    if not hedefler:
        con.print("Hedef yok: `kumbara hedef ekle ...`")
        raise typer.Exit(1)
    _, ozet = _piyasa_baglami(cevrimdisi, None)
    degerleme = _varlik_degerle(depo, cevrimdisi)
    if degerleme is not None:
        hedefler = hedeflere_uygula(hedefler, degerleme)
    planlar = birikimi_dagit(hedefler, birikim, guven=guven)
    if degerleme is not None:
        planlara_dengeleme_uygula(planlar, degerleme)
    _portfoy_yazdir(planlar, ozet, fon)


parametre_app = typer.Typer(help="Getiri, oynaklık ve korelasyon tahminleri", no_args_is_help=True)
app.add_typer(parametre_app, name="parametre")


@parametre_app.command("guncelle")
def parametre_guncelle(fon_sayisi: int = typer.Option(8, help="Sınıf başına temsilci fon sayısı")):
    """TEFAS fon geçmişi (5 yıl) ve TÜFE'den reel getiri/oynaklık/korelasyon tahmin eder."""
    from .piyasa import Piyasa
    from .tahmin import tahmin_et
    p = Piyasa(veri_dizini())
    with con.status("Fon geçmişleri indiriliyor ve tahmin ediliyor…"):
        try:
            param = tahmin_et(p, fon_sayisi=fon_sayisi)
        except RuntimeError as e:
            con.print(f"[red]{e}[/]")
            raise typer.Exit(1) from e
    param.kaydet(veri_dizini() / PARAMETRE_DOSYASI)
    _parametre_yazdir(param)
    basarisiz = [k for k in p.hatalar if k.startswith("gecmis:")]
    if basarisiz:
        con.print(f"[dim]Geçmişi alınamayan fonlar: {', '.join(basarisiz)}[/]")


@parametre_app.command("goster")
def parametre_goster():
    from .tahmin import Parametreler
    param = Parametreler.yukle(veri_dizini() / PARAMETRE_DOSYASI)
    if param is None:
        con.print("Henüz tahmin yok: `kumbara parametre guncelle`")
        raise typer.Exit(1)
    _parametre_yazdir(param)


def _parametre_yazdir(param) -> None:
    con.print(_tablo(f"Reel getiri ve oynaklık tahmini ({param.tarih})",
                     ["Varlık sınıfı", "Ay", "Tarihsel getiri", "Kullanılan getiri",
                      "Tarihsel oynaklık", "Kullanılan oynaklık", "Fonlar"],
                     [(VARLIK_SINIFLARI[k].ad, param.ay_sayisi.get(k, 0),
                       yuzde(param.tarihsel_getiri.get(k)), yuzde(param.reel_getiri[k]),
                       yuzde(param.tarihsel_oynaklik.get(k)), yuzde(param.oynaklik[k]),
                       ", ".join(param.fonlar.get(k, []))) for k in param.reel_getiri]))
    kodlar = list(param.korelasyon)
    con.print(_tablo("Korelasyon", ["", *kodlar],
                     [(i, *[f"{param.korelasyon[i][j]:.2f}" for j in kodlar]) for i in kodlar]))
    for n in param.notlar:
        con.print(f"[yellow]• {n}[/]")
    con.print("[dim]Kullanılan getiri = tarihsel ortalama ile uzun vadeli varsayımın veri uzunluğuna "
              "göre harmanı (para piyasası: güncel politika faizinden ileriye dönük).[/]")


@app.command()
def piyasa(kaydet: bool = typer.Option(False, help="Özeti yerel veritabanına kaydet")):
    """Anlık piyasa özeti (TCMB kurları, altın, politika faizi, TÜFE)."""
    from .piyasa import Piyasa
    p = Piyasa(veri_dizini())
    ozet = p.ozet()
    for k, v in ozet.items():
        con.print(f"{k:<16} {v}")
    if p.hatalar:
        con.print("[yellow]Alınamayanlar:[/]")
        for k, v in p.hatalar.items():
            con.print(f"  {k}: {v}")
    if kaydet:
        Depo().piyasa_kaydet(ozet)
        con.print("[green]Kaydedildi.[/]")


@app.command()
def kap(semboller: list[str], adet: int = typer.Option(5),
        izle: bool = typer.Option(False, help="Yeni bildirimleri sürekli izle"),
        aralik: int = typer.Option(300, help="İzleme aralığı (saniye, en az 60)")):
    """KAP bildirimlerini gösterir; --izle ile yeni bildirim geldikçe yazar."""
    from .piyasa import Piyasa
    p = Piyasa(veri_dizini())
    gorulen: set[str] = set()
    while True:
        for s in semboller:
            df = p.kap_bildirimleri(s, adet)
            for r in df.itertuples():
                if r.URL in gorulen:
                    continue
                gorulen.add(r.URL)
                con.print(f"[bold]{s.upper()}[/] {r.Date}  {r.Title}\n    [dim]{r.URL}[/]")
        if p.hatalar:
            con.print(f"[yellow]{p.hatalar}[/]")
            p.hatalar.clear()
        if not izle:
            break
        time.sleep(max(60, aralik))


# Panel yalnızca bu bilgisayardan açılır (ağdaki başka cihazlar erişemez), Streamlit kullanım
# istatistiği gönderilmez ve "Deploy" (buluta yayınla) düğmesi gizlenir.
STREAMLIT_GIZLILIK = ("--server.address", "127.0.0.1", "--browser.gatherUsageStats", "false",
                      "--client.toolbarMode", "minimal")


@app.command()
def panel(ayrintili: bool = typer.Option(False, "--ayrintili",
                                        help="Ayrıntılı panel (işlem geçmişi, varlıklar, KAP)")):
    """Paneli açar: bu ayın planı (kart ekstresi + gelir → birikim → hedefe göre portföy) ve
    Birikimlerim sayfası. Eski ayrıntılı panel için --ayrintili."""
    import subprocess
    import sys
    yol = Path(__file__).with_name("panel.py" if ayrintili else "uygulama.py")
    port = ("--server.port", os.environ["KUMBARA_PORT"]) if os.environ.get("KUMBARA_PORT") else ()
    raise typer.Exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(yol),
                                      *STREAMLIT_GIZLILIK, *port]))


if __name__ == "__main__":
    app()
