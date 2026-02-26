# TEFAS BES Fon Analizi — Güncelleme Notları

## 📅 22 Şubat 2026 — Portföy Değer Takibi

### 🆕 Yeni Özellikler

#### 💰 Portföy Değer Takibi (Portföy Özeti Sekmesi)
- **Toplam portföy değeri girişi:** Kullanıcı TL cinsinden toplam portföy büyüklüğünü girebilir (örn: 1.000.000 ₺).
- **Fon dağılımı yüzdeleri:** Her fon için ayrı ayrı yüzde dağılımı girilebilir (örn: BGL %40, GMF %35, KJM %25).
- **TL değer hesaplama:** Her fonun portföy içindeki TL karşılığı otomatik hesaplanır.
- **Toplam dağılım kontrolü:** Toplam yüzde %100'e eşit değilse uyarı gösterilir (yeşil ✓ / kırmızı ⚠).
- **Eşitle butonu:** Tüm fonlara eşit dağılım atar (%33.33 vb.).
- **Dönemsel TL getiri tablosu:** Her fon ve toplam portföy için 1 Ay, 3 Ay, 6 Ay, 1 Yıl, 3 Yıl, 5 Yıl dönemlerinde TL bazında getiri/kayıp hesaplanır.
- **Bugünkü değişim:** Günlük getiri verisi mevcutsa, portföyün bugünkü toplam TL değişimi gösterilir.
- **Ağırlıklı varlık dağılımı:** Fon dağılım yüzdeleri girildiyse, varlık dağılımı hesabı eşit ağırlık yerine kullanıcının belirlediği ağırlıklara göre yapılır.
- **Otomatik kaydetme:** Portföy değeri ve fon dağılımı `Fon.md` dosyasına kaydedilir, uygulama yeniden başlatıldığında korunur.

### 🛠️ Teknik Detaylar
- `Fon.md` dosyasına `# Portföy Değeri` ve `# Fon Dağılımı` bölümleri eklendi.
- `read_md_file` ve `save_md_file` metodları yeni bölümleri destekleyecek şekilde güncellendi.
- `_display_portfolio_summary` metodu portföy değer takibi + dönemsel getiri tablosu + varlık dağılımı analizini tek sekmede birleştiriyor.
- `_apply_portfolio_values` ve `_equalize_fund_distribution` yardımcı metodları eklendi.
- Mevcut kod yedeği: `main_backup_20260222.py`

---

## 📅 20 Şubat 2026 — Piyasa Göstergeleri & GUI İyileştirmeleri

### 🆕 Yeni Özellikler

#### Piyasa Göstergeleri Paneli
- **Dikey PanedWindow yapısı:** Tablo+detay paneli üstte, piyasa göstergeleri altta. Kullanıcı aradaki sash'ı sürükleyerek piyasa göstergeleri alanını istediği kadar büyütüp küçültebilir.
- **2 satırlı gösterge düzeni:**
  - **Satır 1 (Ana):** BIST-100, Altın (TL), Gümüş (TL), USD/TRY, EUR/TRY
  - **Satır 2 (Emtia + Kripto):** Brent Petrol, BTC (Bitcoin), ETH (Ethereum)
- **Otomatik yenileme:** Piyasa verileri her 10 saniyede bir arka planda otomatik güncellenir.
- **Başlıkta kaynak ve saat bilgisi:** `Piyasa Göstergeleri • Yahoo Finance • 20.02.2026 14:35:22` formatında LabelFrame başlığında gösterilir. Her yenilemede saat güncellenir.
- **↻ Yenile butonu:** 1. satırın sağında, manuel tam yenileme yapar.

#### Otomatik Yenileme Sistemi (Detay)
- `_schedule_macro_refresh()` → `root.after(N*1000)` ile ana thread'de zamanlayıcı kurar.
- `_auto_refresh_macro()` → Arka plan thread'inde `_load_macro_quick()` çağırır.
- `_load_macro_quick()` → `yf.download()` ile tüm sembolleri toplu çeker (tek API çağrısı, `period='2d'`).
- `_update_macro_labels()` → Label'ları yerinde günceller (widget yeniden oluşturulmaz, titreşim olmaz).
- `_macro_refresh_busy` bayrağı ile eşzamanlı yenileme koruması — önceki yenileme devam ediyorsa yenisi başlatılmaz.
- Hata durumunda döngü kırılmaz (`finally` bloğu ile `busy` sıfırlanır, sonraki yenileme planlanır).
- Uygulama kapatılırken `_macro_auto_refresh_enabled = False` ile döngü durdurulur.

---

### 🛠️ Düzeltmeler

#### Piyasa Göstergeleri Görünmüyordu
- **Kök neden:** `macro_frame` widget'ının parent'ı `self.root` olarak oluşturuluyordu ama `ttk.PanedWindow.add()` ile eklenmeye çalışılıyordu. ttk PanedWindow farklı parent'lı widget'ları düzgün render edemiyordu.
- **Çözüm:** `macro_frame` artık doğrudan `self.main_paned` (dikey PanedWindow) parent'ı ile oluşturuluyor.

#### `create_macro_panel()` Sıralama Hatası
- **Kök neden:** `create_widgets()` içinden `create_macro_panel()` çağrılıyordu ama `macro_frame` henüz oluşturulmamıştı.
- **Çözüm:** `create_macro_panel()` artık `create_table()` içinde, `macro_frame` oluşturulduktan sonra çağrılıyor.

#### Otomatik Yenileme Çalışmıyordu
- **Kök neden 1:** `_schedule_macro_refresh()` arka plan thread'inden çağrılıyordu. `root.after()` tkinter'de sadece ana thread'den güvenli çağrılabilir.
- **Kök neden 2:** Cache'den veri geldiğinde `_schedule_macro_refresh()` hiç çağrılmıyordu — otomatik yenileme döngüsü başlamıyordu.
- **Kök neden 3:** Spark API (toplu sembol çekme) Yahoo tarafından kısıtlanmıştı, boş dönüyordu.
- **Çözüm:** Tüm `_schedule_macro_refresh()` çağrıları `self.root.after(0, ...)` ile sarmalandı. Cache'den açılışta da döngü başlatılıyor. Toplu çekme `yf.download()` ile yapılıyor.

#### Sash Pozisyonu macOS Tam Ekran Geçişinde Bozuluyordu
- **Çözüm:** `<Configure>` event binding eklendi. Pencere boyutu ilk değiştiğinde sash otomatik düzeltilir.

#### "Brent Petrol" Satıra Sığmıyordu
- **Çözüm:** İsimler kısaltıldı (`"Brent Petrol"` → `"Brent"`, `"Altın (TL)"` → `"Altın"` vb.) ve Brent ikinci satıra taşındı.

---

### 📊 Gösterge Sembolleri

| Gösterge  | Yahoo Sembolü | Satır | Not                    |
|-----------|---------------|-------|------------------------|
| BIST-100  | XU100.IS      | 1     |                        |
| Altın     | GC=F          | 1     | USD × USD/TRY = TL    |
| Gümüş     | SI=F          | 1     | USD × USD/TRY = TL    |
| USD/TRY   | USDTRY=X      | 1     |                        |
| EUR/TRY   | EURTRY=X      | 1     |                        |
| Brent     | BZ=F          | 2     | USD cinsinden          |
| BTC       | BTC-USD       | 2     | USD cinsinden          |
| ETH       | ETH-USD       | 2     | USD cinsinden          |

---

### ⚙️ Yapılandırma Değerleri

| Parametre            | Değer  | Açıklama                                |
|----------------------|--------|-----------------------------------------|
| MACRO_AUTO_REFRESH   | 10 sn  | Otomatik yenileme aralığı               |
| yf.download timeout  | 4 sn   | Toplu veri çekme zaman aşımı            |
| Sash başlangıç       | %68/%32| Tablo / Detay panel oranı               |
| Makro min yükseklik  | 100px  | Piyasa göstergeleri minimum alan         |

---

### 📁 Dosya Yapısı

```
TEFAS-Bes/Tefas-New/
├── BefasNew-1.py          # Yedek (önceki sürüm)
├── BefasNew-2.py          # Ana çalışma dosyası (güncel)
├── CHANGELOG.md           # Bu dosya
├── Fon.md                 # Fon ayarları (mevcut/planlanan fonlar, ağırlıklar)
└── fund_cache.json        # Disk önbelleği (makro veriler + fon detayları)
```

---

### 🔮 Sonraki Adımlar (Planlanan)
- [ ] Fon portföy değişiklik takibi
- [ ] Faiz, altın, dolar, borsa getirileri ile fon varlık dağılımı ilişkilendirme
- [ ] Günlük değişim sütununun tüm fonlar için toplu çekilmesi
- [ ] Kod optimizasyonu ve modüler yapıya geçiş
- [ ] Web scraping bölümlerinin temizlenmesi

