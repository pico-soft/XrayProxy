# XrayProxy

**SOCKS5/HTTP прокси без VPN-интерфейса для Android**

[![Version](https://img.shields.io/badge/version-1.0--beta-blue)]()
![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)
[![Platform](https://img.shields.io/badge/platform-Android%20(Termux)-brightgreen)]()

XrayProxy запускает [xray-core](https://github.com/XTLS/Xray-core) как локальный SOCKS5/HTTP-прокси в Termux. В отличие от VPN-клиентов, он **не создаёт VPN-интерфейс** (tun0) и **невидим** для приложений, которые проверяют наличие VPN через `ConnectivityManager.TRANSPORT_VPN`.

## Для чего

- Обход блокировок без VPN-интерфейса на устройстве
- Приложения (банки, маркетплейсы, доставка) не видят VPN
- Управление подписками VLESS+Reality из удобного интерфейса
- Автоматическое тестирование и выбор самого быстрого сервера
- CLI и Web-интерфейс (Flask) на выбор

## Быстрая установка

### 1. Установи Termux

Скачай из [F-Droid](https://f-droid.org/packages/com.termux/) (не из Google Play).

### 2. Установи XrayProxy

Открой Termux и выполни:

```bash
pkg update -y && pkg install -y curl unzip
termux-setup-storage
curl -fsSL https://github.com/pico-soft/XrayProxy/releases/latest/download/xrayproxy.zip -o ~/xrayproxy.zip
cd ~ && unzip -o xrayproxy.zip
bash xrayproxy/install.sh
```

### 3. Запусти

```bash
# Терминальный интерфейс
bash ~/xproxy.sh

# Веб-интерфейс (открой http://localhost:8080 в Firefox)
bash ~/xproxy.sh web

# Остановить прокси
bash ~/xproxy.sh stop
```

### 4. Добавь подписку

В меню нажми `9`, введи URL подписки — тот же, что используешь в v2rayNG, Happ или других клиентах.

### 5. Настрой приложения

| Приложение | Как настроить |
|-----------|--------------|
| **Telegram** | Настройки → Данные → Прокси → SOCKS5 → `127.0.0.1:10828` |
| **Firefox**  **Fennec** Зайди в about:config в Firefox/Fennec и выставь такие настройки: `network.proxy.http`: `127.0.0.1` `network.proxy.http_port`: `10829` `network.proxy.socks`: `127.0.0.1` `network.proxy.socks_port`: `10828` `network.proxy.type`: `1` `network.proxy.socks_remote_dns`: `true` | Установи FoxyProxy → SOCKS5 → `127.0.0.1:10828` + Proxy DNS |
| **WhatsApp, Instagram, ChatGPT** | Через Firefox: `web.whatsapp.com`, `instagram.com`, `chatgpt.com` Рекомендую сделать из них PWA-приложения

Российские приложения (банки, СДЭК, Яндекс) работают напрямую — они не видят прокси.

## Возможности

- **Автоподключение** — находит и подключает самый быстрый сервер
- **3-этапное тестирование** — TCP-пинг → проверка прокси → замер скорости
- **Фоновая проверка** — автоматически раз в час
- **Подписки** — импорт по URL, автоименование, раздельное управление
- **Стоп-лист** — фильтрация серверов по ключевым словам (например: РФ, Беларусь, Крым)
- **Fetch через прокси** — если URL подписки заблокирован, скачает через рабочий сервер
- **Web-интерфейс** — управление из браузера на `localhost:8080`
- **Экспорт логов** — ZIP с диагностикой для техподдержки

## Структура проекта

```
~/xproxy/
├── xproxy.sh           # Лаунчер (CLI/Web/Stop)
├── xproxy_lib.py       # Ядро логики
├── xproxy_cli.py       # CLI-интерфейс
├── xproxy_web.py       # Flask веб-интерфейс
├── templates/           # HTML-шаблоны
├── blacklist.txt       # Стоп-лист
├── subscriptions.json  # Подписки
├── settings.json       # Настройки
├── servers/            # Метаданные серверов
├── xray                # xray-core (скачивается автоматически)
└── xrayproxy.log       # Логи приложения
```

## FAQ

**Q: Приложения видят VPN?**
Нет. XrayProxy работает как обычный TCP-сервер на localhost. Никакого tun-интерфейса, никакого `TRANSPORT_VPN`. Для Android это выглядит как обычное приложение.

**Q: Какие протоколы поддерживаются?**
VLESS (TCP, gRPC, WebSocket) с TLS и Reality. Это покрывает 95% современных подписок.

**Q: Нужен ли root?**
Нет. Всё работает в Termux без root.

**Q: Почему не все серверы работают?**
XrayProxy проверяет серверы в 3 этапа. Те, что не прошли проверку прокси (этап 2), автоматически исключаются.

**Q: Как обновить?**
Скачай новый ZIP и запусти `install.sh` — он создаст бэкап старых файлов и установит обновление.

**Q: Как отправить логи для помощи?**
В CLI: пункт `x`. В Web: Настройки → Экспорт логов. ZIP-файл появится в Downloads.

**Q: Termux убивает процесс в фоне?**
Настройки телефона → Приложения → Termux → Батарея → Без ограничений. В Termux: потяни уведомление → Acquire wakelock.

## Обновление

```bash
curl -fsSL https://github.com/pico-soft/XrayProxy/releases/latest/download/xrayproxy.zip -o ~/xrayproxy.zip
cd ~ && unzip -o xrayproxy.zip
bash xrayproxy/install.sh
```

## Лицензия

GPL

## Автор

[pico-soft](https://github.com/pico-soft)
