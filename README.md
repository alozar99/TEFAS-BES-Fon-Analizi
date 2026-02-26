TEFAS BES Fon Analizi
📌 Genel Bakış
Bu uygulama, TEFAS (Türkiye Elektronik Fon Alım Satım Platformu) üzerindeki BES (Bireysel Emeklilik Sistemi) fonlarını analiz etmenize yardımcı olur.

🚀 Başlangıç
CSV Dosyası Yükleme
Dosya > CSV Yükle veya "Dosya Seç" butonuna tıklayın
TEFAS'tan indirdiğiniz fon karşılaştırma CSV dosyasını seçin
Veriler tabloya yüklenir ve analiz edilmeye hazır hale gelir
Gerekli CSV Sütunları
Fon Kodu
Fon Adı
Fon Türü
1 Ay (%)
3 Ay (%)
6 Ay (%)
1 Yıl (%)
3 Yıl (%)
5 Yıl (%)
📊 Özellikler
1. Skor Hesaplama
Her performans dönemine (1 Ay, 3 Ay, vb.) ağırlık atayın
Toplam ağırlık 10 olmalıdır (yeşil renkte gösterilir)
"Skor Hesapla" butonuna tıklayarak fonları sıralayın
"Ağırlık Eşitle" butonu tüm ağırlıkları eşit dağıtır
2. Fon Filtreleme
Virgülle ayırarak fon kodları girin (örn: ABC, XYZ, KLM)
"Filtrele" butonuna tıklayın
"Mevcut Fonları Ekle" veya "Planlanan Fonları Ekle" ile hızlı filtreleme yapın
3. Fon Takibi
Mevcut Fonlar: Portföyünüzdeki fonlar (kırmızı ile işaretlenir)
Planlanan Fonlar: İlgilendiğiniz fonlar (mavi ile işaretlenir)
4. Varlık Dağılımı (Sağ Panel)
Tablodaki bir fona tek tıklayın
Sağ panelde fonun varlık dağılımı görüntülenir:
Pasta grafik
Varlık türleri listesi (büyükten küçüğe sıralı)
Günlük getiri bilgisi
5. TEFAS Sayfasını Açma
Tablodaki bir fona çift tıklayın
veya sağ paneldeki "TEFAS'ta Görüntüle" butonunu kullanın
6. Öngörü Analizi (Yeni!)
Fonları geleceğe yönelik değerlendirmek için 4 bileşenli bir skor sistemi:

Momentum: Fonun son dönem getiri trendi. Kısa vade (1-3-6 ay) ve uzun vade (1-3-5 yıl) getiri ortalaması. Yüksek momentum = fon yükseliş trendinde.

Varlık Rotasyonu: Fonun portföy dağılımının mevcut piyasa rejimine uygunluğu. Piyasa hisse yönlüyse hisse ağırlıklı fonlar, altın yönlüyse altın ağırlıklı fonlar yüksek puan alır.

Risk/Getiri: Getiri başına alınan risk (Sharpe oranı benzeri). Yüksek getiri + düşük volatilite = yüksek puan.

Tutarlılık: Farklı dönemlerde ne kadar istikrarlı performans gösterildiği. Her dönem düzenli kazandıran fonlar yüksek puan alır.

Nasıl Kullanılır?
CSV yükleyin
"Öngörü Hesapla" butonuna tıklayın
Tablodaki "Öngörü" sütununa tıklayarak sıralayın
Bir fona tıklayarak sağ panelde detaylı analizi görün
Analiz > En İyi 10 Fon ile önerileri inceleyin
Öngörü Skoru Nasıl Hesaplanır?
Composite skor = Momentum × %35 + Rotasyon × %30 + Risk × %20 + Tutarlılık × %15 (Bu ağırlıklar piyasa rejimine göre otomatik değişir)

7. Piyasa Rejimi
Piyasa rejimi, makro göstergelerin son 1 aylık değişimine göre otomatik tespit edilir:

Rejim	Koşul	Tercih
🟢 Risk-On	BIST ↑, USD stabil	Hisse fonları
🔴 Defansif	BIST ↓, Altın ↑	Altın/Tahvil fonları
🟡 Enflasyon	USD/TRY ↑↑	Döviz/Altın fonları
⚪ Nötr	Belirgin yön yok	Dengeli dağılım
Detaylar için: Analiz > Piyasa Rejimi

8. Piyasa Göstergeleri (Alt Band)
BIST-100, Altın-TL, Gümüş-TL, USD/TRY, EUR/TRY
Brent Petrol, BTC, ETH
Otomatik yenileme (10 saniyede bir)
Kaynak: Yahoo Finance
9. Fon Arama (Fon Bul)
Alt barda "Fon Bul" alanına yazın
Fon adında anlık arama yapar
Örn: "ALTIN" yazınca altın fonları listelenir
10. Önbellek Sistemi
Çekilen veriler günlük olarak önbelleğe kaydedilir
Aynı fona tekrar tıklandığında hızlı gösterim
Dosya > Önbelleği Temizle ile temizlenebilir
⌨️ Kısayollar
İşlem	Açıklama
Tek Tıklama	Fonun varlık dağılımını göster
Çift Tıklama	TEFAS sayfasını tarayıcıda aç
Enter	Filtreyi uygula (filtre alanındayken)
Sütun Başlığı Tıklama	O sütuna göre sırala
🎨 Görünüm
Font Boyutu
Görünüm > Font Boyutu Artır (+): Tablo yazılarını büyütür
Görünüm > Font Boyutu Azalt (-): Tablo yazılarını küçültür
Sütun Genişlikleri
Sütun başlıklarını sürükleyerek genişliği ayarlayın
Görünüm > Sütunları Sıfırla: Varsayılan genişliklere döner
💾 Ayarlar
Ayarlar otomatik olarak Fon.md dosyasına kaydedilir:

Mevcut fon listesi
Planlanan fon listesi
Skor ağırlıkları
Manuel Kaydetme: "Ayarları Kaydet" butonu veya Dosya > Ayarları Kaydet

📁 Dosyalar
Dosya	Açıklama
BefasNew-3.py	Ana uygulama dosyası (güncel)
strategy_engine.py	Öngörü strateji motoru
Fon.md	Ayarlar dosyası (fon listeleri, ağırlıklar)
fund_cache.json	Önbellek dosyası (otomatik)
Help.md	Bu yardım dosyası
ONGORU_PLANI.md	Strateji yol haritası
⚠️ Sorun Giderme
CSV Yüklenmiyor
Dosyanın UTF-8 formatında olduğundan emin olun
Gerekli sütunların mevcut olduğunu kontrol edin
Varlık Dağılımı Görünmüyor
İnternet bağlantınızı kontrol edin
TEFAS sitesinin erişilebilir olduğundan emin olun
Skor Hesaplanamıyor
Toplam ağırlığın 10 olduğundan emin olun (yeşil renkte gösterilmeli)
📞 İletişim
Sorularınız için: GitHub Issues

Versiyon: 3.0 (Öngörü Motorlu) Güncelleme: 21 Şubat 2026
