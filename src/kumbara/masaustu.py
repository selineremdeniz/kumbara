"""Masaüstü başlatıcı: çift tıklanan kumbara.exe / kumbara.app bunu çalıştırır.

Paneli yalnızca bu bilgisayardan erişilebilir şekilde açar ve tarayıcıda gösterir. Pencereyi
(Windows'ta siyah konsol penceresini) kapatmak uygulamayı kapatır.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def bos_port(baslangic: int = 8501) -> int:
    """8501'den başlayarak bu bilgisayarda boş olan ilk port."""
    for port in range(baslangic, baslangic + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return baslangic


def tarayicida_ac(port: int, bekle: float = 120.0) -> None:
    """Sunucu yanıt vermeye başlayınca paneli varsayılan tarayıcıda açar."""
    son = time.monotonic() + bekle
    while time.monotonic() < son:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                if os.environ.get("BROWSER") != "none":
                    webbrowser.open(f"http://127.0.0.1:{port}")
                return
        time.sleep(0.5)


def main() -> None:
    from streamlit.web import cli as stcli

    from kumbara.cli import STREAMLIT_GIZLILIK
    uygulama = Path(__file__).with_name("uygulama.py")
    print("kumbara açılıyor… Tarayıcınızda kendiliğinden açılacak.")
    print("Kapatmak için bu pencereyi kapatın. / Close this window to quit.\n")
    port = bos_port()
    print(f"Adres / Address: http://127.0.0.1:{port}\n")
    threading.Thread(target=tarayicida_ac, args=(port,), daemon=True).start()
    # headless: Streamlit ilk açılışta e-posta sormasın; tarayıcıyı biz açıyoruz
    sys.argv = ["streamlit", "run", str(uygulama), *STREAMLIT_GIZLILIK,
                "--server.port", str(port), "--server.headless", "true",
                "--global.developmentMode", "false", "--server.fileWatcherType", "none"]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
