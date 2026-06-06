"""
XrayProxy — ядро логики
pico-soft | https://github.com/pico-soft/XrayProxy
Версия: 2.20-beta

Новое в 2.0:
- Автомониторинг: проверка скорости каждые N минут
- Авто-переключение при падении скорости ниже порога
- Каскадный перебор серверов и подписок
"""

import os
import sys
import json
import time
import socket
import base64
import signal
import logging
import threading
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any, Tuple

VERSION = "2.20-beta"
APP_NAME = "XrayProxy"
APP_AUTHOR = "pico-soft"
APP_REPO = "https://github.com/pico-soft/XrayProxy"

# --- Пути ---

HOME = Path(os.environ.get("HOME", str(Path.home())))
XRAY_DIR = HOME / "xproxy"
XRAY_BIN = XRAY_DIR / "xray"
CONFIG_FILE = XRAY_DIR / "config.json"
SUBS_FILE = XRAY_DIR / "subscriptions.json"
BLACKLIST_FILE = XRAY_DIR / "blacklist.txt"
SETTINGS_FILE = XRAY_DIR / "settings.json"
SERVERS_DIR = XRAY_DIR / "servers"
PID_FILE = XRAY_DIR / "xray.pid"
BG_PID_FILE = XRAY_DIR / "bg_check.pid"
LOG_FILE = XRAY_DIR / "xray.log"
APP_LOG_FILE = XRAY_DIR / "xrayproxy.log"

APP_LOG_MAX_BYTES = 200_000
APP_LOG_BACKUP_COUNT = 1

SOCKS_PORT = 10828
HTTP_PORT = 10829
BG_CHECK_INTERVAL = 3600
PING_WORKERS = 20

# Сколько последних ZIP-логов держать в директории экспорта.
# Переопределяется через settings.log_archive_keep.
LOG_ARCHIVE_KEEP_DEFAULT = 10

# Дефолты настроек
DEFAULT_SETTINGS = {
    "proxy_check_timeout": 2,
    "active_subscription": None,
    "last_test_time": None,
    "last_update_time": None,
    "auto_monitor": True,
    "monitor_interval": 120,              # секунды (2 минуты)
    "min_speed_threshold": 1.0,           # устаревшее, для обратной совместимости
    "direct_speed_threshold": 1.0,        # Мбит/с — порог прямой скорости
    "tunnel_speed_threshold": 1.0,        # Мбит/с — порог скорости туннеля
    "channel_speed_probes": None,         # None = DEFAULT_CHANNEL_SPEED_PROBES
    "external_reach_probes": None,        # None = DEFAULT_EXTERNAL_REACH_PROBES
    "log_archive_keep": None,             # None = LOG_ARCHIVE_KEEP_DEFAULT
}

DEFAULT_BLACKLIST = [
    "москва", "россия", "санкт-петербург", "беларусь", "минск", "крым",
    "moscow", "russia", "st. petersburg", "belarus", "minsk", "crimea",
]

XRAY_DOWNLOAD_URLS = [
    # GitHub (основной)
    "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-android-arm64-v8a.zip",
    # GitHub через зеркало ghproxy
    "https://ghp.ci/https://github.com/XTLS/Xray-core/releases/latest/download/Xray-android-arm64-v8a.zip",
    # GitHub через другое зеркало
    "https://gh-proxy.com/https://github.com/XTLS/Xray-core/releases/latest/download/Xray-android-arm64-v8a.zip",
]

IP_CHECK_URLS = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
    "https://checkip.amazonaws.com",
]
USER_AGENT = "v2rayNG/1.8.0"

# --- Пробники "честного" замера ---
# A: скорость канала — близкие/российские CDN, незаблокированные, НЕ Cloudflare.
# Меняются через settings.channel_speed_probes без правки кода.
DEFAULT_CHANNEL_SPEED_PROBES = [
    "https://mc.yandex.ru/metrika/tag.js",              # ~60 KB, Яндекс Метрика CDN
    "https://yastatic.net/jquery/3.6.4/jquery.min.js",  # ~87 KB, Яндекс статик CDN
    "https://vk.com/js/api/openapi.js",                 # ~30 KB, VK инфра (fallback)
]
# B: достижимость "обычного" внешнего мира — НЕ в РФ-whitelist, НЕ Cloudflare.
# expect_substr защищает от подмены ответа заглушкой whitelist-провайдера.
DEFAULT_EXTERNAL_REACH_PROBES = [
    {"url": "http://detectportal.firefox.com/success.txt", "expect_substr": "success"},
    {"url": "http://example.com/",                          "expect_substr": "Example Domain"},
    {"url": "http://neverssl.com/",                         "expect_substr": "NeverSSL"},
]


# --- Логгирование ---

_logger: Optional[logging.Logger] = None

def _setup_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    XRAY_DIR.mkdir(exist_ok=True)
    _logger = logging.getLogger("xrayproxy")
    _logger.setLevel(logging.DEBUG)
    _logger.handlers.clear()
    handler = RotatingFileHandler(
        str(APP_LOG_FILE), maxBytes=APP_LOG_MAX_BYTES,
        backupCount=APP_LOG_BACKUP_COUNT, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    _logger.addHandler(handler)
    return _logger

def log(msg: str, level: str = "info") -> None:
    try:
        _setup_logger().log(getattr(logging, level.upper(), logging.INFO), msg)
    except Exception:
        pass

def log_action(action: str, details: str = "") -> None:
    log(f"ACTION: {action}" + (f" | {details}" if details else ""))

def get_log_contents() -> str:
    result = ""
    for p in [Path(str(APP_LOG_FILE) + ".1"), APP_LOG_FILE]:
        if p.exists():
            try:
                result += p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
    return result


# --- Утилиты ---

def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def _name_from_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        path = parsed.path.strip("/")
        if path:
            return f"{host}/{path.split('/')[-1][:12]}"
        return host
    except Exception:
        return url[:30]


# --- Инициализация ---

def init() -> None:
    XRAY_DIR.mkdir(exist_ok=True)
    SERVERS_DIR.mkdir(exist_ok=True)

    # Очистка временных артефактов прошлых тестов (_run_temp_xray).
    # Префикс _test_ зарезервирован за временными тестами, ничего рабочего его не носит.
    leftover = 0
    for p in XRAY_DIR.glob("_test_*"):
        try:
            p.unlink()
            leftover += 1
        except Exception:
            pass
    if leftover:
        log(f"init: убрано {leftover} остаточных _test_* артефактов")

    if not BLACKLIST_FILE.exists():
        BLACKLIST_FILE.write_text("\n".join(DEFAULT_BLACKLIST) + "\n")

    old_subs = XRAY_DIR / "subscriptions.txt"
    if old_subs.exists() and not SUBS_FILE.exists():
        subs = []
        for line in old_subs.read_text().splitlines():
            url = line.strip()
            if url:
                subs.append({"url": url, "name": _name_from_url(url)})
        SUBS_FILE.write_text(json.dumps(subs, indent=2, ensure_ascii=False))
        old_subs.rename(str(old_subs) + ".migrated")

    if not SUBS_FILE.exists():
        SUBS_FILE.write_text("[]")

    if not SETTINGS_FILE.exists():
        save_settings(dict(DEFAULT_SETTINGS))
    else:
        # Добавляем новые настройки, сохраняя старые
        s = load_settings()
        changed = False
        for k, v in DEFAULT_SETTINGS.items():
            if k not in s:
                s[k] = v
                changed = True
        if changed:
            save_settings(s)

    log(f"{APP_NAME} v.{VERSION} started")


def xray_installed() -> bool:
    return XRAY_BIN.exists() and os.access(XRAY_BIN, os.X_OK)

def _detect_system_proxy() -> Optional[str]:
    """Ищет активный VPN/прокси в системе."""
    # Проверяем HTTP_PROXY / HTTPS_PROXY
    for var in ["HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy"]:
        val = os.environ.get(var)
        if val:
            return val

    # Проверяем наличие tun0 (VPN-интерфейс)
    try:
        r = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=5)
        if "tun0" in r.stdout or "tun1" in r.stdout:
            return "__vpn__"  # VPN есть, curl пойдёт через него напрямую
    except Exception:
        pass

    return None


def smart_download(url: str, output: Path, urls_alt: List[str] = None,
                   progress_cb=None, timeout: int = 45, min_size: int = 10000) -> bool:
    """Универсальная функция скачивания с каскадом способов.

    Порядок:
    1. Напрямую (все URL)
    2. Через системный VPN/прокси (если есть)
    3. Через XrayProxy туннель (если работает)
    4. Из ~/storage/downloads/ (ручное скачивание)
    """
    all_urls = [url] + (urls_alt or [])

    def msg(m):
        log(m)
        if progress_cb:
            progress_cb(m)

    def try_curl(u, proxy=None, label=""):
        output.unlink(missing_ok=True)
        cmd = ["curl", "-fL", "--progress-bar", "--max-time", str(timeout), "-o", str(output)]
        if proxy and proxy != "__vpn__":
            cmd.extend(["-x", proxy])
        cmd.append(u)
        try:
            r = subprocess.run(cmd, timeout=timeout + 10)
            if r.returncode == 0 and output.exists() and output.stat().st_size > min_size:
                return True
        except Exception:
            pass
        return False

    # --- Способ 1: напрямую по всем URL ---
    for i, u in enumerate(all_urls, 1):
        label = u.split("/")[2][:20] if "/" in u else "direct"
        msg(f"[{i}/{len(all_urls)}] {label}...")
        if try_curl(u):
            msg(f"✓ Скачано ({label})")
            return True

    # --- Способ 2: через системный VPN/прокси ---
    sys_proxy = _detect_system_proxy()
    if sys_proxy:
        if sys_proxy == "__vpn__":
            msg("Обнаружен VPN-туннель, пробую...")
            # VPN уже в системе — curl пойдёт через него напрямую
            if try_curl(all_urls[0]):
                msg("✓ Скачано через VPN")
                return True
        else:
            msg(f"Системный прокси: {sys_proxy[:30]}...")
            if try_curl(all_urls[0], proxy=sys_proxy):
                msg("✓ Скачано через системный прокси")
                return True

    # --- Способ 3: через XrayProxy туннель ---
    if xray_is_running():
        xp_proxy = f"socks5h://127.0.0.1:{SOCKS_PORT}"
        msg("Через XrayProxy туннель...")
        if try_curl(all_urls[0], proxy=xp_proxy):
            msg("✓ Скачано через туннель")
            return True

    # --- Способ 4: из Downloads (рекурсивно, включая подпапки Telegram и др.) ---
    filename = output.name
    stem = filename.replace(".zip", "")
    for dl_dir in [HOME / "storage" / "downloads", HOME / "storage" / "shared" / "Download"]:
        if not dl_dir.exists():
            continue
        candidates = sorted(dl_dir.rglob(f"{stem}*.zip"), key=lambda f: f.stat().st_mtime, reverse=True)
        if candidates:
            import shutil
            shutil.copy2(str(candidates[0]), str(output))
            if output.exists() and output.stat().st_size > min_size:
                msg(f"✓ Найден в Downloads: {candidates[0].name}")
                return True

    msg("Не удалось скачать.")
    msg(f"Скачай вручную: {all_urls[0]}")
    msg(f"Положи в ~/xproxy/ как {filename}")
    output.unlink(missing_ok=True)
    return False


def install_xray(progress_cb=None, force=False) -> bool:
    log_action("install_xray")
    def msg(m):
        log(m)
        if progress_cb:
            progress_cb(m)

    if not force and xray_installed():
        msg("xray-core уже установлен, пропускаю")
        return True

    msg("Скачиваю xray-core...")
    zip_path = XRAY_DIR / "xray.zip"

    ok = smart_download(
        url=XRAY_DOWNLOAD_URLS[0],
        output=zip_path,
        urls_alt=XRAY_DOWNLOAD_URLS[1:],
        progress_cb=progress_cb,
    )

    if not ok:
        return False

    msg("Распаковываю...")
    try:
        import zipfile
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(XRAY_DIR)
        XRAY_BIN.chmod(0o755)
        zip_path.unlink()
        msg("Готово.")
        return True
    except Exception as e:
        msg(f"Ошибка распаковки: {e}")
        return False


# --- Настройки ---

def load_settings() -> Dict[str, Any]:
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except Exception:
        return dict(DEFAULT_SETTINGS)

def save_settings(s: Dict[str, Any]):
    SETTINGS_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False))

def _get_setting(key: str, default=None):
    return load_settings().get(key, default if default is not None else DEFAULT_SETTINGS.get(key))

def _set_setting(key: str, value):
    s = load_settings()
    s[key] = value
    save_settings(s)

def get_proxy_check_timeout() -> int:
    return _get_setting("proxy_check_timeout", 2)

def set_proxy_check_timeout(sec: int):
    _set_setting("proxy_check_timeout", max(1, sec))
    log_action("set_timeout", str(sec))

def get_active_subscription() -> Optional[str]:
    return _get_setting("active_subscription")

def set_active_subscription(url: Optional[str]):
    _set_setting("active_subscription", url)
    if url:
        log_action("set_active_sub", get_subscription_name(url))

def get_last_test_time() -> Optional[str]:
    return _get_setting("last_test_time")

def set_last_test_time():
    _set_setting("last_test_time", _now_str())

def is_test_fresh(max_age_minutes: int = 60) -> bool:
    """Проверяет, был ли последний тест менее max_age_minutes назад."""
    lt = get_last_test_time()
    if not lt:
        return False
    try:
        last = datetime.strptime(lt, "%Y-%m-%d %H:%M")
        return (datetime.now() - last).total_seconds() < max_age_minutes * 60
    except Exception:
        return False

def get_last_update_time() -> Optional[str]:
    return _get_setting("last_update_time")

def set_last_update_time():
    _set_setting("last_update_time", _now_str())

def get_auto_monitor() -> bool:
    return _get_setting("auto_monitor", True)

def set_auto_monitor(enabled: bool):
    _set_setting("auto_monitor", enabled)
    log_action("auto_monitor", "on" if enabled else "off")

def get_monitor_interval() -> int:
    return _get_setting("monitor_interval", 300)

def set_monitor_interval(seconds: int):
    _set_setting("monitor_interval", max(60, seconds))
    log_action("monitor_interval", str(seconds))

def get_min_speed_threshold() -> float:
    return _get_setting("min_speed_threshold", 1.0)

def set_min_speed_threshold(mbps: float):
    _set_setting("min_speed_threshold", max(0.1, mbps))
    log_action("min_speed", str(mbps))

def get_direct_speed_threshold() -> float:
    return _get_setting("direct_speed_threshold", 1.0)

def set_direct_speed_threshold(mbps: float):
    _set_setting("direct_speed_threshold", max(0.1, mbps))
    log_action("direct_threshold", str(mbps))

def get_tunnel_speed_threshold() -> float:
    return _get_setting("tunnel_speed_threshold", 1.0)

def set_tunnel_speed_threshold(mbps: float):
    _set_setting("tunnel_speed_threshold", max(0.1, mbps))
    log_action("tunnel_threshold", str(mbps))

def get_channel_speed_probes() -> List[str]:
    probes = _get_setting("channel_speed_probes", None)
    if isinstance(probes, list) and probes:
        return [p for p in probes if isinstance(p, str) and p]
    return list(DEFAULT_CHANNEL_SPEED_PROBES)

def get_external_reach_probes() -> List[Dict[str, str]]:
    probes = _get_setting("external_reach_probes", None)
    if isinstance(probes, list) and probes:
        out = []
        for p in probes:
            if isinstance(p, dict) and p.get("url"):
                out.append(p)
            elif isinstance(p, str) and p:
                out.append({"url": p, "expect_substr": ""})
        if out:
            return out
    return [dict(p) for p in DEFAULT_EXTERNAL_REACH_PROBES]

def get_log_archive_keep() -> int:
    v = _get_setting("log_archive_keep", None)
    try:
        n = int(v) if v is not None else LOG_ARCHIVE_KEEP_DEFAULT
    except (TypeError, ValueError):
        n = LOG_ARCHIVE_KEEP_DEFAULT
    return max(1, n)

def get_active_scope() -> str:
    active = get_active_subscription()
    if active and active in get_subscription_urls():
        return active
    return "ALL"


# --- Подписки ---

def get_subscriptions() -> List[Dict[str, str]]:
    try:
        data = json.loads(SUBS_FILE.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []

def get_subscription_urls() -> List[str]:
    return [s["url"] for s in get_subscriptions() if s.get("url")]

def get_subscription_name(url: str) -> str:
    for s in get_subscriptions():
        if s.get("url") == url:
            return s.get("name", _name_from_url(url))
    return _name_from_url(url)

def add_subscription(url: str, name: str = None):
    url = url.strip()
    if not url:
        return
    if name is None:
        name = _name_from_url(url)
    subs = get_subscriptions()
    if any(s["url"] == url for s in subs):
        return
    subs.append({"url": url, "name": name})
    SUBS_FILE.write_text(json.dumps(subs, indent=2, ensure_ascii=False))
    log_action("add_sub", name)
    if len(subs) == 1:
        set_active_subscription(url)

def remove_subscription(url: str):
    log_action("remove_sub", get_subscription_name(url))
    subs = [s for s in get_subscriptions() if s.get("url") != url]
    SUBS_FILE.write_text(json.dumps(subs, indent=2, ensure_ascii=False))
    for meta in list_server_files():
        if meta.get("SOURCE") == url:
            Path(meta["_file"]).unlink(missing_ok=True)
    if get_active_subscription() == url:
        remaining = get_subscription_urls()
        set_active_subscription(remaining[0] if remaining else None)

def count_servers_in_sub(url: str) -> int:
    return sum(1 for m in list_server_files() if m.get("SOURCE") == url)


# --- Стоп-лист ---

def get_blacklist() -> List[str]:
    if not BLACKLIST_FILE.exists():
        return []
    return [l.strip().lower() for l in BLACKLIST_FILE.read_text().splitlines() if l.strip()]

def add_to_blacklist(word: str) -> bool:
    word = word.strip().lower()
    if not word or word in get_blacklist():
        return False
    with BLACKLIST_FILE.open("a") as f:
        f.write(word + "\n")
    log_action("blacklist_add", word)
    return True

def remove_from_blacklist(word: str) -> bool:
    current = get_blacklist()
    if word not in current:
        return False
    current.remove(word)
    BLACKLIST_FILE.write_text("\n".join(current) + ("\n" if current else ""))
    log_action("blacklist_remove", word)
    return True

def check_blacklisted(name: str) -> bool:
    return any(kw in name.lower() for kw in get_blacklist())


# --- Парсинг VLESS ---

def parse_vless(uri: str) -> Optional[Dict[str, Any]]:
    if not uri.startswith("vless://"):
        return None
    try:
        parsed = urllib.parse.urlparse(uri)
        params = urllib.parse.parse_qs(parsed.query)
        def get(k, d=""):
            v = params.get(k, [d])
            return v[0] if v else d
        return {
            "NAME": urllib.parse.unquote(parsed.fragment) or "",
            "HOST": parsed.hostname or "", "PORT": parsed.port or 443,
            "UUID": parsed.username or "",
            "SECURITY": get("security", "none"), "SNI": get("sni"),
            "FP": get("fp", "chrome"), "PBK": get("pbk"), "SID": get("sid"),
            "FLOW": get("flow"), "TYPE": get("type", "tcp"),
            "SERVICENAME": get("serviceName"), "PATH": get("path"),
            "HOST_HEADER": get("host"), "HEADERTYPE": get("headerType"),
            "ALPN": get("alpn"),
            "PROTOCOL": "vless",
        }
    except Exception as e:
        log(f"parse_vless error: {e}", level="debug")
        return None


def parse_trojan(uri: str) -> Optional[Dict[str, Any]]:
    """Разбирает trojan:// ссылку."""
    if not uri.startswith("trojan://"):
        return None
    try:
        parsed = urllib.parse.urlparse(uri)
        params = urllib.parse.parse_qs(parsed.query)
        def get(k, d=""):
            v = params.get(k, [d])
            return v[0] if v else d
        return {
            "NAME": urllib.parse.unquote(parsed.fragment) or "",
            "HOST": parsed.hostname or "", "PORT": parsed.port or 443,
            "UUID": parsed.username or "",  # для trojan это пароль, храним в том же поле
            "SECURITY": get("security", "tls"), "SNI": get("sni"),
            "FP": get("fp", "chrome"), "PBK": "", "SID": "",
            "FLOW": "", "TYPE": get("type", "tcp"),
            "SERVICENAME": get("serviceName"), "PATH": get("path"),
            "HOST_HEADER": get("host"), "HEADERTYPE": get("headerType"),
            "ALPN": get("alpn"),
            "PROTOCOL": "trojan",
        }
    except Exception as e:
        log(f"parse_trojan error: {e}", level="debug")
        return None


def parse_proxy_uri(uri: str) -> Optional[Dict[str, Any]]:
    """Универсальный парсер — определяет протокол и вызывает нужный парсер."""
    uri = uri.strip()
    if uri.startswith("vless://"):
        return parse_vless(uri)
    elif uri.startswith("trojan://"):
        return parse_trojan(uri)
    return None


MANUAL_SOURCE = "__manual__"

def add_server_manually(uri: str) -> Optional[str]:
    """Добавляет один сервер вручную по ссылке vless:// или trojan://.
    Возвращает имя сервера или None при ошибке."""
    meta = parse_proxy_uri(uri)
    if not meta:
        return None
    if check_blacklisted(meta["NAME"]):
        return None

    if not meta["NAME"]:
        meta["NAME"] = f"Manual {meta['HOST'][:20]}"

    existing = [int(f.stem) for f in SERVERS_DIR.glob("*.meta") if f.stem.isdigit()]
    idx = max(existing) + 1 if existing else 1

    meta.update({"PING_MS": -1, "SPEED_MBPS": -1, "SOURCE": MANUAL_SOURCE, "LAST_TESTED": None})
    (SERVERS_DIR / f"{idx}.meta").write_text(json.dumps(meta, ensure_ascii=False))

    log_action("add_server_manual", meta["NAME"])
    return meta["NAME"]


def import_servers_batch(text: str) -> Tuple[int, int, int]:
    """Импортирует серверы из текста (по одной ссылке на строку).
    Возвращает (добавлено, пропущено_блэклист, ошибок)."""
    added = skipped = errors = 0
    existing = [int(f.stem) for f in SERVERS_DIR.glob("*.meta") if f.stem.isdigit()]
    idx = max(existing) + 1 if existing else 1

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        meta = parse_proxy_uri(line)
        if not meta:
            errors += 1
            continue
        if check_blacklisted(meta["NAME"]):
            skipped += 1
            continue
        if not meta["NAME"]:
            meta["NAME"] = f"Manual {meta['HOST'][:20]}"
        meta.update({"PING_MS": -1, "SPEED_MBPS": -1, "SOURCE": MANUAL_SOURCE, "LAST_TESTED": None})
        (SERVERS_DIR / f"{idx}.meta").write_text(json.dumps(meta, ensure_ascii=False))
        idx += 1
        added += 1

    log_action("import_batch", f"added={added} skipped={skipped} errors={errors}")
    return added, skipped, errors


def import_servers_from_file(filepath: str) -> Tuple[int, int, int]:
    """Импортирует серверы из текстового файла."""
    path = Path(filepath).expanduser()
    if not path.exists():
        log(f"import_file: not found: {filepath}", level="error")
        return 0, 0, 0
    text = path.read_text(encoding="utf-8", errors="ignore")
    return import_servers_batch(text)


def parse_subscription_content(content: str, source_url: str) -> Tuple[int, int]:
    try:
        padded = content + "=" * (-len(content) % 4)
        decoded = base64.b64decode(padded).decode("utf-8", errors="ignore")
        if "vless://" in decoded or "trojan://" in decoded:
            content = decoded
    except Exception:
        pass

    for meta in list_server_files():
        if meta.get("SOURCE") == source_url:
            Path(meta["_file"]).unlink(missing_ok=True)

    existing = [int(f.stem) for f in SERVERS_DIR.glob("*.meta") if f.stem.isdigit()]
    idx = max(existing) + 1 if existing else 1
    added = skipped = 0

    for line in content.splitlines():
        line = line.strip()
        meta = parse_proxy_uri(line)
        if not meta:
            continue
        if check_blacklisted(meta["NAME"]):
            skipped += 1
            continue
        if not meta["NAME"]:
            meta["NAME"] = f"Server {idx}"
        meta.update({"PING_MS": -1, "SPEED_MBPS": -1, "SOURCE": source_url, "LAST_TESTED": None})
        (SERVERS_DIR / f"{idx}.meta").write_text(json.dumps(meta, ensure_ascii=False))
        idx += 1
        added += 1

    log(f"parse: src={source_url[:50]} added={added} skip={skipped}")
    return added, skipped


# --- Серверы ---

def list_server_files() -> List[Dict[str, Any]]:
    result = []
    for f in sorted(SERVERS_DIR.glob("*.meta")):
        try:
            data = json.loads(f.read_text())
            data["_file"] = str(f)
            result.append(data)
        except Exception:
            continue
    return result

def get_servers_by_scope(scope: str) -> List[Dict[str, Any]]:
    all_s = list_server_files()
    return all_s if scope == "ALL" else [s for s in all_s if s.get("SOURCE") == scope]

def get_alive_servers(scope: str = "ALL") -> List[Dict[str, Any]]:
    return [s for s in get_servers_by_scope(scope)
            if s.get("PING_MS", -1) > 0 and s.get("SPEED_MBPS", -1) > 0]

def update_server_meta(meta_file: str, updates: Dict[str, Any]):
    path = Path(meta_file)
    try:
        data = json.loads(path.read_text())
        data.update(updates)
        data.pop("_file", None)
        path.write_text(json.dumps(data, ensure_ascii=False))
    except Exception as e:
        log(f"update_meta error: {e}", level="debug")

def sort_servers_by_speed(servers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key(x):
        speed, ping = x.get("SPEED_MBPS", -1), x.get("PING_MS", -1)
        if speed > 0:
            return (0, -speed)
        elif ping > 0:
            return (1, ping)
        return (2, 0)
    return sorted(servers, key=key)


# --- Генерация конфига xray ---

def generate_config(meta: Dict[str, Any], socks_port: int, output: Path,
                    http_port: Optional[int] = None):
    protocol = meta.get("PROTOCOL", "vless")

    # --- Outbound settings по протоколу ---
    if protocol == "trojan":
        user = {"password": meta["UUID"], "level": 0}
        outbound_settings = {"servers": [{"address": meta["HOST"], "port": int(meta["PORT"]), "users": [user]}]}
    else:  # vless
        user = {"id": meta["UUID"], "encryption": "none", "level": 0}
        if meta.get("FLOW"):
            user["flow"] = meta["FLOW"]
        outbound_settings = {"vnext": [{"address": meta["HOST"], "port": int(meta["PORT"]), "users": [user]}]}

    # --- streamSettings ---
    stream = {"network": meta.get("TYPE") or "tcp"}
    sec = meta.get("SECURITY") or ("tls" if protocol == "trojan" else "none")
    if sec != "none":
        stream["security"] = sec

    if sec == "reality":
        stream["realitySettings"] = {
            "serverName": meta.get("SNI", ""), "fingerprint": meta.get("FP") or "chrome",
            "publicKey": meta.get("PBK", ""), "shortId": meta.get("SID", ""),
        }
    elif sec == "tls":
        tls = {"serverName": meta.get("SNI", ""), "fingerprint": meta.get("FP") or "chrome"}
        if meta.get("ALPN"):
            tls["alpn"] = meta["ALPN"].split(",")
        stream["tlsSettings"] = tls

    nt = meta.get("TYPE") or "tcp"
    if nt == "grpc":
        stream["grpcSettings"] = {"serviceName": meta.get("SERVICENAME", ""), "multiMode": True}
    elif nt == "ws":
        h = {}
        hh = meta.get("HOST_HEADER") or meta.get("SNI", "")
        if hh:
            h["Host"] = hh
        stream["wsSettings"] = {"path": meta.get("PATH", "/"), "headers": h}
    elif nt == "tcp" and meta.get("HEADERTYPE") == "http":
        stream["tcpSettings"] = {"header": {"type": "http"}}

    inbounds = [
        {"listen": "127.0.0.1", "port": socks_port, "protocol": "socks",
         "settings": {"udp": True}, "tag": "socks-in"},
    ]
    if http_port is not None:
        inbounds.append(
            {"listen": "127.0.0.1", "port": http_port, "protocol": "http",
             "settings": {}, "tag": "http-in"}
        )

    config = {
        "log": {"loglevel": "warning"},
        "inbounds": inbounds,
        "outbounds": [
            {"protocol": protocol,
             "settings": outbound_settings,
             "streamSettings": stream, "tag": "proxy"},
            {"protocol": "freedom", "tag": "direct"},
        ],
    }
    output.write_text(json.dumps(config, indent=2, ensure_ascii=False))


# --- Управление xray ---

def _is_pid_alive(pf: Path) -> bool:
    if not pf.exists():
        return False
    try:
        os.kill(int(pf.read_text().strip()), 0)
        return True
    except (ValueError, OSError, ProcessLookupError):
        return False

def _kill_pid(pf: Path):
    if pf.exists():
        try:
            os.kill(int(pf.read_text().strip()), signal.SIGTERM)
            time.sleep(0.3)
        except Exception:
            pass
        pf.unlink(missing_ok=True)

def _start_xray(config: Path, pid_file: Path, log_path: Path) -> bool:
    _kill_pid(pid_file)
    try:
        test = subprocess.run(
            [str(XRAY_BIN), "-test", "-config", str(config)],
            capture_output=True, text=True, timeout=10)
        if test.returncode != 0:
            log_path.write_text(f"Config error:\n{test.stderr}\n{test.stdout}")
            return False
    except subprocess.TimeoutExpired:
        return False

    try:
        lf = open(log_path, "w")
        proc = subprocess.Popen(
            [str(XRAY_BIN), "run", "-config", str(config)],
            stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
        pid_file.write_text(str(proc.pid))
        time.sleep(1.5)
        return _is_pid_alive(pid_file)
    except Exception as e:
        log(f"xray start error: {e}", level="error")
        return False

def xray_is_running() -> bool:
    return _is_pid_alive(PID_FILE)

def xray_stop():
    log_action("xray_stop")
    _kill_pid(PID_FILE)

def xray_start_with(meta: Dict[str, Any]) -> bool:
    name = meta.get("NAME", "?")
    log_action("xray_start", f"{name} @ {meta.get('HOST')}:{meta.get('PORT')}")
    generate_config(meta, SOCKS_PORT, CONFIG_FILE, http_port=HTTP_PORT)
    ok = _start_xray(CONFIG_FILE, PID_FILE, LOG_FILE)
    log(f"xray {'OK' if ok else 'FAIL'}: {name}", level="info" if ok else "error")
    invalidate_ip_cache()
    return ok

def get_current_server() -> Optional[Dict[str, Any]]:
    if not CONFIG_FILE.exists():
        return None
    try:
        c = json.loads(CONFIG_FILE.read_text())
        v = c["outbounds"][0]["settings"]["vnext"][0]
        host, port = v["address"], v["port"]
    except Exception:
        return None
    for m in list_server_files():
        if m.get("HOST") == host and int(m.get("PORT", 0)) == int(port):
            return m
    return None


# --- Кэш IP ---

_ip_cache = {"ip": None, "ts": 0.0}
_ip_lock = threading.Lock()

def check_external_ip(ttl: int = 30) -> Optional[str]:
    if not xray_is_running():
        return None
    with _ip_lock:
        if _ip_cache["ip"] and time.time() - _ip_cache["ts"] < ttl:
            return _ip_cache["ip"]
    ip = None
    for url in IP_CHECK_URLS:
        try:
            r = subprocess.run(
                ["curl", "-sx", f"socks5h://127.0.0.1:{SOCKS_PORT}", "--max-time", "6", url],
                capture_output=True, text=True, timeout=10)
            result = r.stdout.strip()
            if result and len(result) < 50:  # IP не длиннее 50 символов
                ip = result
                break
        except Exception:
            continue
    with _ip_lock:
        _ip_cache.update({"ip": ip, "ts": time.time()})
    return ip

def invalidate_ip_cache():
    with _ip_lock:
        _ip_cache.update({"ip": None, "ts": 0.0})


# --- Тестирование ---

def test_ping(host: str, port: int, timeout: float = 3.0) -> int:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        t = time.time()
        s.connect((host, port))
        ms = int((time.time() - t) * 1000)
        s.close()
        return ms
    except Exception:
        return -1


def _run_temp_xray(meta: Dict[str, Any], callback, timeout: int) -> Any:
    port = _get_free_port()
    cfg = XRAY_DIR / f"_test_{port}.json"
    pid_f = XRAY_DIR / f"_test_{port}.pid"
    log_f = XRAY_DIR / f"_test_{port}.log"
    try:
        generate_config(meta, port, cfg)
        if not _start_xray(cfg, pid_f, log_f):
            return None
        return callback(port)
    except Exception as e:
        log(f"temp_xray error: {e}", level="debug")
        return None
    finally:
        _kill_pid(pid_f)
        pid_f.unlink(missing_ok=True)
        cfg.unlink(missing_ok=True)
        log_f.unlink(missing_ok=True)


def quick_proxy_check(meta: Dict[str, Any], timeout: int = None) -> bool:
    if timeout is None:
        timeout = get_proxy_check_timeout()
    def check(port):
        for url in IP_CHECK_URLS:
            try:
                r = subprocess.run(
                    ["curl", "-sx", f"socks5h://127.0.0.1:{port}", "--max-time", str(timeout), url],
                    capture_output=True, text=True, timeout=timeout + 5)
                if r.stdout.strip():
                    return True
            except Exception:
                continue
        return False
    result = _run_temp_xray(meta, check, timeout)
    return result is True


def test_speed_via_server(meta: Dict[str, Any], timeout: int = 15) -> float:
    """Скорость через временный xray. Использует тот же список хостов A,
    что measure_channel_speed — для сопоставимости с замером канала."""
    def measure(port):
        for url in get_channel_speed_probes():
            try:
                r = subprocess.run(
                    ["curl", "-sx", f"socks5h://127.0.0.1:{port}", "--max-time", str(timeout),
                     "-w", "%{speed_download}", "-o", "/dev/null", url],
                    capture_output=True, text=True, timeout=timeout + 5)
                mbps = round(float(r.stdout.strip() or 0) * 8 / 1_000_000, 2)
                if mbps > 0:
                    log(f"tunnel_speed(temp): {mbps} Мбит/с via {_probe_label(url)}")
                    return mbps
            except Exception:
                continue
        return 0.0
    result = _run_temp_xray(meta, measure, timeout)
    return result if isinstance(result, float) else 0.0


def measure_current_speed(timeout: int = 15) -> Optional[Tuple[float, float]]:
    """Скорость через активный туннель. Список хостов A с фолбэком —
    сопоставимо с замером канала."""
    if not xray_is_running():
        return None
    for url in get_channel_speed_probes():
        try:
            r = subprocess.run(
                ["curl", "-sx", f"socks5h://127.0.0.1:{SOCKS_PORT}", "--max-time", str(timeout),
                 "-w", "%{speed_download}|%{time_total}", "-o", "/dev/null", url],
                capture_output=True, text=True, timeout=timeout + 5)
            parts = r.stdout.strip().split("|")
            if len(parts) != 2:
                continue
            mbps = round(float(parts[0] or 0) * 8 / 1_000_000, 2)
            if mbps > 0:
                log(f"tunnel_speed: {mbps} Мбит/с via {_probe_label(url)}")
                return (mbps, float(parts[1]))
        except Exception:
            continue
    return None


def run_ping_tests(servers, progress_cb=None) -> list:
    log_action("ping_tests", f"n={len(servers)}")
    alive = []
    total = len(servers)
    done_count = [0]
    lock = threading.Lock()

    def test_one(m):
        ping = test_ping(m["HOST"], m["PORT"])
        upd = {"PING_MS": ping, "LAST_TESTED": _now_str()}
        if ping < 0:
            upd["SPEED_MBPS"] = -1
        update_server_meta(m["_file"], upd)
        m["PING_MS"] = ping
        with lock:
            done_count[0] += 1
            log(f"ping {m.get('NAME','')} -> {ping}", level="debug")
            if progress_cb:
                progress_cb(done_count[0], total, m.get("NAME", ""), ping)
        return m if ping > 0 else None

    with ThreadPoolExecutor(max_workers=PING_WORKERS) as ex:
        futures = [ex.submit(test_one, m) for m in servers]
        for f in as_completed(futures):
            try:
                result = f.result()
                if result:
                    alive.append(result)
            except Exception:
                pass

    log(f"ping done: {len(alive)}/{total}")
    return alive


def run_proxy_checks(servers, progress_cb=None) -> list:
    log_action("proxy_checks", f"n={len(servers)}")
    working = []
    for i, m in enumerate(servers, 1):
        ok = quick_proxy_check(m)
        log(f"proxy {m.get('NAME','')} -> {'OK' if ok else 'FAIL'}", level="debug")
        if progress_cb:
            progress_cb(i, len(servers), m.get("NAME", ""), ok)
        if ok:
            working.append(m)
        else:
            update_server_meta(m["_file"], {"SPEED_MBPS": 0, "LAST_TESTED": _now_str()})
            m["SPEED_MBPS"] = 0
    log(f"proxy done: {len(working)}/{len(servers)}")
    return working


def run_speed_tests(servers, progress_cb=None):
    log_action("speed_tests", f"n={len(servers)}")
    for i, m in enumerate(servers, 1):
        speed = test_speed_via_server(m)
        update_server_meta(m["_file"], {"SPEED_MBPS": speed, "LAST_TESTED": _now_str()})
        m["SPEED_MBPS"] = speed
        log(f"speed {m.get('NAME','')} -> {speed}", level="debug")
        if progress_cb:
            progress_cb(i, len(servers), m.get("NAME", ""), speed)
    set_last_test_time()
    log(f"speed done: {len(servers)} tested")


def run_full_test_with_early_connect(servers, threshold: float = None,
                                      progress_cb=None) -> Optional[Dict[str, Any]]:
    """3-этапный тест с ранним подключением.

    На этапе 2 как только найден живой сервер — замеряет скорость.
    Если скорость >= threshold — подключается сразу.
    Остальные серверы продолжают тестироваться, строится топ по скорости.

    Возвращает сервер к которому подключились, или None.
    """
    if threshold is None:
        threshold = get_tunnel_speed_threshold()

    def msg(m):
        log(m)
        if progress_cb:
            progress_cb(m)

    connected_server = None
    _test_cancel.clear()

    # Проверка интернета один раз перед всем тестом
    msg("Проверяю интернет...")
    direct = measure_direct_speed(timeout=5)
    if direct is None:
        msg("⚠ Нет интернета. Проверь подключение.")
        return None
    msg(f"Интернет: {direct} Мбит/с ✓")

    # Этап 1: параллельный пинг
    msg(f"Этап 1/3: пинг ({len(servers)})...")
    alive = run_ping_tests(servers,
        lambda i, t, n, p: msg(f"[{i}/{t}] {n[:30]} {'OK '+str(p) if p>0 else 'нет'}"))
    msg(f"Откликнулись: {len(alive)}/{len(servers)}")

    if not alive:
        return None

    # Этап 2+3: прокси + скорость с ранним подключением
    msg(f"Этап 2-3: прокси + скорость ({len(alive)})...")
    working = []

    for i, m in enumerate(alive, 1):
        if _test_cancel.is_set():
            _test_cancel.clear()
            msg("Тест прерван пользователем.")
            break
        ok = quick_proxy_check(m)
        log(f"proxy {m.get('NAME','')} -> {'OK' if ok else 'FAIL'}", level="debug")

        if not ok:
            msg(f"[{i}/{len(alive)}] {m.get('NAME','')[:30]} ✗")
            update_server_meta(m["_file"], {"SPEED_MBPS": 0, "LAST_TESTED": _now_str()})
            m["SPEED_MBPS"] = 0
            continue

        # Живой — сразу тест скорости
        speed = test_speed_via_server(m)
        update_server_meta(m["_file"], {"SPEED_MBPS": speed, "LAST_TESTED": _now_str()})
        m["SPEED_MBPS"] = speed

        if speed > 0:
            msg(f"[{i}/{len(alive)}] {m.get('NAME','')[:30]} ✓ {speed} Мбит/с")
            working.append(m)
        else:
            msg(f"[{i}/{len(alive)}] {m.get('NAME','')[:30]} ✓ скорость 0")
            continue

        # Первый рабочий — подключаемся сразу
        if connected_server is None and speed > 0:
            msg(f"⚡ Подключаю: {m.get('NAME','')} ({speed} Мбит/с)")
            if xray_is_running():
                xray_stop()
            xray_start_with(m)
            connected_server = m
            invalidate_ip_cache()
            if get_auto_monitor() and not is_monitor_running():
                start_monitor()
            if speed >= threshold:
                msg(f"Скорость выше порога ({threshold}), продолжаю тест остальных...")
            else:
                msg(f"Скорость ниже порога ({threshold}), ищу быстрее...")

    set_last_test_time()
    msg(f"✓ Готово: {len(working)} рабочих из {len(alive)}")

    # После полного теста — переключиться на самый быстрый если он лучше текущего
    if working and connected_server:
        best = max(working, key=lambda s: s.get("SPEED_MBPS", 0))
        if best.get("SPEED_MBPS", 0) > connected_server.get("SPEED_MBPS", 0):
            msg(f"⚡ Найден быстрее: {best.get('NAME','')} ({best.get('SPEED_MBPS',0)} Мбит/с)")
            if xray_is_running():
                xray_stop()
            xray_start_with(best)
            invalidate_ip_cache()
            connected_server = best

    return connected_server


# --- Fetch подписок ---

def fetch_direct(url: str, timeout: int = 10) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None

def fetch_via_proxy(url: str, via: Dict[str, Any], timeout: int = 20) -> Optional[str]:
    def do_fetch(port):
        try:
            r = subprocess.run(
                ["curl", "-fsSL", "-x", f"socks5h://127.0.0.1:{port}",
                 "-A", USER_AGENT, "--max-time", str(timeout), url],
                capture_output=True, text=True, timeout=timeout + 5)
            return r.stdout if r.returncode == 0 and r.stdout else None
        except Exception:
            return None
    return _run_temp_xray(via, do_fetch, timeout)

def fetch_subscription(url: str, exclude_source: Optional[str] = None,
                       progress_cb=None, max_candidates: int = 5,
                       total_timeout: int = 120) -> Optional[str]:
    log_action("fetch", url[:60])
    def msg(m):
        log(m)
        if progress_cb:
            progress_cb(m)

    msg("Пробую напрямую...")
    content = fetch_direct(url)
    if content:
        msg("Загружено напрямую")
        return content

    msg("Прямой доступ не удался, ищу прокси...")
    candidates = sort_servers_by_speed(
        [m for m in list_server_files() if m.get("SOURCE") != exclude_source]
    )[:max_candidates]

    if not candidates:
        msg("Нет серверов для туннеля")
        return None

    start_time = time.time()
    for m in candidates:
        if time.time() - start_time > total_timeout:
            msg("Общий таймаут")
            break
        msg(f"Через: {m.get('NAME', '?')}")
        content = fetch_via_proxy(url, m)
        if content:
            msg(f"OK через {m.get('NAME', '?')}")
            return content

    msg("Все варианты исчерпаны")
    return None

def update_single_subscription(url: str, progress_cb=None) -> Tuple[bool, int, int]:
    content = fetch_subscription(url, exclude_source=url, progress_cb=progress_cb)
    if not content:
        return False, 0, 0
    added, skipped = parse_subscription_content(content, url)
    set_last_update_time()
    return True, added, skipped


# --- Авто/переключение ---

def find_fastest_server(scope: str = None) -> Optional[Dict[str, Any]]:
    if scope is None:
        scope = get_active_scope()
    tested = [s for s in get_servers_by_scope(scope) if s.get("SPEED_MBPS", 0) > 0]
    return max(tested, key=lambda s: s["SPEED_MBPS"]) if tested else None

def find_next_server(scope: str = "ALL") -> Optional[Dict[str, Any]]:
    tested = sorted(
        [s for s in get_servers_by_scope(scope) if s.get("SPEED_MBPS", 0) > 0],
        key=lambda s: -s["SPEED_MBPS"])
    if not tested:
        return None
    current = get_current_server()
    if not current:
        return tested[0]
    ch, cp = current.get("HOST"), current.get("PORT")
    idx = next((i for i, s in enumerate(tested)
                if s.get("HOST") == ch and int(s.get("PORT", 0)) == int(cp)), -1)
    return tested[(idx + 1) % len(tested)] if idx >= 0 else tested[0]


# --- Автомониторинг ---

_monitor_thread: Optional[threading.Thread] = None
_monitor_stop = threading.Event()
_test_cancel = threading.Event()
_monitor_log: List[str] = []
_monitor_lock = threading.Lock()

def get_monitor_log() -> List[str]:
    with _monitor_lock:
        return list(_monitor_log)

def cancel_full_test():
    _test_cancel.set()

def _monitor_msg(msg: str):
    log(f"MON: {msg}")
    with _monitor_lock:
        _monitor_log.append(f"[{_now_str()}] {msg}")
        if len(_monitor_log) > 100:
            _monitor_log.pop(0)

def _monitor_try_switch_in_scope(scope: str, threshold: float) -> bool:
    """Перебирает серверы в scope. Тестирует через временный xray.
    Переключает основное соединение только на подтверждённый рабочий сервер."""
    servers = sort_servers_by_speed(get_alive_servers(scope))
    current = get_current_server()

    for srv in servers:
        if current and srv.get("HOST") == current.get("HOST") and \
           int(srv.get("PORT", 0)) == int(current.get("PORT", 0)):
            continue

        _monitor_msg(f"Пробую: {srv.get('NAME', '?')} ({srv.get('SPEED_MBPS', 0)} Мбит/с)")

        # Тестируем через временный xray
        ok = quick_proxy_check(srv)
        if not ok:
            _monitor_msg(f"Не работает")
            continue

        speed = test_speed_via_server(srv)
        update_server_meta(srv["_file"], {"SPEED_MBPS": speed, "LAST_TESTED": _now_str()})

        if speed <= 0:
            _monitor_msg(f"Скорость 0")
            continue

        _monitor_msg(f"Скорость: {speed} Мбит/с")

        if speed >= threshold:
            # Подтверждён — переключаем основное
            if xray_is_running():
                xray_stop()
            xray_start_with(srv)
            invalidate_ip_cache()
            _monitor_msg(f"✓ Подключено: {srv.get('NAME', '?')} ({speed} Мбит/с)")
            return True
        else:
            _monitor_msg(f"Ниже порога ({threshold})")

    return False


def _probe_label(url: str) -> str:
    """Короткая метка хоста для логов: detectportal/example/yastatic/..."""
    try:
        host = urllib.parse.urlparse(url).hostname or url
        parts = host.split(".")
        return parts[0] if parts else host
    except Exception:
        return url


def measure_channel_speed(timeout: int = 5) -> Optional[float]:
    """Сигнал A — честная скорость канала.
    Меряет по близким незаблокированным CDN (см. get_channel_speed_probes).
    Возвращает Мбит/с; None если нет связи вообще."""
    ping_ok = False
    for host, port in [("8.8.8.8", 53), ("1.1.1.1", 53), ("77.88.8.8", 53)]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((host, port))
            s.close()
            ping_ok = True
            break
        except Exception:
            continue

    if not ping_ok:
        return None

    url_timeout = min(timeout, 2)
    for url in get_channel_speed_probes():
        try:
            r = subprocess.run(
                ["curl", "--max-time", str(url_timeout),
                 "-w", "%{speed_download}", "-o", "/dev/null", url],
                capture_output=True, text=True, timeout=url_timeout + 3)
            bps = float(r.stdout.strip() or 0)
            mbps = round(bps * 8 / 1_000_000, 2)
            if mbps > 0.05:
                log(f"channel_speed: {mbps} Мбит/с via {_probe_label(url)} ({url})")
                return mbps
        except Exception:
            continue

    # TCP есть, но ни один пробник A не отдал данные — отдаём порог как fallback.
    log("channel_speed: ни один пробник A не отдал данные — fallback на порог")
    return get_direct_speed_threshold()


def check_external_reach(timeout: int = 3) -> Tuple[bool, Optional[float], List[Tuple[str, str]]]:
    """Сигнал B — доступность "обычного" внешнего интернета.
    Прогоняет ВСЕ пробники B (для калибровки), валидирует подстроку в теле.
    Возвращает (reachable, latency_ms первого OK, [(label, "OK"|"FAIL(reason)"), ...]).
    """
    statuses: List[Tuple[str, str]] = []
    overall_reachable = False
    first_latency_ms: Optional[float] = None

    for probe in get_external_reach_probes():
        url = probe.get("url", "") if isinstance(probe, dict) else str(probe)
        expect = probe.get("expect_substr", "") if isinstance(probe, dict) else ""
        if not url:
            continue
        label = _probe_label(url)

        try:
            r = subprocess.run(
                ["curl", "--max-time", str(timeout),
                 "-sS", "-L", "-w", "\n__TIME__%{time_total}", url],
                capture_output=True, text=True, timeout=timeout + 3)
            if r.returncode != 0:
                reason = "timeout" if "timed out" in (r.stderr or "").lower() else "net"
                statuses.append((label, f"FAIL({reason})"))
                log(f"reach[{label}]: FAIL({reason}) rc={r.returncode} url={url}")
                continue

            out = r.stdout
            marker = "\n__TIME__"
            ttotal_str = ""
            body = out
            if marker in out:
                body, _, ttotal_str = out.rpartition(marker)

            if expect and expect not in body:
                statuses.append((label, "FAIL(body)"))
                log(f"reach[{label}]: FAIL(body) ожидал '{expect}' url={url}")
                continue

            lat_ms: Optional[float] = None
            try:
                lat_ms = round(float(ttotal_str) * 1000, 1)
            except Exception:
                pass

            statuses.append((label, "OK"))
            log(f"reach[{label}]: OK lat={lat_ms}мс url={url}")
            if not overall_reachable:
                overall_reachable = True
                first_latency_ms = lat_ms
        except subprocess.TimeoutExpired:
            statuses.append((label, "FAIL(timeout)"))
            log(f"reach[{label}]: FAIL(timeout) url={url}")
        except Exception as e:
            statuses.append((label, "FAIL(err)"))
            log(f"reach[{label}]: FAIL(err) {e} url={url}")

    return overall_reachable, first_latency_ms, statuses


def measure_direct_speed(timeout: int = 5) -> Optional[float]:
    """Обратная совместимость: делегирует на measure_channel_speed (честный замер A).
    Старые вызовы из CLI/Web/тестов продолжают работать без правок."""
    return measure_channel_speed(timeout)


def _monitor_loop():
    """Адаптивный мониторинг v2.5.

    Логика:
    1. Замерить прямую скорость (без туннеля)
    2. Если прямая < direct_threshold → интернет слабый:
       - замерить туннель, считать ок если туннель ≥ 50% от прямой
    3. Если прямая ≥ direct_threshold → замерить туннель:
       - если туннель < tunnel_threshold → переключить сервер
       - если туннель ≥ tunnel_threshold → всё ок
    """
    _monitor_msg("Мониторинг запущен (адаптивный)")

    while not _monitor_stop.is_set():
        interval = get_monitor_interval()
        direct_thr = get_direct_speed_threshold()
        tunnel_thr = get_tunnel_speed_threshold()

        if not get_auto_monitor():
            _monitor_stop.wait(30)
            continue

        if not xray_is_running():
            _monitor_stop.wait(interval)
            continue

        if _monitor_stop.wait(interval):
            break

        if not get_auto_monitor() or not xray_is_running():
            continue

        # --- Шаг 1: прямая скорость (сигнал A — честный замер канала) ---
        _monitor_msg("Замер прямой скорости...")
        direct_speed = measure_channel_speed(timeout=10)

        if direct_speed is None:
            _monitor_msg("Прямая: нет ответа — интернет отсутствует, пропускаю")
            set_last_test_time()
            continue

        _monitor_msg(f"Прямая: {direct_speed} Мбит/с (порог: {direct_thr})")

        # --- Шаг 1b: достижимость внешнего мира (сигнал B, только лог) ---
        reach_ok, reach_lat, reach_statuses = check_external_reach(timeout=3)
        status_str = " ".join(f"{lbl}={st}" for lbl, st in reach_statuses) or "нет пробников"
        _monitor_msg(f"Внешний мир: {'OK' if reach_ok else 'недоступен'} [{status_str}]")

        if direct_speed >= direct_thr and not reach_ok:
            _monitor_msg(f"⚠ whitelist? канал={direct_speed} Мбит/с | B {status_str}")

        # --- Шаг 2: замер туннеля ---
        _monitor_msg("Замер через туннель...")
        tunnel_result = measure_current_speed(timeout=10)
        tunnel_speed = tunnel_result[0] if tunnel_result else 0

        cur = get_current_server()
        if cur and tunnel_speed > 0:
            update_server_meta(cur["_file"], {"SPEED_MBPS": tunnel_speed, "LAST_TESTED": _now_str()})
        set_last_test_time()

        # --- Шаг 3: решение ---
        if direct_speed < direct_thr:
            # Интернет слабый — используем адаптивный порог 50% от прямой
            half_direct = round(direct_speed / 2, 2)
            _monitor_msg(f"Интернет слабый. Туннель: {tunnel_speed} (порог: {half_direct} = 50% от {direct_speed})")
            if tunnel_speed >= half_direct:
                continue  # Ок для слабого интернета
            # Туннель совсем плох даже для слабого интернета — переключаем
        else:
            # Интернет нормальный — используем tunnel_threshold
            _monitor_msg(f"Туннель: {tunnel_speed} Мбит/с (порог: {tunnel_thr})")
            if tunnel_speed >= tunnel_thr:
                continue  # Всё ок

        # --- Переключение ---
        _monitor_msg(f"Туннель слишком медленный! Ищу замену...")

        cur = get_current_server()
        current_source = cur.get("SOURCE", "") if cur else ""
        all_sub_urls = get_subscription_urls()

        ordered_subs = []
        if current_source and current_source in all_sub_urls:
            ordered_subs.append(current_source)
        for u in all_sub_urls:
            if u not in ordered_subs:
                ordered_subs.append(u)

        found = False
        switch_attempts = 0
        max_attempts = 5  # Максимум 5 попыток за цикл

        for sub_url in ordered_subs:
            if switch_attempts >= max_attempts:
                _monitor_msg(f"Лимит попыток ({max_attempts}), жду следующий цикл")
                break
            _monitor_msg(f"Подписка: {get_subscription_name(sub_url)}")

            servers = sort_servers_by_speed(get_alive_servers(sub_url))
            current = get_current_server()

            for srv in servers:
                if switch_attempts >= max_attempts:
                    break
                if current and srv.get("HOST") == current.get("HOST") and \
                   int(srv.get("PORT", 0)) == int(current.get("PORT", 0)):
                    continue

                _monitor_msg(f"Пробую: {srv.get('NAME', '?')}")
                switch_attempts += 1

                # Тестируем через ВРЕМЕННЫЙ xray — не трогаем основное соединение
                ok = quick_proxy_check(srv)
                if not ok:
                    _monitor_msg(f"Не работает, следующий...")
                    continue

                # Сервер живой — замеряем скорость через временный xray
                speed = test_speed_via_server(srv)
                update_server_meta(srv["_file"], {"SPEED_MBPS": speed, "LAST_TESTED": _now_str()})

                if speed <= 0:
                    _monitor_msg(f"Скорость 0, следующий...")
                    continue

                # Проверяем порог
                new_direct = measure_direct_speed(timeout=10)
                if new_direct is None:
                    _monitor_msg("Интернет пропал, останавливаюсь")
                    found = True
                    break

                if new_direct < direct_thr:
                    effective_thr = round(new_direct / 2, 2)
                else:
                    effective_thr = tunnel_thr

                _monitor_msg(f"Скорость: {speed} vs порог {effective_thr}")

                if speed >= effective_thr:
                    # Подтверждён — теперь переключаем основное соединение
                    if xray_is_running():
                        xray_stop()
                    xray_start_with(srv)
                    invalidate_ip_cache()
                    _monitor_msg(f"✓ Подключено: {srv.get('NAME', '?')} ({speed} Мбит/с)")
                    found = True
                    break
                else:
                    _monitor_msg(f"Ниже порога, следующий...")

            if found:
                break

        if not found:
            _monitor_msg("Все серверы медленные. Обновляю подписки...")
            for sub_url in all_sub_urls:
                _monitor_msg(f"Fetch: {get_subscription_name(sub_url)}...")
                update_single_subscription(sub_url, progress_cb=_monitor_msg)

            servers = list_server_files()
            if servers:
                _monitor_msg(f"Тест {len(servers)} серверов...")
                alive = run_ping_tests(servers)
                working = run_proxy_checks(alive)
                if working:
                    run_speed_tests(working)
                for sub_url in ordered_subs:
                    for srv in sort_servers_by_speed(get_alive_servers(sub_url)):
                        if xray_is_running():
                            xray_stop()
                        if xray_start_with(srv):
                            time.sleep(2)
                            t = measure_current_speed(timeout=10)
                            if t and t[0] > 0:
                                _monitor_msg(f"✓ Подключено: {srv.get('NAME','?')} ({t[0]} Мбит/с)")
                                found = True
                                break
                    if found:
                        break

            if not found:
                _monitor_msg("⚠ Не удалось найти рабочий сервер. Повторю через интервал.")

    _monitor_msg("Мониторинг остановлен")


def start_monitor():
    """Запускает мониторинг как фоновый поток."""
    global _monitor_thread
    if _monitor_thread and _monitor_thread.is_alive():
        return
    _monitor_stop.clear()
    with _monitor_lock:
        _monitor_log.clear()
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True, name="xproxy-monitor")
    _monitor_thread.start()
    log_action("monitor_start")

def stop_monitor():
    global _monitor_thread
    _monitor_stop.set()
    if _monitor_thread:
        _monitor_thread.join(timeout=5)
        _monitor_thread = None
    log_action("monitor_stop")

def is_monitor_running() -> bool:
    return _monitor_thread is not None and _monitor_thread.is_alive()


# --- Фоновая проверка (отдельный процесс, раз в час) ---

def run_background_check():
    import signal as sig
    sig.signal(sig.SIGTERM, lambda *_: (BG_PID_FILE.unlink(missing_ok=True), sys.exit(0)))
    BG_PID_FILE.write_text(str(os.getpid()))
    log("BG check started")
    while True:
        try:
            servers = list_server_files()
            if servers:
                log(f"BG: {len(servers)} servers")
                alive = run_ping_tests(servers)
                working = run_proxy_checks(alive)
                if working:
                    run_speed_tests(working)
                log(f"BG done: {len(working)}/{len(servers)}")
        except Exception as e:
            log(f"BG error: {e}", level="error")
        time.sleep(BG_CHECK_INTERVAL)

def start_background_check() -> bool:
    if is_background_running():
        return True
    proc = subprocess.Popen(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, '{XRAY_DIR}'); "
         "import xproxy_lib; xproxy_lib.init(); xproxy_lib.run_background_check()"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    BG_PID_FILE.write_text(str(proc.pid))
    log_action("bg_start", f"pid={proc.pid}")
    return True

def stop_background_check():
    _kill_pid(BG_PID_FILE)
    log_action("bg_stop")

def is_background_running() -> bool:
    return _is_pid_alive(BG_PID_FILE)


# --- Миграция ---

def needs_migration() -> bool:
    for m in list_server_files():
        if not m.get("SOURCE"):
            return True
    return False

def migrate(progress_cb=None):
    def msg(m):
        log(m)
        if progress_cb:
            progress_cb(m)
    msg("Миграция...")
    for f in SERVERS_DIR.glob("*.meta"):
        f.unlink()
    for url in get_subscription_urls():
        msg(f"Обновляю: {url[:50]}...")
        update_single_subscription(url, progress_cb=msg)
    msg("Готово.")


# --- Экспорт ---

def _rotate_log_archives(output_dir: Path, keep: int) -> None:
    """Оставляет N последних архивов xrayproxy_logs_*.zip в output_dir.
    Сортировка по имени: timestamp YYYYMMDD_HHMMSS лексикографически совпадает
    с хронологическим порядком и не сбивается при copy/touch (в отличие от mtime)."""
    try:
        archives = sorted(output_dir.glob("xrayproxy_logs_*.zip"), reverse=True)
    except Exception:
        return
    for old in archives[keep:]:
        try:
            old.unlink()
            log(f"rotate: удалён старый архив {old.name}")
        except Exception as e:
            log(f"rotate: не удалось удалить {old.name}: {e}", level="warning")


def export_logs(output_dir: Optional[Path] = None) -> Optional[str]:
    import zipfile
    if output_dir is None:
        for c in [HOME / "storage" / "downloads", HOME / "storage" / "shared" / "Download"]:
            if c.exists():
                output_dir = c / "XrayProxy"
                break
        if output_dir is None:
            output_dir = XRAY_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zp = output_dir / f"xrayproxy_logs_{ts}.zip"

    files = {
        "xrayproxy.log": APP_LOG_FILE, "xrayproxy.log.1": Path(str(APP_LOG_FILE) + ".1"),
        "xray.log": LOG_FILE, "config.json": CONFIG_FILE,
        "subscriptions.json": SUBS_FILE, "blacklist.txt": BLACKLIST_FILE,
        "settings.json": SETTINGS_FILE,
    }
    try:
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            info = [f"{APP_NAME} v.{VERSION}", f"Export: {datetime.now().isoformat()}",
                    f"Servers: {len(list_server_files())}", f"Alive: {len(get_alive_servers())}",
                    f"Running: {xray_is_running()}", f"Monitor: {is_monitor_running()}",
                    f"Last test: {get_last_test_time()}", f"Last update: {get_last_update_time()}",
                    f"Auto-monitor: {get_auto_monitor()}", f"Interval: {get_monitor_interval()}s",
                    f"Threshold: {get_min_speed_threshold()} Mbps"]
            cur = get_current_server()
            if cur:
                info.append(f"Current: {cur.get('NAME','?')} @ {cur.get('HOST')}")
            z.writestr("system_info.txt", "\n".join(info))
            for n, p in files.items():
                if p.exists():
                    z.write(p, n)
            summary = [{"name": s.get("NAME"), "host": s.get("HOST"), "port": s.get("PORT"),
                        "ping_ms": s.get("PING_MS"), "speed_mbps": s.get("SPEED_MBPS"),
                        "last_tested": s.get("LAST_TESTED"), "source": s.get("SOURCE", "")[:60]}
                       for s in sort_servers_by_speed(get_alive_servers())]
            z.writestr("alive_servers.json", json.dumps(summary, indent=2, ensure_ascii=False))
            # Лог мониторинга
            mon_log = get_monitor_log()
            if mon_log:
                z.writestr("monitor.log", "\n".join(mon_log))

        log_action("export", str(zp))
        _rotate_log_archives(output_dir, get_log_archive_keep())
        return str(zp)
    except Exception as e:
        log(f"export error: {e}", level="error")
        return None
