# PyInstaller tanımı: Windows'ta kumbara.exe, macOS/Linux'ta kumbara (çift tıklanır).
#   pip install ".[panel]" pyinstaller && cd paketleme && pyinstaller kumbara.spec
# Çıktı: dist/kumbara/ klasörü. Program bir terminal penceresinde açılır; pencereyi kapatmak
# uygulamayı kapatır (macOS'ta da bu yüzden .app yerine klasör dağıtılır).
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

datas, binaries, hiddenimports = [], [], []
# Streamlit arayüz dosyaları ve sürüm bilgisi; borsapy/plotly'nin veri dosyaları
for paket in ("streamlit", "plotly", "borsapy", "pdfplumber", "pdfminer"):
    d, b, h = collect_all(paket)
    datas += d
    binaries += b
    hiddenimports += h
for paket in ("streamlit", "pandas", "numpy", "plotly", "pyarrow", "altair", "kumbara"):
    try:
        datas += copy_metadata(paket)
    except Exception:  # paket kurulu değilse ya da metadata yoksa
        pass
# Streamlit sayfaları .py dosyası olarak çalıştırır: kumbara kaynakları da kopyalanır
datas += collect_data_files("kumbara", include_py_files=True)
hiddenimports += collect_submodules("kumbara") + ["pytesseract", "PIL", "yaml", "httpx",
                                                  "websocket", "openpyxl"]
if sys.platform == "darwin":  # ekran görüntüleri için Apple Vision (ocrmac + pyobjc)
    for paket in ("ocrmac", "objc", "Foundation", "Quartz", "Vision", "CoreML"):
        try:
            hiddenimports += collect_submodules(paket)
        except Exception:
            pass

a = Analysis(["baslat.py"], pathex=[], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=["tkinter", "matplotlib", "IPython", "pytest"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="kumbara", console=True,
          icon=None, upx=False)
klasor = COLLECT(exe, a.binaries, a.datas, name="kumbara", upx=False)
