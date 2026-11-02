# Atra Yayın ve Microsoft Store Hazırlık Özeti

## Bu Oturumda Tamamlananlar
- **Çevrimdışı gizlilik sınırı**: `translation_engine == "offline"` iken model bulunamazsa veya yerel çeviri başarısız olursa metin sessizce Google Translate'e gönderilmez.
- **Kimlik bilgisi koruması**: `deepl_api_key` alanı `config.json` içine düz metin olarak yazılmaz; Windows DPAPI (`CryptProtectData`, mevcut kullanıcı kapsamı) ile şifrelenir. Eski düz metin anahtarlar okunup otomatik olarak DPAPI formatına taşınır; koruma başarısız olursa mevcut dosya ezilmez.
- **Kullanıcı veri dizini ve otomatik taşıma (`%LOCALAPPDATA%\Atra`)**: `config.json`, `translation_cache.sqlite3` ve `translator.log` artık `%LOCALAPPDATA%\Atra` (veya `ATRA_DATA_DIR`) altında tutulur. Kurulum dizinindeki (`BASE_DIR`) mevcut `config.json` ve `translation_cache.sqlite3` verileri ilk açılışta veri kaybı olmadan otomatik olarak `%LOCALAPPDATA%\Atra` dizinine taşınır.
- **Uygulama içi önbellek ve geçmiş sıfırlama**: **Son çeviriler → Önbelleği sıfırla** aksiyonu ile bellek içi önbellek, `translation_cache.sqlite3` (`translations_v2`), ekran üstü katman ve `translator.log` tek tıkla temizlenir.
- **Bozuk model karantinası ve otomatik onarım**: `%LOCALAPPDATA%\Atra\models\opus-en-tr\<revision>` dizinindeki dosyalar bozulmuş veya yarım kalmışsa mevcut dosyalar `.corrupt-<timestamp>` karantina klasörüne alınarak korunur ve doğrulanmış model otomatik olarak yeniden indirilir.
- **Hata günlüğü daraltma**: Çeviri servis hatalarında tam URL ve sorgu parametreleri istisna zincirinden ayrıştırılarak `translator.log` içine OCR metni sızması azaltıldı.
- **Ağ bildirimi**: Arayüzde `Google`, `DeepL` ve seslendirme seçeneklerinin metni internete gönderdiği açıkça belirtildi.
- **Otomatik yerel model hazırlama**:
  - `Çevrimdışı` seçildiğinde paketlenmiş model yoksa sabitlenmiş Hugging Face revizyonu `%LOCALAPPDATA%\Atra\models\opus-en-tr\<revision>` altına indirilir, her dosyanın boyutu ve SHA-256 özeti doğrulanır, ardından atomik olarak etkinleştirilir.
  - `Ollama` seçildiğinde yerel `127.0.0.1` / `localhost` sunucusu kontrol edilir; yoksa `winget` (`Ollama.Ollama`) veya SHA-256 doğrulanmış resmi kurulum paketi ile kurulur, servis başlatılır ve RAM miktarına göre `qwen2.5:0.5b` (`<6 GB`) veya `qwen2.5:1.5b` (`>=6 GB`) modeli indirilir.
- **Temiz dağıtım paketleyici (`scripts/build_clean_release.py`) & Lisans bildirimleri (`THIRD_PARTY_NOTICES.md`)**: Yalnızca izin verilen çalışma zamanı dosyalarını içeren, kişisel ayar/önbellek/log barındırmayan temiz dağıtım dizini (`dist/Atra-Release-Staging`) doğrulandı.

## Microsoft Store / MSIX Yayını Öncesi Dış Ortam Kontrol Listesi
1. **MSIX / imzalı kurulum paketi**: `dist/Atra-Release-Staging` çıktısından MSIX veya imzalanmış Windows kurulum paketi üretilmeli ve Code Signing sertifikasıyla imzalanmalı.
2. **Temiz Windows 11 makine testi**: Geliştirici araçları olmayan temiz bir Windows 11 makinede ilk açılış ve sıfırdan Ollama kurulumunun fiziksel ağ testi yapılmalı.
3. **WACK / Store sertifikasyonu**: Paket üretildikten sonra Windows App Certification Kit çalıştırılmalı.
