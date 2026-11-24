"""PyInstaller giriş noktası (kumbara.exe / kumbara.app)."""
import multiprocessing

from kumbara.masaustu import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
