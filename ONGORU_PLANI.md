# Fon Öngörü ve Rotasyon Stratejisi Planı

## 🎯 Amaç
En iyi getiri sağlayabilecek 5-10 fonu belirlemek ve her ay portföyde değişiklik yapmak için sistematik bir analiz ve öngörü mekanizması oluşturmak.

---

## 📊 Mevcut Verilerimiz
1. **CSV Verileri**: 1 Ay, 3 Ay, 6 Ay, 1 Yıl, 3 Yıl, 5 Yıl getirileri
2. **Varlık Dağılımları** (allocation_cache): Her fonun portföy yapısı (Hisse, Tahvil, Altın, Döviz vb.)
3. **Piyasa Göstergeleri** (macro_data): BIST-100, Altın-TL, Gümüş-TL, USD/TRY, EUR/TRY, Brent, BTC, ETH
4. **Günlük Getiriler** (daily_return_cache): Fonların günlük değişimleri

---

## 🧠 Strateji Mantığı

### 1. Momentum Analizi (Geçmiş performans trendi)
Fonun son dönemlerdeki getiri trendi, yakın gelecekte devam etme eğilimindedir.

**Formül:**
```
Kısa Vade Momentum = 1 Ay × 0.4 + 3 Ay × 0.3 + 6 Ay × 0.3
Uzun Vade Momentum = 1 Yıl × 0.5 + (3 Yıl / 3) × 0.3 + (5 Yıl / 5) × 0.2
Momentum İvmesi   = (1 Ay) / (3 Ay / 3)  → >1 ise hızlanıyor
```

**Tutarlılık Bonusu:**
- 6 dönemin 4'ünde pozitif → +%10 bonus
- 6 dönemin 6'sında pozitif → +%25 bonus

### 2. Piyasa Rejimi Tespiti
Makro göstergelerden mevcut piyasa ortamını belirler:

| Rejim | Koşul | Tercih Edilen Varlık |
|-------|-------|---------------------|
| 🟢 Risk-On | BIST ↑, USD ↔ | Hisse ağırlıklı fonlar |
| 🔴 Defansif | BIST ↓, Altın ↑ | Kıymetli Maden + Tahvil fonları |
| 🟡 Enflasyon | USD/TRY ↑↑ | Döviz/Altın ağırlıklı fonlar |
| 🔵 Faiz Fırsatı | Faiz ↑, Enfl ↓ | Borçlanma araçları fonları |

### 3. Varlık Rotasyonu (Fon dağılımı × Rejim)
Her fonun varlık dağılımı, mevcut piyasa rejimine göre puanlanır:
- Risk-On rejiminde "Hisse Senedi" ağırlığı yüksek fon → yüksek puan
- Defansif rejimde "Kıymetli Madenler" ağırlığı yüksek fon → yüksek puan

### 4. Risk-Getiri Metrikleri
- **Pseudo-Sharpe**: Ortalama getiri / Getiri volatilitesi (dönemler arası)
- **Tutarlılık**: Dönemler arası standart sapma düşük → güvenilir fon
- **Drawdown Riski**: En büyük düşüş oranı

### 5. Composite Öngörü Skoru
```
Öngörü = Momentum × 0.35 + Varlık Rotasyonu × 0.30 + Risk-Getiri × 0.20 + Tutarlılık × 0.15
```
Not: Ağırlıklar piyasa rejimine göre dinamik kaydırılır.

---

## 🛠 Uygulama Adımları

### Faz 1: MVP — Hemen Uygulanabilir (Mevcut Verilerle)
- [x] `strategy_engine.py` modülü oluştur
- [ ] Momentum skoru hesaplama
- [ ] Basit rejim tespiti (macro_data'dan)
- [ ] Varlık rotasyonu puanı (allocation_cache'den)
- [ ] Tabloya "Öngörü" sütunu ekleme
- [ ] Detay panelinde öngörü breakdown gösterme

### Faz 2: Gelişmiş Analiz
- [ ] Tarihsel portföy değişikliği takibi
- [ ] TCMB faiz/enflasyon verisi entegrasyonu
- [ ] Sektör endeksleri (XBANK, XUTEK, XGMYO)
- [ ] Fon yöneticisi strateji değişikliği tespiti

### Faz 3: Raporlama
- [ ] Aylık rapor oluşturma
- [ ] Öneri karşılaştırması (önceki ay önerileri vs gerçekleşen)
- [ ] Strateji backtesting (geçmiş verilerle test)

---

## ⚠️ Önemli Notlar
- BES fonlarında değişiklik ayda **6 kez** yapılabiliyor (SPK kuralı)
- Strateji "her ay 1-2 değişiklik" şeklinde olmalı, günlük al-sat değil
- Hiçbir öngörü kesin sonuç vermez, sadece olasılıkları artırır
- TEFAS rate-limiting: Günde 1 kez toplu veri çekme yeterli

---

## 📅 Tarih: 2026-02-21

