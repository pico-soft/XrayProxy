# XrayProxy

**SOCKS5/HTTP прокси без VPN-интерфейса для Android**

[![Version](https://img.shields.io/badge/version-2.4--beta-blue)]()
![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)
[![Platform](https://img.shields.io/badge/platform-Android%20(Termux)-brightgreen)]()

XrayProxy запускает [xray-core](https://github.com/XTLS/Xray-core) как локальный SOCKS5/HTTP-прокси в Termux. В отличие от VPN-клиентов, он **не создаёт VPN-интерфейс** (`tun0`) и **невидим** для приложений, которые проверяют наличие VPN через `ConnectivityManager.TRANSPORT_VPN`.

## Для чего

- Обход блокировок без VPN-интерфейса на устройстве
- Приложения (банки, маркетплейсы, доставка) не видят VPN
- Управление подписками VLESS+Reality из удобного интерфейса
- Автоматическое тестирование и выбор самого быстрого сервера
- Автомониторинг — при падении скорости автоматически переключает сервер
- CLI и Web-интерфейс (Flask) на выбор

## Установка

### 1. Установи Termux

Скачай из [F-Droid](https://f-droid.org/packages/com.termux/) (не из Google Play).

### 2. Выбери способ установки

#### Быстрая установка (latest)

Устанавливает **последнюю доступную версию** из GitHub Releases.

```bash
apt update && apt full-upgrade -y
pkg install -y curl unzip
termux-setup-storage
```

> Появится диалог — нажми «Разрешить».

```bash
cd ~
rm -rf ~/xrayproxy ~/xrayproxy.zip
curl -fsSL https://github.com/pico-soft/XrayProxy/releases/latest/download/xrayproxy.zip -o xrayproxy.zip
unzip -o xrayproxy.zip
bash xrayproxy/install.sh
```

#### Установка конкретной версии

Если нужна **фиксированная версия**, замени `v2.4` на нужный тег релиза.

```bash
cd ~
rm -rf ~/xrayproxy ~/xrayproxy.zip
curl -fsSL https://github.com/pico-soft/XrayProxy/releases/download/v2.4/xrayproxy.zip -o xrayproxy.zip
unzip -o xrayproxy.zip
bash xrayproxy/install.sh
```

#### Ручная установка

Если ZIP уже скачан вручную:

```bash
cd ~/storage/downloads
unzip -o xrayproxy.zip -d ~
bash ~/xrayproxy/install.sh
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
| **Firefox / Fennec** | Зайди в `about:config` и выставь: `network.proxy.http = 127.0.0.1`, `network.proxy.http_port = 10829`, `network.proxy.socks = 127.0.0.1`, `network.proxy.socks_port = 10828`, `network.proxy.type = 1`, `network.proxy.socks_remote_dns = true` |
| **WhatsApp, Instagram, ChatGPT** | Через Firefox: `web.whatsapp.com`, `instagram.com`, `chatgpt.com`. Рекомендую сделать из них PWA-приложения |

Российские приложения (банки, СДЭК, Яндекс) работают напрямую — они не видят прокси.

## Автозапуск при загрузке телефона

Чтобы XrayProxy запускался автоматически при включении телефона:

### 1. Установи Termux:Boot

Скачай из [F-Droid](https://f-droid.org/packages/com.termux.boot/).

**Открой приложение Termux:Boot один раз** — просто запусти и закрой. Это активирует разрешение на автозапуск.

### 2. Настрой автозапуск

В Termux выполни:

```bash
bash ~/xproxy/setup-boot.sh
```

Проверь результат:

```bash
cat ~/.termux/boot/xrayproxy
```

### 3. Настрой Android

Чтобы Android не убивал Termux в фоне:

- **Настройки → Приложения → Termux → Батарея → Без ограничений**
- **Настройки → Приложения → Termux:Boot → Батарея → Без ограничений**
- На Samsung дополнительно: Настройки → Обслуживание устройства → Батарея → убрать Termux из ограничений

### 4. Перезагрузи телефон

Подожди 20–30 секунд после загрузки, затем открой Firefox → `http://localhost:8080`.

Проверить, что автозапуск сработал:

```bash
cat ~/xproxy/boot.log
```

## Возможности

- **Автоподключение** — находит и подключает самый быстрый сервер
- **Автомониторинг** — проверяет скорость каждые 5 минут, при падении ниже порога (1 Мбит/с) автоматически переключает на следующий сервер, каскадно перебирая все подписки
- **Автопереключение при ручной проверке** — если при проверке скорости результат ниже порога, автоматически переключает сервер
- **3-этапное тестирование** — TCP-пинг → проверка прокси (2 сек) → замер скорости
- **Параллельный пинг** — 20 потоков, 100 серверов за 15 секунд
- **Фоновая проверка** — автоматически раз в час
- **Подписки** — импорт по URL, автоименование, раздельное управление
- **Стоп-лист** — фильтрация серверов по ключевым словам (например: РФ, Беларусь, Крым)
- **Fetch через прокси** — если URL подписки заблокирован, скачает через рабочий сервер
- **Web-интерфейс** — управление из браузера на `localhost:8080` с автообновлением статуса
- **Автозапуск** — при перезагрузке телефона через Termux:Boot с проверкой соединения
- **Экспорт логов** — ZIP с диагностикой для техподдержки

## Структура проекта

```text
~/xproxy/
├── xproxy.sh           # Лаунчер (CLI/Web/Stop)
├── xproxy_lib.py       # Ядро логики
├── xproxy_cli.py       # CLI-интерфейс
├── xproxy_web.py       # Flask веб-интерфейс (порт 8080)
├── setup-boot.sh       # Настройка автозапуска
├── templates/          # HTML-шаблоны
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

**Q: Как работает автомониторинг?**
Каждые 5 минут (настраивается) скрипт проверяет скорость текущего соединения. Если она ниже порога (1 Мбит/с по умолчанию) — автоматически переключает на следующий по скорости сервер. Если все серверы текущей подписки медленные — переходит к следующей подписке. Если все исчерпаны — обновляет подписки, тестирует заново и подключается.

**Q: Как обновить?**
См. раздел «Обновление» ниже.

**Q: Как отправить логи для помощи?**
В CLI: пункт `x`. В Web: Настройки → Экспорт логов. ZIP-файл появится в Downloads.

**Q: Termux убивает процесс в фоне?**
Настройки телефона → Приложения → Termux → Батарея → Без ограничений. В Termux: потяни уведомление → Acquire wakelock.

**Q: При установке `termux-setup-storage` не работает?**
Сначала выполни `apt update && apt full-upgrade -y`, потом повтори `termux-setup-storage`.

## Обновление

### До последней версии

```bash
apt update && apt full-upgrade -y
cd ~
rm -rf ~/xrayproxy ~/xrayproxy.zip
curl -fsSL https://github.com/pico-soft/XrayProxy/releases/latest/download/xrayproxy.zip -o xrayproxy.zip
unzip -o xrayproxy.zip
bash xrayproxy/install.sh
```

Подписки, серверы, настройки и стоп-лист сохраняются — они хранятся в `~/xproxy/`, а `~/xrayproxy/` это временная папка установщика.

### До конкретной версии

```bash
cd ~
rm -rf ~/xrayproxy ~/xrayproxy.zip
curl -fsSL https://github.com/pico-soft/XrayProxy/releases/download/v2.4/xrayproxy.zip -o xrayproxy.zip
unzip -o xrayproxy.zip
bash xrayproxy/install.sh
```

## Лицензия

GPL v3

## Автор

[pico-soft](https://github.com/pico-soft)
