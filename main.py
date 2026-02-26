import os
import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import warnings
import webbrowser
import re
import threading
import time
from datetime import date, datetime

from config import Config
from data_fetcher import DataFetcher, HAS_REQUESTS, HAS_YFINANCE

try:
    from strategy_engine import StrategyEngine
    HAS_STRATEGY = True
except ImportError:
    HAS_STRATEGY = False

os.environ['TK_SILENCE_DEPRECATION'] = '1'
warnings.filterwarnings("ignore")

# Uygulama dizini — dosya okuma/yazma bu dizine göre yapılır
APP_DIR = os.path.dirname(os.path.abspath(__file__))


class FundAnalyzer:

    def __init__(self):
        self.config = Config()
        self.performance_columns = self.config.PERFORMANCE_COLUMNS
        self.root = tk.Tk()
        self.root.title("TEFAS BES Fon Analizi")
        self.root.geometry("1400x850")

        self.df = None
        self.tree = None
        self.tree_font_size = 13  # Varsayılan font boyutu artırıldı
        self.table_columns = []
        self.filter_entry = None
        self.mevcut_fonlar_text = None
        self.planlanan_fonlar_text = None
        self.weight_sum_label = None
        self.controls = {}
        self.highlight_funds = set()
        self.planned_funds = set()
        self._tags_configured = False
        self._last_sorted_col = None
        self._sort_reverse = False
        self.style = None
        self.daily_return_cache = {}
        self.allocation_cache = {}   # fon_kodu → allocation_data dict
        self.macro_data = {}         # makro gösterge verileri
        self._macro_auto_refresh_enabled = True  # Otomatik yenileme
        self._macro_refresh_busy = False  # Yenileme devam ediyor mu
        self._macro_label_refs = {}  # {name: {price: Label, daily: Label}}
        self._fetch_in_progress = False
        self._fetch_cancel = False
        self.forecast_cache = {}     # fon_kodu → forecast_result
        self._fund_type_filter = set()  # Seçili fon türleri (boş = hepsi)
        self._fund_type_popup = None    # Açık dropdown penceresi
        self._status_var = None         # Durum çubuğu text değişkeni
        self._visible_count = 0         # Görünen satır sayısı
        self.portfolio_total_value = 0.0  # Toplam portföy değeri (TL)
        self.fund_distribution = {}       # {fon_kodu: yüzde} dağılım
        self._pv_entry_var = None         # Portföy değeri Entry StringVar (UI)
        self._dist_entries = {}           # {fon_kodu: StringVar} dağılım Entry'leri (UI)
        self._dist_tl_labels = {}         # {fon_kodu: Label} TL değer etiketleri (UI)
        self.strategy = StrategyEngine() if HAS_STRATEGY else None

        # Veri çekme modülü
        self.fetcher = DataFetcher(self.config)

        # Disk önbelleğini yükle
        dr, al, md = self.fetcher.load_cache()
        self.daily_return_cache = dr
        self.allocation_cache = al
        self.macro_data = md

        self.create_menu()
        self.setup_ui()

    # ──────────────────────────────────────────────
    # Veri Çekme Wrapper'ları (DataFetcher'a delege)
    # ──────────────────────────────────────────────

    def _save_cache_to_disk(self):
        self.fetcher.save_cache(self.daily_return_cache, self.allocation_cache, self.macro_data)

    def _clear_cache(self):
        if messagebox.askyesno("Önbelleği Temizle",
                               f"Önbellekte {len(self.daily_return_cache)} fon verisi var.\n"
                               "Tüm önbellek silinsin mi?"):
            self.daily_return_cache = {}
            self.allocation_cache = {}
            self.macro_data = {}
            self.fetcher.clear_cache()
            if self.df is not None:
                self.update_table(self.filter_entry.get() if self.filter_entry else None)
            messagebox.showinfo("Bilgi", "Önbellek temizlendi.")

    def _fetch_html(self, url):
        return self.fetcher.fetch_html(url)

    def _parse_allocation_data(self, html_content):
        return self.fetcher.parse_allocation_data(html_content)

    def _parse_daily_return(self, html_content):
        return self.fetcher.parse_daily_return(html_content)

    def _throttle_request(self, min_delay=None):
        self.fetcher.throttle_request(min_delay)

    # ──────────────────────────────────────────────
    # Makro Piyasa Göstergeleri (GUI kısmı burada kalır)
    # ──────────────────────────────────────────────

    def _load_macro_data(self):
        """Arka planda piyasa verilerini çek"""
        result, errors = self.fetcher.load_macro_data()
        self.macro_data = result
        if result:
            self._save_cache_to_disk()
            self.root.after(0, self._display_macro_data)
            self.root.after(0, self._schedule_macro_refresh)
            if errors:
                print(f"Bazı göstergeler alınamadı: {', '.join(errors)}")
        else:
            self.root.after(0, lambda: self._show_macro_loading("Piyasa verisi alınamadı"))
            self.root.after(0, self._schedule_macro_refresh)

    def _schedule_macro_refresh(self):
        if not self._macro_auto_refresh_enabled:
            return
        self.root.after(self.config.MACRO_AUTO_REFRESH * 1000, self._auto_refresh_macro)

    def _auto_refresh_macro(self):
        if not self._macro_auto_refresh_enabled:
            return
        if self._macro_refresh_busy:
            self._schedule_macro_refresh()
            return
        self._macro_refresh_busy = True
        threading.Thread(target=self._load_macro_quick, daemon=True).start()

    def _load_macro_quick(self):
        """Hafif yenileme: toplu çek"""
        try:
            symbols = self.config.MACRO_SYMBOLS
            usd_to_tl = self.config.MACRO_USD_TO_TL
            updated = False
            all_symbols = list(symbols.values())
            symbol_closes = self.fetcher.fetch_yahoo_batch(all_symbols)
            usdtry_sym = symbols.get("USD/TRY")
            usdtry_closes = symbol_closes.get(usdtry_sym)
            usdtry_price = usdtry_closes[-1] if usdtry_closes and len(usdtry_closes) >= 2 else None
            for name, symbol in symbols.items():
                closes = symbol_closes.get(symbol)
                if not closes or len(closes) < 2:
                    continue
                current, prev = closes[-1], closes[-2]
                if name in usd_to_tl and usdtry_price:
                    current *= usdtry_price
                    prev *= usdtry_price
                daily_chg = ((current - prev) / prev) * 100
                if name in self.macro_data:
                    self.macro_data[name]['price'] = current
                    self.macro_data[name]['daily'] = daily_chg
                else:
                    self.macro_data[name] = {'price': current, 'daily': daily_chg,
                                             'monthly': None, 'quarterly': None}
                updated = True
            if updated:
                self.root.after(0, self._update_macro_labels)
        except Exception as e:
            print(f"Hafif yenileme hatası: {e}")
        finally:
            self._macro_refresh_busy = False
        self.root.after(0, self._schedule_macro_refresh)

    def _update_macro_labels(self):
        if self._macro_label_refs:
            for name, refs in self._macro_label_refs.items():
                info = self.macro_data.get(name)
                if not info:
                    continue
                price = info['price']
                price_text = f"{price:,.0f}" if price > 1000 else f"{price:.2f}"
                old_price = refs.get('_old_price')
                refs['price'].config(text=price_text)
                daily = info['daily']
                color = "#4CAF50" if daily >= 0 else "#f44336"
                arrow = "▲" if daily >= 0 else "▼"
                refs['daily'].config(text=f"{arrow}{abs(daily):.2f}%", fg=color)
                if old_price is not None and old_price != price_text:
                    self._flash_label(refs['price'])
                    self._flash_label(refs['daily'])
                refs['_old_price'] = price_text
            self._update_macro_title()
        else:
            self._display_macro_data()

    def _flash_label(self, label, times=3):
        flash_colors = ["#FFFF00", "#FFA500"]
        def _do_flash(count):
            try:
                if not label.winfo_exists():
                    return
                if count <= 0:
                    try:
                        label.config(bg=label.master.cget("bg"))
                    except Exception:
                        label.config(bg="SystemButtonFace")
                    return
                label.config(bg=flash_colors[count % len(flash_colors)])
                self.root.after(180, lambda: _do_flash(count - 1))
            except tk.TclError:
                pass
        _do_flash(times * 2 + 1)

    def _display_macro_data(self):
        for widget in self.macro_frame.winfo_children():
            widget.destroy()
        self._macro_label_refs = {}
        self._update_macro_title()
        row1 = ttk.Frame(self.macro_frame)
        row1.pack(fill=tk.X, pady=(0, 2))
        self._build_indicator_row(row1, self.config.MACRO_SYMBOLS_ROW1)
        ttk.Button(row1, text="↻", command=self._refresh_macro_data, width=3).pack(side=tk.RIGHT, padx=4)
        row2 = ttk.Frame(self.macro_frame)
        row2.pack(fill=tk.X, pady=(2, 0))
        self._build_indicator_row(row2, self.config.MACRO_SYMBOLS_ROW2)
        self.macro_labels['loaded'] = True

    def _build_indicator_row(self, parent, symbols_dict):
        names = list(symbols_dict.keys())
        for i, name in enumerate(names):
            info = self.macro_data.get(name)
            if not info:
                continue
            item_frame = ttk.Frame(parent)
            item_frame.pack(side=tk.LEFT, padx=6)
            refs = {}
            tk.Label(item_frame, text=name, font=("Arial", 13, "bold"), fg="#555").pack(side=tk.LEFT, padx=(0, 4))
            price = info['price']
            price_text = f"{price:,.0f}" if price > 1000 else f"{price:.2f}"
            price_lbl = tk.Label(item_frame, text=price_text, font=("Arial", 13, "bold"))
            price_lbl.pack(side=tk.LEFT, padx=(0, 3))
            refs['price'] = price_lbl
            daily = info['daily']
            color = "#4CAF50" if daily >= 0 else "#f44336"
            arrow = "▲" if daily >= 0 else "▼"
            daily_lbl = tk.Label(item_frame, text=f"{arrow}{abs(daily):.2f}%", font=("Arial", 13, "bold"), fg=color)
            daily_lbl.pack(side=tk.LEFT, padx=(0, 3))
            refs['daily'] = daily_lbl
            refs['_old_price'] = price_text
            self._macro_label_refs[name] = refs
            if info.get('monthly') is not None:
                m = info['monthly']
                mc = "#4CAF50" if m >= 0 else "#f44336"
                tk.Label(item_frame, text=f"({m:+.1f}%)", font=("Arial", 11), fg=mc).pack(side=tk.LEFT)
            if i < len(names) - 1:
                ttk.Separator(parent, orient='vertical').pack(side=tk.LEFT, padx=4, fill=tk.Y, pady=2)

    def _update_macro_title(self):
        now_str = datetime.now().strftime("%H:%M:%S")
        today_str = date.today().strftime("%d.%m.%Y")
        self.macro_frame.config(text=f"Piyasa Göstergeleri  •  Yahoo Finance  •  {today_str} {now_str}")

    def _refresh_macro_data(self):
        self.macro_data = {}
        self._macro_label_refs = {}
        self._show_macro_loading("Güncelleniyor...")
        threading.Thread(target=self._load_macro_data, daemon=True).start()

    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Dosya", menu=file_menu)
        file_menu.add_command(label="CSV Yükle          ⌘O", command=self.load_file)
        file_menu.add_command(label="Ayarları Kaydet     ⌘S", command=self.save_settings)
        file_menu.add_command(label="Dışa Aktar (Excel)  ⌘E", command=self._export_to_excel)
        file_menu.add_separator()
        file_menu.add_command(label="Önbelleği Temizle", command=self._clear_cache)
        file_menu.add_separator()
        file_menu.add_command(label="Çıkış              ⌘Q", command=self.on_exit)

        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Görünüm", menu=view_menu)
        view_menu.add_command(label="Font Boyutu Artır (+)",
                              command=lambda: self.change_font_size(1))
        view_menu.add_command(label="Font Boyutu Azalt (-)",
                              command=lambda: self.change_font_size(-1))
        view_menu.add_separator()
        view_menu.add_command(label="Sütunları Sıfırla",
                              command=self.reset_columns)

        analysis_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Analiz", menu=analysis_menu)
        analysis_menu.add_command(label="Öngörü Hesapla",
                                  command=self._calculate_forecasts)
        analysis_menu.add_command(label="En İyi 10 Fon",
                                  command=self._show_top_funds_dialog)
        analysis_menu.add_separator()
        analysis_menu.add_command(label="Piyasa Rejimi",
                                  command=self._show_regime_dialog)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Yardım", menu=help_menu)
        help_menu.add_command(label="Yardım", command=self.show_help)
        help_menu.add_command(label="Klavye Kısayolları", command=self._show_shortcuts)

    def setup_table_styles(self):
        """Treeview stillerini bir kez ayarla"""
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self._update_tree_styles()

    def _update_tree_styles(self):
        """Font boyutu değiştiğinde çağır"""
        self.style.configure("Treeview.Heading",
                            background="#4CAF50",
                            foreground="white",
                            font=("Arial", self.tree_font_size, "bold"),
                            padding=12)

        self.style.configure("Treeview",
                            font=("Arial", self.tree_font_size),
                            rowheight=28 + (self.tree_font_size - 12) * 2,
                            padding=5)

        self.style.map('Treeview',
                      background=[('selected', '#0078D7')],
                      foreground=[('selected', 'white')])

    def setup_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # macOS için uyumlu tam ekran
        try:
            if self.root.tk.call('tk', 'windowingsystem') == 'aqua':
                self.root.attributes('-zoomed', True)
            else:
                self.root.state('zoomed')
        except Exception:
            pass  # Pencere boyutu geometry ile ayarlandı

        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)

        self.setup_table_styles()
        self.create_frames()
        self.create_widgets()

        self.create_table()

        self.load_initial_settings()
        self.setup_auto_save()
        self._bind_keyboard_shortcuts()

    def _bind_keyboard_shortcuts(self):
        """Klavye kısayollarını bağla"""
        # macOS: Command, diğer: Control
        mod = "Command" if self.root.tk.call('tk', 'windowingsystem') == 'aqua' else "Control"

        self.root.bind(f"<{mod}-o>", lambda e: self.load_file())
        self.root.bind(f"<{mod}-s>", lambda e: self.save_settings())
        self.root.bind(f"<{mod}-f>", lambda e: self._focus_search())
        self.root.bind(f"<{mod}-e>", lambda e: self._export_to_excel())
        self.root.bind(f"<{mod}-q>", lambda e: self.on_exit())
        self.root.bind("<Escape>", lambda e: self._clear_all_filters())

    def _focus_search(self):
        """Fon Bul kutusuna odaklan"""
        if hasattr(self, 'search_entry'):
            self.search_entry.focus_set()
            self.search_entry.select_range(0, tk.END)

    def _clear_all_filters(self):
        """Tüm filtreleri temizle (Escape)"""
        self.search_var.set("")
        self.filter_entry.delete(0, tk.END)
        if self._fund_type_filter:
            self._fund_type_filter = set()
            self.tree.heading("Fon Türü", text="Fon Türü",
                              command=lambda: self._on_heading_click("Fon Türü"))
        if self.df is not None:
            self.update_table()

    def _export_to_excel(self):
        """Görünen tabloyu Excel/CSV olarak dışa aktar"""
        if self.df is None:
            messagebox.showwarning("Uyarı", "Önce CSV dosyası yükleyin.")
            return

        # Mevcut treeview'daki verileri topla
        rows = []
        for item in self.tree.get_children():
            rows.append(self.tree.item(item)['values'])

        if not rows:
            messagebox.showwarning("Uyarı", "Tabloda görünen veri yok.")
            return

        # Kaydet dialogu
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
            title="Tabloyu Dışa Aktar",
            initialfile=f"TEFAS_Analiz_{date.today().strftime('%Y%m%d')}"
        )
        if not file_path:
            return

        try:
            export_df = pd.DataFrame(rows, columns=self.table_columns)

            if file_path.endswith('.xlsx'):
                try:
                    export_df.to_excel(file_path, index=False, engine='openpyxl')
                except ImportError:
                    # openpyxl yoksa CSV olarak kaydet
                    file_path = file_path.replace('.xlsx', '.csv')
                    export_df.to_csv(file_path, index=False, encoding='utf-8-sig')
                    messagebox.showinfo("Bilgi",
                        f"openpyxl kurulu olmadığı için CSV olarak kaydedildi:\n{file_path}")
                    return
            else:
                export_df.to_csv(file_path, index=False, encoding='utf-8-sig')

            messagebox.showinfo("Başarılı",
                f"{len(rows)} satır dışa aktarıldı:\n{file_path}")
        except Exception as e:
            self.handle_error(f"Dışa aktarma hatası: {str(e)}")

    def create_frames(self):
        self.top_frame = ttk.Frame(self.root)
        self.top_frame.pack(fill=tk.X, pady=2)

        self.filter_frame = ttk.Frame(self.root)
        self.filter_frame.pack(fill=tk.X, pady=2)

        self.middle_frame = ttk.Frame(self.root)
        self.middle_frame.pack(fill=tk.X, pady=2)



    def create_widgets(self):
        self.create_fund_entries()
        self.create_buttons()
        self.create_filter_widgets()
        self.create_performance_controls()

    def create_macro_panel(self):
        """Piyasa göstergeleri bandını oluştur"""
        self.macro_labels = {}

        # Cache'ten varsa direkt göster (kendi widget'larını oluşturur)
        if self.macro_data:
            self._display_macro_data()
            # Cache'den gösterilse bile otomatik yenileme döngüsünü başlat
            self._schedule_macro_refresh()
        else:
            # Yükleniyor mesajı + yenile butonu göster
            self._show_macro_loading(
                "Piyasa verileri yükleniyor..." if HAS_YFINANCE
                else "yfinance kurulu değil (pip install yfinance)"
            )
            if HAS_YFINANCE:
                threading.Thread(target=self._load_macro_data, daemon=True).start()

    def _show_macro_loading(self, message="Güncelleniyor..."):
        """Makro bandında yükleniyor/mesaj durumunu göster"""
        for widget in self.macro_frame.winfo_children():
            widget.destroy()

        row = ttk.Frame(self.macro_frame)
        row.pack(fill=tk.X, expand=True)

        tk.Label(
            row, text=message,
            font=("Arial", 13, "italic"), fg="gray"
        ).pack(side=tk.LEFT, padx=10)

        ttk.Button(
            row, text="↻ Yenile",
            command=self._refresh_macro_data, width=10
        ).pack(side=tk.RIGHT, padx=5)

    def create_fund_entries(self):
        # ── Fon Yönetimi Grubu ──
        fund_group = ttk.LabelFrame(self.top_frame, text="Fon Yönetimi", padding=4)
        fund_group.pack(side=tk.LEFT, padx=5, fill=tk.Y)

        tk.Label(fund_group, text="Mevcut:", font=("Arial", 12, "bold"),
                 fg="red").pack(side=tk.LEFT, padx=2)
        self.mevcut_fonlar_text = tk.Entry(fund_group, width=18)
        self.mevcut_fonlar_text.pack(side=tk.LEFT, padx=2)

        tk.Label(fund_group, text="Planlanan:", font=("Arial", 12, "bold"),
                 fg="blue").pack(side=tk.LEFT, padx=2)
        self.planlanan_fonlar_text = tk.Entry(fund_group, width=18)
        self.planlanan_fonlar_text.pack(side=tk.LEFT, padx=2)

        # Fon Bul — aynı satırda, fon yönetiminin yanında
        ttk.Separator(fund_group, orient='vertical').pack(side=tk.LEFT, padx=6, fill=tk.Y)

        tk.Label(fund_group, text="Fon Bul:", font=("Arial", 12, "bold"),
                 fg="#555").pack(side=tk.LEFT, padx=2)

        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self._on_search_change)

        self.search_entry = ttk.Entry(fund_group, textvariable=self.search_var, width=18)
        self.search_entry.pack(side=tk.LEFT, padx=2)

        self.clear_search_btn = ttk.Button(fund_group, text="✕", width=3,
                                           command=self._clear_search)
        self.clear_search_btn.pack(side=tk.LEFT)

    def create_buttons(self):
        # ── Dosya İşlemleri Grubu ──
        file_group = ttk.LabelFrame(self.top_frame, text="Dosya", padding=4)
        file_group.pack(side=tk.LEFT, padx=5, fill=tk.Y)

        ttk.Button(file_group, text="Dosya Seç",
                   command=self.load_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(file_group, text="Kaydet",
                   command=self.save_settings).pack(side=tk.LEFT, padx=2)

        # ── Veri İşlemleri Grubu ──
        data_group = ttk.LabelFrame(self.top_frame, text="Veri", padding=4)
        data_group.pack(side=tk.LEFT, padx=5, fill=tk.Y)

        self.fetch_daily_btn = ttk.Button(data_group, text="Günlük Getiri Çek",
                                          command=self._start_batch_fetch)
        self.fetch_daily_btn.pack(side=tk.LEFT, padx=2)

        self.cancel_fetch_btn = ttk.Button(data_group, text="İptal",
                                           command=self._cancel_batch_fetch)
        # İptal butonu başlangıçta gizli

        # İlerleme göstergesi (başlangıçta gizli)
        self.progress_frame = ttk.Frame(data_group)
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, mode='determinate', length=150
        )
        self.progress_bar.pack(side=tk.LEFT, padx=3)
        self.progress_label = tk.Label(
            self.progress_frame, text="", font=("Arial", 12), fg="#555"
        )
        self.progress_label.pack(side=tk.LEFT, padx=3)

        # ── Uygulama Grubu (sağ taraf) ──
        app_group = ttk.Frame(self.top_frame)
        app_group.pack(side=tk.RIGHT, padx=5)

        ttk.Button(app_group, text="Yardım",
                   command=self.show_help).pack(side=tk.LEFT, padx=2)
        ttk.Button(app_group, text="Çıkış",
                   command=self.on_exit).pack(side=tk.LEFT, padx=2)

    def create_filter_widgets(self):
        tk.Label(self.filter_frame,
                 text="Fon Kodları (virgülle ayırarak):",
                 font=("Arial", 12, "bold")).pack(side=tk.LEFT, padx=5)

        self.filter_entry = tk.Entry(self.filter_frame, width=40)
        self.filter_entry.pack(side=tk.LEFT, padx=5)
        self.filter_entry.config(state=tk.DISABLED)
        self.filter_entry.bind("<Return>", lambda e: self.apply_filter())

        self.filter_button = ttk.Button(self.filter_frame,
                                        text="Filtrele",
                                        command=self.apply_filter)
        self.filter_button.pack(side=tk.LEFT, padx=5)
        self.filter_button.config(state=tk.DISABLED)

        self.clear_filter_button = ttk.Button(self.filter_frame,
                                              text="Filtreyi Temizle",
                                              command=self.clear_filter)
        self.clear_filter_button.pack(side=tk.LEFT, padx=5)
        self.clear_filter_button.config(state=tk.DISABLED)

        self.add_current_button = ttk.Button(
            self.filter_frame,
            text="Mevcut Fonları Ekle",
            command=lambda: self.add_to_filter(
                [f.strip() for f in self.mevcut_fonlar_text.get().split(',') if f.strip()]
            )
        )
        self.add_current_button.pack(side=tk.LEFT, padx=5)
        self.add_current_button.config(state=tk.DISABLED)

        self.add_planned_button = ttk.Button(
            self.filter_frame,
            text="Planlanan Fonları Ekle",
            command=lambda: self.add_to_filter(
                [f.strip() for f in self.planlanan_fonlar_text.get().split(',') if f.strip()]
            )
        )
        self.add_planned_button.pack(side=tk.LEFT, padx=5)
        self.add_planned_button.config(state=tk.DISABLED)

        self.add_forecast_button = ttk.Button(
            self.filter_frame,
            text="Öngörü Fonları Ekle",
            command=self._add_forecast_funds_to_filter
        )
        self.add_forecast_button.pack(side=tk.LEFT, padx=5)
        self.add_forecast_button.config(state=tk.DISABLED)

    def create_performance_controls(self):
        for col in self.performance_columns:
            frame = ttk.Frame(self.middle_frame)
            frame.pack(side=tk.LEFT, padx=5)
            self.controls[col] = self.create_control(frame, col, 2)

        # ── Skor & Öngörü Grubu — performans kontrollerinin sağında ──
        ttk.Separator(self.middle_frame, orient='vertical').pack(side=tk.LEFT, padx=8, fill=tk.Y)

        score_group = ttk.LabelFrame(self.middle_frame, text="Hesaplama", padding=4)
        score_group.pack(side=tk.LEFT, padx=5, fill=tk.Y)

        self.weight_sum_label = tk.Label(score_group,
                                         text="Ağırlık: 10",
                                         font=("Arial", 12),
                                         fg="green")
        self.weight_sum_label.pack(side=tk.LEFT, padx=3)

        ttk.Button(score_group, text="Eşitle",
                   command=self.equalize_weights).pack(side=tk.LEFT, padx=2)
        ttk.Button(score_group, text="Skor Hesapla",
                   command=self.calculate_scores).pack(side=tk.LEFT, padx=2)
        ttk.Button(score_group, text="Öngörü Hesapla",
                   command=self._calculate_forecasts).pack(side=tk.LEFT, padx=2)

    def create_control(self, frame, col, default_weight):
        var = tk.BooleanVar(value=True)
        var.trace_add('write', self.update_weight_sum)
        checkbox = ttk.Checkbutton(frame, text=col, variable=var)
        checkbox.pack()

        weight_var = tk.StringVar(value=str(default_weight))
        weight_var.trace_add('write', self.update_weight_sum)
        textbox = ttk.Entry(frame, textvariable=weight_var, width=5)
        textbox.pack()

        return var, weight_var


    def _on_search_change(self, *args):
        """Arama kutusu değiştiğinde çağrılır - anlık arama"""
        if self.df is None:
            return

        search_text = self.search_var.get().strip().upper()

        if search_text:
            # Fon Adı sütununda ara
            self._update_table_with_search(search_text)
        else:
            # Arama boşsa normal filtreyi uygula
            self.update_table(self.filter_entry.get() if self.filter_entry else None)

    def _update_table_with_search(self, search_text):
        """Fon adında arama yaparak tabloyu güncelle"""
        if self.df is None:
            return
        df_view = self.df[self.df['Fon Adı'].str.upper().str.contains(search_text, na=False)]
        # Fon türü filtresi de uygula
        if self._fund_type_filter:
            df_view = df_view[df_view['Fon Türü'].isin(self._fund_type_filter)]
        self._render_table(df_view)

    def _clear_search(self):
        """Arama kutusunu temizle"""
        self.search_var.set("")
        if self.df is not None:
            self.update_table(self.filter_entry.get() if self.filter_entry else None)

    def update_weight_sum(self, *args):
        """Ağırlık toplamını güncelle ve renkle göster"""
        total_weight = 0
        for col, (var, weight_var) in self.controls.items():
            if var.get():
                try:
                    weight = float(weight_var.get())
                    total_weight += weight
                except ValueError:
                    pass

        color = "green" if abs(total_weight - 10.0) <= Config.WEIGHT_TOLERANCE else "red"
        self.weight_sum_label.config(text=f"Ağırlık: {total_weight:.1f}", fg=color)

    def create_table(self):
        """Treeview ile optimized tablo oluştur - sağda detay paneli, altta makro göstergeleri"""
        self.table_columns = [
                                 "Sıra", "Fon Kodu", "Fon Adı", "Fon Türü"
                             ] + self.performance_columns + ["Skor", "Tür Sırası", "Günlük (%)", "Öngörü"]

        # ── Durum Çubuğu — en altta sabit (main_paned'den önce pack edilmeli) ──
        self._create_status_bar()

        # Ana dikey PanedWindow: üstte tablo+detay, altta makro göstergeleri
        self.main_paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, pady=2)

        # Üst kısım: yatay PanedWindow (tablo + detay)
        self.content_frame = ttk.PanedWindow(self.main_paned, orient=tk.HORIZONTAL)

        # Sol taraf - Tablo
        self.table_frame = ttk.Frame(self.content_frame)

        scrollbar = ttk.Scrollbar(self.table_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree = ttk.Treeview(
            self.table_frame,
            columns=self.table_columns,
            height=20,
            yscrollcommand=scrollbar.set,
            show='headings'
        )
        scrollbar.config(command=self.tree.yview)

        for col in self.table_columns:
            width = self.config.COLUMN_WIDTHS.get(col, 100)
            self.tree.column(col, width=width, minwidth=50, anchor="center", stretch=True)
            self.tree.heading(col, text=col, command=lambda c=col: self._on_heading_click(c))

        self.tree.pack(fill=tk.BOTH, expand=True)

        # Tek tıklama - detay panelinde göster
        self.tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        # Çift tıklama - tarayıcıda aç
        self.tree.bind('<Double-1>', self._on_tree_double_click)
        # Sağ tıklama - bağlam menüsü (macOS: Button-2, diğer: Button-3)
        self.tree.bind('<Button-2>', self._on_tree_right_click)
        self.tree.bind('<Button-3>', self._on_tree_right_click)

        self.content_frame.add(self.table_frame, weight=4)

        # Sağ taraf - Detay Paneli
        self.detail_frame = ttk.Frame(self.content_frame, width=350)
        self._create_detail_panel()
        self.content_frame.add(self.detail_frame, weight=2)

        # Sağ panelin minimum genişliğini zorla
        self.detail_frame.pack_propagate(False)

        # Üst kısmı (tablo+detay) dikey PanedWindow'a ekle
        self.main_paned.add(self.content_frame, weight=10)

        # Alt kısım: Makro Göstergeleri (boyutlandırılabilir)
        # macro_frame'in parent'ı main_paned olmalı
        self.macro_frame = ttk.LabelFrame(self.main_paned, text="Piyasa Göstergeleri", padding=8)
        self.main_paned.add(self.macro_frame, weight=1)

        # Makro paneli içeriğini oluştur (veri çekmeyi başlat)
        self.create_macro_panel()


        self.root.update_idletasks()
        # PanedWindow sash pozisyonlarını ayarla (pencere render'ı tamamlandıktan sonra)
        self._sash_initialized = False
        self.root.after(200, lambda: self._set_initial_sash_positions())
        # Pencere boyutu değiştiğinde de sash'ı düzelt (tam ekran geçişi için)
        self.main_paned.bind('<Configure>', self._on_main_paned_configure)

    def _create_status_bar(self):
        """Pencerenin en altına durum çubuğu ekle"""
        status_frame = tk.Frame(self.root, bd=1, relief=tk.SUNKEN)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self._status_var = tk.StringVar(value="Hazır — CSV dosyası yükleyin")
        status_label = tk.Label(
            status_frame, textvariable=self._status_var,
            font=("Arial", 11), fg="#555", anchor="w", padx=8, pady=3
        )
        status_label.pack(fill=tk.X)

    def _update_status_bar(self):
        """Durum çubuğunu güncel bilgilerle güncelle"""
        if self._status_var is None:
            return

        parts = []

        # Toplam fon sayısı
        total = len(self.df) if self.df is not None else 0
        if total > 0:
            parts.append(f"📊 {total} fon")

            # Görünen satır sayısı
            if self._visible_count != total:
                parts.append(f"👁 {self._visible_count} görünür")

            # Aktif filtreler
            filters = []
            filter_text = self.filter_entry.get().strip() if self.filter_entry else ""
            if filter_text:
                count = len([c for c in filter_text.split(',') if c.strip()])
                filters.append(f"{count} fon kodu")
            if self._fund_type_filter:
                filters.append(f"{len(self._fund_type_filter)} tür")
            search_text = self.search_var.get().strip() if hasattr(self, 'search_var') else ""
            if search_text:
                filters.append(f'"{search_text}"')
            if filters:
                parts.append(f"🔍 Filtre: {', '.join(filters)}")
        else:
            parts.append("CSV dosyası yükleyin")

        # Piyasa rejimi
        if HAS_STRATEGY and self.strategy:
            regime_label, _ = self.strategy.get_regime_label()
            parts.append(f"Rejim: {regime_label}")

        # Önbellek durumu
        cached = len(self.daily_return_cache)
        if cached > 0:
            parts.append(f"💾 Önbellek: {cached} fon")

        # Saat
        parts.append(f"⏱ {datetime.now().strftime('%H:%M')}")

        self._status_var.set("  │  ".join(parts))

    def _create_detail_panel(self):
        """Sağ taraftaki detay panelini oluştur - sekmeli yapı"""
        # Başlık satırı: fon adı + TEFAS butonu (sabit, sekme dışı)
        title_row = ttk.Frame(self.detail_frame)
        title_row.pack(fill=tk.X, pady=(8, 4), padx=5)

        self.detail_title = tk.Label(
            title_row,
            text="Fon Detayları",
            font=("Arial", 14, "bold"),
            fg="#4CAF50"
        )
        self.detail_title.pack(side=tk.LEFT)

        # TEFAS butonu — başlık yanında sabit
        self._tefas_btn = ttk.Button(
            title_row, text="TEFAS'ta Aç",
            command=self._open_selected_fund
        )
        # Başlangıçta gizli, fon seçildiğinde gösterilecek

        # Notebook (sekmeli yapı)
        self.detail_notebook = ttk.Notebook(self.detail_frame)
        self.detail_notebook.pack(fill=tk.BOTH, expand=True)

        # ── Sekme 1: Varlık Dağılımı ──
        self._alloc_tab = ttk.Frame(self.detail_notebook)
        self.detail_notebook.add(self._alloc_tab, text="  Varlık Dağılımı  ")
        self._create_scrollable_tab(self._alloc_tab, "_alloc")

        # ── Sekme 2: Öngörü Analizi ──
        self._forecast_tab = ttk.Frame(self.detail_notebook)
        self.detail_notebook.add(self._forecast_tab, text="  Öngörü Analizi  ")
        self._create_scrollable_tab(self._forecast_tab, "_forecast")

        # ── Sekme 3: Portföy Özeti ──
        self._portfolio_tab = ttk.Frame(self.detail_notebook)
        self.detail_notebook.add(self._portfolio_tab, text="  Portföy Özeti  ")
        self._create_scrollable_tab(self._portfolio_tab, "_portfolio")

        # Başlangıç mesajı
        self.detail_message = tk.Label(
            self._alloc_content,
            text="Bir fon seçin...",
            font=("Arial", 13, "italic"),
            fg="gray"
        )
        self.detail_message.pack(expand=True, pady=50)

        self._forecast_message = tk.Label(
            self._forecast_content,
            text="Bir fon seçin...",
            font=("Arial", 13, "italic"),
            fg="gray"
        )
        self._forecast_message.pack(expand=True, pady=50)

        # Portföy Özeti başlangıç mesajı
        self._portfolio_message = tk.Label(
            self._portfolio_content,
            text="Mevcut fonlarınızı tanımlayın\nve varlık verilerini çekin.",
            font=("Arial", 13, "italic"),
            fg="gray",
            justify="center"
        )
        self._portfolio_message.pack(expand=True, pady=50)

        # Portföy sekmesi ilk gösterimde güncelle
        self.detail_notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.selected_fund_code = None

    def _create_scrollable_tab(self, parent, prefix):
        """Sekme için scrollable alan oluştur"""
        scroll_container = ttk.Frame(parent)
        scroll_container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(scroll_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)

        content = ttk.Frame(canvas)
        content.bind(
            "<Configure>",
            lambda e, c=canvas: c.configure(scrollregion=c.bbox("all"))
        )

        canvas_window = canvas.create_window((0, 0), window=content, anchor="nw")

        def _on_canvas_resize(event, c=canvas, cw=canvas_window):
            c.itemconfig(cw, width=event.width)
        canvas.bind("<Configure>", _on_canvas_resize)

        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Mousewheel desteği
        def _on_mousewheel(event, c=canvas):
            c.yview_scroll(int(-1 * (event.delta)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
        content.bind("<MouseWheel>", _on_mousewheel)

        # Referansları kaydet
        setattr(self, f"{prefix}_canvas", canvas)
        setattr(self, f"{prefix}_scrollbar", scrollbar)
        setattr(self, f"{prefix}_content", content)
        setattr(self, f"{prefix}_canvas_window", canvas_window)
        setattr(self, f"{prefix}_mousewheel_handler", _on_mousewheel)

    def _on_tab_changed(self, event=None):
        """Sekme değiştiğinde Portföy Özeti sekmesini güncelle"""
        try:
            current = self.detail_notebook.index(self.detail_notebook.select())
            if current == 2:  # Portföy Özeti sekmesi
                self._display_portfolio_summary()
        except Exception:
            pass

    def _display_portfolio_summary(self):
        """Mevcut/Planlanan fonların portföy değer takibi ve birleşik varlık dağılımını göster"""
        content = self._portfolio_content
        mw_handler = self._portfolio_mousewheel_handler

        # İçeriği temizle
        for widget in content.winfo_children():
            widget.destroy()

        # ── Radio butonlar: Mevcut / Planlanan ──
        radio_frame = ttk.Frame(content)
        radio_frame.pack(fill=tk.X, padx=10, pady=(8, 4))

        if not hasattr(self, '_portfolio_mode'):
            self._portfolio_mode = tk.StringVar(value="mevcut")

        tk.Radiobutton(
            radio_frame, text="Mevcut Fonlar", variable=self._portfolio_mode,
            value="mevcut", font=("Arial", 12, "bold"), fg="red",
            command=self._display_portfolio_summary
        ).pack(side=tk.LEFT, padx=(0, 15))

        tk.Radiobutton(
            radio_frame, text="Planlanan Fonlar", variable=self._portfolio_mode,
            value="planlanan", font=("Arial", 12, "bold"), fg="blue",
            command=self._display_portfolio_summary
        ).pack(side=tk.LEFT)

        # Hangi grup seçili?
        mode = self._portfolio_mode.get()
        if mode == "mevcut":
            target_funds = self.highlight_funds
            mode_label = "Mevcut"
            mode_color = "red"
        else:
            target_funds = self.planned_funds
            mode_label = "Planlanan"
            mode_color = "blue"

        # Fonları kontrol et
        if not target_funds:
            tk.Label(content, text=f"{mode_label} fonlarınız tanımlı değil.\n\n"
                     "Fon Yönetimi kutusuna\nfon kodlarını girin ve kaydedin.",
                     font=("Arial", 13), fg="gray", justify="center").pack(pady=40)
            return

        # ── Fon kodları listesi ──
        codes_frame = ttk.Frame(content)
        codes_frame.pack(fill=tk.X, padx=10, pady=(2, 6))

        tk.Label(codes_frame, text=f"{mode_label} Fonlar:",
                 font=("Arial", 11, "bold"), fg=mode_color).pack(side=tk.LEFT, padx=(0, 5))
        codes_text = ", ".join(sorted(target_funds))
        tk.Label(codes_frame, text=codes_text,
                 font=("Arial", 11), fg="#555", wraplength=280,
                 justify="left").pack(side=tk.LEFT, fill=tk.X)

        ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=5, pady=4)

        # ══════════════════════════════════════════
        # PORTFÖY DEĞER TAKİBİ BÖLÜMÜ
        # ══════════════════════════════════════════

        pv_header = ttk.Frame(content)
        pv_header.pack(fill=tk.X, padx=10, pady=(6, 2))
        tk.Label(pv_header, text="💰 Portföy Değer Takibi",
                 font=("Arial", 14, "bold"), fg="#4CAF50").pack(anchor="w")

        # Toplam portföy değeri girişi
        pv_input_frame = ttk.Frame(content)
        pv_input_frame.pack(fill=tk.X, padx=10, pady=(4, 6))

        tk.Label(pv_input_frame, text="Toplam Değer (TL):",
                 font=("Arial", 12, "bold"), fg="#555").pack(side=tk.LEFT, padx=(0, 5))

        self._pv_entry_var = tk.StringVar(
            value=f"{self.portfolio_total_value:,.0f}" if self.portfolio_total_value > 0 else ""
        )
        pv_entry = ttk.Entry(pv_input_frame, textvariable=self._pv_entry_var, width=18,
                             font=("Arial", 13))
        pv_entry.pack(side=tk.LEFT, padx=(0, 5))
        pv_entry.bind("<Return>", lambda e: self._apply_portfolio_values())

        ttk.Button(pv_input_frame, text="Uygula",
                   command=self._apply_portfolio_values).pack(side=tk.LEFT, padx=2)
        ttk.Button(pv_input_frame, text="Eşitle",
                   command=lambda: self._equalize_fund_distribution(target_funds)
                   ).pack(side=tk.LEFT, padx=2)

        # ── Fon dağılımı girişleri ──
        dist_header = ttk.Frame(content)
        dist_header.pack(fill=tk.X, padx=10, pady=(4, 2))

        tk.Label(dist_header, text="Fon", font=("Arial", 11, "bold"),
                 fg="#555", width=8, anchor="w").pack(side=tk.LEFT)
        tk.Label(dist_header, text="Dağılım %", font=("Arial", 11, "bold"),
                 fg="#555", width=8, anchor="center").pack(side=tk.LEFT, padx=(0, 5))
        tk.Label(dist_header, text="TL Değer", font=("Arial", 11, "bold"),
                 fg="#555", width=14, anchor="e").pack(side=tk.LEFT)

        self._dist_entries = {}  # {fon_kodu: StringVar}
        self._dist_tl_labels = {}  # {fon_kodu: Label}

        sorted_funds = sorted(target_funds)
        for fon_kodu in sorted_funds:
            row_f = ttk.Frame(content)
            row_f.pack(fill=tk.X, padx=10, pady=2)

            # Fon kodu etiketi
            tk.Label(row_f, text=fon_kodu, font=("Arial", 12, "bold"),
                     fg=mode_color, width=8, anchor="w").pack(side=tk.LEFT)

            # Yüzde girişi
            saved_pct = self.fund_distribution.get(fon_kodu, 0)
            pct_var = tk.StringVar(value=f"{saved_pct:.1f}" if saved_pct > 0 else "")
            pct_entry = ttk.Entry(row_f, textvariable=pct_var, width=8,
                                  font=("Arial", 12), justify="center")
            pct_entry.pack(side=tk.LEFT, padx=(0, 5))
            pct_entry.bind("<Return>", lambda e: self._apply_portfolio_values())
            self._dist_entries[fon_kodu] = pct_var

            # TL değer etiketi
            tl_val = self.portfolio_total_value * (saved_pct / 100) if saved_pct > 0 else 0
            tl_text = f"{tl_val:,.0f} ₺" if tl_val > 0 else "—"
            tl_lbl = tk.Label(row_f, text=tl_text, font=("Arial", 12),
                              fg="#333", width=14, anchor="e")
            tl_lbl.pack(side=tk.LEFT)
            self._dist_tl_labels[fon_kodu] = tl_lbl

            for w in row_f.winfo_children():
                w.bind("<MouseWheel>", mw_handler)

        # Toplam yüzde göstergesi
        total_pct_frame = ttk.Frame(content)
        total_pct_frame.pack(fill=tk.X, padx=10, pady=(4, 2))

        total_pct = sum(
            self.fund_distribution.get(f, 0) for f in sorted_funds
        )
        pct_color = "#4CAF50" if abs(total_pct - 100) < 0.5 else "#f44336"
        self._total_pct_label = tk.Label(
            total_pct_frame,
            text=f"Toplam Dağılım: %{total_pct:.1f}" + (" ✓" if abs(total_pct - 100) < 0.5 else " ⚠"),
            font=("Arial", 12, "bold"), fg=pct_color
        )
        self._total_pct_label.pack(side=tk.LEFT)

        if self.portfolio_total_value > 0:
            tk.Label(total_pct_frame, text=f"  |  Portföy: {self.portfolio_total_value:,.0f} ₺",
                     font=("Arial", 12), fg="#555").pack(side=tk.LEFT, padx=(10, 0))

        # ── Dönemsel TL Getiri Tablosu ──
        if self.portfolio_total_value > 0 and self.df is not None and total_pct > 0:
            ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=5, pady=6)

            tk.Label(content, text="📊 Dönemsel Getiri (TL)",
                     font=("Arial", 13, "bold"), fg="#4CAF50").pack(anchor="w", padx=10, pady=(2, 4))

            # Tablo başlığı
            ret_header = ttk.Frame(content)
            ret_header.pack(fill=tk.X, padx=10, pady=(0, 2))

            tk.Label(ret_header, text="Fon", font=("Arial", 11, "bold"),
                     fg="#555", width=7, anchor="w").pack(side=tk.LEFT)
            for col_name, label, _ in self.config.PORTFOLIO_PERIODS:
                tk.Label(ret_header, text=label, font=("Arial", 10, "bold"),
                         fg="#555", width=10, anchor="center").pack(side=tk.LEFT)

            ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=10)

            # Her fon için getiri satırı
            period_totals = {col_name: 0.0 for col_name, _, _ in self.config.PORTFOLIO_PERIODS}

            for fon_kodu in sorted_funds:
                pct = self.fund_distribution.get(fon_kodu, 0)
                if pct <= 0:
                    continue

                fon_tl = self.portfolio_total_value * (pct / 100)

                row_f = ttk.Frame(content)
                row_f.pack(fill=tk.X, padx=10, pady=1)

                tk.Label(row_f, text=fon_kodu, font=("Arial", 11, "bold"),
                         fg=mode_color, width=7, anchor="w").pack(side=tk.LEFT)

                # DataFrame'den fon verilerini al
                fon_row = None
                if self.df is not None:
                    fon_data = self.df[self.df['Fon Kodu'].str.strip() == fon_kodu]
                    if not fon_data.empty:
                        fon_row = fon_data.iloc[0]

                for col_name, label, months in self.config.PORTFOLIO_PERIODS:
                    if fon_row is not None:
                        pct_val = fon_row.get(col_name, 0)
                        if isinstance(pct_val, (int, float)) and pct_val != 0:
                            tl_getiri = fon_tl * (pct_val / 100)
                            period_totals[col_name] += tl_getiri
                            color = "#4CAF50" if tl_getiri >= 0 else "#f44336"
                            sign = "+" if tl_getiri >= 0 else ""
                            text = f"{sign}{tl_getiri:,.0f}"
                        else:
                            text = "—"
                            color = "#999"
                    else:
                        text = "—"
                        color = "#999"

                    lbl = tk.Label(row_f, text=text, font=("Arial", 10),
                                   fg=color, width=10, anchor="center")
                    lbl.pack(side=tk.LEFT)

                for w in row_f.winfo_children():
                    w.bind("<MouseWheel>", mw_handler)

            # Toplam satırı
            ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=10)
            total_row = ttk.Frame(content)
            total_row.pack(fill=tk.X, padx=10, pady=2)

            tk.Label(total_row, text="TOPLAM", font=("Arial", 11, "bold"),
                     fg="#333", width=7, anchor="w").pack(side=tk.LEFT)

            for col_name, label, _ in self.config.PORTFOLIO_PERIODS:
                total_tl = period_totals[col_name]
                if total_tl != 0:
                    color = "#4CAF50" if total_tl >= 0 else "#f44336"
                    sign = "+" if total_tl >= 0 else ""
                    text = f"{sign}{total_tl:,.0f}"
                else:
                    text = "—"
                    color = "#999"

                tk.Label(total_row, text=text, font=("Arial", 10, "bold"),
                         fg=color, width=10, anchor="center").pack(side=tk.LEFT)

            for w in total_row.winfo_children():
                w.bind("<MouseWheel>", mw_handler)

            # Günlük getiri varsa ekle
            daily_frame = ttk.Frame(content)
            daily_frame.pack(fill=tk.X, padx=10, pady=(6, 2))

            has_daily = False
            total_daily_tl = 0.0
            for fon_kodu in sorted_funds:
                pct = self.fund_distribution.get(fon_kodu, 0)
                daily = self.daily_return_cache.get(fon_kodu, "")
                if pct > 0 and daily and daily not in ("N/A", "Hata", ""):
                    try:
                        daily_val = float(daily.replace('%', '').replace(',', '.').strip())
                        fon_tl = self.portfolio_total_value * (pct / 100)
                        daily_tl = fon_tl * (daily_val / 100)
                        total_daily_tl += daily_tl
                        has_daily = True
                    except (ValueError, AttributeError):
                        pass

            if has_daily:
                d_color = "#4CAF50" if total_daily_tl >= 0 else "#f44336"
                d_sign = "+" if total_daily_tl >= 0 else ""
                tk.Label(daily_frame, text="Bugünkü Değişim:",
                         font=("Arial", 12, "bold"), fg="#555").pack(side=tk.LEFT)
                tk.Label(daily_frame, text=f"{d_sign}{total_daily_tl:,.0f} ₺",
                         font=("Arial", 14, "bold"), fg=d_color).pack(side=tk.LEFT, padx=8)

        ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=5, pady=8)

        # ══════════════════════════════════════════
        # VARLIK DAĞILIMI ANALİZİ (mevcut özellik korunuyor)
        # ══════════════════════════════════════════

        # Cache'te kaç fonun varlık verisi var?
        available = {f: self.allocation_cache[f] for f in target_funds
                     if f in self.allocation_cache and self.allocation_cache[f]}
        missing = target_funds - set(available.keys())

        if not available:
            tk.Label(content, text=f"{mode_label} fonların varlık verileri\nhenüz çekilmemiş.\n\n"
                     "Her fona tıklayarak veya\n'Günlük Getiri Çek' ile verileri alın.",
                     font=("Arial", 13), fg="gray", justify="center").pack(pady=40)
            return

        # ── Birleşik varlık dağılımını hesapla ──
        combined = {}  # varlık_adı → toplam yüzde
        fund_count = len(available)

        for fon_kodu, alloc in available.items():
            # Fon dağılımında ağırlık varsa onu kullan, yoksa eşit ağırlık
            weight = self.fund_distribution.get(fon_kodu, 0) / 100 if self.fund_distribution.get(fon_kodu, 0) > 0 else 1 / fund_count
            for asset_name, data in alloc.items():
                pct = data.get('percentage', 0) if isinstance(data, dict) else float(data)
                if pct > 0:
                    weighted_pct = pct * weight
                    combined[asset_name] = combined.get(asset_name, 0) + weighted_pct

        if not combined:
            tk.Label(content, text="Varlık dağılımı verisi bulunamadı.",
                     font=("Arial", 13), fg="orange").pack(pady=30)
            return

        # Büyükten küçüğe sırala
        sorted_assets = sorted(combined.items(), key=lambda x: x[1], reverse=True)

        # Varlık sınıflarına grupla
        groups = {}
        GROUP_KEYWORDS = {
            "Altın / Kıymetli Maden": ["altın", "kıymetli maden", "gold", "madenler cinsinden"],
            "Hisse Senedi": ["hisse", "pay senedi"],
            "Tahvil / Borçlanma": ["tahvil", "borçlanma", "bono", "kira sertifika"],
            "Döviz / Mevduat": ["döviz", "mevduat", "katılma hesabı", "repo"],
            "Yatırım Fonları": ["yatırım fon", "borsa yatırım", "byf", "girişim sermayesi"],
        }

        for asset_name, pct in sorted_assets:
            grouped = False
            name_lower = asset_name.lower()
            for group_name, keywords in GROUP_KEYWORDS.items():
                if any(kw in name_lower for kw in keywords):
                    groups[group_name] = groups.get(group_name, 0) + pct
                    grouped = True
                    break
            if not grouped:
                groups["Diğer"] = groups.get("Diğer", 0) + pct

        sorted_groups = sorted(groups.items(), key=lambda x: x[1], reverse=True)

        # ── Başlık ──
        weight_method = "fon dağılımı ağırlıklı" if any(self.fund_distribution.get(f, 0) > 0 for f in target_funds) else "eşit ağırlıklı"
        tk.Label(content, text="Toplam Varlık Dağılımı",
                 font=("Arial", 14, "bold"), fg="#4CAF50").pack(pady=(6, 2))
        tk.Label(content, text=f"{fund_count} fonun birleşik dağılımı ({weight_method})",
                 font=("Arial", 12), fg="#999").pack(pady=(0, 8))

        if missing:
            tk.Label(content, text=f"⚠ {', '.join(sorted(missing))} verisi eksik",
                     font=("Arial", 12), fg="orange").pack(pady=(0, 5))

        # ── Gruplu yatay çubuklar ──
        GROUP_COLORS = {
            "Altın / Kıymetli Maden": "#FFD700",
            "Hisse Senedi": "#4572A7",
            "Tahvil / Borçlanma": "#89A54E",
            "Döviz / Mevduat": "#3D96AE",
            "Yatırım Fonları": "#80699B",
            "Diğer": "#DB843D",
        }

        for group_name, pct in sorted_groups:
            if pct < 0.1:
                continue

            row_f = ttk.Frame(content)
            row_f.pack(fill=tk.X, padx=10, pady=4)

            color = GROUP_COLORS.get(group_name, "#999")

            # Renk kutusu
            color_box = tk.Frame(row_f, width=14, height=14, bg=color)
            color_box.pack(side=tk.LEFT, padx=(0, 6))
            color_box.pack_propagate(False)

            # İsim
            tk.Label(row_f, text=group_name, font=("Arial", 12),
                     anchor="w", width=22).pack(side=tk.LEFT)

            # Çubuk
            bar_frame = tk.Frame(row_f, height=18, width=120, bg="#eee",
                                 highlightthickness=1, highlightbackground="#ddd")
            bar_frame.pack(side=tk.LEFT, padx=4)
            bar_frame.pack_propagate(False)

            bar_w = max(1, int(pct * 1.2))
            tk.Frame(bar_frame, width=bar_w, bg=color).pack(side=tk.LEFT, fill=tk.Y)

            # Yüzde
            tk.Label(row_f, text=f"%{pct:.1f}",
                     font=("Arial", 12, "bold"), fg=color).pack(side=tk.LEFT, padx=5)

            for w in row_f.winfo_children():
                w.bind("<MouseWheel>", mw_handler)

        ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=10, pady=10)

        # ── Detaylı liste ──
        tk.Label(content, text="Detaylı Varlık Dağılımı",
                 font=("Arial", 13, "bold"), fg="#555").pack(anchor="w", padx=10, pady=(0, 5))

        for asset_name, pct in sorted_assets:
            if pct < 0.05:
                continue
            row_f = ttk.Frame(content)
            row_f.pack(fill=tk.X, padx=15, pady=1)

            tk.Label(row_f, text=asset_name, font=("Arial", 12),
                     anchor="w", wraplength=220, justify="left").pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(row_f, text=f"%{pct:.2f}",
                     font=("Arial", 12, "bold"), fg="#555").pack(side=tk.RIGHT, padx=5)

            for w in row_f.winfo_children():
                w.bind("<MouseWheel>", mw_handler)

        ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=10, pady=10)

        # ── Basit uyarılar / öneriler ──
        tk.Label(content, text="💡 Değerlendirme",
                 font=("Arial", 13, "bold"), fg="#555").pack(anchor="w", padx=10, pady=(0, 5))

        warnings_list = []
        for group_name, pct in sorted_groups:
            if pct >= 50:
                warnings_list.append(
                    f"⚠️ Portföyünüzün %{pct:.0f}'i {group_name} ağırlıklı. "
                    f"Tek varlık sınıfına yoğunlaşma riski var."
                )

        if len(sorted_groups) <= 2:
            warnings_list.append(
                "⚠️ Portföyünüz sadece 1-2 varlık sınıfına dağılmış. "
                "Daha fazla çeşitlendirme düşünebilirsiniz."
            )

        if not warnings_list:
            warnings_list.append("✅ Portföyünüz birden fazla varlık sınıfına dağılmış görünüyor.")

        for w_text in warnings_list:
            lbl = tk.Label(content, text=w_text, font=("Arial", 12),
                           fg="#555", wraplength=320, justify="left")
            lbl.pack(anchor="w", padx=15, pady=3)
            lbl.bind("<MouseWheel>", mw_handler)

    def _sync_portfolio_from_ui(self):
        """Portföy sekmesindeki Entry widget'larından güncel değerleri oku.
        Widget yoksa veya okunamazsa mevcut değerleri korur (üzerine yazmaz)."""
        # Toplam değer Entry'si varsa oku
        if self._pv_entry_var is not None:
            try:
                pv_text = self._pv_entry_var.get().strip()
                if pv_text:
                    # Format: "1,000,000" veya "1.000.000" veya "1000000" hepsini destekle
                    clean = pv_text.replace('₺', '').replace(' ', '').replace(',', '').replace('.', '')
                    if clean:
                        parsed = float(clean)
                        if parsed > 0:
                            self.portfolio_total_value = parsed
            except (ValueError, AttributeError, tk.TclError):
                pass  # Mevcut değeri koru

        # Fon dağılım Entry'leri varsa oku
        if self._dist_entries:
            try:
                new_dist = {}
                for fon_kodu, var in self._dist_entries.items():
                    val = var.get().strip().replace(',', '.')
                    if val:
                        new_dist[fon_kodu] = float(val)
                # Sadece en az bir değer varsa güncelle
                if new_dist:
                    self.fund_distribution.update(new_dist)
            except (ValueError, AttributeError, tk.TclError):
                pass  # Mevcut değeri koru

    def _apply_portfolio_values(self):
        """Portföy değerini ve fon dağılımını kaydet ve görünümü güncelle"""
        # Toplam portföy değerini parse et
        try:
            pv_text = self._pv_entry_var.get().strip() if self._pv_entry_var else ""
            # "1,000,000" veya "1.000.000" veya "1000000" formatlarını destekle
            pv_text = pv_text.replace('₺', '').replace(' ', '')
            pv_text = pv_text.replace(',', '').replace('.', '')
            if pv_text:
                self.portfolio_total_value = float(pv_text)
            else:
                self.portfolio_total_value = 0.0
        except ValueError:
            messagebox.showwarning("Uyarı", "Geçersiz portföy değeri.\nÖrnek: 1000000")
            return
        except Exception as e:
            messagebox.showerror("Hata", f"Portföy değeri okunamadı:\n{e}")
            return

        # Fon dağılımlarını oku
        new_dist = {}
        total_pct = 0.0
        for fon_kodu, var in self._dist_entries.items():
            try:
                val = var.get().strip().replace(',', '.')
                if val:
                    pct = float(val)
                    new_dist[fon_kodu] = pct
                    total_pct += pct
            except ValueError:
                messagebox.showwarning("Uyarı", f"{fon_kodu} için geçersiz yüzde değeri.")
                return

        if total_pct > 0 and abs(total_pct - 100) > 1.0:
            if not messagebox.askyesno(
                "Uyarı",
                f"Toplam dağılım %{total_pct:.1f} (%100 olmalı).\n"
                "Yine de kaydetmek istiyor musunuz?"
            ):
                return

        self.fund_distribution = new_dist

        # Doğrudan Fon.md'ye kaydet
        try:
            self._save_portfolio_to_md()
            # Dosyanın gerçekten yazıldığını doğrula
            fon_md_path = os.path.join(APP_DIR, 'Fon.md')
            verify = self.read_md_file('Fon.md')
            if verify and verify.get("Portföy Değeri", 0) > 0:
                print(f"[✓ Portföy Kayıt OK] {fon_md_path} — Değer: {verify['Portföy Değeri']}, Dağılım: {verify['Fon Dağılımı']}")
            else:
                print(f"[✗ Portföy Kayıt SORUN] Dosya yazıldı ama doğrulama başarısız! Path: {fon_md_path}")
        except Exception as e:
            messagebox.showerror("Hata", f"Portföy kaydedilemedi:\n{e}")
            print(f"[Portföy Kayıt HATA] {e}")
            return

        # Görünümü güncelle
        self._display_portfolio_summary()

    def _save_portfolio_to_md(self):
        """Portföy dahil tüm ayarları Fon.md'ye kaydet — direkt, _sync gerektirmez"""
        try:
            mevcut_fonlar = [f.strip() for f in self.mevcut_fonlar_text.get().split(",") if f.strip()]
            planlanan_fonlar = [f.strip() for f in self.planlanan_fonlar_text.get().split(",") if f.strip()]

            data = {
                "Mevcut Fonlar": mevcut_fonlar,
                "Planlanan Fonlar": planlanan_fonlar,
                "Skorlar": {},
                "Portföy Değeri": self.portfolio_total_value,
                "Fon Dağılımı": dict(self.fund_distribution)
            }

            for col, (var, weight_var) in self.controls.items():
                if var.get():
                    try:
                        data["Skorlar"][col] = float(weight_var.get())
                    except ValueError:
                        pass

            fon_md_path = os.path.join(APP_DIR, 'Fon.md')
            self.save_md_file('Fon.md', data)
            print(f"[Portföy Kayıt] {fon_md_path} → Değer: {self.portfolio_total_value}, Dağılım: {self.fund_distribution}")
        except Exception as e:
            print(f"[Portföy Kayıt Hata] {e}")
            raise

    def _equalize_fund_distribution(self, target_funds):
        """Fon dağılımını eşit ağırlıklara böl"""
        if not target_funds:
            return

        equal_pct = 100.0 / len(target_funds)
        for fon_kodu in target_funds:
            self.fund_distribution[fon_kodu] = round(equal_pct, 2)

        # Son fona kalanı ver (%100'e tamamla)
        sorted_funds = sorted(target_funds)
        remainder = 100.0 - sum(self.fund_distribution.get(f, 0) for f in sorted_funds[:-1])
        self.fund_distribution[sorted_funds[-1]] = round(remainder, 2)

        # Portföy değerini de UI'dan senkronize et (Eşitle sırasında girilmiş olabilir)
        if self._pv_entry_var is not None:
            try:
                pv_text = self._pv_entry_var.get().strip()
                clean = pv_text.replace('₺', '').replace(' ', '').replace(',', '').replace('.', '')
                if clean:
                    self.portfolio_total_value = float(clean)
            except (ValueError, AttributeError, tk.TclError):
                pass

        self._save_portfolio_to_md()
        self._display_portfolio_summary()

    def _on_main_paned_configure(self, event=None):
        """Pencere boyutu değiştiğinde sash'ı yeniden ayarla (sadece ilk 2 kez)"""
        if not hasattr(self, '_sash_config_count'):
            self._sash_config_count = 0
        if self._sash_config_count < 3:
            self._sash_config_count += 1
            self.root.after(50, self._set_initial_sash_positions)

    def _set_initial_sash_positions(self):
        """PanedWindow sash pozisyonlarını ayarla"""
        try:
            # Yatay sash: tablo %68, detay %32
            total_width = self.content_frame.winfo_width()
            if total_width > 100:
                sash_pos = int(total_width * 0.68)
                self.content_frame.sashpos(0, sash_pos)
        except Exception:
            pass

        try:
            # Dikey sash: makro göstergeleri altta min 100px (2 satır gösterge)
            total_height = self.main_paned.winfo_height()
            if total_height > 200:
                macro_height = max(100, self.macro_frame.winfo_reqheight() + 20)
                sash_pos = total_height - macro_height
                self.main_paned.sashpos(0, sash_pos)
        except Exception:
            pass

    def _on_tree_select(self, event):
        """Tek tıklama - fon seçildiğinde detay panelini güncelle"""
        selection = self.tree.selection()
        if not selection:
            return

        item = selection[0]
        values = self.tree.item(item)['values']
        if len(values) > 1:
            fon_kodu = str(values[1]).strip()
            self.selected_fund_code = fon_kodu
            self._load_fund_allocation(fon_kodu)

    def _load_fund_allocation(self, fon_kodu):
        """TEFAS'tan fon dağılımını çek ve göster (önbellek destekli)"""
        # Başlığı güncelle + TEFAS butonunu göster
        self.detail_title.config(text=f"{fon_kodu} Fon Detayları")
        self._tefas_btn.config(text=f"TEFAS'ta Aç ({fon_kodu})")
        self._tefas_btn.pack(side=tk.RIGHT, padx=5)

        # Her iki sekmenin içeriğini temizle
        for widget in self._alloc_content.winfo_children():
            widget.destroy()
        for widget in self._forecast_content.winfo_children():
            widget.destroy()

        # Scroll'u en üste al
        self._alloc_canvas.yview_moveto(0)
        self._forecast_canvas.yview_moveto(0)

        # Öngörü sekmesini her zaman doldur
        self._display_forecast_in_tab(fon_kodu)

        # Önbellekte var mı kontrol et
        cached_alloc = self.allocation_cache.get(fon_kodu)
        cached_daily = self.daily_return_cache.get(fon_kodu)

        if cached_alloc:
            self._display_allocation(cached_alloc, cached_daily)
            return

        # Yükleniyor göster
        tk.Label(
            self._alloc_content,
            text="Veriler yükleniyor...",
            font=("Arial", 13, "italic"),
            fg="gray"
        ).pack(expand=True, pady=30)
        self.root.update()

        try:
            self._throttle_request()

            url = f"https://www.tefas.gov.tr/FonAnaliz.aspx?FonKod={fon_kodu}"
            html_content = self._fetch_html(url)

            allocation_data = self._parse_allocation_data(html_content)
            daily_return = self._parse_daily_return(html_content)

            if allocation_data:
                self.allocation_cache[fon_kodu] = allocation_data
            if daily_return:
                self.daily_return_cache[fon_kodu] = daily_return
                self._update_single_row_daily(fon_kodu, daily_return)

            self._save_cache_to_disk()

            # İçeriği temizle ve göster
            for widget in self._alloc_content.winfo_children():
                widget.destroy()

            if allocation_data:
                self._display_allocation(allocation_data, daily_return)
            else:
                self._show_no_data_message(fon_kodu)

            # Öngörü sekmesini yeniden doldur (allocation güncellenmiş olabilir)
            for widget in self._forecast_content.winfo_children():
                widget.destroy()
            self._display_forecast_in_tab(fon_kodu)

        except Exception as e:
            for widget in self._alloc_content.winfo_children():
                widget.destroy()

            error_msg = str(e)
            if "rejected" in error_msg.lower() or "403" in error_msg:
                error_text = ("TEFAS erişim engeli!\n\n"
                              "Çok fazla istek yapıldığı için\n"
                              "engellendiniz.\n\n"
                              "Birkaç dakika bekleyin.")
            else:
                error_text = f"Veri alınamadı:\n{error_msg}"

            tk.Label(
                self._alloc_content,
                text=error_text,
                font=("Arial", 12),
                fg="red",
                wraplength=280
            ).pack(pady=20)


    def _display_forecast_in_tab(self, fon_kodu):
        """Öngörü sekmesine öngörü detaylarını yerleştir"""
        content = self._forecast_content
        mw_handler = self._forecast_mousewheel_handler

        if not HAS_STRATEGY or self.strategy is None:
            tk.Label(content, text="Strateji motoru yüklenmedi.",
                     font=("Arial", 13), fg="gray").pack(pady=30)
            return

        # Forecast hesapla/cache'den al
        fc = self.forecast_cache.get(fon_kodu)
        if not fc and self.df is not None:
            try:
                row_data = self.df[self.df['Fon Kodu'].str.strip() == fon_kodu]
                if not row_data.empty:
                    row = row_data.iloc[0]
                    alloc = self.allocation_cache.get(fon_kodu, {})
                    fc = self.strategy.calculate_forecast(row, alloc, self.macro_data)
                    self.forecast_cache[fon_kodu] = fc
            except Exception:
                pass

        if not fc:
            tk.Label(content, text="Öngörü verisi hesaplanamadı.\nCSV yükleyin ve tekrar deneyin.",
                     font=("Arial", 13), fg="gray", justify="center").pack(pady=30)
            return

        # ── Tooltip açıklamaları ──
        TOOLTIPS = {
            "Momentum": (
                "Momentum: Fonun son dönemlerdeki getiri trendi.\n"
                "Kısa vade (1-3-6 ay) ve uzun vade (1-3-5 yıl) getiri\n"
                "ortalaması hesaplanır. Yüksek momentum, fonun\n"
                "yükseliş trendinde olduğunu gösterir."
            ),
            "Varlık Rotasyonu": (
                "Varlık Rotasyonu: Fonun portföy dağılımının\n"
                "mevcut piyasa rejimine uygunluğu.\n"
                "Örn: Piyasa 'Risk-On' ise hisse ağırlıklı fonlar,\n"
                "'Defansif' ise altın/tahvil fonları yüksek puan alır."
            ),
            "Risk/Getiri": (
                "Risk/Getiri: Fonun getirisi ile riski arasındaki\n"
                "denge (Sharpe oranı benzeri). Yüksek getiri + düşük\n"
                "volatilite = yüksek puan. Riskli ama getirisi düşük\n"
                "fonlar düşük puan alır."
            ),
            "Tutarlılık": (
                "Tutarlılık: Fonun farklı dönemlerde ne kadar\n"
                "istikrarlı performans gösterdiği. Tüm dönemlerde\n"
                "düzenli kazandıran fonlar yüksek puan alır.\n"
                "Dalgalı performans düşük puan demektir."
            ),
        }

        # ── Composite skor ──
        composite = fc["composite"]
        comp_color = "#4CAF50" if composite >= 60 else "#FF9800" if composite >= 40 else "#f44336"

        header = ttk.Frame(content)
        header.pack(fill=tk.X, padx=8, pady=(8, 4))
        tk.Label(header, text="Öngörü Skoru",
                 font=("Arial", 14, "bold"), fg="#FF6600").pack(side=tk.LEFT)
        tk.Label(header, text=f"{composite:.1f}",
                 font=("Arial", 20, "bold"), fg=comp_color).pack(side=tk.RIGHT)

        # ── Rejim bilgisi ──
        regime_frame = ttk.Frame(content)
        regime_frame.pack(fill=tk.X, padx=8, pady=4)
        tk.Label(regime_frame, text=f"Rejim: {fc['regime_label']}",
                 font=("Arial", 13, "bold"), fg="#555").pack(anchor="w")
        tk.Label(regime_frame, text=fc.get("regime_desc", ""),
                 font=("Arial", 12), fg="#777").pack(anchor="w")

        # Rejim nedeni
        regime_reasons = self._build_regime_explanation(fc)
        tk.Label(regime_frame, text=regime_reasons,
                 font=("Arial", 12), fg="#999",
                 wraplength=340, justify="left").pack(anchor="w", pady=(2, 0))

        # Ağırlık açıklaması
        weights = fc.get("weights", {})
        weight_text = (f"Ağırlıklar: Mom ×{weights.get('momentum',0):.0%}, "
                       f"Rot ×{weights.get('rotation',0):.0%}, "
                       f"Risk ×{weights.get('risk_return',0):.0%}, "
                       f"Tut ×{weights.get('consistency',0):.0%}")
        tk.Label(content, text=weight_text,
                 font=("Arial", 12), fg="#aaa",
                 wraplength=340).pack(anchor="w", padx=8, pady=(0, 6))

        ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=5, pady=4)

        # ── Bileşen skorları ──
        components = [
            ("Momentum", fc["normalized"]["momentum"], fc["weights"]["momentum"]),
            ("Varlık Rotasyonu", fc["normalized"]["rotation"], fc["weights"]["rotation"]),
            ("Risk/Getiri", fc["normalized"]["risk_return"], fc["weights"]["risk_return"]),
            ("Tutarlılık", fc["normalized"]["consistency"], fc["weights"]["consistency"]),
        ]

        for name, score, weight in components:
            row_f = ttk.Frame(content)
            row_f.pack(fill=tk.X, padx=8, pady=3)

            name_lbl = tk.Label(row_f, text=f"ℹ {name}", font=("Arial", 13),
                                anchor="w", width=18, cursor="hand2", fg="#333")
            name_lbl.pack(side=tk.LEFT)

            tooltip_text = TOOLTIPS.get(name, "")
            if tooltip_text:
                self._bind_tooltip(name_lbl, tooltip_text)

            bar_frame = tk.Frame(row_f, height=16, width=100,
                                 bg="#eee", highlightthickness=1,
                                 highlightbackground="#ddd")
            bar_frame.pack(side=tk.LEFT, padx=4)
            bar_frame.pack_propagate(False)

            bar_width = max(1, int(score))
            bar_color = "#4CAF50" if score >= 60 else "#FF9800" if score >= 40 else "#f44336"
            bar = tk.Frame(bar_frame, width=bar_width, bg=bar_color)
            bar.pack(side=tk.LEFT, fill=tk.Y)

            tk.Label(row_f, text=f"{score:.0f}",
                     font=("Arial", 13, "bold"), fg=bar_color,
                     width=4).pack(side=tk.LEFT)

            tk.Label(row_f, text=f"×{weight:.0%}",
                     font=("Arial", 12), fg="#999").pack(side=tk.LEFT)

            for w in (row_f, bar_frame, bar, name_lbl):
                w.bind("<MouseWheel>", mw_handler)

        ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=5, pady=6)

        # ── Detay metrikleri ──
        mom = fc["momentum"]
        detail_f = ttk.Frame(content)
        detail_f.pack(fill=tk.X, padx=10, pady=4)

        # Kısa vade tooltip
        sv_lbl = tk.Label(detail_f, text=f"ℹ Kısa vade: {mom['short_momentum']:.1f}",
                          font=("Arial", 12), fg="#555", cursor="hand2")
        sv_lbl.pack(anchor="w")
        self._bind_tooltip(sv_lbl,
            "Kısa Vade Momentum:\n"
            "Son 1 ay (%40) + 3 ay (%30) + 6 ay (%30)\n"
            "getirilerinin ağırlıklı ortalaması.\n"
            "Yüksek = son dönemde iyi performans.")

        lv_lbl = tk.Label(detail_f, text=f"ℹ Uzun vade: {mom['long_momentum']:.1f}",
                          font=("Arial", 12), fg="#555", cursor="hand2")
        lv_lbl.pack(anchor="w")
        self._bind_tooltip(lv_lbl,
            "Uzun Vade Momentum:\n"
            "1 yıl (%50) + 3 yıl yıllık (%30) + 5 yıl yıllık (%20)\n"
            "getirilerinin ağırlıklı ortalaması.\n"
            "Yüksek = uzun vadede güçlü performans.")

        acc_lbl = tk.Label(detail_f, text=f"ℹ İvme: {mom['acceleration']:.1f}x",
                           font=("Arial", 12), fg="#555", cursor="hand2")
        acc_lbl.pack(anchor="w")
        self._bind_tooltip(acc_lbl,
            "Momentum İvmesi:\n"
            "Son 1 aylık getirinin, 3 aylık aylık ortalamaya oranı.\n"
            ">1 = hızlanıyor (son dönem daha iyi)\n"
            "<1 = yavaşlıyor (son dönem daha kötü)")

        pos = mom["positive_periods"]
        total_p = mom.get("total_periods", 6)
        pos_lbl = tk.Label(detail_f, text=f"ℹ Pozitif dönem: {pos}/{total_p}"
                 + (" ✓" if total_p > 0 and pos / total_p >= 0.67 else ""),
                 font=("Arial", 12), cursor="hand2",
                 fg="#4CAF50" if total_p > 0 and pos / total_p >= 0.67 else "#f44336")
        pos_lbl.pack(anchor="w")
        self._bind_tooltip(pos_lbl,
            "Pozitif Dönem:\n"
            "6 dönemden (1ay, 3ay, 6ay, 1yıl, 3yıl, 5yıl)\n"
            "kaçında getiri pozitif (>0).\n\n"
            "6/6 = tüm dönemlerde kazanmış (×1.25 bonus)\n"
            "5/6 = çoğu dönemde kazanmış (×1.15 bonus)\n"
            "4/6 = yeterli (×1.10 bonus)\n"
            "<4/6 = tutarsız performans (bonus yok)\n\n"
            "Not: Yeni fonlarda 0 değerli dönemler\n"
            "hesaplamadan çıkarılır.")

        # Sharpe detayı
        rr = fc["risk_return"]
        sharpe_lbl = tk.Label(detail_f,
                              text=f"ℹ Sharpe: {rr['sharpe']:.2f}  Volatilite: {rr['volatility']:.2f}",
                              font=("Arial", 12), fg="#555", cursor="hand2")
        sharpe_lbl.pack(anchor="w", pady=(4, 0))
        self._bind_tooltip(sharpe_lbl,
            "Sharpe Oranı (Pseudo):\n"
            "Ortalama getiri / Getiri volatilitesi.\n"
            "Yüksek Sharpe = az riskle çok getiri.\n"
            "Düşük Sharpe = çok riskle az getiri.\n\n"
            "Volatilite: Dönemler arası getiri standart sapması.\n"
            "Düşük = istikrarlı, Yüksek = dalgalı.")



    def _display_allocation(self, allocation_data, daily_return=None):
        """Varlık dağılımını panelde göster - pasta grafik + sıralı liste + günlük getiri"""

        # Verileri yüzdeye göre büyükten küçüğe sırala
        sorted_data = sorted(
            allocation_data.items(),
            key=lambda x: x[1].get('percentage', 0) if isinstance(x[1], dict) else x[1],
            reverse=True
        )

        content = self._alloc_content
        mw_handler = self._alloc_mousewheel_handler

        # Pasta Grafik Canvas
        pie_frame = ttk.Frame(content)
        pie_frame.pack(fill=tk.X, pady=5)

        canvas_size = 140
        canvas = tk.Canvas(pie_frame, width=canvas_size, height=canvas_size,
                          bg='white', highlightthickness=1, highlightbackground='#ddd')
        canvas.pack()

        # Pasta dilimlerini çiz
        center_x, center_y = canvas_size // 2, canvas_size // 2
        radius = 60
        start_angle = 0

        for asset_name, data in sorted_data:
            percentage = data.get('percentage', 0) if isinstance(data, dict) else data
            color = data.get('color', '#4572A7') if isinstance(data, dict) else '#4572A7'

            if percentage > 0:
                extent = (percentage / 100) * 360
                canvas.create_arc(
                    center_x - radius, center_y - radius,
                    center_x + radius, center_y + radius,
                    start=start_angle, extent=extent,
                    fill=color, outline='white', width=2
                )
                start_angle += extent

        # Ortaya toplam yüzde yaz
        total = sum(
            d.get('percentage', 0) if isinstance(d, dict) else d
            for _, d in sorted_data
        )
        canvas.create_oval(center_x-22, center_y-22, center_x+22, center_y+22,
                          fill='white', outline='#ddd')
        canvas.create_text(center_x, center_y, text=f"%{total:.0f}",
                          font=("Arial", 12, "bold"), fill="#333")

        # Ayırıcı
        ttk.Separator(content, orient='horizontal').pack(fill=tk.X, pady=5)

        # Liste başlığı
        header_frame = ttk.Frame(content)
        header_frame.pack(fill=tk.X, padx=5)
        tk.Label(header_frame, text="Varlık Türü", font=("Arial", 12, "bold"),
                 anchor="w").pack(side=tk.LEFT)
        tk.Label(header_frame, text="Oran", font=("Arial", 12, "bold"),
                 anchor="e").pack(side=tk.RIGHT)

        for asset_name, data in sorted_data:
            percentage = data.get('percentage', 0) if isinstance(data, dict) else data
            color = data.get('color', '#4572A7') if isinstance(data, dict) else '#4572A7'

            if percentage <= 0:
                continue

            row_frame = ttk.Frame(content)
            row_frame.pack(fill=tk.X, pady=3, padx=5)

            color_box = tk.Frame(row_frame, width=14, height=14, bg=color)
            color_box.pack(side=tk.LEFT, padx=(0, 8))
            color_box.pack_propagate(False)

            name_label = tk.Label(
                row_frame, text=asset_name,
                font=("Arial", 12), anchor="w",
                wraplength=200, justify="left"
            )
            name_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

            pct_label = tk.Label(
                row_frame, text=f"%{percentage:.2f}",
                font=("Arial", 12, "bold"), fg=color
            )
            pct_label.pack(side=tk.RIGHT, padx=5)

            for w in (row_frame, color_box, name_label, pct_label):
                w.bind("<MouseWheel>", mw_handler)

        # Günlük Getiri
        if daily_return:
            ttk.Separator(content, orient='horizontal').pack(fill=tk.X, pady=10)

            daily_frame = ttk.Frame(content)
            daily_frame.pack(fill=tk.X, padx=10, pady=5)

            tk.Label(daily_frame, text="Günlük Getiri:",
                     font=("Arial", 12, "bold"), anchor="w").pack(side=tk.LEFT)

            try:
                value_str = daily_return.replace('%', '').replace(',', '.').strip()
                value = float(value_str)
                d_color = "#4CAF50" if value >= 0 else "#f44336"
            except:
                d_color = "#333"

            tk.Label(daily_frame, text=daily_return,
                     font=("Arial", 14, "bold"), fg=d_color,
                     anchor="e").pack(side=tk.RIGHT)

    def _show_no_data_message(self, fon_kodu):
        """Veri bulunamadı mesajı göster"""
        msg = tk.Label(
            self._alloc_content,
            text=f"{fon_kodu} için varlık dağılımı\nverisi bulunamadı.",
            font=("Arial", 13),
            fg="orange",
            justify="center"
        )
        msg.pack(expand=True, pady=20)

    # ──────────────────────────────────────────────
    # Öngörü Hesaplama ve Gösterimi
    # ──────────────────────────────────────────────

    def _calculate_forecasts(self):
        """Tüm fonlar için öngörü skorunu hesapla"""
        if self.df is None:
            messagebox.showwarning("Uyarı", "Önce CSV dosyası yükleyin.")
            return

        if not HAS_STRATEGY or self.strategy is None:
            messagebox.showerror("Hata", "Strateji motoru (strategy_engine.py) bulunamadı.")
            return

        try:
            # Rejimi tespit et
            regime, detail = self.strategy.detect_regime(self.macro_data)
            regime_label, regime_desc = self.strategy.get_regime_label()

            # Tüm fonlar için öngörü hesapla
            self.forecast_cache = self.strategy.calculate_all_forecasts(
                self.df, self.allocation_cache, self.macro_data
            )

            # Tabloyu güncelle
            self.update_table(self.filter_entry.get() if self.filter_entry else None)

            # En iyi 10 fon
            top_funds = self.strategy.get_top_funds(self.forecast_cache, n=10)
            top_list = "\n".join(
                f"  {i+1}. {code} ({score:.1f})"
                for i, (code, score, _) in enumerate(top_funds)
            )

            messagebox.showinfo(
                "Öngörü Hesaplandı",
                f"Piyasa Rejimi: {regime_label}\n"
                f"{regime_desc}\n\n"
                f"Bu rejim, BIST-100, Altın ve USD/TRY'nin\n"
                f"son 1 aylık değişimlerine göre otomatik belirlendi.\n\n"
                f"En İyi 10 Fon:\n{top_list}\n\n"
                f"Toplam {len(self.forecast_cache)} fon analiz edildi.\n\n"
                f"💡 Detaylar için: Analiz → Piyasa Rejimi\n"
                f"📊 Öngörü sütununa tıklayarak sıralayabilirsiniz."
            )

        except Exception as e:
            self.handle_error(f"Öngörü hesaplama hatası: {str(e)}")


    def _build_regime_explanation(self, fc):
        """Rejimin neden seçildiğini açıklayan metin oluştur"""
        regime = fc.get("regime", "neutral")
        regime_reasons = {
            "risk_on": (
                "BIST-100 yükseliş trendinde, USD/TRY stabil.\n"
                "→ Hisse ağırlıklı fonlar öne çıkarıldı.\n"
                "Momentum ağırlığı artırıldı (%40)."
            ),
            "defensive": (
                "BIST düşüşte veya altın yükselişte.\n"
                "→ Altın/Tahvil ağırlıklı fonlar öne çıkarıldı.\n"
                "Varlık Rotasyonu ağırlığı artırıldı (%40)."
            ),
            "inflation": (
                "USD/TRY hızlı yükselişte.\n"
                "→ Döviz/Altın ağırlıklı fonlar öne çıkarıldı.\n"
                "Varlık Rotasyonu ağırlığı artırıldı (%35)."
            ),
            "neutral": (
                "Piyasada belirgin bir yön yok.\n"
                "→ Dengeli dağılım ile değerlendirme yapıldı.\n"
                "Tüm bileşenler dengeli ağırlıklandırıldı."
            ),
        }
        return regime_reasons.get(regime, "")

    def _bind_tooltip(self, widget, text):
        """Widget'a tooltip (ipucu) bağla — üzerine gelince açıklama kutusu"""
        tip_win = [None]

        def show_tip(event):
            if tip_win[0]:
                return
            tw = tk.Toplevel(widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{event.x_root + 15}+{event.y_root + 10}")

            frame = tk.Frame(tw, bg="#333", padx=1, pady=1)
            frame.pack()

            label = tk.Label(frame, text=text, justify="left",
                             bg="#FFFFDD", fg="#333",
                             font=("Arial", 12), padx=8, pady=6,
                             wraplength=350)
            label.pack()
            tip_win[0] = tw

        def hide_tip(event):
            if tip_win[0]:
                tip_win[0].destroy()
                tip_win[0] = None

        widget.bind("<Enter>", show_tip)
        widget.bind("<Leave>", hide_tip)

    def _open_selected_fund(self):
        """Seçili fonu tarayıcıda aç"""
        if self.selected_fund_code:
            self.open_fund_url(self.selected_fund_code)

    def _update_single_row_daily(self, fon_kodu, daily_return):
        """Tablodaki tek bir satırın Günlük (%) değerini güncelle — O(1) lookup"""
        try:
            iid = getattr(self, '_fon_iid_map', {}).get(fon_kodu)
            if iid and self.tree.exists(iid):
                values = list(self.tree.item(iid)['values'])
                # Günlük (%) sütunu: sondan 2. (son = Öngörü)
                values[-2] = daily_return
                self.tree.item(iid, values=values)
        except Exception:
            pass

    # ──────────────────────────────────────────────
    # Toplu Günlük Getiri Çekme
    # ──────────────────────────────────────────────


    def _start_batch_fetch(self):
        """Tüm fonların günlük getirisini çekmeye başla"""
        if self.df is None:
            messagebox.showwarning("Uyarı", "Önce CSV dosyası yükleyin.")
            return

        if self._fetch_in_progress:
            messagebox.showwarning("Uyarı", "Zaten bir çekme işlemi devam ediyor.")
            return

        self._fetch_in_progress = True
        self._fetch_cancel = False
        self.fetch_daily_btn.config(state=tk.DISABLED)
        self.cancel_fetch_btn.pack(side=tk.LEFT, padx=2)

        # İlerleme göstergesini göster
        self.progress_frame.pack(side=tk.LEFT, padx=5)

        # Arka plan thread'i başlat
        thread = threading.Thread(target=self._batch_fetch_worker, daemon=True)
        thread.start()

    def _cancel_batch_fetch(self):
        """Toplu fetch işlemini iptal et"""
        self._fetch_cancel = True

    def _batch_fetch_worker(self):
        """Arka planda tüm fonların günlük getirilerini çek"""
        fon_kodlari = self.df['Fon Kodu'].str.strip().tolist()
        total = len(fon_kodlari)

        for i, fon_kodu in enumerate(fon_kodlari):
            if self._fetch_cancel:
                # İptal edilse bile şimdiye kadar çekilenleri kaydet
                self._save_cache_to_disk()
                self.root.after(0, self._batch_fetch_done, "İptal edildi.")
                return

            # Zaten cache'te varsa atla
            if fon_kodu in self.daily_return_cache:
                self.root.after(0, self._update_progress, i + 1, total, fon_kodu)
                continue

            try:
                url = f"https://www.tefas.gov.tr/FonAnaliz.aspx?FonKod={fon_kodu}"
                html = self._fetch_html(url)

                daily = self._parse_daily_return(html)
                self.daily_return_cache[fon_kodu] = daily if daily else "N/A"

                allocation = self._parse_allocation_data(html)
                if allocation:
                    self.allocation_cache[fon_kodu] = allocation

            except Exception:
                self.daily_return_cache[fon_kodu] = "Hata"

            # İlerlemeyi güncelle
            self.root.after(0, self._update_progress, i + 1, total, fon_kodu)

            # Her 20 fonda bir disk'e kaydet (veri kaybını önle)
            if (i + 1) % 20 == 0:
                self._save_cache_to_disk()

            # Sunucuyu yormamak için bekleme (engellenmemek için)
            time.sleep(self.config.BATCH_REQUEST_DELAY)

        self.root.after(0, self._batch_fetch_done, "Tamamlandı!")

    def _update_progress(self, current, total, fon_kodu):
        """İlerleme çubuğu ve etiketi güncelle"""
        pct = (current / total) * 100
        self.progress_bar['value'] = pct
        self.progress_label.config(text=f"{current}/{total} - {fon_kodu}")

        # Her 25 fonda bir tabloyu güncelle (performans için)
        if current % 25 == 0 or current == total:
            self.update_table(self.filter_entry.get() if self.filter_entry else None)

    def _batch_fetch_done(self, message):
        """Toplu fetch tamamlandığında çağrılır"""
        self._fetch_in_progress = False
        self._fetch_cancel = False
        self.fetch_daily_btn.config(state=tk.NORMAL)
        self.cancel_fetch_btn.pack_forget()
        self.progress_frame.pack_forget()
        self.progress_bar['value'] = 0
        self.progress_label.config(text="")

        # Disk'e son kez kaydet
        self._save_cache_to_disk()

        # Tabloyu son kez güncelle
        self.update_table(self.filter_entry.get() if self.filter_entry else None)

        cached_count = len(self.daily_return_cache)
        messagebox.showinfo("Bilgi",
                            f"Günlük getiri çekme: {message}\n"
                            f"Önbellekte {cached_count} fon verisi mevcut.")


    def _on_heading_click(self, col):
        """Başlık sütununa tıklandığında sıralama yap (Fon Türü → filtre dropdown)"""
        if self.df is None:
            return

        # Fon Türü sütununa tıklanırsa dropdown filtre aç
        if col == "Fon Türü":
            self._show_fund_type_dropdown()
            return

        self._sort_reverse = not self._sort_reverse if self._last_sorted_col == col else False
        self._last_sorted_col = col

        try:
            if col == "Günlük (%)":
                # Cache'ten geçici sütun oluştur ve sırala
                def parse_daily(fon_kodu):
                    val = self.daily_return_cache.get(fon_kodu.strip(), "")
                    if not val or val in ("N/A", "Hata", ""):
                        return float('-inf')
                    try:
                        return float(val.replace('%', '').replace(',', '.').strip())
                    except (ValueError, AttributeError):
                        return float('-inf')

                self.df['_daily_sort'] = self.df['Fon Kodu'].apply(parse_daily)
                self.df.sort_values('_daily_sort', ascending=not self._sort_reverse, inplace=True)
                self.df.drop(columns=['_daily_sort'], inplace=True)
                self.df.reset_index(drop=True, inplace=True)
            elif col == "Öngörü":
                def parse_forecast(fon_kodu):
                    fc = self.forecast_cache.get(fon_kodu.strip())
                    return fc['composite'] if fc else float('-inf')

                self.df['_forecast_sort'] = self.df['Fon Kodu'].apply(parse_forecast)
                self.df.sort_values('_forecast_sort', ascending=not self._sort_reverse, inplace=True)
                self.df.drop(columns=['_forecast_sort'], inplace=True)
                self.df.reset_index(drop=True, inplace=True)
            elif col == "Tür Sırası":
                # "3/15" formatını parse et — payı (sıra numarasını) baz al
                def parse_rank(val):
                    try:
                        return int(str(val).split('/')[0])
                    except (ValueError, IndexError):
                        return 9999

                self.df['_rank_sort'] = self.df.get('Tür Sırası', '').apply(parse_rank)
                self.df.sort_values('_rank_sort', ascending=not self._sort_reverse, inplace=True)
                self.df.drop(columns=['_rank_sort'], inplace=True)
                self.df.reset_index(drop=True, inplace=True)
            else:
                self.df.sort_values(col, ascending=not self._sort_reverse, inplace=True)
                self.df.reset_index(drop=True, inplace=True)

            self.update_table(self.filter_entry.get() if self.filter_entry else None)
        except Exception as e:
            messagebox.showerror("Hata", f"Sıralama başarısız: {str(e)}")

    # ──────────────────────────────────────────────
    # Fon Türü Dropdown Filtresi
    # ──────────────────────────────────────────────

    def _show_fund_type_dropdown(self):
        """Fon Türü sütun başlığına tıklanınca checkbox'lu dropdown göster"""
        if self.df is None:
            return

        # Zaten açıksa kapat
        if self._fund_type_popup and self._fund_type_popup.winfo_exists():
            self._fund_type_popup.destroy()
            self._fund_type_popup = None
            return

        # Benzersiz fon türlerini al
        fund_types = sorted(self.df['Fon Türü'].dropna().unique().tolist())
        if not fund_types:
            return

        # Popup penceresi
        popup = tk.Toplevel(self.root)
        popup.wm_overrideredirect(True)
        popup.attributes('-topmost', True)
        self._fund_type_popup = popup

        # Sütun başlığının ekran konumunu bul
        try:
            col_box = self.tree.bbox(self.tree.get_children()[0], column="Fon Türü") \
                if self.tree.get_children() else None
        except Exception:
            col_box = None

        if col_box:
            x = self.tree.winfo_rootx() + col_box[0]
            y = self.tree.winfo_rooty()
        else:
            x = self.tree.winfo_rootx() + 250
            y = self.tree.winfo_rooty()

        # Yüksekliği hesapla (max 450px)
        item_height = 24
        total_h = min(450, len(fund_types) * item_height + 110)
        popup.geometry(f"320x{total_h}+{x}+{y}")

        # Çerçeve
        main_frame = tk.Frame(popup, bg="#fff", highlightthickness=1,
                              highlightbackground="#999")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Başlık
        header = tk.Frame(main_frame, bg="#f0f0f0")
        header.pack(fill=tk.X)
        tk.Label(header, text="Fon Türü Filtresi", font=("Arial", 12, "bold"),
                 bg="#f0f0f0", fg="#333").pack(side=tk.LEFT, padx=8, pady=4)

        # ── Tümünü Seç checkbox'u ──
        select_all_frame = tk.Frame(main_frame, bg="#e8e8e8")
        select_all_frame.pack(fill=tk.X)

        self._fund_type_select_all = tk.BooleanVar(value=(not self._fund_type_filter))
        select_all_cb = tk.Checkbutton(
            select_all_frame, text="Tümünü Seç / Kaldır",
            variable=self._fund_type_select_all, bg="#e8e8e8",
            font=("Arial", 12, "bold"), anchor="w",
            activebackground="#ddd",
            command=lambda: self._toggle_all_fund_types(self._fund_type_select_all.get())
        )
        select_all_cb.pack(fill=tk.X, padx=4, pady=3)

        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X)

        # Scrollable alan
        canvas = tk.Canvas(main_frame, bg="#fff", highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#fff")
        scroll_frame.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Mousewheel
        def _on_mw(event):
            canvas.yview_scroll(int(-1 * (event.delta)), "units")
        canvas.bind("<MouseWheel>", _on_mw)
        scroll_frame.bind("<MouseWheel>", _on_mw)

        # Checkbox'lar
        self._fund_type_vars = {}
        for ft in fund_types:
            var = tk.BooleanVar(value=(ft in self._fund_type_filter or not self._fund_type_filter))
            self._fund_type_vars[ft] = var

            row = tk.Frame(scroll_frame, bg="#fff")
            row.pack(fill=tk.X, padx=4, pady=1)
            cb = tk.Checkbutton(row, text=ft, variable=var, bg="#fff",
                                font=("Arial", 12), anchor="w",
                                activebackground="#e8e8e8")
            cb.pack(fill=tk.X)
            cb.bind("<MouseWheel>", _on_mw)

        # Alt butonlar
        btn_frame = tk.Frame(main_frame, bg="#f0f0f0")
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(btn_frame, text="Uygula",
                   command=self._apply_fund_type_filter).pack(side=tk.LEFT, padx=5, pady=4)
        ttk.Button(btn_frame, text="Filtreyi Temizle",
                   command=lambda: [self._toggle_all_fund_types(True),
                                    self._fund_type_select_all.set(True),
                                    self._apply_fund_type_filter()]
                   ).pack(side=tk.LEFT, padx=2, pady=4)
        ttk.Button(btn_frame, text="Kapat",
                   command=popup.destroy).pack(side=tk.RIGHT, padx=5, pady=4)

        # Pencere dışına tıklanınca kapat
        def _on_focus_out(event):
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except tk.TclError:
                pass
        popup.bind("<FocusOut>", _on_focus_out)

    def _toggle_all_fund_types(self, state):
        """Tüm fon türü checkbox'larını seç/kaldır"""
        for var in self._fund_type_vars.values():
            var.set(state)
        if hasattr(self, '_fund_type_select_all'):
            self._fund_type_select_all.set(state)

    def _apply_fund_type_filter(self):
        """Seçili fon türlerine göre filtrele"""
        selected = {ft for ft, var in self._fund_type_vars.items() if var.get()}
        all_types = set(self._fund_type_vars.keys())

        if selected == all_types or not selected:
            # Tümü seçili veya hiçbiri → filtreyi kaldır
            self._fund_type_filter = set()
            # Sütun başlığını sıfırla
            self.tree.heading("Fon Türü", text="Fon Türü",
                              command=lambda: self._on_heading_click("Fon Türü"))
        else:
            self._fund_type_filter = selected
            # Sütun başlığına filtre göstergesi ekle
            self.tree.heading("Fon Türü", text=f"Fon Türü ▼ ({len(selected)})",
                              command=lambda: self._on_heading_click("Fon Türü"))

        # Popup'ı kapat
        if self._fund_type_popup and self._fund_type_popup.winfo_exists():
            self._fund_type_popup.destroy()
            self._fund_type_popup = None

        # Tabloyu güncelle
        self.update_table(self.filter_entry.get() if self.filter_entry else None)

    # ──────────────────────────────────────────────
    # Öngörü Fonları Ekle
    # ──────────────────────────────────────────────

    def _add_forecast_funds_to_filter(self):
        """Öngörü skoruna göre en iyi fonları filtre listesine ekle"""
        if not self.forecast_cache:
            messagebox.showwarning("Uyarı", "Önce 'Öngörü Hesapla' butonuna tıklayın.")
            return

        if not HAS_STRATEGY or self.strategy is None:
            return

        top_funds = self.strategy.get_top_funds(self.forecast_cache, n=10)
        fund_codes = [code for code, _, _ in top_funds]

        if fund_codes:
            self.add_to_filter(fund_codes)

    def _on_tree_double_click(self, event):
        """Treeview'da çift tıkla - TEFAS sayfasını aç"""
        item = self.tree.identify('item', event.x, event.y)
        if not item:
            return

        values = self.tree.item(item)['values']
        if len(values) > 1:
            fon_kodu = str(values[1]).strip()
            self.open_fund_url(fon_kodu)

    def _on_tree_right_click(self, event):
        """Sağ tıklama — bağlam menüsü göster"""
        item = self.tree.identify('item', event.x, event.y)
        if not item:
            return

        # Satırı seç (görsel geri bildirim)
        self.tree.selection_set(item)

        values = self.tree.item(item)['values']
        if len(values) < 3:
            return

        fon_kodu = str(values[1]).strip()
        fon_adi = str(values[2]).strip()

        # Popup menü oluştur
        menu = tk.Menu(self.root, tearoff=0, font=("Arial", 12))

        menu.add_command(
            label=f"🌐  TEFAS'ta Aç — {fon_kodu}",
            command=lambda: self.open_fund_url(fon_kodu)
        )
        menu.add_command(
            label="📋  Fon Kodunu Kopyala",
            command=lambda: self._copy_to_clipboard(fon_kodu)
        )

        menu.add_separator()

        # Mevcut/Planlanan fonlara ekleme
        if fon_kodu in self.highlight_funds:
            menu.add_command(
                label="✅  Mevcut Fonlarda (zaten ekli)",
                state=tk.DISABLED
            )
        else:
            menu.add_command(
                label="➕  Mevcut Fonlara Ekle",
                command=lambda: self._add_fund_to_entry(fon_kodu, "mevcut")
            )

        if fon_kodu in self.planned_funds:
            menu.add_command(
                label="✅  Planlanan Fonlarda (zaten ekli)",
                state=tk.DISABLED
            )
        else:
            menu.add_command(
                label="➕  Planlanan Fonlara Ekle",
                command=lambda: self._add_fund_to_entry(fon_kodu, "planlanan")
            )

        menu.add_command(
            label="🔍  Filtre Listesine Ekle",
            command=lambda: self.add_to_filter([fon_kodu])
        )

        menu.add_separator()

        # Öngörü bilgisi
        fc = self.forecast_cache.get(fon_kodu)
        if fc:
            menu.add_command(
                label=f"📊  Öngörü: {fc['composite']:.1f} puan",
                command=lambda: self.detail_notebook.select(self._forecast_tab)
            )
        else:
            menu.add_command(
                label="📊  Öngörü hesaplanmamış",
                state=tk.DISABLED
            )

        # Menüyü göster
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy_to_clipboard(self, text):
        """Metni panoya kopyala"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _add_fund_to_entry(self, fon_kodu, target):
        """Fon kodunu mevcut veya planlanan fonlar kutusuna ekle"""
        if target == "mevcut":
            entry = self.mevcut_fonlar_text
        else:
            entry = self.planlanan_fonlar_text

        current = entry.get().strip()
        existing = {f.strip().upper() for f in current.split(',') if f.strip()}

        if fon_kodu.upper() not in existing:
            if current:
                entry.delete(0, tk.END)
                entry.insert(0, f"{current}, {fon_kodu}")
            else:
                entry.insert(0, fon_kodu)

            # Otomatik kaydet ve renkleri güncelle
            self.save_settings(silent=True)
            if self.df is not None:
                self.update_table(self.filter_entry.get() if self.filter_entry else None)

    def _configure_tags(self):
        """Tag'ları bir kez ayarla — fon tipi + performans renkleri"""
        fs = self.tree_font_size

        # Fon tipi tag'leri (foreground)
        self.tree.tag_configure("highlight", foreground="red",
                               font=("Arial", fs, "bold"))
        self.tree.tag_configure("planned", foreground="blue",
                               font=("Arial", fs, "bold"))
        self.tree.tag_configure("normal", foreground="black",
                               font=("Arial", fs))

        # Performans arka plan renk tag'leri (background gradyan)
        self.tree.tag_configure("perf_great",  background="#C8E6C9")  # Koyu yeşil — çok iyi
        self.tree.tag_configure("perf_good",   background="#E8F5E9")  # Açık yeşil — iyi
        self.tree.tag_configure("perf_ok",     background="#FFFDE7")  # Açık sarı — orta
        self.tree.tag_configure("perf_weak",   background="#FFF3E0")  # Açık turuncu — zayıf
        self.tree.tag_configure("perf_bad",    background="#FFEBEE")  # Açık kırmızı — kötü

    def update_table(self, filter_text=None):
        """Tabloyu güncelle - Treeview ile (optimize edilmiş)"""
        if self.df is None:
            return

        # Fon kodu filtresi
        if filter_text:
            filter_codes = {code.strip().upper() for code in filter_text.split(',') if code.strip()}
            df_view = self.df[self.df['Fon Kodu'].str.upper().isin(filter_codes)] if filter_codes else self.df
        else:
            df_view = self.df

        # Fon türü filtresi
        if self._fund_type_filter:
            df_view = df_view[df_view['Fon Türü'].isin(self._fund_type_filter)]

        self._render_table(df_view)

    def _render_table(self, df_view):
        """DataFrame'i Treeview'a render et (ortak metot)"""
        self.tree.delete(*self.tree.get_children())
        self._fon_iid_map = {}  # fon_kodu → tree item id (hızlı satır güncelleme için)

        perf_cols = self.performance_columns
        highlight = self.highlight_funds
        planned = self.planned_funds
        daily_cache = self.daily_return_cache
        forecast_cache = self.forecast_cache

        for idx, row in df_view.iterrows():
            fon_kodu = str(row['Fon Kodu']).strip()

            values = [
                idx + 1, fon_kodu,
                str(row['Fon Adı']).strip(),
                str(row['Fon Türü']).strip()
            ]

            # Performans değerlerini topla
            m1 = 0  # 1 Ay değeri (renk hesabı için)
            m3 = 0  # 3 Ay değeri
            for col in perf_cols:
                val = row.get(col, 0)
                values.append(f"{val:.2f}" if isinstance(val, (int, float)) else str(val))
                if col == "1 Ay (%)" and isinstance(val, (int, float)):
                    m1 = val
                elif col == "3 Ay (%)" and isinstance(val, (int, float)):
                    m3 = val

            skor = row.get('Skor', 0)
            values.append(f"{skor:.2f}" if skor != 0 else "")

            # Tür içi sıralama
            tur_sirasi = row.get('Tür Sırası', '')
            values.append(str(tur_sirasi) if tur_sirasi else "")

            values.append(daily_cache.get(fon_kodu, ""))

            # Öngörü skoru
            fc = forecast_cache.get(fon_kodu)
            values.append(f"{fc['composite']:.1f}" if fc else "")

            # Fon tipi tag'i (foreground renk)
            type_tag = "highlight" if fon_kodu in highlight else \
                       "planned" if fon_kodu in planned else "normal"

            # Performans arka plan tag'i — kısa vade odaklı (1 Ay %60 + 3 Ay aylık %40)
            m3_monthly = m3 / 3 if m3 != 0 else 0
            recent_perf = m1 * 0.6 + m3_monthly * 0.4
            if recent_perf >= 5:
                perf_tag = "perf_great"
            elif recent_perf >= 2:
                perf_tag = "perf_good"
            elif recent_perf >= 0:
                perf_tag = "perf_ok"
            elif recent_perf >= -2:
                perf_tag = "perf_weak"
            else:
                perf_tag = "perf_bad"

            iid = self.tree.insert('', 'end', values=values, tags=(type_tag, perf_tag))
            self._fon_iid_map[fon_kodu] = iid

        if not self._tags_configured:
            self._configure_tags()
            self._tags_configured = True

        # Durum çubuğunu güncelle
        self._visible_count = len(df_view)
        self._update_status_bar()

    def change_font_size(self, delta):
        """Font boyutunu değiştir"""
        try:
            self.tree_font_size = max(8, min(16, self.tree_font_size + delta))
            self._update_tree_styles()

            if self._tags_configured:
                self._configure_tags()

            messagebox.showinfo("Başarılı", f"Font boyutu: {self.tree_font_size}pt")
        except Exception as e:
            self.handle_error(f"Font boyutu değiştirilemedi: {str(e)}")

    def reset_columns(self):
        """Sütun genişliklerini sıfırla"""
        for col in self.table_columns:
            width = self.config.COLUMN_WIDTHS.get(col, 100)
            self.tree.column(col, width=width)

        messagebox.showinfo("Başarılı", "Sütun genişlikleri sıfırlandı")

    def load_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if file_path:
            self.root.title(f"TEFAS BES Fon Analizi - {file_path}")
            self.df = self.load_and_prepare_data(file_path)
            if self.df is None:
                return

            self.enable_filter_widgets()
            self.calculate_scores()
            self.update_table(self.filter_entry.get() if self.filter_entry else None)

    def load_and_prepare_data(self, file_path):
        try:
            df = pd.read_csv(file_path, encoding='utf-8')

            required_columns = {"Fon Kodu", "Fon Adı", "Fon Türü"}.union(self.performance_columns)
            missing_columns = required_columns - set(df.columns)

            if missing_columns:
                raise ValueError(f"Eksik sütunlar: {', '.join(missing_columns)}")

            for col in ['Fon Türü', 'Fon Kodu', 'Fon Adı']:
                df[col] = df[col].astype(str)

            for col in self.performance_columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str)
                    .str.replace(',', '.')
                    .str.replace('%', '')
                    .str.strip(),
                    errors='coerce'
                )

            df = df.fillna(0)
            return df

        except Exception as e:
            self.handle_error(f"CSV yükleme hatası: {str(e)}")
            return None

    def enable_filter_widgets(self):
        self.filter_entry.config(state=tk.NORMAL)
        self.filter_button.config(state=tk.NORMAL)
        self.clear_filter_button.config(state=tk.NORMAL)
        self.add_current_button.config(state=tk.NORMAL)
        self.add_planned_button.config(state=tk.NORMAL)
        self.add_forecast_button.config(state=tk.NORMAL)

    def apply_filter(self):
        if self.df is not None:
            self.update_table(self.filter_entry.get())

    def clear_filter(self):
        self.filter_entry.delete(0, tk.END)
        # Fon türü filtresini de temizle
        if self._fund_type_filter:
            self._fund_type_filter = set()
            self.tree.heading("Fon Türü", text="Fon Türü",
                              command=lambda: self._on_heading_click("Fon Türü"))
        if self.df is not None:
            self.update_table()

    def add_to_filter(self, funds_list):
        current_filter = self.filter_entry.get().strip()
        if current_filter:
            current_codes = [code.strip() for code in current_filter.split(',')]
            new_codes = list(set(funds_list) - set(current_codes))
            if new_codes:
                updated_filter = current_filter + ', ' + ', '.join(new_codes)
                self.filter_entry.delete(0, tk.END)
                self.filter_entry.insert(0, updated_filter)
        else:
            self.filter_entry.insert(0, ', '.join(funds_list))
        self.apply_filter()

    # Dönem → aylık normalize böleni (aylık getiriye çevirmek için)
    _PERIOD_DIVISORS = {
        "1 Ay (%)": 1,
        "3 Ay (%)": 3,
        "6 Ay (%)": 6,
        "1 Yıl (%)": 12,
        "3 Yıl (%)": 36,
        "5 Yıl (%)": 60,
    }

    def calculate_scores(self):
        if self.df is None:
            messagebox.showwarning("Uyarı", "Önce bir CSV dosyası yükleyin.")
            return

        weights = {}
        total_weight = 0
        for col, (var, weight_var) in self.controls.items():
            if var.get():
                try:
                    weight = float(weight_var.get())
                    weights[col] = weight
                    total_weight += weight
                except ValueError:
                    pass

        if abs(total_weight - 10.0) > Config.WEIGHT_TOLERANCE:
            messagebox.showerror("Hata", "Ağırlıkların toplamı 10 olmalıdır.")
            return

        try:
            # Aylık normalize + ağırlıklı skor hesaplama
            # Her dönem aylık getiriye çevrilir, böylece ölçek farkı ortadan kalkar
            skor = sum(
                (self.df[col] / self._PERIOD_DIVISORS.get(col, 1)) * (w / 10.0)
                for col, w in weights.items()
            )
            self.df['Skor'] = skor

            # Tür içi sıralama hesapla (her fon kendi türünde kaçıncı?)
            self.df['_tur_sira'] = self.df.groupby('Fon Türü')['Skor'].rank(
                ascending=False, method='min'
            ).astype(int)
            tur_counts = self.df['Fon Türü'].map(self.df.groupby('Fon Türü')['Skor'].count())
            self.df['Tür Sırası'] = self.df['_tur_sira'].astype(str) + '/' + tur_counts.astype(str)
            self.df.drop(columns=['_tur_sira'], inplace=True)

            self.df.sort_values('Skor', ascending=False, inplace=True)
            self.df.reset_index(drop=True, inplace=True)

            self.update_table(self.filter_entry.get() if self.filter_entry else None)

        except Exception as e:
            self.handle_error(f"Skor hesaplama hatası: {str(e)}")

    def equalize_weights(self):
        selected_controls = [(col, weight_var)
                             for col, (var, weight_var) in self.controls.items()
                             if var.get()]

        if selected_controls:
            equal_weight = 10.0 / len(selected_controls)
            for _, weight_var in selected_controls[:-1]:
                weight_var.set(f"{equal_weight:.2f}")

            last_weight = 10.0 - (equal_weight * (len(selected_controls) - 1))
            selected_controls[-1][1].set(f"{last_weight:.2f}")

            self.update_weight_sum()

    def load_initial_settings(self):
        try:
            data = self.read_md_file('Fon.md')
            if data:
                self.highlight_funds = set(data.get("Mevcut Fonlar", []))
                self.planned_funds = set(data.get("Planlanan Fonlar", []))

                if self.mevcut_fonlar_text:
                    self.mevcut_fonlar_text.delete(0, tk.END)
                    self.mevcut_fonlar_text.insert(0, ", ".join(data.get("Mevcut Fonlar", [])))

                if self.planlanan_fonlar_text:
                    self.planlanan_fonlar_text.delete(0, tk.END)
                    self.planlanan_fonlar_text.insert(0, ", ".join(data.get("Planlanan Fonlar", [])))

                if data.get("Skorlar"):
                    for col in self.performance_columns:
                        if col in data["Skorlar"] and col in self.controls:
                            var, weight_var = self.controls[col]
                            weight_var.set(f"{data['Skorlar'][col]:.2f}")

                    self.update_weight_sum()

                # Portföy verileri
                self.portfolio_total_value = data.get("Portföy Değeri", 0.0)
                self.fund_distribution = data.get("Fon Dağılımı", {})

        except Exception as e:
            self.handle_error(f"Başlangıç ayarları yüklenirken hata: {str(e)}", show_dialog=False)


    def read_md_file(self, file_path):
        """MD dosyasından veri okuma"""
        try:
            abs_path = os.path.join(APP_DIR, file_path) if not os.path.isabs(file_path) else file_path
            with open(abs_path, 'r', encoding='utf-8') as file:
                content = file.read()
                data = {
                    "Mevcut Fonlar": [],
                    "Planlanan Fonlar": [],
                    "Skorlar": {},
                    "Portföy Değeri": 0.0,
                    "Fon Dağılımı": {}
                }

                current_section = None
                for line in content.split('\n'):
                    line = line.strip()
                    if not line:
                        continue

                    if line.startswith('#'):
                        current_section = line[1:].strip()
                        continue

                    if current_section == "Mevcut Fonlar":
                        data["Mevcut Fonlar"] = [f.strip() for f in line.split(',') if f.strip()]
                    elif current_section == "Planlanan Fonlar":
                        data["Planlanan Fonlar"] = [f.strip() for f in line.split(',') if f.strip()]
                    elif current_section == "Skorlar" and ':' in line:
                        try:
                            col, weight = line.split(':')
                            data["Skorlar"][col.strip()] = float(weight.strip())
                        except ValueError:
                            pass
                    elif current_section == "Portföy Değeri":
                        try:
                            # "1000000" veya "1.000.000" veya "1,000,000" hepsini destekle
                            clean = line.replace('.', '').replace(',', '').strip()
                            data["Portföy Değeri"] = float(clean)
                        except ValueError:
                            pass
                    elif current_section == "Fon Dağılımı" and ':' in line:
                        try:
                            fon_kodu, pct = line.split(':')
                            data["Fon Dağılımı"][fon_kodu.strip()] = float(pct.strip())
                        except ValueError:
                            pass

                return data

        except FileNotFoundError:
            return None
        except Exception as e:
            self.handle_error(f"Fon.md okuma hatası: {str(e)}")
            return None

    def save_md_file(self, file_path, data):
        """MD dosyasına veri kaydetme"""
        try:
            abs_path = os.path.join(APP_DIR, file_path) if not os.path.isabs(file_path) else file_path
            with open(abs_path, 'w', encoding='utf-8') as file:
                file.write("# Mevcut Fonlar\n")
                file.write(", ".join(data.get("Mevcut Fonlar", [])) + "\n\n")

                file.write("# Planlanan Fonlar\n")
                file.write(", ".join(data.get("Planlanan Fonlar", [])) + "\n\n")

                file.write("# Skorlar\n")
                for col, weight in data.get("Skorlar", {}).items():
                    file.write(f"{col}: {weight:.2f}\n")

                file.write("\n# Portföy Değeri\n")
                pv = data.get("Portföy Değeri", 0)
                file.write(f"{pv:.0f}\n")

                file.write("\n# Fon Dağılımı\n")
                for fon_kodu, pct in data.get("Fon Dağılımı", {}).items():
                    file.write(f"{fon_kodu}: {pct:.2f}\n")

        except Exception as e:
            raise Exception(f"Ayarlar kaydedilirken hata: {str(e)}")

    def save_settings(self, silent=False):
        try:
            # Mevcut ve planlanan fonları al
            mevcut_fonlar = [f.strip() for f in self.mevcut_fonlar_text.get().split(",") if f.strip()]
            planlanan_fonlar = [f.strip() for f in self.planlanan_fonlar_text.get().split(",") if f.strip()]

            # Kullanıcı elle kaydet dediğinde, portföy sekmesindeki Entry'lerden de oku
            if not silent:
                self._sync_portfolio_from_ui()

            data = {
                "Mevcut Fonlar": mevcut_fonlar,
                "Planlanan Fonlar": planlanan_fonlar,
                "Skorlar": {},
                "Portföy Değeri": self.portfolio_total_value,
                "Fon Dağılımı": dict(self.fund_distribution)
            }

            for col, (var, weight_var) in self.controls.items():
                if var.get():
                    try:
                        data["Skorlar"][col] = float(weight_var.get())
                    except ValueError:
                        pass

            self.save_md_file('Fon.md', data)

            # Debug: Kayıt edilen değerleri logla
            print(f"[save_settings] silent={silent}, Portföy: {data['Portföy Değeri']}, Dağılım: {data['Fon Dağılımı']}, Path: {os.path.join(APP_DIR, 'Fon.md')}")

            # highlight_funds ve planned_funds setlerini güncelle
            self.highlight_funds = set(mevcut_fonlar)
            self.planned_funds = set(planlanan_fonlar)

            # Tabloyu yenile (renkleri güncellemek için) — auto-save'de atla
            if not silent and self.df is not None:
                self.update_table(self.filter_entry.get() if self.filter_entry else None)

            if not silent:
                messagebox.showinfo("Bilgi", "Ayarlar kaydedildi.")
        except Exception as e:
            if not silent:
                messagebox.showerror("Hata", f"Ayarlar kaydedilirken hata oluştu: {str(e)}")

    def setup_auto_save(self):
        def auto_save():
            try:
                self.save_settings(silent=True)
            except Exception:
                pass
            finally:
                self.root.after(self.config.SAVING_INTERVAL * 1000, auto_save)

        self.root.after(self.config.SAVING_INTERVAL * 1000, auto_save)

    def _show_shortcuts(self):
        """Klavye kısayolları penceresi"""
        win = tk.Toplevel(self.root)
        win.title("Klavye Kısayolları")
        win.geometry("400x320")
        win.resizable(False, False)

        tk.Label(win, text="⌨️ Klavye Kısayolları",
                 font=("Arial", 15, "bold"), fg="#333").pack(pady=(15, 10))

        shortcuts = [
            ("⌘O / Ctrl+O", "CSV dosyası aç"),
            ("⌘S / Ctrl+S", "Ayarları kaydet"),
            ("⌘F / Ctrl+F", "Fon Bul kutusuna odaklan"),
            ("⌘E / Ctrl+E", "Tabloyu Excel/CSV'ye aktar"),
            ("⌘Q / Ctrl+Q", "Çıkış"),
            ("Escape", "Tüm filtreleri temizle"),
            ("", ""),
            ("Tek tıklama", "Fon detaylarını göster"),
            ("Çift tıklama", "TEFAS'ta aç"),
            ("Sağ tıklama", "Bağlam menüsü"),
        ]

        for key, desc in shortcuts:
            if not key:
                ttk.Separator(win, orient='horizontal').pack(fill=tk.X, padx=20, pady=4)
                continue
            row = ttk.Frame(win)
            row.pack(fill=tk.X, padx=20, pady=2)
            tk.Label(row, text=key, font=("Menlo", 12, "bold"),
                     fg="#4572A7", width=18, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=desc, font=("Arial", 12),
                     fg="#555", anchor="w").pack(side=tk.LEFT)

        ttk.Button(win, text="Kapat", command=win.destroy).pack(pady=12)

    def show_help(self):
        try:
            with open('Help.md', 'r', encoding='utf-8') as file:
                help_content = file.read()
        except FileNotFoundError:
            help_content = "Help.md dosyası bulunamadı."

        help_window = tk.Toplevel(self.root)
        help_window.title("Yardım")
        help_window.geometry("600x400")

        help_text = tk.Text(help_window, wrap=tk.WORD)
        help_text.insert(tk.END, help_content)
        help_text.config(state=tk.DISABLED)
        help_text.pack(expand=True, fill=tk.BOTH)

    def _show_top_funds_dialog(self):
        """En iyi 10 fon önerisi penceresi"""
        if not self.forecast_cache:
            messagebox.showinfo("Bilgi", "Önce 'Öngörü Hesapla' butonuna tıklayın.")
            return

        if not HAS_STRATEGY or self.strategy is None:
            return

        top_funds = self.strategy.get_top_funds(self.forecast_cache, n=10)
        regime_label, regime_desc = self.strategy.get_regime_label()

        win = tk.Toplevel(self.root)
        win.title("En İyi 10 Fon Önerisi")
        win.geometry("750x580")

        # Başlık
        tk.Label(win, text=f"Piyasa Rejimi: {regime_label}",
                 font=("Arial", 15, "bold"), fg="#333").pack(pady=(10, 2))
        tk.Label(win, text=regime_desc,
                 font=("Arial", 13), fg="#777").pack(pady=(0, 3))
        tk.Label(win, text="(Bu sıralama mevcut piyasa koşullarına göre otomatik hesaplanmıştır)",
                 font=("Arial", 12, "italic"), fg="#aaa").pack(pady=(0, 10))

        # Tablo
        cols = ("Sıra", "Fon Kodu", "Öngörü", "Momentum", "Rotasyon", "Risk/Getiri", "Tutarlılık")
        tree = ttk.Treeview(win, columns=cols, show='headings', height=12)

        widths = [40, 80, 80, 80, 80, 80, 80]
        for col, w in zip(cols, widths):
            tree.column(col, width=w, anchor="center")
            tree.heading(col, text=col)

        for i, (code, score, detail) in enumerate(top_funds):
            n = detail["normalized"]
            tree.insert('', 'end', values=(
                i + 1, code,
                f"{score:.1f}",
                f"{n['momentum']:.0f}",
                f"{n['rotation']:.0f}",
                f"{n['risk_return']:.0f}",
                f"{n['consistency']:.0f}",
            ))

        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Mevcut fonlarla karşılaştırma
        if self.highlight_funds:
            ttk.Separator(win, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
            mevcut_in_top = [c for c, _, _ in top_funds if c in self.highlight_funds]
            mevcut_not_top = self.highlight_funds - {c for c, _, _ in top_funds}
            top_not_mevcut = [c for c, _, _ in top_funds if c not in self.highlight_funds]

            info_text = ""
            if mevcut_in_top:
                info_text += f"✅ Mevcut fonlarınızdan Top 10'da: {', '.join(mevcut_in_top)}\n"
            if mevcut_not_top:
                info_text += f"⚠️ Top 10'da olmayan mevcut fonlar: {', '.join(mevcut_not_top)}\n"
            if top_not_mevcut:
                info_text += f"💡 Değerlendirebileceğiniz fonlar: {', '.join(top_not_mevcut)}"

            tk.Label(win, text=info_text, font=("Arial", 12),
                     justify="left", wraplength=650, fg="#333").pack(padx=10, pady=5)

        ttk.Button(win, text="Kapat", command=win.destroy).pack(pady=10)

    def _show_regime_dialog(self):
        """Piyasa rejimi detay penceresi — açıklayıcı"""
        if not HAS_STRATEGY or self.strategy is None:
            messagebox.showerror("Hata", "Strateji motoru bulunamadı.")
            return

        regime, detail = self.strategy.detect_regime(self.macro_data)
        regime_label, regime_desc = self.strategy.get_regime_label()

        win = tk.Toplevel(self.root)
        win.title("Piyasa Rejimi Analizi")
        win.geometry("650x600")

        # Scrollable içerik
        canvas = tk.Canvas(win, highlightthickness=0)
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Başlık
        tk.Label(content, text=f"Piyasa Rejimi: {regime_label}",
                 font=("Arial", 16, "bold"), fg="#333").pack(pady=(15, 5), padx=15)
        tk.Label(content, text=regime_desc,
                 font=("Arial", 13), fg="#777").pack(pady=(0, 10))

        # Rejim ne demek?
        ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=15, pady=5)
        tk.Label(content, text="Rejim Nedir?",
                 font=("Arial", 14, "bold"), fg="#444").pack(anchor="w", padx=15, pady=(10, 5))

        regime_explain = (
            "Piyasa rejimi, BIST-100, Altın ve USD/TRY'nin son 1 aylık\n"
            "değişimlerine bakılarak otomatik tespit edilir:\n\n"
            "🟢 Risk-On: BIST yükseliyor, döviz stabil → Hisse fonları öne çıkar\n"
            "🔴 Defansif: BIST düşüyor veya altın yükseliyor → Altın/Tahvil fonları\n"
            "🟡 Enflasyon: USD/TRY hızlı yükseliyor → Döviz/Altın fonları\n"
            "⚪ Nötr: Belirgin yön yok → Dengeli değerlendirme"
        )
        tk.Label(content, text=regime_explain, font=("Arial", 12),
                 fg="#555", justify="left", wraplength=600).pack(anchor="w", padx=20)

        # Makro veriler
        ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=15, pady=10)
        tk.Label(content, text="Piyasa Verileri (Aylık Değişim)",
                 font=("Arial", 14, "bold"), fg="#444").pack(anchor="w", padx=15, pady=(5, 5))

        macro_items = [
            ("BIST-100", detail.get("bist_monthly", 0), detail.get("bist_daily", 0)),
            ("Altın (TL)", detail.get("gold_monthly", 0), detail.get("gold_daily", 0)),
            ("USD/TRY", detail.get("usd_monthly", 0), detail.get("usd_daily", 0)),
        ]
        for name, monthly, daily in macro_items:
            row = ttk.Frame(content)
            row.pack(fill=tk.X, padx=20, pady=2)
            tk.Label(row, text=name, font=("Arial", 13), width=14, anchor="w").pack(side=tk.LEFT)
            m_color = "#4CAF50" if monthly >= 0 else "#f44336"
            d_color = "#4CAF50" if daily >= 0 else "#f44336"
            tk.Label(row, text=f"Aylık: %{monthly:.1f}", font=("Arial", 13, "bold"),
                     fg=m_color, width=14).pack(side=tk.LEFT)
            tk.Label(row, text=f"Günlük: %{daily:.2f}", font=("Arial", 13),
                     fg=d_color).pack(side=tk.LEFT)

        # Rejim skorları
        scores = detail.get("regime_scores", {})
        if scores:
            ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=15, pady=10)
            tk.Label(content, text="Rejim Puanları (Hangi rejim daha güçlü?)",
                     font=("Arial", 14, "bold"), fg="#444").pack(anchor="w", padx=15, pady=(5, 5))

            labels = {"risk_on": "🟢 Risk-On", "defensive": "🔴 Defansif", "inflation": "🟡 Enflasyon"}
            max_score = max(scores.values()) if scores else 0
            for k, v in scores.items():
                row = ttk.Frame(content)
                row.pack(fill=tk.X, padx=20, pady=2)
                lbl = labels.get(k, k)
                is_active = (v == max_score and v > 1)
                font = ("Arial", 13, "bold") if is_active else ("Arial", 13)
                color = "#333" if is_active else "#888"
                tk.Label(row, text=f"{lbl}: {v} puan" + (" ← aktif" if is_active else ""),
                         font=font, fg=color).pack(anchor="w")

        # Önerilen varlık dağılımı
        ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=15, pady=10)
        tk.Label(content, text="Bu Rejimde Önerilen Varlık Dağılımı",
                 font=("Arial", 14, "bold"), fg="#444").pack(anchor="w", padx=15, pady=(5, 5))

        weights = self.strategy.REGIME_WEIGHTS.get(regime, {})
        group_labels = {
            "hisse": "Hisse Senedi", "tahvil": "Tahvil/Borçlanma",
            "altin": "Altın/Kıymetli Maden", "doviz": "Döviz",
            "repo": "Repo/Mevduat", "fon": "Yatırım Fonları",
        }
        for group, weight in sorted(weights.items(), key=lambda x: -x[1]):
            row = ttk.Frame(content)
            row.pack(fill=tk.X, padx=20, pady=2)
            tk.Label(row, text=group_labels.get(group, group),
                     font=("Arial", 13), width=22, anchor="w").pack(side=tk.LEFT)
            # Mini çubuk
            bar_f = tk.Frame(row, height=14, width=100, bg="#eee")
            bar_f.pack(side=tk.LEFT, padx=5)
            bar_f.pack_propagate(False)
            bar_w = max(1, int(weight * 100))
            tk.Frame(bar_f, width=bar_w, bg="#4CAF50").pack(side=tk.LEFT, fill=tk.Y)
            tk.Label(row, text=f"%{weight*100:.0f}",
                     font=("Arial", 13, "bold"), fg="#555").pack(side=tk.LEFT, padx=5)

        # Skorlama açıklaması
        ttk.Separator(content, orient='horizontal').pack(fill=tk.X, padx=15, pady=10)
        tk.Label(content, text="Öngörü Skoru Nasıl Hesaplanır?",
                 font=("Arial", 14, "bold"), fg="#444").pack(anchor="w", padx=15, pady=(5, 5))

        explain = (
            "Her fon 4 bileşenden oluşan bir composite skorla değerlendirilir:\n\n"
            "1️⃣ Momentum: Son dönem getiri trendi (kısa + uzun vade)\n"
            "2️⃣ Varlık Rotasyonu: Fonun portföyünün rejime uygunluğu\n"
            "3️⃣ Risk/Getiri: Getiri başına alınan risk (Sharpe benzeri)\n"
            "4️⃣ Tutarlılık: Dönemler arası performans istikrarı\n\n"
            "Her bileşenin ağırlığı piyasa rejimine göre değişir.\n"
            "Örn: Risk-On rejimde Momentum %40, Defansif rejimde\n"
            "Varlık Rotasyonu %40 ağırlık alır.\n\n"
            "Sonuç: 0-100 arası bir puan. Yüksek = daha iyi öngörü."
        )
        tk.Label(content, text=explain, font=("Arial", 12),
                 fg="#555", justify="left", wraplength=600).pack(anchor="w", padx=20, pady=(0, 15))

        ttk.Button(content, text="Kapat", command=win.destroy).pack(pady=10)

    def open_fund_url(self, fon_kodu):
        """Fon kodunun URL'sini tarayıcıda aç"""
        try:
            url = f"https://www.tefas.gov.tr/FonAnaliz.aspx?FonKod={fon_kodu}"
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("Hata", f"URL açılamadı: {str(e)}")

    def handle_error(self, error_msg, show_dialog=True):
        """Merkezi hata yönetimi"""
        if show_dialog:
            messagebox.showerror("Hata", error_msg)
        print(f"HATA: {error_msg}")

    def on_exit(self):
        def save_and_exit():
            try:
                self._macro_auto_refresh_enabled = False
                self.save_settings(silent=True)
                self._save_cache_to_disk()
                self.root.quit()
            except Exception as e:
                if messagebox.askretrycancel("Hata",
                                            f"Ayarlar kaydedilirken hata oluştu:\n{str(e)}\n\nRetry/İptal?"):
                    save_and_exit()
                else:
                    self.root.quit()

        if messagebox.askokcancel("Çıkış", "Programdan çıkmak istiyor musunuz?"):
            save_and_exit()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        app = FundAnalyzer()
        app.run()
    except Exception as e:
        print(f"Kritik Hata: {str(e)}")
        messagebox.showerror("Kritik Hata", f"Program başlatılamadı: {str(e)}")
