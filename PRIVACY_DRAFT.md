# Atra Gizlilik Özeti

## Yerel İşleme
- Ekran yakalama yalnızca kullanıcı çeviriyi başlattığında (`F8`), anlık çeviri istediğinde (`F9`) veya simülatörü açtığında çalışır.
- Ekran görüntüsü piksel verisi bellekte Windows OCR (WinRT) ile metne dönüştürülür; ham ekran görüntüleri diske kaydedilmez.
- `Çevrimdışı` mod seçildiğinde çeviri yerel CTranslate2 modeliyle yapılır. Model bulunamazsa veya hata oluşursa metin sessizce çevrimiçi bir servise gönderilmez.
- Çevrimdışı model mevcut değilse uygulama, sabitlenmiş model dosyalarını Hugging Face üzerinden HTTPS ile `%LOCALAPPDATA%\Atra\models\opus-en-tr` dizinine indirir ve SHA-256 özetlerini doğrular; bu indirme sırasında oyun metni gönderilmez.

## Çevrimiçi ve Yerel Servis Seçenekleri
- `Google` seçildiğinde algılanan oyun metni çeviri için `translate.googleapis.com` adresine gönderilir.
- `DeepL` seçildiğinde algılanan oyun metni ve kullanıcının girdiği DeepL API anahtarı `api-free.deepl.com` veya `api.deepl.com` adresine gönderilir.
- `Ollama` seçildiğinde metin varsayılan olarak yerel Ollama adresine (`http://127.0.0.1:11434/api/generate`) gönderilir. Ollama kurulu değilse resmi Windows paketi / kurulum dosyası doğrulanarak kurulur ve cihaz belleğine uygun yerel model (`qwen2.5:0.5b` veya `qwen2.5:1.5b`) indirilir.
- `Türkçe seslendirme` açıldığında çevrilen Türkçe diyalog metni ses üretimi için Microsoft Edge TTS servisine gönderilebilir; geçici ses dosyaları oynatma sonrasında silinir.

## Yerel Olarak Saklanan Veriler (`%LOCALAPPDATA%\Atra`)
- `%LOCALAPPDATA%\Atra\config.json`: Görünüm modu, seçili çeviri motoru, yakalama alanı ve ayarlar. DeepL API anahtarı düz metin olarak değil, Windows DPAPI (`CryptProtectData`) ile mevcut Windows kullanıcısına bağlı şifreli değer olarak saklanır.
- `%LOCALAPPDATA%\Atra\translation_cache.sqlite3`: Tekrarlı OCR metinlerini hızlandırmak için kaynak metin, Türkçe çeviri ve motor kapsam bilgisi.
- `%LOCALAPPDATA%\Atra\translator.log`: Hata ayıklama kayıtları. Ham OCR metinlerini veya tam çeviri istek URL'lerini yazdırmamak üzere sınırlandırılmıştır.

## Veri Silme ve Kontrol
- Uygulama içindeki **Son çeviriler → Önbelleği sıfırla** düğmesi ile çeviri önbelleği (`translation_cache.sqlite3`), geçmiş listesi ve hata günlüğü (`translator.log`) tek tıklamayla sıfırlanabilir.
- DeepL API anahtarı uygulama içindeki alan boşaltılarak silinebilir.
