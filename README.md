# Atra — Oyun Çeviri Stüdyosu

Gerçek zamanlı ekran yakalama (Windows WinRT OCR), çevrimdışı yerel sinirsel çeviri (**CTranslate2 + SentencePiece Opus-MT EN→TR**), yerel **Ollama LLM**, **DeepL** ve **Google GTX** motorlarıyla çalışan oyun içi Türkçe çeviri stüdyosu.

## Özellikler
- **Oyun Dosyalarına Dokunmadan Çeviri**: Anti-cheat sistemleriyle çakışmayan, `WDA_EXCLUDEFROMCAPTURE` korumalı şeffaf ekran üstü katman (`Yerinde çeviri` ve `Sinematik altyazı` modları).
- **%100 Çevrimdışı Sinirsel Motor**: İnternet bağlantısı gerektirmeyen INT8 optimize `opus-mt-tc-big-en-tr` yerel çeviri motoru ve otomatik model doğrulama/indirme.
- **Yerel Ollama Kurulumu**: Cihaz RAM kapasitesine göre (`qwen2.5:0.5b` / `qwen2.5:1.5b`) otomatik yerel model seçimi ve kurulumu.
- **Oyun Terminolojisi ve Özel İsim Koruması**: 85+ oyun terimi sözlüğü, tuş ataması (`[E]`, `[SPACE]`, `[F]`) ve karakter/yer adı koruma katmanı.
- **Windows DPAPI Güvenliği**: DeepL API anahtarları `%LOCALAPPDATA%\Atra\config.json` içinde Windows DPAPI (`CryptProtectData`) ile kullanıcı hesabına bağlı şifreli saklanır.
- **Canlı RPG Simülatörü**: RDR2, Witcher 3 ve Cyberpunk 2077 sahneleriyle anında test imkânı.

## Kısayollar
- `F8`: Canlı çeviriyi başlat / duraklat
- `F9`: Anlık ekran taraması ve çeviri
- `F10`: Çeviri alanı (ROI) seçimi
- `F11`: Yerinde çeviri / Sinematik altyazı geçişi
- `F12`: Türkçe seslendirme (TTS) aç / kapat

## Çalıştırma ve Doğrulama
```powershell
python main.py
python -u audit/verify.py
python -u scripts/build_clean_release.py
```
