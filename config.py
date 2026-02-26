"""
TEFAS BES Fon Analizi — Yapılandırma Modülü
Tüm sabitler ve ayarlar burada tanımlıdır.
"""


class Config:
    """Yapılandırma singleton"""
    _instance = None

    PERFORMANCE_COLUMNS = [
        "1 Ay (%)", "3 Ay (%)", "6 Ay (%)",
        "1 Yıl (%)", "3 Yıl (%)", "5 Yıl (%)"
    ]
    WEIGHT_TOLERANCE = 0.01
    SAVING_INTERVAL = 300
    CACHE_FILE = "fund_cache.json"
    BATCH_REQUEST_DELAY = 1.5   # Toplu çekme: istekler arası bekleme (saniye)
    SINGLE_REQUEST_DELAY = 3    # Tek fon tıklama: minimum bekleme (saniye)

    # Portföy analizi dönemleri
    PORTFOLIO_PERIODS = [
        ("1 Ay (%)", "1 Ay", 1),
        ("3 Ay (%)", "3 Ay", 3),
        ("6 Ay (%)", "6 Ay", 6),
        ("1 Yıl (%)", "1 Yıl", 12),
        ("3 Yıl (%)", "3 Yıl", 36),
        ("5 Yıl (%)", "5 Yıl", 60),
    ]

    # Makro gösterge sembolleri (yfinance)
    MACRO_SYMBOLS_ROW1 = {
        "BIST-100": "XU100.IS",
        "Altın": "GC=F",
        "Gümüş": "SI=F",
        "USD/TRY": "USDTRY=X",
        "EUR/TRY": "EURTRY=X",
    }
    MACRO_SYMBOLS_ROW2 = {
        "Brent": "BZ=F",
        "BTC": "BTC-USD",
        "ETH": "ETH-USD",
    }
    MACRO_SYMBOLS = {**MACRO_SYMBOLS_ROW1, **MACRO_SYMBOLS_ROW2}
    MACRO_USD_TO_TL = {"Altın", "Gümüş"}
    MACRO_AUTO_REFRESH = 10  # Otomatik yenileme aralığı (saniye)

    COLUMN_WIDTHS = {
        "Sıra": 50,
        "Fon Kodu": 50,
        "Fon Adı": 150,
        "Fon Türü": 100,
        "1 Ay (%)": 100,
        "3 Ay (%)": 100,
        "6 Ay (%)": 100,
        "1 Yıl (%)": 100,
        "3 Yıl (%)": 100,
        "5 Yıl (%)": 100,
        "Skor": 100,
        "Tür Sırası": 80,
        "Günlük (%)": 100,
        "Öngörü": 80
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

