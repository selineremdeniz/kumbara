# kumbara

An open-source personal finance assistant that runs on your own computer. Upload last month's credit card statement, enter this month's income, and kumbara shows how much you can save this month and how to invest it for each of your goals.

- **Monthly plan:** Reads card statements (PDF, JPG or PNG screenshots) and uses the total printed by the bank. It then computes this month's investable savings and savings rate, and splits that amount across your goals as a shopping list.
- **My savings:** Enter funds, shares, physical gold (grams, coins, 22k bracelets including *ajda*), foreign currency and cash by quantity. Holdings are valued at live prices. Linking a holding to a goal makes it count as that goal's current savings.
- **Goal-based portfolios:** Goals are split into short (≤1 year), medium (1–3 years) and long (>3 years) horizons. Each horizon × risk profile has a model allocation across money market, bonds, global bonds, gold, domestic and international equities. The panel uses the allocation's expected return to work out how much of what is left to each goal returns should cover and how much you need to invest. The CLI can also run a Monte Carlo simulation for a target probability.
- **Countries and languages:** Turkey, United States, Germany/Euro area and United Kingdom. The country you select sets the currency, inflation assumption, local instruments and the panel language: Turkish, English or German. Portfolio rules are the same in every country.
- **Live data (Turkey):** CBRT exchange rates, policy rate and CPI; gold, BIST and TEFAS fund prices; KAP disclosures.

> ⚠️ **Not investment advice.** The allocations are educational examples based on general assumptions. In Turkey, investment advice requires a CMB (SPK) licence. Make decisions with a licensed adviser.

## Download the app (no installation)

Get the latest version from the [Releases page](https://github.com/selineremdeniz/kumbara/releases/latest):

- **Windows:** download `kumbara-windows.zip`, unzip it, open the `kumbara` folder and double-click `kumbara.exe`.
- **macOS (Apple Silicon, M1 or newer):** download `kumbara-macos-apple-silicon.zip`, unzip it, open the `kumbara` folder and double-click `kumbara`.

A small terminal window opens and the panel opens in your browser. Closing that window quits kumbara. Your data is stored in `~/.kumbara/` as usual.

The apps are not signed, so the system warns you the first time:

- **Windows:** SmartScreen shows "Windows protected your PC". Click **More info → Run anyway**.
- **macOS:** the app is not signed, so macOS blocks it and may call it *damaged*. It is not damaged. Remove the block **before unzipping**:
  1. Open **Terminal**, type `xattr -c ` with a space at the end, drag the downloaded zip into the window and press Enter. If the zip contains another zip, do the same for that one.
  2. Unzip it and double-click `kumbara` in the `kumbara` folder.

  If macOS still says *"…is damaged and can't be opened. You should move it to the Trash"*, click **Cancel**. Never click *Move to Trash*: it deletes a file inside the app and kumbara will no longer start. Then run `xattr -cr ` the same way on the `kumbara` folder and try again. If it still won't open, run `codesign --force --deep --sign - ` on the folder too. If you already moved a file to the Trash, delete the folder and unzip it again.

Reading screenshots on Windows needs [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) installed separately. PDF statements work without it, and macOS uses its built-in text recognition.

## Installation (from source)

```bash
git clone https://github.com/selineremdeniz/kumbara && cd kumbara
uv sync --extra panel        # or: pip install -e ".[panel]"
```

To build the desktop app yourself, run `pip install ".[panel]" pyinstaller`, then `cd paketleme && pyinstaller kumbara.spec`. The app is created in `paketleme/dist/kumbara/`. Publishing a GitHub release (or pushing a tag such as `v0.1.0`) builds the Windows and macOS apps on GitHub Actions and attaches them to that release.

## The panel

```bash
uv run kumbara panel
```

Pick your country at the top of the sidebar; the panel switches language with it. There are two pages.

**This month's plan**

1. **Latest card statement:** Upload a PDF, JPG or PNG; add more files if you have more than one card. Uploaded files stay while you switch pages during the session; they are never written to disk. kumbara uses the total printed by the bank ("Dönem Borcu", "Hesap Özeti Borcu", "Dönem İçi Harcamalar", …). If the total is missing, it adds up the parsed transactions. You can correct the figure by hand. The previous statement is assumed to be paid.
2. **This month's income:** Enter net income and expenses not paid by card, such as rent or bank-transfer bills. Pension (BES) payments on the card can count as savings.
3. **How much can I save?** Shows the amount you can invest, your savings rate, and the instalments already due on next month's statements.
4. **Your goals:** For each goal enter the amount in today's money, the target date, priority and risk profile. Add any money set aside outside *My savings*; holdings you included in the goal are added automatically.
5. **Investment split:** For each goal you see:
   - what is left to the goal;
   - the expected annual return of its allocation;
   - how much of the remainder expected returns should cover, and how much you need to invest yourself (in total and per month);
   - this month's share.

   You then get this month's shopping list by asset class with example funds for each class. In Turkey these are the three TEFAS funds with the best one-year return. In the US, UK and Germany they are common low-cost ETFs on NYSE/Nasdaq, the London Stock Exchange or Xetra, shown with live 1-month, 1-year and 3-year price returns.
6. **What I bought this month:** Record your purchases; they are added to *My savings* (on top of the same asset in the same goal) and compared with the suggested amount. A purchase can be undone.

**My savings**

Enter each holding with its quantity:

| Asset | Code | Quantity |
|---|---|---|
| Investment fund (TEFAS) | fund code, e.g. `AFT` | units |
| Share (BIST) | ticker, e.g. `THYAO` | shares |
| Share / ETF abroad (US, London, Frankfurt) | ticker, e.g. `AAPL`, `VOO`; with the exchange for London/Frankfurt: `LSE:VWRL`, `XETR:EUNL` | shares |
| Gold: gram (24k), quarter/half/full/Republic/Ata coins, 22k gold, **22k ajda bracelet**, 18k, 14k, silver | – | grams or pieces |
| Foreign currency | `USD`, `EUR`, … | amount |
| Cash / deposit | optional name | amount |
| Other (pension, foreign ETFs, crypto…) | name | enter a manual total value |

Valuation sources:

- Funds use the TEFAS price; BIST shares use the BIST price, which is about 15 minutes delayed.
- Shares and ETFs abroad use the TradingView price of their exchange (NASDAQ, NYSE, AMEX, LSE, XETR). A ticker without an exchange is looked up, trying the selected country's exchanges first. Their asset class depends on the country: VOO counts as domestic equities for a US investor and as international equities for a Turkish one, and a US bond ETF counts as foreign-currency bonds in Turkey.
- Gold and silver use live prices; 22k, 18k and 14k gold use the gram price × fineness. A jeweller usually pays a few points less.
- Foreign currency uses the CBRT buying rate.

If you select a country other than Turkey, Turkish market prices are converted at the CBRT rate. Cash, manual values and the country's own currency are taken as entered.

The valuation is saved once a day, so you can follow your total savings over time and see gain or loss against cost. Link a holding to a goal and the plan page does two things:

- It uses the holding's live value as that goal's current savings.
- It splits this month's contribution so the current mix moves towards the model allocation, without selling.

Statements are never stored; each plan is computed only from the files you upload. Goals, holdings and settings are stored locally.

Outside Turkey, return and volatility figures are assumptions based on long-run historical averages. The statement reader was written for Turkish bank formats; for other banks you may need to type the total. To add a country:

1. Add an entry to [`ulke.py`](src/kumbara/ulke.py).
2. Add a country → language mapping, and a translation if needed, in [`dil.py`](src/kumbara/dil.py).

## Detailed panel and command line

`uv run kumbara panel --ayrintili` opens the older detailed panel. It adds transaction history, categories, next month's budget and KAP. The command-line commands are in Turkish:

```bash
uv run kumbara ornek                      # load synthetic sample data (remove with: ornek --sil)
uv run kumbara yukle statement.pdf --tur kart        # import a statement into the database
uv run kumbara yukle donem_ici.jpg --hesap "Yapı Kredi Kart"   # current-period screenshot
uv run kumbara analiz                     # monthly income/expense, categories, recurring payments
uv run kumbara gelir ekle Maaş 60000      # recurring income; a raise: --baslangic 2026-12
uv run kumbara sabit ekle Kira 25000 --kategori Kira          # fixed expense
uv run kumbara hedef ekle "Emergency fund" 90000 2027-09-01 --oncelik 1 --risk muhafazakar
uv run kumbara plan --fon                 # next month's budget + portfolio + TEFAS candidates
uv run kumbara varlik ekle altin ajda 20 --hedef "House"      # holdings (also: varlik yukle file.csv)
uv run kumbara varlik liste               # live valuation
uv run kumbara kart                       # card balances and remaining instalments
uv run kumbara piyasa                     # live market summary
uv run kumbara kap THYAO --izle           # follow new KAP disclosures
uv run kumbara parametre guncelle         # estimate returns/volatility from TEFAS history
```

Run `uv run kumbara --help` or `uv run kumbara <command> --help` for every option.

### How statements are read

- **PDF:** Most text-based bank PDFs work. Supported formats:
  - table and line layouts;
  - dates with month names (`12 Ekim 2026`) or without a year (`12.10`);
  - descriptions split over several lines;
  - instalment rows, where the instalment amount is used instead of the total.

  Use the password field (or `--sifre`) for encrypted PDFs. Scanned PDFs cannot be read.
- **Screenshots:** OCR runs locally, so images never leave your computer.
  - macOS uses Apple Vision (`ocrmac`) with no extra setup.
  - Other systems need Tesseract (`apt install tesseract-ocr tesseract-ocr-tur`).
  - The bank's on-screen totals ("Güncel Dönem Borcu", "Dönem İçi Harcamalar Toplamı") are read too. The totals stay correct even when the screenshot shows only part of the list.
- **Card credits are never income:** Payments to the card become "Transfer" and refunds become "İade".
- **Troubleshooting:** `kumbara pdf-tani file.pdf` prints a masked layout (digits → 9, letters → x) that you can safely attach to a bug report.
- **Categories:** Rules are in [`veri/kategoriler.yaml`](src/kumbara/veri/kategoriler.yaml). Corrections you make are learned as rules in `~/.kumbara/kategoriler.yaml`.

### How the numbers are estimated

- **Real terms:** All goal maths uses today's money. Raise your contributions with inflation every year.
- **Return and volatility (Turkey):** `kumbara parametre guncelle` downloads 5 years of TEFAS history for representative funds in each asset class and deflates it by CPI.
  - Funds are picked from every return quantile, not only the best performers.
  - Five-year mean returns are very noisy: for an asset with 30% volatility the standard error is about 13 points. They are therefore blended with long-run priors, weighted by N / (N + 120 months).
  - Volatility and correlations are shrunk less.
  - The money market expectation comes from the current policy rate.

  See [`tahmin.py`](src/kumbara/tahmin.py).
- **Probability of reaching a goal (CLI and detailed panel):** A 4,000-scenario Monte Carlo ([`simulasyon.py`](src/kumbara/simulasyon.py)):
  - Returns are correlated and fat-tailed (Student-t), and the portfolio glides towards the short-term mix as the goal approaches.
  - The required contribution is the one that reaches the goal with your chosen probability.
- **Your own assumptions:** Override the priors in `~/.kumbara/varsayimlar.yaml`:

  ```yaml
  reel_getiri: {bist_hisse: 0.04, altin: 0.02}
  oynaklik: {bist_hisse: 0.35}
  ```

## Data sources

| Data | Source | Key | Note |
|---|---|---|---|
| Daily exchange rates | CBRT `today.xml` | – | Official, once a day |
| Policy rate, CPI | tcmb.gov.tr ([borsapy](https://github.com/saidsurucu/borsapy)) | – | |
| EVDS series | evds3.tcmb.gov.tr | `EVDS_API_KEY` (free) | Optional |
| Spot FX, gold | canlidoviz.com (borsapy) | – | |
| BIST prices | TradingView (borsapy) | – | **~15 min delayed** |
| Company financials | İş Yatırım (borsapy) | – | |
| Investment funds | TEFAS (borsapy) | – | |
| KAP disclosures | kap.org.tr (borsapy) | – | Public pages |

- Real-time BIST data is licensed and paid; free sources are delayed.
- KAP's official data API requires MKK membership. kumbara uses the public pages. Keep polling infrequent (`--aralik` ≥ 60 s) and follow each source's terms of use.
- Many sources are not official APIs. If a site changes, that data comes back empty and the rest keeps working; the panel shows which data could not be fetched.

## Privacy

kumbara has no server, account or cloud storage. Everything runs on your computer.

- **Statements never leave your computer.** Uploaded files go only to the panel running on your machine. They are read in memory or in a temporary folder that is deleted right away, and they are never written to the database. OCR also runs locally (Apple Vision or Tesseract).
- **The panel is reachable only from your computer.** `kumbara panel` binds Streamlit to `127.0.0.1`, so other devices on your network cannot open it. It also turns off Streamlit's usage statistics and hides the "Deploy" button. If you start it yourself with `streamlit run`, pass the same options:

  ```bash
  streamlit run src/kumbara/uygulama.py --server.address 127.0.0.1 --browser.gatherUsageStats false --client.toolbarMode minimal
  ```

- **Your data stays local.** Goals, holdings, purchases, settings and transactions imported with the CLI are stored in `~/.kumbara/` (SQLite). Set `KUMBARA_VERI_DIZINI` to move it.
- **Outbound requests are for market data only.** kumbara fetches prices from TCMB, TEFAS, TradingView and similar sources. To price your holdings it sends their codes (for example `AFT` or `VOO`), but never quantities, amounts or anything from your statements.
- **Never commit statements or the database.** `.gitignore` excludes them by default.

## Development

```bash
uv sync --extra dev
uv run pytest            # offline tests
uv run pytest -m ag      # tests that hit live data sources
uv run ruff check .
python scripts/ornek_veri_uret.py   # regenerate sample statements
```

Contributions are especially welcome for bank-specific statement profiles, category rules, new countries and translations, and new data sources. The code and identifiers are in Turkish.

## License

MIT
