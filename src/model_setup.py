"""Install selected local translation components without blocking the Qt event loop."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
import ctranslate2  # noqa: F401 -- native DLL order before Qt
import sentencepiece  # noqa: F401
from PyQt6.QtCore import QObject, pyqtSignal
from .model_manifest import FILES, MODEL_REPOSITORY, REVISION

OLLAMA_INSTALLER_URL = 'https://github.com/ollama/ollama/releases/download/v0.22.0/OllamaSetup.exe'
OLLAMA_INSTALLER_SHA256 = 'ad66d4b92fee95c4c456f593970275386bfcc50b6db807d0f3f31d997a81e8bb'


class SetupCancelled(Exception):
    pass


def managed_model_directory() -> Path:
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    return base / 'Atra' / 'models' / 'opus-en-tr' / REVISION


def _check_cancel(event):
    if event.is_set():
        raise SetupCancelled()


def _verified_file(path: Path, size: int, expected: str) -> bool:
    if not path.is_file() or path.stat().st_size != size:
        return False
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest() == expected


def install_offline_model(destination: Path, progress, cancel, *, files=FILES,
                          revision=REVISION, repository=MODEL_REPOSITORY,
                          quarantine_corrupt: bool = False) -> Path:
    """Download a pinned revision into a private staging dir, verify, then publish atomically."""
    destination = Path(destination)
    if destination.is_dir() and all(_verified_file(destination/n, *spec) for n,spec in files.items()):
        return destination
    if destination.exists():
        if quarantine_corrupt or destination == managed_model_directory():
            quarantine = destination.with_name(f"{destination.name}.corrupt-{int(time.time() * 1000)}")
            os.replace(destination, quarantine)
        else:
            raise RuntimeError('Kayıtlı model eksik veya bozuk; mevcut dosyalar korunuyor.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = sum(size for size,_ in files.values())
    if shutil.disk_usage(destination.parent).free < total + 200*1024*1024:
        raise RuntimeError('Çevrimdışı model için yeterli boş disk alanı yok.')
    downloaded = 0
    progress('Çevrimdışı model indiriliyor · yaklaşık 475 MB')
    with tempfile.TemporaryDirectory(prefix='.atra-download-', dir=destination.parent) as temp:
        staging = Path(temp)
        for name,(expected_size,expected_hash) in files.items():
            _check_cancel(cancel)
            url = f'https://huggingface.co/{repository}/resolve/{revision}/{name}'
            digest = hashlib.sha256(); count = 0; last_update = 0.
            with requests.get(url, stream=True, timeout=(15,60)) as response:
                response.raise_for_status()
                if any(urlsplit(r.url).scheme != 'https' for r in [*response.history,response]):
                    raise RuntimeError('Güvensiz model indirme yönlendirmesi engellendi.')
                with (staging/name).open('wb') as output:
                    for chunk in response.iter_content(1024*256):
                        _check_cancel(cancel)
                        if not chunk: continue
                        count += len(chunk); downloaded += len(chunk)
                        if count > expected_size: raise RuntimeError('Model dosyası beklenenden büyük.')
                        output.write(chunk); digest.update(chunk)
                        if time.monotonic()-last_update > .2:
                            progress(f'Çevrimdışı model indiriliyor · %{int(downloaded*100/total)}')
                            last_update = time.monotonic()
            if count != expected_size or digest.hexdigest() != expected_hash:
                raise RuntimeError('Model doğrulaması başarısız; indirme kullanılmadı.')
        _check_cancel(cancel)
        try:
            os.rename(staging,destination)
        except FileExistsError:
            if not all(_verified_file(destination/n,*spec) for n,spec in files.items()):
                raise RuntimeError('Eşzamanlı kurulum tamamlanamadı.')
    return destination


def _physical_memory_bytes() -> int:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),
                    ('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),
                    ('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),
                    ('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual',ctypes.c_ulonglong)]
    status=MEMORYSTATUSEX(); status.dwLength=ctypes.sizeof(status)
    return status.ullTotalPhys if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) else 0


def choose_ollama_model(total_ram: int) -> str:
    # Conservative RAM tiers; actual quality and speed depend on hardware and game text.
    if total_ram and total_ram < 6*1024**3:
        return 'qwen2.5:0.5b'
    return 'qwen2.5:1.5b'


def _ollama_executable() -> str | None:
    found = shutil.which('ollama')
    if found: return found
    path = Path(os.environ.get('LOCALAPPDATA','')) / 'Programs' / 'Ollama' / 'ollama.exe'
    return str(path) if path.is_file() else None


def _ollama_api_base(url: str) -> str:
    parsed=urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password:
        raise RuntimeError('Otomatik Ollama kurulumu yalnızca bu bilgisayardaki sunucuyu destekler.')
    return f'http://{parsed.netloc}'


def _local_session():
    session=requests.Session()
    session.trust_env=False  # Local inference must never pass through an HTTP proxy.
    return session


def _install_ollama(progress, cancel):
    """Use Microsoft's exact package ID, or a hash-pinned official installer as fallback."""
    local_appdata=Path(os.environ.get('LOCALAPPDATA') or Path.home())
    if shutil.disk_usage(local_appdata).free < 4*1024**3:
        raise RuntimeError('Ollama kurulumu için en az 4 GB boş alan gerekli.')
    winget=shutil.which('winget')
    if winget:
        progress('Ollama kuruluyor · Windows Paket Yöneticisi')
        _check_cancel(cancel)
        try:
            result=subprocess.run([winget,'install','--id','Ollama.Ollama','--exact','--source','winget',
                                   '--scope','user','--silent','--disable-interactivity',
                                   '--accept-source-agreements'],
                                  stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                  timeout=600,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode == 0 and _ollama_executable():
                return _ollama_executable()
        except (OSError,subprocess.TimeoutExpired):
            pass
    _check_cancel(cancel)
    if shutil.disk_usage(tempfile.gettempdir()).free < 2200*1024**2:
        raise RuntimeError('Ollama indiricisi için geçici diskte en az 2,2 GB boş alan gerekli.')
    progress('Ollama indiriliyor · yaklaşık 2 GB')
    with tempfile.TemporaryDirectory(prefix='atra-ollama-') as temp:
        installer=Path(temp)/'OllamaSetup.exe'
        digest=hashlib.sha256(); count=0; last=0.
        with requests.get(OLLAMA_INSTALLER_URL,stream=True,timeout=(15,90)) as response:
            response.raise_for_status()
            if any(urlsplit(r.url).scheme != 'https' for r in [*response.history,response]):
                raise RuntimeError('Güvensiz kurulum yönlendirmesi engellendi.')
            length=int(response.headers.get('Content-Length') or 0)
            with installer.open('wb') as output:
                for chunk in response.iter_content(1024*1024):
                    _check_cancel(cancel)
                    if not chunk: continue
                    count+=len(chunk)
                    if count > 2500*1024**2: raise RuntimeError('Kurulum dosyası beklenenden büyük.')
                    output.write(chunk); digest.update(chunk)
                    if length and time.monotonic()-last>.3:
                        progress(f'Ollama indiriliyor · %{min(100,int(count*100/length))}')
                        last=time.monotonic()
        if digest.hexdigest()!=OLLAMA_INSTALLER_SHA256:
            raise RuntimeError('Ollama kurulum dosyası doğrulanamadı.')
        _check_cancel(cancel)
        progress('Ollama bu kullanıcı için kuruluyor…')
        result=subprocess.run([str(installer),'/VERYSILENT','/NORESTART'],
                              stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                              timeout=600,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode != 0: raise RuntimeError('Ollama kurulamadı. ollama.com/download adresinden kurup yeniden deneyin.')
    executable=_ollama_executable()
    if not executable: raise RuntimeError('Ollama kuruldu ancak uygulama yolu bulunamadı.')
    return executable


def ensure_ollama(url: str, configured_model: str, progress, cancel) -> str:
    base=_ollama_api_base(url)
    if configured_model.endswith(':cloud'):
        raise RuntimeError('Otomatik kurulum yalnızca yerel Ollama modellerini destekler.')
    with _local_session() as session:
        def tags():
            response=session.get(base+'/api/tags',timeout=2)
            response.raise_for_status()
            return {x.get('name','') for x in response.json().get('models',[])}
        try:
            available=tags()
        except requests.RequestException:
            executable=_ollama_executable()
            if not executable:
                executable=_install_ollama(progress,cancel)
            _check_cancel(cancel)
            progress('Yerel Ollama sunucusu başlatılıyor…')
            subprocess.Popen([executable,'serve'], stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,close_fds=True,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            deadline=time.monotonic()+45
            while True:
                _check_cancel(cancel)
                try: available=tags(); break
                except requests.RequestException:
                    if time.monotonic()>=deadline: raise RuntimeError('Ollama sunucusu başlatılamadı.') from None
                    cancel.wait(.5)
        # Respect an already-installed configured model, then select a small local model.
        if configured_model in available:
            return configured_model
        model=choose_ollama_model(_physical_memory_bytes())
        if model in available: return model
        model_root=Path(os.environ.get('OLLAMA_MODELS') or Path.home()/'.ollama')
        while not model_root.exists() and model_root != model_root.parent:
            model_root=model_root.parent
        needed=(1200 if model.endswith(':1.5b') else 650)*1024*1024
        if shutil.disk_usage(model_root).free < needed:
            raise RuntimeError('Ollama modeli için yeterli boş disk alanı yok.')
        progress(f'{model} indiriliyor · yaklaşık 1 GB gerekebilir')
        _check_cancel(cancel)
        with session.post(base+'/api/pull',json={'model':model,'stream':True},stream=True,timeout=(10,120)) as response:
            response.raise_for_status()
            success=False; last_update=0.
            for line in response.iter_lines():
                _check_cancel(cancel)
                if not line: continue
                message=json.loads(line)
                if message.get('error'): raise RuntimeError('Ollama modeli indirilemedi.')
                if message.get('status')=='success': success=True
                total=message.get('total',0); done=message.get('completed',0)
                if total and time.monotonic()-last_update>.2:
                    progress(f'{model} indirme katmanı · %{min(100,int(done*100/total))}')
                    last_update=time.monotonic()
            if not success: raise RuntimeError('Ollama model indirmesi tamamlanmadı.')
        if model not in tags(): raise RuntimeError('İndirilen Ollama modeli doğrulanamadı.')
        return model


class ModelProvisioner(QObject):
    progress = pyqtSignal(int,str)
    ready = pyqtSignal(int,str,str)
    failed = pyqtSignal(int,str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._generation=0; self._cancel=threading.Event(); self._serial=threading.Lock()

    def cancel(self):
        self._cancel.set(); self._generation+=1

    def start(self, kind, engine, url, model):
        self.cancel(); self._cancel=threading.Event()
        event=self._cancel; token=self._generation
        def run():
            try:
                with self._serial:
                    _check_cancel(event)
                    notify=lambda value: self.progress.emit(token,value) if not event.is_set() else None
                    if kind=='offline':
                        if engine.is_available():
                            try:
                                engine._ensure_loaded()
                            except Exception:
                                engine.model_dir=install_offline_model(managed_model_directory(),notify,event)
                        else:
                            engine.model_dir=install_offline_model(managed_model_directory(),notify,event)
                        notify('Çevrimdışı model hazırlanıyor…')
                        engine._ensure_loaded()
                        result=''
                    else:
                        result=ensure_ollama(url,model,notify,event)
                    _check_cancel(event)
                    self.ready.emit(token,kind,result)
            except SetupCancelled:
                pass
            except Exception as exc:
                # Do not surface URLs or user data from network exceptions.
                message=str(exc) if isinstance(exc,RuntimeError) else 'Kurulum tamamlanamadı. İnternet ve disk alanını kontrol edin.'
                if not event.is_set(): self.failed.emit(token,message)
        threading.Thread(target=run,name='atra-model-setup',daemon=True).start()
        return token
