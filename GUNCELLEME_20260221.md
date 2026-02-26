# Güncelleme Notları — 2026-02-22

## Son Güncellemeler (22 Şubat 2026)

### GUI Yeniden Düzenleme
- **Sekmeli detay paneli**: Sağ taraf artık iki sekmeli:
  - **Varlık Dağılımı** sekmesi: pasta grafik, varlık listesi, günlük getiri
  - **Öngörü Analizi** sekmesi: composite skor, bileşen breakdown, rejim bilgisi
- **Buton grupları yeniden düzenlendi**:
  - Üst satır: Fon Yönetimi (Mevcut, Planlanan, Fon Bul) + Dosya + Veri + Yardım/Çıkış
  - Alt satır: Performans kontrolleri + Hesaplama grubu (Eşitle, Skor Hesapla, Öngörü Hesapla)
  - Fon Bul, Fon Yönetimi grubuna taşındı
  - Skor Hesapla ve Öngörü Hesapla performans kontrollerinin yanına taşındı
- **Bottom frame** kaldırıldı — 4 satır yerine 3 satır

### Tooltip Sistemi Genişletildi
- **Momentum, Varlık Rotasyonu, Risk/Getiri, Tutarlılık**: üzerine gelince açıklama
- **Kısa vade, Uzun vade, İvme, Sharpe, Volatilite**: detay metrikleri için tooltip
- **Pozitif Dönem**: ne anlama geldiği, bonus katsayıları, yeni fon uyarısı
- Her kavramın başında ℹ ikonu, cursor hand2

### Piyasa Göstergeleri Flash Efekti Düzeltildi
- Veri değiştiğinde label **arka plan rengi sarı/turuncu** ile yanıp sönüyor
- 3 kez flash (180ms aralık), macOS uyumlu
- İlk render'da flash yapılmıyor (`_old_price` initial set)
- Widget destroyed hatası yakalanıyor

### TEFAS Butonu Başlığa Taşındı
- Artık her sekmenin altında tekrar oluşturulmuyor
- **Başlık satırında sabit** — "KJM Fon Detayları [TEFAS'ta Aç (KJM)]"
- Fon değiştiğinde buton metni güncelleniyor

### "Öngörü Fonları Ekle" Butonu
- Filtre satırında "Planlanan Fonları Ekle" yanına eklendi
- Öngörü hesaplandıktan sonra en iyi 10 fonu filtre listesine ekler
- Öngörü hesaplanmamışsa uyarı gösterir

### Fon Türü Dropdown Checkbox Filtresi
- **Fon Türü** sütun başlığına tıklanınca dropdown açılır
- Tüm fon türleri checkbox'lu liste olarak gösterilir
- İstenen fon türleri seçilip "Uygula" ile filtrelenir
- Aktif filtre varsa sütun başlığında `Fon Türü ▼ (3)` gösterilir
- "Tümü" ve "Hiçbiri" hızlı seçim butonları
- "Filtreyi Temizle" butonu fon türü filtresini de temizler
- Arama ve fon kodu filtresi ile birlikte çalışır

### Yeni Fon Sorunu Çözüldü (strategy_engine.py)
- Tarihsel verisi olmayan (0 değerli) dönemler artık hesaplamadan **hariç tutuluyor**
- `calculate_momentum`: Ağırlıklar sadece verisi olan dönemlere normalize ediliyor
- `calculate_risk_return`: 0 dönemler returns listesine eklenmez
- `calculate_consistency`: 0 dönemler monthly listesine eklenmez
- Pozitif dönem oranı: mutlak sayı yerine oran bazlı bonus (ör: 2/2 = %100 → ×1.25)
- `total_periods` bilgisi eklendi (kaç dönemin verisi var)

### Öngörü Detaylarında Rejim Açıklaması
- Neden bu rejimin seçildiği açıklanıyor
- Ağırlıkların nasıl dağıtıldığı gösteriliyor

---

## Önceki Güncellemeler (21 Şubat 2026)

### 1. Fon Öngörü Motoru Eklendi (BefasNew-3.py)
- **strategy_engine.py** modülü oluşturuldu (bağımsız, test edilebilir)
- **Momentum Analizi**: Kısa/uzun vade momentum, ivme hesabı, tutarlılık bonusu
- **Piyasa Rejimi Tespiti**: Risk-On / Defansif / Enflasyon / Nötr
  - BIST-100, Altın, USD/TRY aylık değişimlerine göre otomatik tespit
- **Varlık Rotasyonu Puanı**: Fonun varlık dağılımını rejime göre puanlama
  - Hisse, Tahvil, Altın, Döviz, Repo, Fon gruplarına ayrıştırma
- **Risk-Getiri Metrikleri**: Pseudo-Sharpe, volatilite, drawdown
- **Tutarlılık Skoru**: Dönemler arası standart sapma, trend yönü
- **Composite Öngörü Skoru**: 4 bileşen × rejime göre dinamik ağırlıklar
- Tabloya **"Öngörü" sütunu** eklendi (sıralanabilir)
- Detay panelinde **öngörü breakdown** (çubuk grafik + detaylar)
- Menüye **Analiz** menüsü eklendi (Öngörü Hesapla, En İyi 10 Fon, Piyasa Rejimi)
- **En İyi 10 Fon** penceresi: Mevcut fonlarla karşılaştırma, değişiklik önerileri
- **Piyasa Rejimi** detay penceresi

### 2. Yedekleme
- `BefasNew-2.backup.py` — çalışan son sürümün yedeği
- `BefasNew-2.py` — değiştirilmemiş önceki sürüm

### 3. Oluşturulan Yeni Dosyalar
- `strategy_engine.py` — Öngörü strateji motoru
- `ONGORU_PLANI.md` — Detaylı strateji ve yol haritası

### 4. Önceki Oturumda Yapılanlar (2026-02-19 / 2026-02-20)
- **Piyasa Göstergeleri**: BIST-100, Altın-TL, Gümüş-TL, USD/TRY, EUR/TRY, Brent, BTC, ETH
  - Yahoo Finance + yfinance entegrasyonu
  - Otomatik yenileme (10 sn)
  - Kaynak ve tarih bilgisi gösterimi
- **Fon Varlık Dağılımı**: Tek tıkla sağ panelde pasta grafik + liste
- **Günlük Getiri**: TEFAS sayfasından günlük getiri çekme
- **Fon Arama (Fon Bul)**: Anlık arama özelliği
- **Önbellek Sistemi**: fund_cache.json ile günlük cache (disk + RAM)
- **Toplu Getiri Çekme**: İlerleme çubuklu toplu veri çekme
- **Çift Tıklama**: TEFAS sayfasını tarayıcıda açma
- **GUI İyileştirmeleri**: Scrollable detay paneli, boyutlandırılabilir paneller, font boyutu ayarı

## Dosya Yapısı
| Dosya | Açıklama |
|-------|----------|
| BefasNew-3.py | Ana uygulama (güncel, öngörü motorlu) |
| BefasNew-2.py | Önceki sürüm (çalışan) |
| BefasNew-2.backup.py | Yedek (öngörü öncesi) |
| strategy_engine.py | Öngörü strateji motoru |
| ONGORU_PLANI.md | Strateji yol haritası |

