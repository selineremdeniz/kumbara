"""Panel metinleri (Türkçe / English / Deutsch). Dil, seçilen ülkeden gelir.

Yeni dil eklemek: METINLER'e aynı anahtarlarla bir sözlük ve ULKE_DILI'ne ülke eşlemesi ekleyin.
Eksik anahtar Türkçeye düşer (test: tests/test_dil.py tüm anahtarların her dilde olduğunu denetler).
"""

from __future__ import annotations

ULKE_DILI = {"TR": "tr", "US": "en", "GB": "en", "DE": "de"}

METINLER: dict[str, dict[str, str]] = {
    "tr": {
        # gezinme / kenar çubuğu
        "veri_aliniyor": "Piyasa verisi alınıyor…", "kaynak_diger": "uzun vadeli tarihsel ortalamalar",
        "degerleniyor": "Birikimler canlı fiyatla değerleniyor…",
        "bk_eski": "Canlı fiyatı alınamayıp son bilinen fiyatla değerlenenler: {x}",
        "c_birim": "Birim fiyat", "c_deger": "Değer", "c_kar": "Kâr / zarar", "c_sinif": "Sınıf",
        "bk_maliyet_yardim": "Toplam alış maliyeti; kâr/zararı göstermek için (isteğe bağlı).",
        "bk_maliyet_toplam": "Toplam maliyet: {x}",
        "yuklu": "Yüklenen ekstreler", "kaldir": "Kaldır",
        "fonlar_baslik": "Bu ay alabileceğiniz fonlar (TEFAS)",
        "fonlar_aciklama": "Her varlık sınıfında son 1 yılda en çok getiren 3 fon. Geçmiş getiri "
                           "geleceği göstermez; masraf oranına ve fon büyüklüğüne de bakın.",
        "fonlar_yok": "TEFAS fon listesi şu an alınamadı.", "c_fon": "Fon", "c_kod": "Kod",
        "c_1a": "1 ay", "c_1y": "1 yıl", "c_3y": "3 yıl", "ornek_arac": "Örnek araçlar",
        "alim_baslik": "Bu ay aldıklarım",
        "alim_aciklama": "Bu ay aldığınız fon, altın, döviz vb.'yi yazın; Birikimlerim'e eklenir "
                         "(aynı varlık aynı hedefte varsa üstüne eklenir).",
        "alim_tutar": "Ödenen tutar ({s})", "alim_ekle": "Birikimlerime ekle",
        "alim_eklendi": "Birikimlerinize eklendi: {x}", "alim_liste": "Bu ay eklenen alımlar",
        "alim_toplam": "Bu ay yatırdığınız: {x} · önerilen: {y}", "alim_sil": "Seçili alımı geri al",
        "alim_eksik": "Miktar ya da tutar girin.", "c_tarih_alim": "Tarih",
        "sayfa_plan": "Bu ayın planı", "sayfa_birikim": "Birikimlerim",
        "ayarlar": "Ayarlar", "ulke": "Ülke", "canli_tcmb": "Canlı TCMB verisi",
        "enflasyon": "Yıllık enflasyon varsayımı (%)",
        "not_tr": "Canlı TCMB politika faizi/TÜFE ve (varsa) TEFAS geçmişinden tahmin kullanılır.",
        "not_diger": "Getiri ve oynaklık: uzun vadeli tarihsel ortalamalara dayanan varsayımlar.",
        "ayrintili": "Ayrıntılı panel (işlem geçmişi, KAP): `kumbara panel --ayrintili`",
        "uyari": "Bu araç yatırım danışmanlığı değildir. Dağılımlar genel varsayımlara dayanan, "
                 "eğitim amaçlı örneklerdir; kararlarınızı lisanslı bir danışmanla verin.",
        # plan sayfası
        "plan_baslik": "kumbara · bu ayın planı",
        "plan_aciklama": "Son kart ekstrenizi yükleyin, bu ayki gelirinizi yazın: bu ay ne kadar "
                         "birikim yapabileceğinizi ve hedeflerinize göre nasıl yatırım "
                         "yapabileceğinizi görün. Ekstreler diske kaydedilmez; bu oturum boyunca hatırlanır.",
        "adim1": "1 · Son kart ekstresi",
        "yukle": "PDF, JPG veya PNG (birden çok kart için birden çok dosya)",
        "sifre": "PDF şifresi (varsa)", "okunuyor": "{ad} okunuyor…",
        "c_dosya": "Dosya", "c_kart": "Kart", "c_islem": "İşlem",
        "c_banka": "Bankanın toplamı", "c_okunan": "Okunan işlemler", "c_bes": "BES / birikim",
        "c_taksit": "Sıradaki taksitler",
        "u_fark": "okunan işlemlerin toplamı bankanın toplamından farklı; bankanın toplamı "
                  "kullanıldı.",
        "u_fark_gorsel": "görüntüde listenin hepsi görünmüyor; bankanın toplamı kullanıldı.",
        "u_toplam_yok": "bankanın toplamı bulunamadı; okunan işlemler kullanıldı. Rakamı "
                        "kontrol edin.",
        "kategori_dokumu": "Kategori dökümü (okunan işlemler)",
        "kart_harcama": "Bu ayın kart harcaması ({s}) — gerekirse düzeltin",
        "kart_harcama_yardim": "Ekstrelerde bankanın yazdığı toplam (yoksa okunan işlemler). "
                               "Önceki ekstre ödendi varsayılır.",
        "adim2": "2 · Bu ayki geliriniz", "gelir": "Net gelir ({s})",
        "kart_disi": "Kart dışı giderler ({s}) — kira, havaleyle ödenen faturalar, nakit…",
        "bes_say": "Kart ekstresindeki {x} BES/birikim ödemesini birikim say",
        "adim3": "3 · Bu ay ne kadar birikim yapabilirim?", "gelir_girin": "Gelirinizi girin.",
        "yatirilabilir": "Yatırıma ayırabileceğiniz", "oran": "Birikim oranı",
        "toplam_birikim": "Toplam birikim", "bes_dahil": " (BES dahil)",
        "formul": "{g} gelir − {k} kart harcaması − {d} kart dışı gider",
        "bes_gitti": "; BES ({x}) zaten birikime gitti.",
        "taksit_bilgi": "Gelecek ay ekstrelerinize şimdiden {x} taksit girecek; sonraki aylara "
                        "{y} kalıyor.",
        "acik": "Bu ay giderler geliri aşıyor ya da eşit; yatırıma ayrılacak tutar yok.",
        "adim4": "4 · Hedefleriniz", "c_hedef": "Hedef", "c_tutar": "Tutar ({s}, bugünün parasıyla)",
        "c_tarih": "Hedef tarihi", "c_mevcut": "Şu an ayrılmış", "c_oncelik": "Öncelik",
        "c_mevcut_elle": "Ayrıca ayrılmış (Birikimlerim dışında)",
        "c_risk": "Risk", "hedef_kaydet": "Hedefleri kaydet",
        "hedef_ekle": "Bir hedef ekleyin (ör. Acil durum fonu, Ev peşinatı) ve kaydedin.",
        "mevcut_varliktan": "'Birikimlerim'de bu hedefe dahil ettiğiniz varlıkların güncel değeri, "
                            "'ayrıca ayrılmış' tutara eklenir. Aynı parayı iki yere yazmayın.",
        "adim5": "5 · Hedeflerinize göre bu ayki yatırım dağılımı",
        "kaynak_notu": "{ulke} · getiri varsayımı: {kaynak}. Hedefe kalan tutarın bir kısmını "
                       "beklenen getiri karşılar; kalanını sizin yatırmanız gerekir. Tutarlar bugünün "
                       "parasıyla (enflasyon üstü); katkıları her yıl enflasyon kadar (~%{e}) artırın. "
                       "Getiri garanti değildir: düşük gelirse daha fazla yatırmanız gerekir.",
        "c_vade": "Vade", "c_kalan_ay": "Kalan ay", "c_kalan": "Hedefe kalan",
        "c_getiri": "Beklenen yıllık getiri", "getiri_bicim": "%{n} (enflasyon üstü %{r})",
        "c_getiriden": "Getiriden beklenen", "c_yatirilacak": "Yatırmanız gereken (toplam)",
        "c_aylik": "Aylık yatırmanız gereken", "c_ayrilan": "Bu ay ayrılan",
        "c_varlik": "Varlık", "c_oran": "Oran",
        "c_bu_ay": "Bu ay", "alim_listesi": "Bu ay toplam alım listesi",
        "w_kapasite": "bu ayki birikim gereken aylık katkıya yetmiyor (karşılanan: %{p}); tarihi "
                      "uzatmayı ya da tutarı düşürmeyi düşünün.",
        "w_kisa_agresif": "kısa vadeli hedefte yüksek risk: hedef tarihte değer düşük olabilir.",
        "w_3ay": "hedefe 3 aydan az kaldı; birikimi likit tutun.",
        "w_disarida": "bu hedefe bağlı {x} bu vadenin dağılımında yok; yeni katkı bunlara "
                      "yönlendirilmiyor.",
        "bagli": "Bu hedefe bağlı birikimleriniz: {x}. Bu ayki katkı, mevcut dağılımı modele "
                 "yaklaştıracak şekilde bölündü.",
        "b_donem_ici": "Dönem içi harcamalar", "b_hesap_ozeti": "Hesap özeti borcu",
        "b_donem_borcu": "Dönem borcu", "b_toplam_borc": "Toplam borç",
        "b_guncel": "Güncel dönem borcu", "b_donem_ici_toplam": "Dönem içi harcamalar toplamı",
        "vade_kısa": "kısa", "vade_orta": "orta", "vade_uzun": "uzun",
        "risk_muhafazakar": "muhafazakâr", "risk_dengeli": "dengeli", "risk_agresif": "agresif",
        "hata": "{ad} okunamadı: {e}",
        # birikimler sayfası
        "bk_baslik": "Birikimlerim",
        "bk_aciklama": "Yatırım hesaplarınızdaki fon ve hisseleri, altınınızı, dövizinizi ve "
                       "nakdinizi adet/gram olarak girin; güncel değerleri hesaplanır. Bir hedefe "
                       "bağlarsanız plan sayfası o hedefin mevcut birikimini buradan alır.",
        "bk_tur": "Varlık", "bk_kod": "Kod (fon / hisse / döviz)",
        "bk_kod_yardim": "Fon: TEFAS kodu (AFT) · Hisse: BIST sembolü (THYAO) · Yurt dışı hisse/ETF: "
                         "AAPL, VOO; Londra/Frankfurt için borsasıyla: LSE:VWRL, XETR:EUNL · "
                         "Döviz: USD, EUR. Diğerlerinde boş bırakabilirsiniz.",
        "bk_miktar": "Miktar (adet / gram / tutar)", "bk_maliyet": "Toplam maliyet ({s})",
        "bk_yer": "Kurum / yer", "bk_hedef": "Hedefime dahil et",
        "bk_elle": "Elle değer ({s}, toplam)",
        "bk_elle_yardim": "Canlı fiyatı olmayan varlıklar için (BES, yurt dışı hisse, kripto…).",
        "bk_kaydet": "Birikimlerimi kaydet", "bk_yok": "(yok)",
        "bk_bos": "Henüz varlık yok. Tabloya satır ekleyip kaydedin.",
        "bk_toplam": "Toplam birikim", "bk_maliyetli": "Maliyeti girilenler",
        "bk_net": "Hedefe bağlı olmayan", "bk_fiyatsiz": "{n} varlık fiyatlanamadı (kodu "
                                                       "kontrol edin ya da elle değer girin).",
        "bk_sinif": "Varlık sınıfına göre", "bk_seyir": "Toplam birikimin seyri",
        "bk_seyir_bilgi": "Değerleme her gün kaydedilir; ikinci kayıttan sonra grafik görünür.",
        "bk_kur": "Türk piyasası fiyatları TCMB kuruyla {para}'ya çevrildi (1 {para} = {kur} ₺).",
        "bk_kur_yok": "Kur alınamadı; Türk piyasası varlıklarını elle değerle girin.",
        "bk_detay": "Ayrıntı",
        "t_fon": "Yatırım fonu (TEFAS)", "t_hisse": "Hisse (BIST)", "t_doviz": "Döviz",
        "t_yabanci": "Yurt dışı hisse / ETF (ABD, Londra, Frankfurt)",
        "etf_baslik": "Bu ay alabileceğiniz ETF'ler ({borsa})",
        "etf_aciklama": "Her varlık sınıfı için yaygın, düşük maliyetli örnek ETF'ler ve getirileri "
                        "(canlı, fiyat getirisi; temettü hariç). Geçmiş getiri geleceği göstermez; masraf "
                        "oranına da bakın.",
        "etf_yok": "ETF getirileri şu an alınamadı.",
        "t_nakit": "Nakit / mevduat", "t_diger": "Diğer (elle değer)",
        "a_gram": "Gram altın (24 ayar)", "a_ceyrek": "Çeyrek altın (adet)",
        "a_yarim": "Yarım altın (adet)", "a_tam": "Tam altın (adet)",
        "a_cumhuriyet": "Cumhuriyet altını (adet)", "a_ata": "Ata altın (adet)",
        "a_22ayar": "22 ayar altın / bilezik (gram)", "a_ajda": "22 ayar ajda bilezik (gram)",
        "a_18ayar": "18 ayar altın (gram)", "a_14ayar": "14 ayar altın (gram)",
        "a_gumus": "Gram gümüş",
        "s_ppf": "Nakit / mevduat / para piyasası", "s_kisa_borc": "Kısa vadeli borçlanma",
        "s_tl_tahvil": "Tahvil / bono", "s_eurobond": "Döviz tahvil",
        "s_altin": "Altın / gümüş", "s_bist_hisse": "Yerel hisse",
        "s_yabanci_hisse": "Yabancı hisse", "s_doviz": "Döviz (nakit)", "s_diger": "Diğer",
    },
    "en": {
        "veri_aliniyor": "Fetching market data…", "kaynak_diger": "long-run historical averages",
        "degerleniyor": "Valuing your savings at live prices…",
        "bk_eski": "No live price; valued at the last known price: {x}",
        "c_birim": "Unit price", "c_deger": "Value", "c_kar": "Gain / loss", "c_sinif": "Class",
        "bk_maliyet_yardim": "Total purchase cost, to show gain/loss (optional).",
        "bk_maliyet_toplam": "Total cost: {x}",
        "yuklu": "Uploaded statements", "kaldir": "Remove",
        "fonlar_baslik": "Funds you could buy this month (TEFAS)",
        "fonlar_aciklama": "The 3 best-performing funds of the last year in each asset class. Past "
                           "returns don't predict the future; also check fees and fund size.",
        "fonlar_yok": "The TEFAS fund list is unavailable right now.", "c_fon": "Fund",
        "c_kod": "Code", "c_1a": "1 month", "c_1y": "1 year", "c_3y": "3 years",
        "ornek_arac": "Example instruments",
        "alim_baslik": "What I bought this month",
        "alim_aciklama": "Enter the funds, gold, currency etc. you bought this month; they are added "
                         "to My savings (added on top if the same asset is in the same goal).",
        "alim_tutar": "Amount paid ({s})", "alim_ekle": "Add to my savings",
        "alim_eklendi": "Added to your savings: {x}", "alim_liste": "Purchases added this month",
        "alim_toplam": "Invested this month: {x} · suggested: {y}",
        "alim_sil": "Undo selected purchase", "alim_eksik": "Enter a quantity or an amount.",
        "c_tarih_alim": "Date",
        "sayfa_plan": "This month's plan", "sayfa_birikim": "My savings",
        "ayarlar": "Settings", "ulke": "Country", "canli_tcmb": "Live CBRT data",
        "enflasyon": "Annual inflation assumption (%)",
        "not_tr": "Uses live CBRT policy rate/CPI and (if available) estimates from TEFAS history.",
        "not_diger": "Returns and volatility: assumptions based on long-run historical averages.",
        "ayrintili": "Detailed panel (transaction history, KAP): `kumbara panel --ayrintili`",
        "uyari": "This tool is not investment advice. Allocations are educational examples based "
                 "on general assumptions; make decisions with a licensed adviser.",
        "plan_baslik": "kumbara · this month's plan",
        "plan_aciklama": "Upload your latest credit card statement and enter this month's income "
                         "to see how much you can save and how to invest it for your goals. "
                         "Statements are not saved to disk; they are kept for this session.",
        "adim1": "1 · Latest card statement",
        "yukle": "PDF, JPG or PNG (several files for several cards)",
        "sifre": "PDF password (if any)", "okunuyor": "Reading {ad}…",
        "c_dosya": "File", "c_kart": "Card", "c_islem": "Transactions",
        "c_banka": "Bank's total", "c_okunan": "Parsed transactions", "c_bes": "Pension / savings",
        "c_taksit": "Next instalments",
        "u_fark": "parsed transactions differ from the bank's total; the bank's total was used.",
        "u_fark_gorsel": "the screenshot doesn't show the whole list; the bank's total was used.",
        "u_toplam_yok": "bank's total not found; parsed transactions were used. Please check.",
        "kategori_dokumu": "Spending by category (parsed transactions)",
        "kart_harcama": "This month's card spending ({s}) — correct if needed",
        "kart_harcama_yardim": "The total stated by the bank (or parsed transactions). The "
                               "previous statement is assumed paid.",
        "adim2": "2 · This month's income", "gelir": "Net income ({s})",
        "kart_disi": "Non-card expenses ({s}) — rent, bills paid by transfer, cash…",
        "bes_say": "Count the {x} pension/savings payment on the statement as savings",
        "adim3": "3 · How much can I save this month?", "gelir_girin": "Enter your income.",
        "yatirilabilir": "Available to invest", "oran": "Savings rate",
        "toplam_birikim": "Total savings", "bes_dahil": " (incl. pension)",
        "formul": "{g} income − {k} card spending − {d} non-card expenses",
        "bes_gitti": "; pension ({x}) already went to savings.",
        "taksit_bilgi": "{x} of instalments are already due on next month's statements; {y} "
                        "remain for later months.",
        "acik": "Expenses exceed or equal income this month; nothing left to invest.",
        "adim4": "4 · Your goals", "c_hedef": "Goal", "c_tutar": "Amount ({s}, in today's money)",
        "c_tarih": "Target date", "c_mevcut": "Already saved", "c_oncelik": "Priority",
        "c_mevcut_elle": "Also set aside (outside My savings)",
        "c_risk": "Risk", "hedef_kaydet": "Save goals",
        "hedef_ekle": "Add a goal (e.g. Emergency fund, House deposit) and save.",
        "mevcut_varliktan": "The current value of assets you included in a goal on 'My savings' "
                            "is added to 'also set aside'. Don't enter the same money twice.",
        "adim5": "5 · This month's investment split by goal",
        "kaynak_notu": "{ulke} · return assumptions: {kaynak}. Expected returns cover part of what "
                       "is left to the goal; you invest the rest. Amounts in today's money (above "
                       "inflation); raise contributions with inflation (~{e}%) every year. Returns "
                       "are not guaranteed: if they come in lower, you need to invest more.",
        "c_vade": "Horizon", "c_kalan_ay": "Months left", "c_kalan": "Left to goal",
        "c_getiri": "Expected annual return", "getiri_bicim": "{n}% ({r}% above inflation)",
        "c_getiriden": "Expected from returns", "c_yatirilacak": "You need to invest (total)",
        "c_aylik": "You need to invest monthly", "c_ayrilan": "This month",
        "c_varlik": "Asset", "c_oran": "Weight", "c_bu_ay": "This month",
        "alim_listesi": "This month's shopping list",
        "w_kapasite": "this month's savings cover {p}% of the required contribution; consider a "
                      "later date or a smaller amount.",
        "w_kisa_agresif": "high risk for a short-term goal: value may be low at the target date.",
        "w_3ay": "less than 3 months left; keep the money liquid.",
        "w_disarida": "{x} linked to this goal is not part of this horizon's allocation; new "
                      "contributions are not directed there.",
        "bagli": "Savings linked to this goal: {x}. This month's contribution is split to move "
                 "the current mix towards the model.",
        "b_donem_ici": "Spending this period", "b_hesap_ozeti": "Statement balance",
        "b_donem_borcu": "Period balance", "b_toplam_borc": "Total balance",
        "b_guncel": "Current period balance", "b_donem_ici_toplam": "Total spending this period",
        "vade_kısa": "short", "vade_orta": "medium", "vade_uzun": "long",
        "risk_muhafazakar": "conservative", "risk_dengeli": "balanced", "risk_agresif": "aggressive",
        "hata": "Could not read {ad}: {e}",
        "bk_baslik": "My savings",
        "bk_aciklama": "Enter the funds and shares in your investment accounts, your gold, foreign "
                       "currency and cash by quantity; current values are calculated. Link an "
                       "asset to a goal and the plan page uses it as that goal's current savings.",
        "bk_tur": "Asset", "bk_kod": "Code (fund / share / currency)",
        "bk_kod_yardim": "Share/ETF: ticker (AAPL, VOO); for London/Frankfurt add the exchange: "
                         "LSE:VWRL, XETR:EUNL · Turkish fund: TEFAS code (AFT) · BIST share: "
                         "THYAO · Currency: USD, EUR. Leave empty for others.",
        "bk_miktar": "Quantity (units / grams / amount)", "bk_maliyet": "Total cost ({s})",
        "bk_yer": "Institution / place", "bk_hedef": "Include in goal",
        "bk_elle": "Manual value ({s}, total)",
        "bk_elle_yardim": "For assets without a live price (pension, foreign shares, crypto…).",
        "bk_kaydet": "Save my savings", "bk_yok": "(none)",
        "bk_bos": "No assets yet. Add rows to the table and save.",
        "bk_toplam": "Total savings", "bk_maliyetli": "Assets with cost entered",
        "bk_net": "Not linked to a goal", "bk_fiyatsiz": "{n} asset(s) could not be priced (check "
                                                       "the code or enter a manual value).",
        "bk_sinif": "By asset class", "bk_seyir": "Total savings over time",
        "bk_seyir_bilgi": "The valuation is saved daily; the chart appears after the second day.",
        "bk_kur": "Turkish market prices converted to {para} at the CBRT rate (1 {para} = {kur} ₺).",
        "bk_kur_yok": "Exchange rate unavailable; enter Turkish market assets with a manual value.",
        "bk_detay": "Details",
        "t_fon": "Investment fund (TEFAS)", "t_hisse": "Share (BIST)", "t_doviz": "Foreign currency",
        "t_yabanci": "Share / ETF (US, London, Frankfurt)",
        "etf_baslik": "ETFs you could buy this month ({borsa})",
        "etf_aciklama": "Common low-cost example ETFs for each asset class, with live price returns "
                        "(excluding dividends). Past returns don't predict the future; also check "
                        "fees.",
        "etf_yok": "ETF returns are unavailable right now.",
        "t_nakit": "Cash / deposit", "t_diger": "Other (manual value)",
        "a_gram": "Gold, gram (24k)", "a_ceyrek": "Quarter gold coin (pcs)",
        "a_yarim": "Half gold coin (pcs)", "a_tam": "Full gold coin (pcs)",
        "a_cumhuriyet": "Republic gold coin (pcs)", "a_ata": "Ata gold coin (pcs)",
        "a_22ayar": "22k gold / bracelet (gram)", "a_ajda": "22k ajda bracelet (gram)",
        "a_18ayar": "18k gold (gram)", "a_14ayar": "14k gold (gram)", "a_gumus": "Silver, gram",
        "s_ppf": "Cash / money market", "s_kisa_borc": "Short-term bonds",
        "s_tl_tahvil": "Government bonds", "s_eurobond": "Global bonds",
        "s_altin": "Gold / silver", "s_bist_hisse": "Domestic equities",
        "s_yabanci_hisse": "International equities", "s_doviz": "Foreign currency",
        "s_diger": "Other",
    },
    "de": {
        "veri_aliniyor": "Marktdaten werden geladen…",
        "kaynak_diger": "langfristige historische Durchschnitte",
        "degerleniyor": "Ersparnisse werden zu Live-Kursen bewertet…",
        "bk_eski": "Kein Live-Kurs; zum letzten bekannten Kurs bewertet: {x}",
        "c_birim": "Stückpreis", "c_deger": "Wert", "c_kar": "Gewinn / Verlust", "c_sinif": "Klasse",
        "bk_maliyet_yardim": "Gesamte Anschaffungskosten, für Gewinn/Verlust (optional).",
        "bk_maliyet_toplam": "Kosten gesamt: {x}",
        "yuklu": "Hochgeladene Abrechnungen", "kaldir": "Entfernen",
        "fonlar_baslik": "Fonds, die Sie diesen Monat kaufen könnten (TEFAS)",
        "fonlar_aciklama": "Die 3 renditestärksten Fonds des letzten Jahres je Anlageklasse. "
                           "Vergangene Renditen sagen nichts über die Zukunft; Kosten und Fondsgröße "
                           "prüfen.",
        "fonlar_yok": "Die TEFAS-Fondsliste ist gerade nicht verfügbar.", "c_fon": "Fonds",
        "c_kod": "Kennung", "c_1a": "1 Monat", "c_1y": "1 Jahr", "c_3y": "3 Jahre",
        "ornek_arac": "Beispielinstrumente",
        "alim_baslik": "Diesen Monat gekauft",
        "alim_aciklama": "Tragen Sie ein, was Sie diesen Monat gekauft haben; es wird zu Meine "
                         "Ersparnisse addiert (bei gleicher Anlage und gleichem Ziel aufaddiert).",
        "alim_tutar": "Bezahlter Betrag ({s})", "alim_ekle": "Zu meinen Ersparnissen",
        "alim_eklendi": "Zu Ihren Ersparnissen hinzugefügt: {x}",
        "alim_liste": "Diesen Monat erfasste Käufe",
        "alim_toplam": "Diesen Monat angelegt: {x} · empfohlen: {y}",
        "alim_sil": "Ausgewählten Kauf rückgängig machen",
        "alim_eksik": "Menge oder Betrag eingeben.", "c_tarih_alim": "Datum",
        "sayfa_plan": "Monatsplan", "sayfa_birikim": "Meine Ersparnisse",
        "ayarlar": "Einstellungen", "ulke": "Land", "canli_tcmb": "Live-Daten der CBRT",
        "enflasyon": "Angenommene jährliche Inflation (%)",
        "not_tr": "Nutzt Leitzins/VPI der CBRT live und (falls vorhanden) Schätzungen aus TEFAS.",
        "not_diger": "Rendite und Volatilität: Annahmen auf Basis langfristiger Durchschnitte.",
        "ayrintili": "Detailansicht (Umsätze, KAP): `kumbara panel --ayrintili`",
        "uyari": "Dieses Tool ist keine Anlageberatung. Die Aufteilungen sind Lehrbeispiele auf "
                 "Basis allgemeiner Annahmen; entscheiden Sie mit einem zugelassenen Berater.",
        "plan_baslik": "kumbara · Monatsplan",
        "plan_aciklama": "Laden Sie Ihre letzte Kreditkartenabrechnung hoch und geben Sie Ihr "
                         "Einkommen dieses Monats ein: Sie sehen, wie viel Sie sparen und wie Sie "
                         "es für Ihre Ziele anlegen können. Abrechnungen werden nur "
                         "für diese Sitzung behalten.",
        "adim1": "1 · Letzte Kartenabrechnung",
        "yukle": "PDF, JPG oder PNG (mehrere Dateien für mehrere Karten)",
        "sifre": "PDF-Passwort (falls vorhanden)", "okunuyor": "{ad} wird gelesen…",
        "c_dosya": "Datei", "c_kart": "Karte", "c_islem": "Umsätze",
        "c_banka": "Summe der Bank", "c_okunan": "Gelesene Umsätze", "c_bes": "Altersvorsorge",
        "c_taksit": "Nächste Raten",
        "u_fark": "die gelesenen Umsätze weichen von der Summe der Bank ab; die Banksumme wurde "
                  "verwendet.",
        "u_fark_gorsel": "der Screenshot zeigt nicht die ganze Liste; die Banksumme wurde "
                         "verwendet.",
        "u_toplam_yok": "keine Banksumme gefunden; gelesene Umsätze verwendet. Bitte prüfen.",
        "kategori_dokumu": "Ausgaben nach Kategorie (gelesene Umsätze)",
        "kart_harcama": "Kartenausgaben dieses Monats ({s}) — bei Bedarf korrigieren",
        "kart_harcama_yardim": "Von der Bank angegebene Summe (sonst gelesene Umsätze). Die "
                               "vorherige Abrechnung gilt als bezahlt.",
        "adim2": "2 · Einkommen dieses Monats", "gelir": "Nettoeinkommen ({s})",
        "kart_disi": "Ausgaben ohne Karte ({s}) — Miete, überwiesene Rechnungen, Bargeld…",
        "bes_say": "Die Altersvorsorgezahlung von {x} auf der Abrechnung als Ersparnis zählen",
        "adim3": "3 · Wie viel kann ich diesen Monat sparen?",
        "gelir_girin": "Geben Sie Ihr Einkommen ein.",
        "yatirilabilir": "Zum Anlegen verfügbar", "oran": "Sparquote",
        "toplam_birikim": "Ersparnis gesamt", "bes_dahil": " (inkl. Vorsorge)",
        "formul": "{g} Einkommen − {k} Kartenausgaben − {d} sonstige Ausgaben",
        "bes_gitti": "; Vorsorge ({x}) wurde bereits gespart.",
        "taksit_bilgi": "Auf den nächsten Abrechnungen stehen bereits {x} Raten an; {y} folgen "
                        "in späteren Monaten.",
        "acik": "Die Ausgaben erreichen oder übersteigen das Einkommen; nichts zum Anlegen übrig.",
        "adim4": "4 · Ihre Ziele", "c_hedef": "Ziel", "c_tutar": "Betrag ({s}, in heutigem Geld)",
        "c_tarih": "Zieldatum", "c_mevcut": "Bereits gespart", "c_oncelik": "Priorität",
        "c_mevcut_elle": "Zusätzlich zurückgelegt (außerhalb Meine Ersparnisse)",
        "c_risk": "Risiko", "hedef_kaydet": "Ziele speichern",
        "hedef_ekle": "Fügen Sie ein Ziel hinzu (z. B. Notgroschen, Eigenkapital) und speichern.",
        "mevcut_varliktan": "Der aktuelle Wert der Anlagen, die Sie in 'Meine Ersparnisse' einem "
                            "Ziel zugeordnet haben, wird zu 'zusätzlich zurückgelegt' addiert. "
                            "Dasselbe Geld nicht doppelt eintragen.",
        "adim5": "5 · Anlageaufteilung dieses Monats nach Zielen",
        "kaynak_notu": "{ulke} · Renditeannahmen: {kaynak}. Erwartete Erträge decken einen Teil "
                       "des Restbetrags; den Rest zahlen Sie ein. Beträge in heutigem Geld (über "
                       "Inflation); Beiträge jährlich um die Inflation (~{e} %) erhöhen. Erträge "
                       "sind nicht garantiert: fallen sie niedriger aus, müssen Sie mehr anlegen.",
        "c_vade": "Horizont", "c_kalan_ay": "Restmonate", "c_kalan": "Bis zum Ziel",
        "c_getiri": "Erwartete Jahresrendite", "getiri_bicim": "{n} % ({r} % über Inflation)",
        "c_getiriden": "Erwartet aus Erträgen", "c_yatirilacak": "Von Ihnen anzulegen (gesamt)",
        "c_aylik": "Monatlich anzulegen", "c_ayrilan": "Diesen Monat",
        "c_varlik": "Anlage", "c_oran": "Anteil",
        "c_bu_ay": "Diesen Monat", "alim_listesi": "Einkaufsliste dieses Monats",
        "w_kapasite": "die Ersparnis dieses Monats deckt {p} % des nötigen Beitrags; späteres "
                      "Datum oder kleineren Betrag erwägen.",
        "w_kisa_agresif": "hohes Risiko für ein kurzfristiges Ziel: der Wert kann zum Zieldatum "
                          "niedrig sein.",
        "w_3ay": "weniger als 3 Monate übrig; das Geld liquide halten.",
        "w_disarida": "{x} ist mit diesem Ziel verknüpft, gehört aber nicht zur Aufteilung dieses "
                      "Horizonts; neue Beiträge fließen nicht dorthin.",
        "bagli": "Mit diesem Ziel verknüpfte Ersparnisse: {x}. Der Beitrag dieses Monats wird so "
                 "aufgeteilt, dass sich die Mischung dem Modell annähert.",
        "b_donem_ici": "Ausgaben im Zeitraum", "b_hesap_ozeti": "Abrechnungssaldo",
        "b_donem_borcu": "Saldo des Zeitraums", "b_toplam_borc": "Gesamtsaldo",
        "b_guncel": "Aktueller Saldo", "b_donem_ici_toplam": "Ausgaben im Zeitraum gesamt",
        "vade_kısa": "kurz", "vade_orta": "mittel", "vade_uzun": "lang",
        "risk_muhafazakar": "konservativ", "risk_dengeli": "ausgewogen", "risk_agresif": "offensiv",
        "hata": "{ad} konnte nicht gelesen werden: {e}",
        "bk_baslik": "Meine Ersparnisse",
        "bk_aciklama": "Erfassen Sie Fonds und Aktien Ihrer Depots, Gold, Devisen und Bargeld nach "
                       "Menge; die aktuellen Werte werden berechnet. Mit einem Ziel verknüpfte "
                       "Anlagen zählen im Monatsplan als dessen aktuelle Ersparnis.",
        "bk_tur": "Anlage", "bk_kod": "Kennung (Fonds / Aktie / Währung)",
        "bk_kod_yardim": "Aktie/ETF: Kürzel mit Börse, z. B. XETR:EUNL, LSE:VWRL, oder US-Kürzel "
                         "(AAPL, VOO) · Türkischer Fonds: TEFAS-Code (AFT) · BIST-Aktie: THYAO · "
                         "Währung: USD, EUR. Sonst leer lassen.",
        "bk_miktar": "Menge (Stück / Gramm / Betrag)", "bk_maliyet": "Kosten gesamt ({s})",
        "bk_yer": "Institut / Ort", "bk_hedef": "Ziel zuordnen",
        "bk_elle": "Manueller Wert ({s}, gesamt)",
        "bk_elle_yardim": "Für Anlagen ohne Live-Kurs (Vorsorge, ausländische Aktien, Krypto…).",
        "bk_kaydet": "Ersparnisse speichern", "bk_yok": "(keins)",
        "bk_bos": "Noch keine Anlagen. Zeilen hinzufügen und speichern.",
        "bk_toplam": "Ersparnis gesamt", "bk_maliyetli": "Anlagen mit Kosten",
        "bk_net": "Ohne Zielverknüpfung", "bk_fiyatsiz": "{n} Anlage(n) ohne Kurs (Kennung prüfen "
                                                         "oder manuellen Wert eingeben).",
        "bk_sinif": "Nach Anlageklasse", "bk_seyir": "Entwicklung der Ersparnisse",
        "bk_seyir_bilgi": "Die Bewertung wird täglich gespeichert; das Diagramm erscheint ab dem "
                          "zweiten Tag.",
        "bk_kur": "Türkische Marktpreise zum CBRT-Kurs in {para} umgerechnet (1 {para} = {kur} ₺).",
        "bk_kur_yok": "Kein Wechselkurs; türkische Anlagen bitte mit manuellem Wert erfassen.",
        "bk_detay": "Details",
        "t_fon": "Investmentfonds (TEFAS)", "t_hisse": "Aktie (BIST)", "t_doviz": "Devisen",
        "t_yabanci": "Aktie / ETF (USA, London, Frankfurt)",
        "etf_baslik": "ETFs, die Sie diesen Monat kaufen könnten ({borsa})",
        "etf_aciklama": "Verbreitete, günstige Beispiel-ETFs je Anlageklasse mit Live-Kursrenditen "
                        "(ohne Ausschüttungen). Vergangene Renditen sagen nichts über die Zukunft; "
                        "Kosten prüfen.",
        "etf_yok": "ETF-Renditen sind gerade nicht verfügbar.",
        "t_nakit": "Bargeld / Einlage", "t_diger": "Sonstiges (manueller Wert)",
        "a_gram": "Gold, Gramm (24 K)", "a_ceyrek": "Viertel-Goldmünze (Stk.)",
        "a_yarim": "Halbe Goldmünze (Stk.)", "a_tam": "Ganze Goldmünze (Stk.)",
        "a_cumhuriyet": "Republik-Goldmünze (Stk.)", "a_ata": "Ata-Goldmünze (Stk.)",
        "a_22ayar": "Gold 22 K / Armreif (Gramm)", "a_ajda": "Ajda-Armreif 22 K (Gramm)",
        "a_18ayar": "Gold 18 K (Gramm)", "a_14ayar": "Gold 14 K (Gramm)", "a_gumus": "Silber, Gramm",
        "s_ppf": "Bargeld / Geldmarkt", "s_kisa_borc": "Kurzlaufende Anleihen",
        "s_tl_tahvil": "Staatsanleihen", "s_eurobond": "Globale Anleihen",
        "s_altin": "Gold / Silber", "s_bist_hisse": "Heimische Aktien",
        "s_yabanci_hisse": "Internationale Aktien", "s_doviz": "Devisen (bar)", "s_diger": "Sonstiges",
    },
}

# Varsayılan kategori adlarının çevirileri (kullanıcının kendi kategorileri olduğu gibi kalır)
KATEGORILER = {
    "en": {"Market": "Groceries", "Yeme-İçme": "Eating out", "Taksi ve Uber": "Taxi & ride-hailing",
           "Ulaşım": "Transport", "Yakıt": "Fuel", "Fatura": "Bills", "Kira": "Rent",
           "Abonelik": "Subscriptions", "Sağlık": "Health", "Eğitim": "Education",
           "Giyim": "Clothing", "Elektronik": "Electronics", "Online Alışveriş": "Online shopping",
           "Alışveriş (AVM)": "Shopping (malls)", "Seyahat": "Travel", "Eğlence": "Entertainment",
           "Nakit Çekim": "Cash withdrawal", "Banka Masrafı": "Bank fees", "Sigorta": "Insurance",
           "Vergi ve Harç": "Taxes & fees", "Kredi ve Taksit": "Loans", "Taksitler": "Instalments",
           "Kişisel Bakım": "Personal care", "BES ve Birikim": "Pension & savings",
           "Transfer": "Transfer", "İade": "Refund", "Maaş": "Salary", "Diğer": "Other",
           "Diğer Gelir": "Other income", "Faiz ve Getiri": "Interest & returns"},
    "de": {"Market": "Lebensmittel", "Yeme-İçme": "Essen gehen", "Taksi ve Uber": "Taxi & Fahrdienste",
           "Ulaşım": "Verkehr", "Yakıt": "Kraftstoff", "Fatura": "Rechnungen", "Kira": "Miete",
           "Abonelik": "Abos", "Sağlık": "Gesundheit", "Eğitim": "Bildung", "Giyim": "Kleidung",
           "Elektronik": "Elektronik", "Online Alışveriş": "Online-Shopping",
           "Alışveriş (AVM)": "Einkaufszentren", "Seyahat": "Reisen", "Eğlence": "Freizeit",
           "Nakit Çekim": "Bargeldabhebung", "Banka Masrafı": "Bankgebühren",
           "Sigorta": "Versicherung", "Vergi ve Harç": "Steuern & Gebühren",
           "Kredi ve Taksit": "Kredite", "Taksitler": "Raten", "Kişisel Bakım": "Körperpflege",
           "BES ve Birikim": "Vorsorge & Sparen", "Transfer": "Überweisung", "İade": "Erstattung",
           "Maaş": "Gehalt", "Diğer": "Sonstiges", "Diğer Gelir": "Sonstige Einnahmen",
           "Faiz ve Getiri": "Zinsen & Erträge"},
}


def dil_kodu(ulke_kodu: str) -> str:
    return ULKE_DILI.get(ulke_kodu, "tr")


def t(dil: str, anahtar: str, **degerler) -> str:
    metin = METINLER.get(dil, {}).get(anahtar) or METINLER["tr"].get(anahtar, anahtar)
    return metin.format(**degerler) if degerler else metin


def kategori_adi(dil: str, kategori: str) -> str:
    return KATEGORILER.get(dil, {}).get(kategori, kategori)


def yuzde(dil: str, x: float, ondalik: int = 0) -> str:
    """Yüzde biçimi: tr %80 · en 80% · de 80 %."""
    sayi = f"{x:.{ondalik}f}"
    if dil == "tr":
        return f"%{sayi.replace('.', ',')}"
    if dil == "de":
        return f"{sayi.replace('.', ',')} %"
    return f"{sayi}%"
