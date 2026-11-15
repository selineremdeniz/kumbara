"""Yerel SQLite deposu. Tüm kişisel veriler bilgisayarınızda kalır (varsayılan: ~/.kumbara)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import date
from pathlib import Path

import pandas as pd

from .butce import SabitGider
from .gelir import SabitGelir
from .portfoy import Hedef
from .varlik import Varlik

_YEREL = threading.local()


def yerel_depo() -> Depo:
    """Bu iş parçacığına ait Depo. Streamlit her yeniden çalıştırmayı ayrı bir iş parçacığında
    yapar; tek bağlantıyı paylaşmak eşzamanlı sorgularda sonuçları bozar."""
    yol = veri_dizini() / "kumbara.db"
    d = getattr(_YEREL, "depo", None)
    if d is None or d.yol != yol:
        d = _YEREL.depo = Depo(yol)
    return d


def veri_dizini() -> Path:
    dizin = Path(os.environ.get("KUMBARA_VERI_DIZINI", Path.home() / ".kumbara")).expanduser()
    dizin.mkdir(parents=True, exist_ok=True)
    return dizin


ORNEK_HESAPLAR = ("Örnek Vadesiz", "Örnek Kart")
ORNEK_HEDEFLER = (("Acil durum fonu", 90_000), ("Araba peşinatı", 400_000),
                  ("Ev / emeklilik", 3_000_000))
ORNEK_KIRA = ("Kira", 25_000)

_SEMA = """
CREATE TABLE IF NOT EXISTS islemler (
    islem_id TEXT PRIMARY KEY, tarih TEXT NOT NULL, aciklama TEXT, tutar REAL NOT NULL,
    hesap TEXT, kaynak TEXT, taksit_no INTEGER, taksit_toplam INTEGER,
    kategori TEXT, elle INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_islem_tarih ON islemler(tarih);
CREATE TABLE IF NOT EXISTS hedefler (
    ad TEXT PRIMARY KEY, tutar REAL NOT NULL, tarih TEXT NOT NULL, mevcut REAL DEFAULT 0,
    oncelik INTEGER DEFAULT 2, risk TEXT DEFAULT 'dengeli'
);
CREATE TABLE IF NOT EXISTS sabit_giderler (
    ad TEXT PRIMARY KEY, tutar REAL NOT NULL, kategori TEXT, bitis TEXT
);
CREATE TABLE IF NOT EXISTS kart_ozetleri (
    hesap TEXT NOT NULL, tarih TEXT NOT NULL, toplam REAL NOT NULL, taksit REAL,
    taksit_dahil INTEGER DEFAULT 0, kesim TEXT, PRIMARY KEY (hesap, tarih)
);
CREATE TABLE IF NOT EXISTS gelirler (
    ad TEXT NOT NULL, tutar REAL NOT NULL, baslangic TEXT NOT NULL DEFAULT '', bitis TEXT,
    hesap TEXT, PRIMARY KEY (ad, baslangic)
);
CREATE TABLE IF NOT EXISTS varliklar (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tur TEXT NOT NULL, kod TEXT NOT NULL,
    miktar REAL NOT NULL, maliyet REAL, kurum TEXT, hedef TEXT, deger_elle REAL
);
CREATE TABLE IF NOT EXISTS varlik_gecmisi (
    tarih TEXT PRIMARY KEY, toplam REAL NOT NULL, maliyet REAL, detay TEXT
);
CREATE TABLE IF NOT EXISTS piyasa_gecmisi (zaman TEXT PRIMARY KEY, veri TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alimlar (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tarih TEXT NOT NULL, tur TEXT NOT NULL, kod TEXT NOT NULL,
    miktar REAL NOT NULL, tutar REAL NOT NULL, hedef TEXT, varlik_id INTEGER
);
"""


class Depo:
    def __init__(self, yol: Path | None = None):
        self.yol = Path(yol) if yol else veri_dizini() / "kumbara.db"
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        # Bağlantı yalnızca oluşturulduğu iş parçacığında kullanılabilir (SQLite koruması açık).
        # Çok iş parçacıklı ortamlarda (Streamlit) yerel_depo() kullanın.
        self.bag = sqlite3.connect(self.yol, timeout=10)
        self.bag.executescript(_SEMA)
        kolonlar = {r[1] for r in self.bag.execute("PRAGMA table_info(islemler)")}
        if "kaynak_turu" not in kolonlar:  # eski veritabanlarını yükselt
            self.bag.execute("ALTER TABLE islemler ADD COLUMN kaynak_turu TEXT")
        if "donem_ici" not in kolonlar:
            self.bag.execute("ALTER TABLE islemler ADD COLUMN donem_ici INTEGER DEFAULT 0")
        self.bag.commit()
        self.son_rapor: dict[str, int] = {}

    def kapat(self):
        self.bag.close()

    # --- işlemler ---
    def islem_ekle(self, df: pd.DataFrame) -> int:
        """Yeni işlemleri ekler; aynı islem_id zaten varsa atlar. Eklenen satır sayısını döndürür.

        Kart işlemlerinde dönem içi (henüz ekstreye girmemiş) kayıtlar eşleştirilir
        (aynı tutar, en çok 3 gün tarih farkı, mümkünse aynı hesap):
          - ekstre satırı gelince eşleşen dönem içi kaydın yerini alır (kesinleşir);
          - yeni dönem içi kaydı zaten ekstrede varsa eklenmez;
          - daha yeni bir dönem içi görüntüsü eskisindeki eşleşen kaydı günceller.
        Elle verilen kategoriler korunur. Ayrıntı: self.son_rapor
        """
        df = df.copy()
        if "donem_ici" not in df.columns:
            df["donem_ici"] = False
        rapor = {"eklenen": 0, "kesinlesen": 0, "zaten_ekstrede": 0, "guncellenen": 0}
        silinecek, atlanacak, tasinan = [], set(), {}
        mevcut = self.islemler()
        kart = mevcut[mevcut["kaynak_turu"] == "kart"] if len(mevcut) else mevcut
        if len(kart) and (df["kaynak_turu"] == "kart").any():
            kart = kart.assign(_t=pd.to_datetime(kart["tarih"]))
            kart_hesaplari = set(kart["hesap"])
            kullanilan: set[str] = set()

            def eslesen(r, donem_ici: bool) -> pd.Series | None:
                aday = kart[(kart["donem_ici"] == donem_ici) & (kart["kaynak"] != r.kaynak)
                            & ~kart["islem_id"].isin(kullanilan)
                            & ((kart["tutar"] - r.tutar).abs() < 0.01)
                            & ((kart["_t"] - pd.Timestamp(r.tarih)).abs() <= pd.Timedelta(days=3))]
                if r.hesap in kart_hesaplari:
                    aday = aday[aday["hesap"] == r.hesap]
                if aday.empty:
                    return None
                secilen = aday.iloc[(aday["_t"] - pd.Timestamp(r.tarih)).abs().argmin()]
                kullanilan.add(secilen["islem_id"])
                return secilen

            for r in df[df["kaynak_turu"] == "kart"].itertuples(index=False):
                if not r.donem_ici:
                    m = eslesen(r, True)
                    if m is not None:
                        silinecek.append(m["islem_id"])
                        rapor["kesinlesen"] += 1
                        if m["elle"]:
                            tasinan[r.islem_id] = m["kategori"]
                    continue
                if eslesen(r, False) is not None:
                    atlanacak.add(r.islem_id)
                    rapor["zaten_ekstrede"] += 1
                    continue
                m = eslesen(r, True)
                if m is not None:
                    silinecek.append(m["islem_id"])
                    rapor["guncellenen"] += 1
                    if m["elle"]:
                        tasinan[r.islem_id] = m["kategori"]
        silinecek += self._donem_ici_devral(df, mevcut, rapor, set(silinecek))
        if silinecek:
            self.bag.executemany("DELETE FROM islemler WHERE islem_id = ?",
                                 [(i,) for i in set(silinecek)])
        once = self.bag.total_changes
        kayitlar = [
            (r.islem_id, str(r.tarih), r.aciklama, float(r.tutar), r.hesap, r.kaynak,
             None if pd.isna(r.taksit_no) else int(r.taksit_no),
             None if pd.isna(r.taksit_toplam) else int(r.taksit_toplam),
             getattr(r, "kategori", None), getattr(r, "kaynak_turu", None), int(bool(r.donem_ici)))
            for r in df.itertuples(index=False) if r.islem_id not in atlanacak
        ]
        self.bag.executemany(
            "INSERT OR IGNORE INTO islemler (islem_id, tarih, aciklama, tutar, hesap, kaynak, "
            "taksit_no, taksit_toplam, kategori, kaynak_turu, donem_ici) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)", kayitlar)
        rapor["eklenen"] = self.bag.total_changes - once
        if tasinan:
            self.bag.executemany("UPDATE islemler SET kategori = ?, elle = 1 WHERE islem_id = ?",
                                 [(k, i) for i, k in tasinan.items()])
        self.bag.commit()
        ozet = df.attrs.get("ekran_ozeti") or {}
        if ozet.get("toplam") and len(df) and df["donem_ici"].any():
            hesap = df["hesap"].iat[0]
            tarih = df.attrs.get("ekran_tarihi") or max(df["tarih"])
            self.bag.execute("INSERT OR REPLACE INTO kart_ozetleri VALUES (?,?,?,?,?,?)",
                             (hesap, str(tarih), ozet["toplam"], ozet.get("donem_taksit"),
                              int(bool(ozet.get("taksit_dahil"))),
                              str(ozet["kesim"]) if ozet.get("kesim") else None))
            self.bag.commit()
            rapor["banka_toplami"] = ozet["toplam"]
        for hesap in set(df.loc[df["kaynak_turu"] == "kart", "hesap"]):
            self.ekran_kalanini_guncelle(hesap)
        self.son_rapor = rapor
        return rapor["eklenen"]

    def ekran_kalanini_guncelle(self, hesap: str) -> None:
        """Kartın son ekran özeti (banka toplamı) ile görünen dönem içi işlemleri arasındaki farkı
        iki yardımcı satırla tamamlar: 'bu döneme ait taksitler' ve 'ekranda görünmeyen işlemler'.
        Böylece dönem içi giderler bankanın rakamıyla tutar. Ekstre geldiyse (özetten yeni) satırlar
        kaldırılır."""
        import hashlib

        from .gorsel import KALAN_ACIKLAMA, OZET_ACIKLAMA, TAKSIT_ACIKLAMA
        yardimci = (KALAN_ACIKLAMA, TAKSIT_ACIKLAMA)
        self.bag.execute(f"DELETE FROM islemler WHERE hesap = ? AND aciklama IN "
                         f"({','.join('?' * len(yardimci))})", (hesap, *yardimci))
        oz = self.bag.execute("SELECT tarih, toplam, taksit, taksit_dahil FROM kart_ozetleri "
                              "WHERE hesap = ? ORDER BY tarih DESC LIMIT 1", (hesap,)).fetchone()
        if oz is None:
            self.bag.commit()
            return
        tarih, toplam, taksit, taksit_dahil = oz
        df = self.islemler()
        h = df[(df["hesap"] == hesap) & (df["kaynak_turu"] == "kart")]
        kesin = h[~h["donem_ici"]]
        son_ekstre = max(kesin["tarih"]) if len(kesin) else None
        if son_ekstre and str(son_ekstre) >= tarih:  # ekstre özetten yeni: özet geçersiz
            self.bag.commit()
            return
        di = h[h["donem_ici"] & ~h["aciklama"].isin((*yardimci, OZET_ACIKLAMA))
               & (h["kategori"].fillna("") != "Transfer")]
        if son_ekstre:
            di = di[di["tarih"] > son_ekstre]
        harcama = float(-di.loc[di["tutar"] < 0, "tutar"].sum())
        iade = float(di.loc[di["tutar"] > 0, "tutar"].sum())
        satirlar = []
        taksit_satiri = 0.0
        if taksit_dahil and taksit:
            gorunen_taksit = float(-di.loc[(di["tutar"] < 0) & di["taksit_toplam"].notna(),
                                           "tutar"].sum())
            taksit_satiri = max(0.0, taksit - gorunen_taksit)
            satirlar.append((TAKSIT_ACIKLAMA, taksit_satiri, "Taksitler"))
        kalan = toplam - (harcama - iade) - taksit_satiri
        if kalan > 1:
            satirlar.append((KALAN_ACIKLAMA, kalan, "Diğer"))
        for aciklama, tutar, kategori in satirlar:
            if tutar <= 1:
                continue
            kimlik = hashlib.sha1(f"ekran|{hesap}|{aciklama}".encode()).hexdigest()[:16]
            self.bag.execute(
                "INSERT OR REPLACE INTO islemler (islem_id, tarih, aciklama, tutar, hesap, kaynak, "
                "kategori, kaynak_turu, donem_ici) VALUES (?,?,?,?,?,?,?,?,1)",
                (kimlik, tarih, aciklama, -round(tutar, 2), hesap, "banka ekran özeti", kategori,
                 "kart"))
        self.bag.commit()

    def _donem_ici_devral(self, df: pd.DataFrame, mevcut: pd.DataFrame, rapor: dict,
                          zaten: set[str]) -> list[str]:
        """Eşleştirmeden bağımsız, kart bazında devralma kuralları:
        - Ekstre, o kartın ekstrenin son tarihine kadarki TÜM dönem içi kayıtlarının yerini alır
          (OCR bir tutarı yanlış okusa bile çift sayım olmaz).
        - Özet satırı (dönem içi toplamı) o kartın önceki dönem içi kayıtlarının yerini alır;
          ayrıntılı dönem içi kayıtları gelince de özet satırı silinir.
        """
        from .gorsel import OZET_ACIKLAMA
        if mevcut.empty or "donem_ici" not in mevcut:
            return []
        di = mevcut[(mevcut["kaynak_turu"] == "kart") & mevcut["donem_ici"]]
        sil: list[str] = []

        def ekle(idler, anahtar):
            yeni = [i for i in idler if i not in zaten and i not in sil]
            rapor[anahtar] += len(yeni)
            sil.extend(yeni)

        kart = df[df["kaynak_turu"] == "kart"]
        for hesap, g in kart.groupby("hesap"):
            eski = di[(di["hesap"] == hesap) & ~di["kaynak"].isin(set(g["kaynak"]))]
            if eski.empty:
                continue
            kesin = g[~g["donem_ici"].astype(bool)]
            if len(kesin):
                son = max(kesin["tarih"])
                ekle(eski.loc[eski["tarih"] <= son, "islem_id"], "kesinlesen")
            yeni_di = g[g["donem_ici"].astype(bool)]
            if len(yeni_di):
                if (yeni_di["aciklama"] == OZET_ACIKLAMA).any():
                    ekle(eski["islem_id"], "guncellenen")
                else:
                    ekle(eski.loc[eski["aciklama"] == OZET_ACIKLAMA, "islem_id"], "guncellenen")
        return sil

    def islemler(self) -> pd.DataFrame:
        df = pd.read_sql_query("SELECT * FROM islemler ORDER BY tarih", self.bag)
        df["tarih"] = pd.to_datetime(df["tarih"]).dt.date
        df["donem_ici"] = df["donem_ici"].fillna(0).astype(bool)
        df["elle"] = df["elle"].fillna(0).astype(int)
        for k in ("taksit_no", "taksit_toplam"):
            df[k] = df[k].astype("Int64")
        return df

    def kategori_ata(self, islem_id: str, kategori: str) -> None:
        self.bag.execute("UPDATE islemler SET kategori=?, elle=1 WHERE islem_id=?",
                         (kategori, islem_id))
        self.bag.commit()

    def kategorileri_guncelle(self, df: pd.DataFrame) -> None:
        """Elle atanmamış işlemlerin kategorilerini yazar."""
        self.bag.executemany("UPDATE islemler SET kategori=? WHERE islem_id=? AND elle=0",
                             list(zip(df["kategori"], df["islem_id"], strict=True)))
        self.bag.commit()

    def ornek_sil(self) -> dict[str, int]:
        """`kumbara ornek` ile eklenen sentetik işlemleri, hedefleri ve kirayı siler.

        Hedef ve sabit gider yalnızca adı VE tutarı örnektekiyle birebir aynıysa silinir;
        kendi eklediğiniz kayıtlara dokunulmaz.
        """
        sayi = {}
        c = self.bag.execute("DELETE FROM islemler WHERE hesap IN (?, ?)", ORNEK_HESAPLAR)
        sayi["islem"] = c.rowcount
        c = self.bag.execute(
            "DELETE FROM hedefler WHERE (ad, tutar) IN (VALUES (?, ?), (?, ?), (?, ?))",
            [x for h in ORNEK_HEDEFLER for x in h])
        sayi["hedef"] = c.rowcount
        c = self.bag.execute("DELETE FROM sabit_giderler WHERE ad = ? AND tutar = ?", ORNEK_KIRA)
        sayi["sabit"] = c.rowcount
        self.bag.commit()
        return sayi

    def islemleri_sil(self, kaynak: str | None = None, hesap: str | None = None) -> int:
        """Tüm işlemleri, bir dosyadan gelenleri ya da bir dosyanın belirli hesap adıyla
        yüklenmiş kopyasını siler; hedefler ve sabit giderler kalır."""
        if kaynak and hesap:
            c = self.bag.execute("DELETE FROM islemler WHERE kaynak = ? AND hesap = ?",
                                 (kaynak, hesap))
        elif kaynak:
            c = self.bag.execute("DELETE FROM islemler WHERE kaynak = ?", (kaynak,))
        else:
            c = self.bag.execute("DELETE FROM islemler")
        self.bag.commit()
        return c.rowcount

    def hesap_degistir(self, kaynak: str, eski: str, yeni: str) -> int:
        """Bir dosyadan gelen işlemleri başka bir hesap adına taşır (ör. görüntü yanlış karta
        kaydedildiyse). Hesap adı islem_id'nin parçası olduğundan kimlikler yeniden üretilir."""
        df = self.islemler()
        tasinacak = df[(df["kaynak"] == kaynak) & (df["hesap"] == eski)]
        if tasinacak.empty or eski == yeni:
            return 0
        from .ekstre import normalize
        yeni_df = normalize(tasinacak.drop(columns=["islem_id"]).assign(hesap=yeni))
        yeni_df["kategori"] = tasinacak["kategori"].values
        elle = dict(zip(yeni_df["islem_id"], tasinacak["elle"].values, strict=True))
        self.islemleri_sil(kaynak, eski)
        eklenen = self.islem_ekle(yeni_df)
        self.bag.executemany("UPDATE islemler SET elle = ? WHERE islem_id = ?",
                             [(int(e), i) for i, e in elle.items() if e])
        self.bag.commit()
        return eklenen

    def kopya_kaynaklar(self) -> dict[str, list[str]]:
        """Aynı dosya adının birden çok hesap adıyla yüklendiği durumlar (olası çift sayım)."""
        kopyalar: dict[str, list[str]] = {}
        for kaynak, hesap, _ in self.kaynaklar():
            kopyalar.setdefault(kaynak, []).append(hesap)
        return {k: h for k, h in kopyalar.items() if len(h) > 1}

    def donem_ici_tarihlerini_duzelt(self) -> list[tuple[str, str, str]]:
        """Eski sürümlerin OCR hatasıyla yanlış tarihlediği dönem içi kayıtları onarır.

        Bir görüntüden gelen kayıt, görüntünün tarihinden (panel dosya adındaki
        -YYYYAAGG-SSDDSS damgası; yoksa dosyadaki en geç tarih) 62 günden eski ya da
        1 günden yeniyse tarihi o güne çekilir. Tutar gerçek olduğu için kayıt silinmez.
        Dönen liste: (kaynak, eski tarih, yeni tarih).
        """
        import re
        from datetime import timedelta

        from .gorsel import PENCERE_GERI
        df = self.islemler()
        if df.empty:
            return []
        di = df[df["donem_ici"] & (df["kaynak_turu"] == "kart")
                & (df["kaynak"] != "banka ekran özeti")]
        duzeltmeler = []
        for kaynak, g in di.groupby("kaynak"):
            m = re.search(r"-(20\d{2})(\d{2})(\d{2})-\d{6}", str(kaynak))
            try:
                ref = date(int(m[1]), int(m[2]), int(m[3])) if m else None
            except ValueError:
                ref = None
            if ref is None:  # damgasız dosya: en geç tarih (bugünden ileri olamaz)
                ref = min(max(g["tarih"]), date.today())
            for r in g.itertuples():
                if not ref - timedelta(days=PENCERE_GERI) <= r.tarih <= ref + timedelta(days=1):
                    duzeltmeler.append((ref.isoformat(), r.islem_id, kaynak, str(r.tarih)))
        if duzeltmeler:
            self.bag.executemany("UPDATE islemler SET tarih = ? WHERE islem_id = ?",
                                 [(d[0], d[1]) for d in duzeltmeler])
            self.bag.commit()
            for hesap in set(di.loc[di["islem_id"].isin([d[1] for d in duzeltmeler]), "hesap"]):
                self.ekran_kalanini_guncelle(hesap)
        return [(k, eski, yeni) for yeni, _, k, eski in duzeltmeler]

    def toplamsiz_kartlar(self) -> list[str]:
        """Dönem içi (görüntü) işlemi olup banka ekran toplamı kayıtlı olmayan kartlar."""
        satirlar = self.bag.execute(
            "SELECT DISTINCT hesap FROM islemler WHERE donem_ici = 1 AND kaynak_turu = 'kart' "
            "AND kaynak != 'banka ekran özeti' AND hesap NOT IN (SELECT hesap FROM kart_ozetleri)"
        ).fetchall()
        return sorted(h for (h,) in satirlar)

    def kaynak_ozeti(self) -> pd.DataFrame:
        """Dosya + hesap başına işlem sayısı, tarih aralığı, dönem içi mi, gider toplamı."""
        return pd.read_sql_query(
            "SELECT kaynak, hesap, COUNT(*) AS adet, MIN(tarih) AS ilk, MAX(tarih) AS son, "
            "MAX(COALESCE(donem_ici, 0)) AS donem_ici, "
            "ROUND(-SUM(CASE WHEN tutar < 0 THEN tutar ELSE 0 END), 2) AS gider "
            "FROM islemler GROUP BY kaynak, hesap ORDER BY MIN(tarih)", self.bag)

    def kaynaklar(self) -> list[tuple[str, str, int]]:
        return self.bag.execute("SELECT kaynak, hesap, COUNT(*) FROM islemler "
                                "GROUP BY kaynak, hesap ORDER BY MIN(tarih)").fetchall()

    def ornek_var_mi(self) -> bool:
        return self.bag.execute("SELECT 1 FROM islemler WHERE hesap IN (?, ?) LIMIT 1",
                                ORNEK_HESAPLAR).fetchone() is not None

    # --- hedefler ---
    def hedef_kaydet(self, h: Hedef) -> None:
        self.bag.execute("INSERT OR REPLACE INTO hedefler VALUES (?,?,?,?,?,?)",
                         (h.ad, h.tutar, h.tarih.isoformat(), h.mevcut, h.oncelik, h.risk))
        self.bag.commit()

    def hedef_sil(self, ad: str) -> None:
        self.bag.execute("DELETE FROM hedefler WHERE ad=?", (ad,))
        self.bag.commit()

    def hedefler(self) -> list[Hedef]:
        satirlar = self.bag.execute("SELECT ad, tutar, tarih, mevcut, oncelik, risk FROM hedefler "
                                    "ORDER BY oncelik, tarih").fetchall()
        return [Hedef(ad=a, tutar=t, tarih=date.fromisoformat(d), mevcut=m, oncelik=o, risk=r)
                for a, t, d, m, o, r in satirlar]

    # --- sabit giderler ---
    def sabit_kaydet(self, s: SabitGider) -> None:
        self.bag.execute("INSERT OR REPLACE INTO sabit_giderler VALUES (?,?,?,?)",
                         (s.ad, s.tutar, s.kategori, s.bitis.isoformat() if s.bitis else None))
        self.bag.commit()

    def sabit_sil(self, ad: str) -> None:
        self.bag.execute("DELETE FROM sabit_giderler WHERE ad=?", (ad,))
        self.bag.commit()

    def sabit_giderler(self) -> list[SabitGider]:
        satirlar = self.bag.execute("SELECT ad, tutar, kategori, bitis FROM sabit_giderler").fetchall()
        return [SabitGider(ad=a, tutar=t, kategori=k, bitis=date.fromisoformat(b) if b else None)
                for a, t, k, b in satirlar]

    # --- düzenli gelirler ---
    def gelir_kaydet(self, g: SabitGelir) -> None:
        self.bag.execute("INSERT OR REPLACE INTO gelirler VALUES (?,?,?,?,?)",
                         (g.ad, g.tutar, g.baslangic.isoformat() if g.baslangic else "",
                          g.bitis.isoformat() if g.bitis else None, g.hesap))
        self.bag.commit()

    def gelirler(self) -> list[SabitGelir]:
        satirlar = self.bag.execute("SELECT ad, tutar, baslangic, bitis, hesap FROM gelirler "
                                    "ORDER BY ad, baslangic").fetchall()
        return [SabitGelir(a, t, date.fromisoformat(b) if b else None,
                           date.fromisoformat(s) if s else None, h) for a, t, b, s, h in satirlar]

    def gelir_sil(self, ad: str, baslangic: date | None = None) -> int:
        if baslangic is None:
            c = self.bag.execute("DELETE FROM gelirler WHERE ad = ?", (ad,))
        else:
            c = self.bag.execute("DELETE FROM gelirler WHERE ad = ? AND baslangic = ?",
                                 (ad, baslangic.isoformat()))
        self.bag.commit()
        return c.rowcount

    # --- varlıklar ---
    def varlik_kaydet(self, v: Varlik) -> int:
        alanlar = (v.tur, v.kod, v.miktar, v.maliyet, v.kurum, v.hedef, v.deger_elle)
        if v.id is None:
            c = self.bag.execute("INSERT INTO varliklar (tur, kod, miktar, maliyet, kurum, hedef, "
                                 "deger_elle) VALUES (?,?,?,?,?,?,?)", alanlar)
            v.id = c.lastrowid
        else:
            self.bag.execute("UPDATE varliklar SET tur=?, kod=?, miktar=?, maliyet=?, kurum=?, "
                             "hedef=?, deger_elle=? WHERE id=?", (*alanlar, v.id))
        self.bag.commit()
        return v.id

    def varliklar(self) -> list[Varlik]:
        satirlar = self.bag.execute("SELECT id, tur, kod, miktar, maliyet, kurum, hedef, deger_elle "
                                    "FROM varliklar ORDER BY tur, kod").fetchall()
        return [Varlik(tur=t, kod=k, miktar=m, maliyet=ml, kurum=ku, hedef=h, deger_elle=d, id=i)
                for i, t, k, m, ml, ku, h, d in satirlar]

    def varlik_sil(self, varlik_id: int) -> int:
        c = self.bag.execute("DELETE FROM varliklar WHERE id = ?", (varlik_id,))
        self.bag.commit()
        return c.rowcount

    def alim_ekle(self, alim: Varlik, tutar: float, tarih: date | None = None) -> Varlik:
        """Bir alımı kaydeder ve Birikimlerim'e işler (aynı varlık + hedef varsa üstüne eklenir)."""
        from .varlik import alimi_birlestir, alimi_normallestir
        alim = alimi_normallestir(alim, tutar)
        v = alimi_birlestir(self.varliklar(), alim, tutar)
        self.varlik_kaydet(v)
        self.bag.execute("INSERT INTO alimlar (tarih, tur, kod, miktar, tutar, hedef, varlik_id) "
                         "VALUES (?,?,?,?,?,?,?)", ((tarih or date.today()).isoformat(), alim.tur,
                                                    alim.kod, alim.miktar, tutar, alim.hedef, v.id))
        self.bag.commit()
        return v

    def alimlar(self, baslangic: date | None = None) -> pd.DataFrame:
        satirlar = self.bag.execute(
            "SELECT id, tarih, tur, kod, miktar, tutar, hedef, varlik_id FROM alimlar WHERE tarih >= ? "
            "ORDER BY tarih, id", ((baslangic or date.min).isoformat(),)).fetchall()
        return pd.DataFrame(satirlar, columns=["id", "tarih", "tur", "kod", "miktar", "tutar", "hedef",
                                               "varlik_id"])

    def alim_sil(self, alim_id: int) -> None:
        """Alımı geri alır: kaydı siler ve Birikimlerim'deki varlıktan miktarını/maliyetini düşer."""
        r = self.bag.execute("SELECT tur, kod, miktar, tutar, varlik_id FROM alimlar WHERE id = ?",
                             (alim_id,)).fetchone()
        if r is None:
            return
        tur, _, miktar, tutar, vid = r
        v = next((x for x in self.varliklar() if x.id == vid), None)
        if v is not None:
            if tur == "diger":
                v.deger_elle = max(0.0, (v.deger_elle or 0) - tutar)
            else:
                v.miktar = max(0.0, v.miktar - miktar)
            if v.maliyet is not None:
                v.maliyet = max(0.0, v.maliyet - tutar) or None
            if v.miktar <= 1e-9 or (tur == "diger" and not v.deger_elle):
                self.varlik_sil(v.id)
            else:
                self.varlik_kaydet(v)
        self.bag.execute("DELETE FROM alimlar WHERE id = ?", (alim_id,))
        self.bag.commit()

    def varlik_degeri_kaydet(self, tarih: str, ozet: dict) -> None:
        """Günlük değerleme kaydı (aynı gün tekrar kaydedilirse güncellenir)."""
        self.bag.execute("INSERT OR REPLACE INTO varlik_gecmisi VALUES (?,?,?,?)",
                         (tarih, ozet["toplam"], ozet["maliyet"], json.dumps(ozet, ensure_ascii=False)))
        self.bag.commit()

    def varlik_gecmisi(self) -> pd.DataFrame:
        satirlar = self.bag.execute("SELECT tarih, toplam, maliyet, detay FROM varlik_gecmisi "
                                    "ORDER BY tarih").fetchall()
        df = pd.DataFrame(satirlar, columns=["tarih", "toplam", "maliyet", "detay"])
        df["detay"] = df["detay"].map(lambda x: json.loads(x) if x else {})
        return df

    # --- piyasa ---
    def piyasa_kaydet(self, ozet: dict) -> None:
        self.bag.execute("INSERT OR REPLACE INTO piyasa_gecmisi VALUES (?,?)",
                         (ozet["zaman"], json.dumps(ozet, ensure_ascii=False)))
        self.bag.commit()

    def piyasa_gecmisi(self) -> pd.DataFrame:
        satirlar = self.bag.execute("SELECT veri FROM piyasa_gecmisi ORDER BY zaman").fetchall()
        return pd.DataFrame([json.loads(v) for (v,) in satirlar])
