"""
TEFAS BES Fon Analizi — Veri Çekme Modülü
HTTP istekleri, TEFAS HTML parse, Yahoo Finance, önbellek yönetimi.
GUI'den bağımsızdır, FundAnalyzer tarafından kullanılır.
"""
import os
import json
import re
import time
from datetime import date

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import ssl
    HAS_REQUESTS = False

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False


_USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
)
_DEFAULT_HEADERS = {
    'User-Agent': _USER_AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
}

# Highcharts varsayılan renk paleti
_PIE_COLORS = [
    '#4572A7', '#AA4643', '#89A54E', '#80699B', '#3D96AE',
    '#DB843D', '#92A8CD', '#A47D7C', '#B5CA92', '#7cb5ec',
]


class DataFetcher:
    """Tüm veri çekme ve parse işlemlerini yöneten sınıf."""

    def __init__(self, config):
        self.config = config
        self._http_session = self._create_http_session()
        self._last_request_time = 0

    # ── HTTP Session ──────────────────────────────

    @staticmethod
    def _create_http_session():
        if HAS_REQUESTS:
            session = requests.Session()
            session.headers.update(_DEFAULT_HEADERS)
            return session
        return None

    # ── Throttle ──────────────────────────────────

    def throttle_request(self, min_delay=None):
        """İstekler arası minimum bekleme süresini uygula."""
        if min_delay is None:
            min_delay = self.config.SINGLE_REQUEST_DELAY
        elapsed = time.time() - self._last_request_time
        if elapsed < min_delay:
            time.sleep(min_delay - elapsed)
        self._last_request_time = time.time()

    # ── HTML Çekme ────────────────────────────────

    def fetch_html(self, url):
        """Tek bir URL için HTML içeriğini çek."""
        if HAS_REQUESTS:
            resp = self._http_session.get(url, timeout=15, verify=False)
            resp.encoding = 'utf-8'
            return resp.text
        else:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers=_DEFAULT_HEADERS)
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                return resp.read().decode('utf-8')

    # ── TEFAS Parse ───────────────────────────────

    @staticmethod
    def parse_allocation_data(html_content):
        """HTML içeriğinden varlık dağılımı verilerini çıkar (Highcharts)."""
        allocation_data = {}

        if 'PieChartFonDagilim' in html_content:
            data_start = html_content.find('"data":[[')
            if data_start != -1:
                data_end = html_content.find(']]', data_start)
                if data_end != -1:
                    data_str = html_content[data_start + 8:data_end + 2]
                    items = re.findall(r'\["([^"]+)",\s*([\d.]+)\]', data_str)
                    for i, (name, value) in enumerate(items):
                        try:
                            pct = float(value)
                            if name.strip() and pct > 0:
                                allocation_data[name.strip()] = {
                                    'percentage': pct,
                                    'color': _PIE_COLORS[i % len(_PIE_COLORS)]
                                }
                        except ValueError:
                            pass

        if not allocation_data:
            pattern = r'"name"\s*:\s*"([^"]+)"[^}]*"y"\s*:\s*([\d.]+)'
            for i, (name, value) in enumerate(re.findall(pattern, html_content)):
                try:
                    pct = float(value)
                    if name.strip() and 0 < pct <= 100:
                        allocation_data[name.strip()] = {
                            'percentage': pct,
                            'color': _PIE_COLORS[i % len(_PIE_COLORS)]
                        }
                except ValueError:
                    pass

        return allocation_data

    @staticmethod
    def parse_daily_return(html_content):
        """HTML içeriğinden günlük getiri bilgisini çıkar."""
        pattern = r'Günlük Getiri \(%\).*?<span>([^<]+)</span>'
        match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else None

    # ── Yahoo Finance ─────────────────────────────

    def fetch_yahoo_quote(self, symbol):
        """Yahoo'dan ~3 aylık kapanış fiyatlarını çek."""
        _ua = {'User-Agent': _USER_AGENT}

        for host in ['query2', 'query1']:
            try:
                url = (f"https://{host}.finance.yahoo.com"
                       f"/v8/finance/chart/{symbol}?range=3mo&interval=1d")
                if HAS_REQUESTS:
                    resp = self._http_session.get(url, timeout=10, verify=False)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                else:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    req = urllib.request.Request(url, headers=_ua)
                    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                        data = json.loads(r.read().decode('utf-8'))

                chart = data.get('chart', {}).get('result', [])
                if chart:
                    closes = [c for c in chart[0].get('indicators', {})
                              .get('quote', [{}])[0].get('close', [])
                              if c is not None]
                    if len(closes) >= 2:
                        return closes
            except Exception:
                continue

        # Spark API fallback
        try:
            url = (f"https://query2.finance.yahoo.com"
                   f"/v7/finance/spark?symbols={symbol}&range=3mo&interval=1d")
            if HAS_REQUESTS:
                resp = self._http_session.get(url, timeout=10, verify=False)
                if resp.status_code == 200:
                    spark = resp.json().get('spark', {}).get('result', [])
                    if spark:
                        closes = [c for c in spark[0].get('response', [{}])[0]
                                  .get('indicators', {}).get('quote', [{}])[0]
                                  .get('close', []) if c is not None]
                        if len(closes) >= 2:
                            return closes
        except Exception:
            pass

        return None

    def fetch_yahoo_quote_short(self, symbol):
        """Son 5 günlük kapanış fiyatlarını çek (hafif istek)."""
        _ua = {'User-Agent': _USER_AGENT}
        for host in ['query2', 'query1']:
            try:
                url = (f"https://{host}.finance.yahoo.com"
                       f"/v8/finance/chart/{symbol}?range=5d&interval=1d")
                if HAS_REQUESTS:
                    resp = self._http_session.get(url, timeout=8, verify=False)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                else:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    req = urllib.request.Request(url, headers=_ua)
                    with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
                        data = json.loads(r.read().decode('utf-8'))

                chart = data.get('chart', {}).get('result', [])
                if chart:
                    closes = [c for c in chart[0].get('indicators', {})
                              .get('quote', [{}])[0].get('close', [])
                              if c is not None]
                    if len(closes) >= 2:
                        return closes
            except Exception:
                continue
        return None

    def fetch_yahoo_batch(self, symbols_list):
        """Birden fazla sembolü toplu çek."""
        result = {}

        if HAS_YFINANCE:
            import logging
            logging.getLogger('yfinance').setLevel(logging.CRITICAL)
            try:
                joined = ' '.join(symbols_list)
                data = yf.download(joined, period='2d', interval='1d',
                                   progress=False, threads=True, timeout=4)
                if data is not None and not data.empty:
                    close_data = data.get('Close', data)
                    if hasattr(close_data, 'columns'):
                        for sym in symbols_list:
                            if sym in close_data.columns:
                                closes = close_data[sym].dropna().tolist()
                                if len(closes) >= 2:
                                    result[sym] = [float(c) for c in closes]
                    else:
                        closes = close_data.dropna().tolist()
                        if len(closes) >= 2 and len(symbols_list) == 1:
                            result[symbols_list[0]] = [float(c) for c in closes]
            except Exception:
                pass

        for sym in symbols_list:
            if sym not in result:
                closes = self.fetch_yahoo_quote_short(sym)
                if closes:
                    result[sym] = closes

        return result

    # ── Makro Veri Yükleme ────────────────────────

    def load_macro_data(self):
        """Piyasa verilerini çek, hesapla ve dict olarak döndür."""
        import logging
        logging.getLogger('yfinance').setLevel(logging.CRITICAL)

        symbols = self.config.MACRO_SYMBOLS
        usd_to_tl = self.config.MACRO_USD_TO_TL
        result = {}
        errors = []
        all_closes = {}

        if HAS_YFINANCE:
            try:
                all_symbols = list(symbols.values())
                joined = ' '.join(all_symbols)
                data = yf.download(joined, period='3mo', interval='1d',
                                   progress=False, threads=True, timeout=10)
                if data is not None and not data.empty:
                    close_data = data.get('Close', data)
                    if hasattr(close_data, 'columns'):
                        for sym in all_symbols:
                            if sym in close_data.columns:
                                raw = close_data[sym].dropna().tolist()
                                if len(raw) >= 2:
                                    name = {k for k, v in symbols.items()
                                            if v == sym}.pop()
                                    all_closes[name] = [float(x) for x in raw]
                    elif len(all_symbols) == 1:
                        raw = close_data.dropna().tolist()
                        if len(raw) >= 2:
                            all_closes[list(symbols.keys())[0]] = \
                                [float(x) for x in raw]
            except Exception:
                pass

        for name, symbol in symbols.items():
            if name in all_closes:
                continue
            try:
                closes = self.fetch_yahoo_quote(symbol)
                if closes and len(closes) >= 2:
                    all_closes[name] = closes
                else:
                    errors.append(name)
            except Exception:
                errors.append(name)

        usdtry_closes = all_closes.get("USD/TRY")

        for name, closes in all_closes.items():
            if name in usd_to_tl and usdtry_closes:
                min_len = min(len(closes), len(usdtry_closes))
                closes = [closes[i] * usdtry_closes[i] for i in range(min_len)]

            if len(closes) < 2:
                continue

            current = closes[-1]
            prev = closes[-2]
            daily_chg = ((current - prev) / prev) * 100

            monthly_chg = None
            if len(closes) >= 22:
                monthly_chg = ((current - closes[-22]) / closes[-22]) * 100

            quarterly_chg = None
            if len(closes) >= 60:
                quarterly_chg = ((current - closes[0]) / closes[0]) * 100

            result[name] = {
                'price': current,
                'daily': daily_chg,
                'monthly': monthly_chg,
                'quarterly': quarterly_chg,
            }

        return result, errors

    # ── Disk Önbellek ─────────────────────────────

    def get_cache_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            self.config.CACHE_FILE)

    def load_cache(self):
        """Disk'ten bugünün cache'ini yükle. (daily_returns, allocations, macro_data) döndürür."""
        cache_path = self.get_cache_path()
        try:
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get("date") == date.today().isoformat():
                    return (data.get("daily_returns", {}),
                            data.get("allocations", {}),
                            data.get("macro_data", {}))
        except Exception:
            pass
        return {}, {}, {}

    def save_cache(self, daily_returns, allocations, macro_data):
        """Önbelleği disk'e kaydet."""
        cache_path = self.get_cache_path()
        try:
            data = {
                "date": date.today().isoformat(),
                "daily_returns": daily_returns,
                "allocations": allocations,
                "macro_data": macro_data,
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        except Exception as e:
            print(f"Önbellek kaydedilemedi: {e}")

    def clear_cache(self):
        """Disk cache dosyasını sil."""
        cache_path = self.get_cache_path()
        if os.path.exists(cache_path):
            os.remove(cache_path)

