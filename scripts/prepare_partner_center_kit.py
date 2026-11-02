"""
Prepare the complete Microsoft Partner Center submission kit in dist/store-submission/:
  1. 5x 1920x1080 (16:9 Full HD) Store-compliant screenshots
  2. Partner Center Store Listing Logos (300x300, 1080x1080, 720x1080, 1920x1080)
  3. Standalone silent-capable Windows installer (AtraSetup.exe) + Uninstall support
  4. Interactive HTML Partner Center Copy-Paste Dashboard (PARTNER_CENTER_REHBERI.html)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = Path(r"C:\Users\ataka\.gemini\antigravity\brain\d7b3bd9f-acb9-4092-ba12-cac087e3c4bc")
DIST_ATRA = ROOT / "dist" / "Atra"
SUBMISSION_DIR = ROOT / "dist" / "store-submission"
SCREENSHOTS_DIR = SUBMISSION_DIR / "screenshots"
STORE_ASSETS_DIR = SUBMISSION_DIR / "store-assets"
INSTALLER_BUILD_DIR = ROOT / "build" / "installer"


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("segoeuib.ttf" if bold else "segoeui.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _create_1080p_canvas(title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    canvas = Image.new("RGBA", (1920, 1080), (14, 16, 21, 255))
    draw = ImageDraw.Draw(canvas)

    # Subtle top studio header bar
    draw.rectangle((0, 0, 1920, 96), fill=(22, 24, 30, 255))
    draw.line((0, 96, 1920, 96), fill=(48, 52, 64, 255), width=1)

    icon_path = ROOT / "assets" / "app_logo.png"
    if icon_path.is_file():
        with Image.open(icon_path) as ic:
            ic_small = ic.convert("RGBA").resize((48, 48), Image.Resampling.LANCZOS)
            canvas.paste(ic_small, (48, 24), ic_small)

    f_title = _load_font(26, bold=True)
    f_sub = _load_font(18, bold=False)
    draw.text((112, 20), title, fill=(245, 246, 250, 255), font=f_title)
    draw.text((112, 54), subtitle, fill=(165, 170, 184, 255), font=f_sub)

    # Subtle badge on top-right
    badge_txt = "ÜCRETSİZ • %100 ÇEVRİMDIŞI & YEREL AI DESTEKLİ"
    f_badge = _load_font(15, bold=True)
    draw.rounded_rectangle((1430, 28, 1872, 68), radius=10, fill=(34, 58, 108, 255), outline=(72, 124, 228, 255), width=1)
    draw.text((1452, 38), badge_txt, fill=(235, 242, 255, 255), font=f_badge)
    return canvas, draw


def _paste_centered_pair(
    canvas: Image.Image,
    left_img_path: Path,
    right_img_path: Path,
) -> None:
    max_h = 910
    with Image.open(left_img_path) as l_raw, Image.open(right_img_path) as r_raw:
        l_img = l_raw.convert("RGBA")
        r_img = r_raw.convert("RGBA")

        if r_img.height > max_h:
            scale = max_h / r_img.height
            r_img = r_img.resize((int(r_img.width * scale), max_h), Image.Resampling.LANCZOS)
        if l_img.height > max_h:
            scale = max_h / l_img.height
            l_img = l_img.resize((int(l_img.width * scale), max_h), Image.Resampling.LANCZOS)

        gap = 48
        total_w = l_img.width + gap + r_img.width
        start_x = (1920 - total_w) // 2
        avail_top = 108
        avail_h = 1080 - avail_top

        ly = avail_top + (avail_h - l_img.height) // 2
        ry = avail_top + (avail_h - r_img.height) // 2
        canvas.paste(l_img, (start_x, ly), l_img)
        canvas.paste(r_img, (start_x + l_img.width + gap, ry), r_img)


def generate_store_screenshots() -> list[Path]:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    # 1. RDR2 Live In-Place + Studio Control Panel
    c1, _ = _create_1080p_canvas(
        "Atra — Oyun Çeviri Stüdyosu",
        "Oyun dosyalarına dokunmadan gerçek zamanlı yerinde (In-Place) Türkçe çeviri katmanı",
    )
    _paste_centered_pair(c1, ARTIFACTS_DIR / "simulator_scene_1.png", ARTIFACTS_DIR / "atra_studio.png")
    p1 = SCREENSHOTS_DIR / "01_Atra_Canli_Oyun_Ceviri_RDR2.png"
    c1.convert("RGB").save(p1, format="PNG")
    generated.append(p1)

    # 2. Cyberpunk Sinematik Altyazı Modu + Studio Panel
    c2, _ = _create_1080p_canvas(
        "Sinematik Altyazı Modu (Cyberpunk 2077 Örneği)",
        "Konuşmacı rozeti ve yüksek okunabilirlikli sinema altyazı bandı (F11 ile anında geçiş)",
    )
    _paste_centered_pair(c2, ARTIFACTS_DIR / "simulator_subtitle.png", ARTIFACTS_DIR / "atra_studio.png")
    p2 = SCREENSHOTS_DIR / "02_Atra_Sinematik_Altyazi_Cyberpunk.png"
    c2.convert("RGB").save(p2, format="PNG")
    generated.append(p2)

    # 3. Witcher 3 Yerinde Çeviri + Özel İsim ve Tuş Koruması
    c3, _ = _create_1080p_canvas(
        "Oyun Terminolojisi, Karakter Adı ve Tuş Ataması Koruması",
        "Geralt, Night City, Blackwater gibi özel adları ve [E], [SPACE], [F] tuşlarını bozmadan çevirir",
    )
    _paste_centered_pair(c3, ARTIFACTS_DIR / "simulator_scene_2.png", ARTIFACTS_DIR / "atra_keyboard_focus.png")
    p3 = SCREENSHOTS_DIR / "03_Atra_Witcher3_Ozel_Isim_Korumasi.png"
    c3.convert("RGB").save(p3, format="PNG")
    generated.append(p3)

    # 4. Cyberpunk Yerinde Çeviri + DeepL / Ollama / Çevrimdışı Motor Seçenekleri
    c4, _ = _create_1080p_canvas(
        "4 Farklı Çeviri Motoru: Çevrimdışı (Opus-MT), Yerel Ollama, DeepL ve Google",
        "İnternetsiz yerel sinirsel çeviri veya Windows DPAPI şifreli DeepL API desteği",
    )
    _paste_centered_pair(c4, ARTIFACTS_DIR / "simulator_scene_3.png", ARTIFACTS_DIR / "atra_deepl.png")
    p4 = SCREENSHOTS_DIR / "04_Atra_Coklu_Motor_DeepL_Ollama.png"
    c4.convert("RGB").save(p4, format="PNG")
    generated.append(p4)

    # 5. Kompakt HUD Modu & Tam Stüdyo Karşılaştırması
    c5, _ = _create_1080p_canvas(
        "Kompakt Başlık Çubuğu ve Tam Stüdyo Görünümü",
        "Oyun sırasında tek tıkla küçülen kompakt mod ve F8 / F9 / F10 / F11 / F12 küresel kısayollar",
    )
    _paste_centered_pair(c5, ARTIFACTS_DIR / "atra_compact.png", ARTIFACTS_DIR / "atra_idle.png")
    p5 = SCREENSHOTS_DIR / "05_Atra_Kompakt_ve_Tam_Gorunum.png"
    c5.convert("RGB").save(p5, format="PNG")
    generated.append(p5)

    return generated


def generate_store_listing_logos() -> list[Path]:
    STORE_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    out_files: list[Path] = []
    icon_src = ROOT / "assets" / "atra_icon_1024.png"

    with Image.open(icon_src) as raw:
        icon_rgba = raw.convert("RGBA")

        # 1. 300x300 Store Listing Logo
        p_300 = STORE_ASSETS_DIR / "StoreLogo_300x300.png"
        icon_rgba.resize((300, 300), Image.Resampling.LANCZOS).save(p_300, format="PNG")
        out_files.append(p_300)

        # 2. 1080x1080 Box Art (1:1)
        box = Image.new("RGBA", (1080, 1080), (20, 22, 28, 255))
        ic_520 = icon_rgba.resize((520, 520), Image.Resampling.LANCZOS)
        box.paste(ic_520, ((1080 - 520) // 2, 190), ic_520)
        d_box = ImageDraw.Draw(box)
        d_box.text((395, 760), "Atra", fill=(245, 246, 250, 255), font=_load_font(96, bold=True))
        d_box.text((255, 885), "Oyun Çeviri Stüdyosu • EN → TR", fill=(165, 172, 190, 255), font=_load_font(38, bold=False))
        p_1080 = STORE_ASSETS_DIR / "BoxArt_1080x1080.png"
        box.convert("RGB").save(p_1080, format="PNG")
        out_files.append(p_1080)

        # 3. 720x1080 Poster Art (2:3)
        poster = Image.new("RGBA", (720, 1080), (20, 22, 28, 255))
        ic_380 = icon_rgba.resize((380, 380), Image.Resampling.LANCZOS)
        poster.paste(ic_380, ((720 - 380) // 2, 220), ic_380)
        d_pos = ImageDraw.Draw(poster)
        d_pos.text((240, 650), "Atra", fill=(245, 246, 250, 255), font=_load_font(84, bold=True))
        d_pos.text((135, 765), "Oyun Çeviri Stüdyosu", fill=(165, 172, 190, 255), font=_load_font(34, bold=False))
        p_poster = STORE_ASSETS_DIR / "PosterArt_720x1080.png"
        poster.convert("RGB").save(p_poster, format="PNG")
        out_files.append(p_poster)

        # 4. 1920x1080 Hero / Promotional Art (16:9)
        hero = Image.new("RGBA", (1920, 1080), (16, 18, 24, 255))
        ic_320 = icon_rgba.resize((320, 320), Image.Resampling.LANCZOS)
        hero.paste(ic_320, (140, 220), ic_320)
        d_hero = ImageDraw.Draw(hero)
        d_hero.text((140, 580), "Atra", fill=(245, 246, 250, 255), font=_load_font(104, bold=True))
        d_hero.text((140, 710), "Gerçek Zamanlı Türkçe Oyun Çeviri Stüdyosu", fill=(195, 202, 220, 255), font=_load_font(36, bold=True))
        d_hero.text((140, 770), "%100 Çevrimdışı Sinirsel Çeviri • Yerel Ollama • DeepL • Google", fill=(140, 148, 168, 255), font=_load_font(26, bold=False))
        if (ARTIFACTS_DIR / "atra_studio.png").is_file():
            with Image.open(ARTIFACTS_DIR / "atra_studio.png") as st:
                st_rgba = st.convert("RGBA")
                scale = 880 / st_rgba.height
                st_resized = st_rgba.resize((int(st_rgba.width * scale), 880), Image.Resampling.LANCZOS)
                hero.paste(st_resized, (1180, 100), st_resized)
        p_hero = STORE_ASSETS_DIR / "HeroBanner_1920x1080.png"
        hero.convert("RGB").save(p_hero, format="PNG")
        out_files.append(p_hero)

    return out_files


def build_win32_installer() -> Path:
    """Compile the native Inno Setup installer and a separate portable archive."""
    if not (DIST_ATRA / "Atra.exe").is_file():
        raise FileNotFoundError("Build dist/Atra first with scripts/build_store_package.py")
    SUBMISSION_DIR.mkdir(parents=True, exist_ok=True)
    iscc = shutil.which("ISCC.exe")
    if not iscc:
        candidates = [Path.home() / "AppData/Local/Programs/Inno Setup 6/ISCC.exe",
                      Path(r"C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
                      Path(r"C:/Program Files/Inno Setup 6/ISCC.exe")]
        iscc = next((str(path) for path in candidates if path.is_file()), None)
    if not iscc:
        raise RuntimeError("Inno Setup 6 compiler (ISCC.exe) is required")
    subprocess.run([iscc, str(ROOT / "packaging" / "atra.iss")], check=True)
    portable = SUBMISSION_DIR / "Atra-Portable-Windows-x64.zip"
    with zipfile.ZipFile(portable, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
        for path in sorted(DIST_ATRA.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(Path("Atra") / path.relative_to(DIST_ATRA)))
    installer = SUBMISSION_DIR / "AtraSetup.exe"
    if not installer.is_file():
        raise FileNotFoundError(f"Expected installer not found: {installer}")
    return installer


def generate_html_dashboard(installer_exe: Path, screenshots: list[Path], logos: list[Path]) -> Path:
    html_path = SUBMISSION_DIR / "PARTNER_CENTER_REHBERI.html"
    privacy_text = (ROOT / "PRIVACY_DRAFT.md").read_text(encoding="utf-8")

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>Atra — Microsoft Store Partner Center Başvuru Paneli</title>
<style>
  :root {{
    --bg: #12141a;
    --card: #1b1e26;
    --border: #2e3340;
    --text: #f3f4f8;
    --muted: #9ca3b5;
    --accent: #3b82f6;
    --accent-hover: #2563eb;
    --ok: #22c55e;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px 40px;
    background: var(--bg); color: var(--text);
    font-family: 'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif;
    line-height: 1.55;
  }}
  .container {{ max-width: 1120px; margin: 0 auto; }}
  .hero {{
    display: flex; align-items: center; justify-content: space-between;
    background: var(--card); border: 1px solid var(--border);
    border-radius: 14px; padding: 22px 28px; margin-bottom: 24px;
  }}
  .hero h1 {{ margin: 0 0 6px 0; font-size: 24px; }}
  .hero p {{ margin: 0; color: var(--muted); font-size: 14px; }}
  .badge {{
    background: rgba(34, 197, 94, 0.14); color: #4ade80;
    border: 1px solid rgba(34, 197, 94, 0.35);
    padding: 8px 14px; border-radius: 999px; font-weight: 600; font-size: 13px;
  }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 22px; }}
  .card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 20px 22px; margin-bottom: 18px;
  }}
  .card h2 {{ margin: 0 0 12px 0; font-size: 17px; color: #e2e8f0; display: flex; justify-content: space-between; align-items: center; }}
  .field {{ margin-bottom: 14px; }}
  .field-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
  .field-label {{ font-size: 13px; font-weight: 600; color: var(--muted); }}
  pre, textarea {{
    width: 100%; background: #111318; color: var(--text);
    border: 1px solid #282c37; border-radius: 8px;
    padding: 11px 13px; font-family: 'Cascadia Code', Consolas, monospace;
    font-size: 13px; margin: 0; white-space: pre-wrap; word-break: break-word;
  }}
  button.copy-btn {{
    background: var(--accent); color: #fff; border: none;
    border-radius: 6px; padding: 5px 12px; font-size: 12px; font-weight: 600;
    cursor: pointer; transition: background 0.15s;
  }}
  button.copy-btn:hover {{ background: var(--accent-hover); }}
  button.copy-btn.copied {{ background: var(--ok); }}
  .thumbs {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-top: 10px; }}
  .thumbs img {{ width: 100%; border-radius: 8px; border: 1px solid var(--border); }}
  .step-tag {{ color: #60a5fa; font-weight: 700; }}
</style>
</head>
<body>
<div class="container">
  <div class="hero">
    <div>
      <h1>Atra — Microsoft Store Başvuru & Kopyala-Yapıştır Merkezi</h1>
      <p>Yan sekmede açılan <b>Partner Center</b> formundaki tüm kutuları buradan tek tıkla kopyalayıp yapıştırabilirsin.</p>
    </div>
    <div class="badge">✓ TÜM DOSYALAR HAZIR (ÜCRETSİZ YAYIN)</div>
  </div>

  <div class="grid">
    <div class="card">
      <h2><span><span class="step-tag">ADIM 1</span> · Uygulama Oluşturma & Paket Yükleme</span></h2>
      <div class="field">
        <div class="field-header">
          <span class="field-label">Uygulama Adı (Reserve App Name)</span>
          <button class="copy-btn" onclick="copyText('app-name', this)">Kopyala</button>
        </div>
        <pre id="app-name">Atra — Oyun Çeviri Stüdyosu</pre>
      </div>
      <div class="field">
        <div class="field-header">
          <span class="field-label">Alternatif Kısa Ad (Eğer sadece Atra seçersen)</span>
          <button class="copy-btn" onclick="copyText('app-name-short', this)">Kopyala</button>
        </div>
        <pre id="app-name-short">Atra</pre>
      </div>
      <div class="field">
        <div class="field-header">
          <span class="field-label">Canlı HTTPS Paket İndirme Bağlantısı (Partner Center Package URL kutusuna yapıştır)</span>
          <button class="copy-btn" onclick="copyText('pkg-https-url', this)">URL'yi Kopyala</button>
        </div>
        <pre id="pkg-https-url">https://github.com/ataturukmen420/atra/releases/download/v1.0.1/AtraSetup.exe</pre>
      </div>
      <div class="field">
        <div class="field-header">
          <span class="field-label">Yerel Kurulum Paketi Dosya Yolu</span>
          <button class="copy-btn" onclick="copyText('pkg-path', this)">Yolu Kopyala</button>
        </div>
        <pre id="pkg-path">{installer_exe}</pre>
      </div>
      <div class="field">
        <div class="field-header">
          <span class="field-label">Sessiz Kurulum Parametresi (Installer Parameters kutusuna yapıştır)</span>
          <button class="copy-btn" onclick="copyText('silent-arg', this)">Kopyala</button>
        </div>
        <pre id="silent-arg">/S</pre>
      </div>
    </div>

    <div class="card">
      <h2><span><span class="step-tag">ADIM 2</span> · Fiyatlandırma, Kategori & Yaş Sınırı</span></h2>
      <div class="field">
        <div class="field-header">
          <span class="field-label">Fiyatlandırma (Pricing and availability)</span>
        </div>
        <pre>• Base price: Free (Ücretsiz)
• Markets: All markets (Tüm ülkeler veya Türkiye + seçili ülkeler)
• Category: Utilities &amp; tools (Araçlar ve yardımcı programlar)</pre>
      </div>
      <div class="field">
        <div class="field-header">
          <span class="field-label">Ekran Görüntüleri Klasörü (1920×1080 5 Adet PNG)</span>
          <button class="copy-btn" onclick="copyText('ss-path', this)">Klasör Yolunu Kopyala</button>
        </div>
        <pre id="ss-path">{SCREENSHOTS_DIR}</pre>
      </div>
      <div class="field">
        <div class="field-header">
          <span class="field-label">Store Logo &amp; Kapak Görselleri Klasörü (300×300, 1080×1080, 720×1080)</span>
          <button class="copy-btn" onclick="copyText('logo-path', this)">Klasör Yolunu Kopyala</button>
        </div>
        <pre id="logo-path">{STORE_ASSETS_DIR}</pre>
      </div>
    </div>
  </div>

  <div class="card">
    <h2><span><span class="step-tag">ADIM 3</span> · Mağaza Listeleme Metinleri (Store Listing — Turkish / English)</span></h2>
    <div class="field">
      <div class="field-header">
        <span class="field-label">Kısa Açıklama (Short Description)</span>
        <button class="copy-btn" onclick="copyText('short-desc', this)">Kopyala</button>
      </div>
      <pre id="short-desc">Oyun dosyalarına dokunmadan çalışan, %100 çevrimdışı yerel sinirsel çeviri (Opus-MT EN→TR), yerel Ollama, DeepL ve Google destekli gerçek zamanlı Türkçe oyun ve altyazı çeviri stüdyosu.</pre>
    </div>

    <div class="field">
      <div class="field-header">
        <span class="field-label">Tam Açıklama (Description)</span>
        <button class="copy-btn" onclick="copyText('full-desc', this)">Kopyala</button>
      </div>
      <pre id="full-desc">Atra — Oyun Çeviri Stüdyosu, İngilizce oyunları oyun dosyalarına müdahale etmeden veya yama kurmadan gerçek zamanlı olarak Türkçeye çeviren masaüstü çeviri stüdyosudur.

Öne Çıkan Özellikler:
• Oyun Dosyalarına Dokunmaz: Ekran üstü şeffaf katman (Overlay) ile çalışır; oyun dosyalarını değiştirmez.
• İki Farklı Görünüm Modu: Orijinal metnin tam üzerine yerleşen "Yerinde Çeviri (In-Place)" veya ekranın altında beliren "Sinematik Altyazı" modu (F11 ile anında geçiş).
• %100 Çevrimdışı Sinirsel Çeviri: İnternet bağlantısı gerektirmeyen yerel CTranslate2 + SentencePiece (Opus-MT EN→TR) motoru.
• Yerel Ollama LLM, DeepL ve Google Desteği: Cihaz belleğine göre otomatik yerel Qwen 2.5 kurulumu veya Windows DPAPI şifreli DeepL API anahtarı desteği.
• Oyun Terminolojisi ve Özel İsim Koruması: Karakter ve yer adlarını (Geralt, Arthur Morgan, Night City, Blackwater vb.) ve tuş atamalarını ([E], [SPACE], [F]) koruyarak doğal Türkçe üretir.
• Dahili Canlı Simülatör: RDR2, Witcher 3 ve Cyberpunk sahneleriyle oyun açmadan anında test imkânı.
• Küresel Kısayollar: F8 (Başlat/Duraklat), F9 (Anlık Çeviri), F10 (Alan Seçimi), F11 (Görünüm Modu), F12 (Türkçe Seslendirme).</pre>
    </div>

    <div class="field">
      <div class="field-header">
        <span class="field-label">Anahtar Kelimeler (Search Terms / Keywords — en fazla 7 adet)</span>
        <button class="copy-btn" onclick="copyText('keywords', this)">Kopyala</button>
      </div>
      <pre id="keywords">oyun çeviri, türkçe yama, ekran çeviri, altyazı çeviri, offline translator, game translator, ocr çeviri</pre>
    </div>

    <div class="field">
      <div class="field-header">
        <span class="field-label">Bu Sürümdeki Yenilikler (What's new in this version)</span>
        <button class="copy-btn" onclick="copyText('whats-new', this)">Kopyala</button>
      </div>
      <pre id="whats-new">Atra 1.0 İlk Sürüm:
• Çevrimdışı yerel sinirsel çeviri motoru (Opus-MT EN→TR) ve otomatik model doğrulama
• Yerinde çeviri (In-Place) ve Sinematik altyazı görünüm modları
• Yerel Ollama, DeepL (DPAPI şifreli) ve Google çeviri motorları
• 3 sahneli dahili RPG oyun simülatörü ve Türkçe seslendirme (TTS) desteği</pre>
    </div>
  </div>

  <div class="card">
    <h2><span><span class="step-tag">ADIM 4</span> · Gizlilik Politikası &amp; Microsoft İnceleme Notları (Notes for Certification)</span></h2>
    <div class="field">
      <div class="field-header">
        <span class="field-label">Microsoft İnceleme Ekibine Not (Notes for certification — Test instructions)</span>
        <button class="copy-btn" onclick="copyText('cert-notes', this)">Kopyala</button>
      </div>
      <pre id="cert-notes">Atra is a free desktop screen-capture OCR translation utility (English to Turkish) for Windows games.
How to test immediately without installing a game:
1. Launch Atra.
2. Click the "Simülatör" (SIM) button inside the main control panel to open the built-in 3-scene RPG simulator window.
3. Click "Çeviriyi başlat" (F8) or "Anlık çeviri" (F9) to observe real-time English-to-Turkish in-place and subtitle translations.
4. No login or account is required. User data is stored solely under %LOCALAPPDATA%\\Atra and can be cleared anytime via "Önbelleği sıfırla".</pre>
    </div>

    <div class="field">
      <div class="field-header">
        <span class="field-label">Canlı HTTPS Gizlilik Politikası Bağlantısı (Privacy Policy URL kutusuna yapıştır)</span>
        <button class="copy-btn" onclick="copyText('privacy-url', this)">URL'yi Kopyala</button>
      </div>
      <pre id="privacy-url">https://github.com/ataturukmen420/atra/blob/main/PRIVACY_DRAFT.md</pre>
    </div>

    <div class="field">
      <div class="field-header">
        <span class="field-label">Canlı HTTPS Resmi Proje / Destek Bağlantısı (Website / Support URL kutusuna yapıştır)</span>
        <button class="copy-btn" onclick="copyText('support-url', this)">URL'yi Kopyala</button>
      </div>
      <pre id="support-url">https://github.com/ataturukmen420/atra</pre>
    </div>

    <div class="field">
      <div class="field-header">
        <span class="field-label">Gizlilik Politikası Metni (Privacy Policy Text)</span>
        <button class="copy-btn" onclick="copyText('privacy-body', this)">Kopyala</button>
      </div>
      <pre id="privacy-body">{privacy_text}</pre>
    </div>
  </div>

  <div class="card">
    <h2><span>Hazırlanan 1920×1080 Microsoft Store Ekran Görüntüleri ({len(screenshots)} Adet)</span></h2>
    <div class="thumbs">
      {"".join(f'<img src="screenshots/{p.name}" alt="{p.name}" title="{p.name}">' for p in screenshots)}
    </div>
  </div>
</div>

<script>
function copyText(id, btn) {{
  const text = document.getElementById(id).innerText;
  navigator.clipboard.writeText(text).then(() => {{
    const old = btn.innerText;
    btn.innerText = "✓ Kopyalandı";
    btn.classList.add("copied");
    setTimeout(() => {{
      btn.innerText = old;
      btn.classList.remove("copied");
    }}, 1600);
  }});
}}
</script>
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")
    return html_path


if __name__ == "__main__":
    shots = generate_store_screenshots()
    logos = generate_store_listing_logos()
    installer = build_win32_installer()
    dashboard = generate_html_dashboard(installer, shots, logos)
    print(f"[PASS] Screenshots ({len(shots)}): {SCREENSHOTS_DIR}")
    print(f"[PASS] Store Logos ({len(logos)}): {STORE_ASSETS_DIR}")
    print(f"[PASS] Silent-capable Win32 Store Installer: {installer}")
    print(f"[PASS] Partner Center Dashboard HTML: {dashboard}")
