# XrayProxy

**SOCKS5/HTTP прокси без VPN-интерфейса для Android**

[![Version](https://img.shields.io/badge/version-2.12--beta-blue)]()
![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)
[![Platform](https://img.shields.io/badge/platform-Android%20(Termux)-brightgreen)]()

XrayProxy запускает [xray-core](https://github.com/XTLS/Xray-core) как локальный SOCKS5/HTTP-прокси в Termux. В отличие от VPN-клиентов, он **не создаёт VPN-интерфейс** (`tun0`) и **невидим** для приложений, которые проверяют наличие VPN через `ConnectivityManager.TRANSPORT_VPN`.

## Для чего

- Обход блокировок без VPN-интерфейса на устройстве
- Приложения (банки, маркетплейсы, доставка) не видят VPN
- Управление подписками VLESS и Trojan из удобного интерфейса
- Автоматическое тестирование и выбор самого быстрого сервера
- Адаптивный мониторинг — при падении скорости автоматически переключает сервер
- CLI и Web-интерфейс (Flask) на выбор
- Автозапуск при загрузке телефона

## Установка

### 1. Установи Termux

Скачай из [F-Droid](https://f-droid.org/packages/com.termux/) (не из Google Play — там устаревшая версия).

### 1.1. Рекомендуемый браузер

Для полноценной работы с XrayProxy лучше использовать **Fennec из F-Droid** или **Firefox Nightly**.

- **Fennec** — рекомендуемый вариант: стабильнее работает с настройками прокси через `about:config`.
- **Firefox Nightly** тоже подходит, но на некоторых версиях Android может работать нестабильно.
- Панель управления `http://localhost:8080` можно открывать как в браузере, настроенном на работу через прокси, так и в любом другом браузере на устройстве.


### 2. Установи XrayProxy

#### Быстрая установка (latest)

Устанавливает **последнюю доступную версию** из GitHub Releases.

#### Если GitHub доступен (curl работает), в Termux::

```bash
apt update && apt full-upgrade -y && pkg install -y curl unzip && termux-setup-storage && sleep 3 && cd ~ && rm -rf ~/xrayproxy ~/xrayproxy.zip && curl -fL --progress-bar --max-time 60 -o xrayproxy.zip https://github.com/pico-soft/XrayProxy/releases/latest/download/xrayproxy.zip && unzip -o xrayproxy.zip && bash xrayproxy/install.sh
```

#### Если GitHub заблокирован (curl зависает):

Скачай последнюю версию xrayproxy.zip через браузер или получи файл от того, кто может его скачать  через Telegram

```bash
apt update && apt full-upgrade -y && pkg install -y unzip && termux-setup-storage && sleep 3 && f=$(find ~/storage/downloads ~/storage/shared/Download -maxdepth 3 -name "xrayproxy*.zip" -type f -exec stat -c '%Y %n' {} \; 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-) && if [ -n "$f" ]; then echo "Найден: $f" && cd ~ && rm -rf ~/xrayproxy && unzip -o "$f" && bash xrayproxy/install.sh; else echo "xrayproxy.zip не найден в Downloads"; fi
```

Установщик автоматически поставит Python, Flask, скачает xray-core, настроит автозапуск и запустит веб-интерфейс.

#### Установка конкретной версии

Замени `v2.12` на нужный тег релиза:

```bash
cd ~
rm -rf ~/xrayproxy ~/xrayproxy.zip
curl -fL --progress-bar --resolve github.com:443:140.82.121.3 -o xrayproxy.zip https://github.com/pico-soft/XrayProxy/releases/download/v2.12/xrayproxy.zip
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

# Веб-интерфейс (открой http://localhost:8080 в Fennec, Firefox Nightly или любом браузере)
bash ~/xproxy.sh web

# Остановить прокси
bash ~/xproxy.sh stop
```

После установки скрипт автоматически запускает веб-интерфейс и подключается к лучшему серверу (если есть протестированные).

### 4. Добавь подписку

В меню нажми `9` (CLI) или используй поле в веб-интерфейсе. Введи URL подписки — тот же, что используешь в v2rayNG, Happ или других клиентах.

Также можно добавить серверы вручную — вставь одну или несколько ссылок `vless://` или `trojan://` (пункт `a` в CLI, поле «+🔗» в Web).

### 5. Настрой приложения

| Приложение | Как настроить |
|-----------|--------------|
| **Telegram** | Настройки → Данные → Прокси → SOCKS5 → `127.0.0.1:10828` |
| **Fennec / Firefox nightly** | Зайди в `about:config` и выставь: `network.proxy.http = 127.0.0.1`, `network.proxy.http_port = 10829`, `network.proxy.socks = 127.0.0.1`, `network.proxy.socks_port = 10828`, `network.proxy.type = 1`, `network.proxy.socks_remote_dns = true` |
| **WhatsApp, Instagram, ChatGPT** | Через Fennec: `web.whatsapp.com`, `instagram.com`, `chatgpt.com`. Рекомендую сделать из них PWA-приложения |

Российские приложения (банки, СДЭК, Яндекс) работают напрямую — они не видят прокси.

## Автозапуск при загрузке телефона

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

Подожди 20–30 секунд после загрузки, затем открой Fennec, Firefox Nightly или любой другой браузер → `http://localhost:8080`.

Проверить, что автозапуск сработал:

```bash
cat ~/xproxy/boot.log
```

## Возможности

- **Раннее подключение при тесте** — скрипт подключает первый рабочий сервер не дожидаясь окончания теста, остальные тестируются в фоне, по завершении автоматически переключается на самый быстрый
- **Умная кнопка «Авто»** — использует результаты свежего теста (< 1 часа), не запускает повторный тест без необходимости
- **Адаптивный мониторинг** — каждые 2 минуты замеряет прямую скорость и скорость через туннель. Если прямой интернет слабый — не переключает (экономит ресурсы). Если туннель медленнее порога — автоматически переключает сервер
- **Настраиваемые пороги** — порог прямой скорости и порог скорости туннеля (по умолчанию 1 Мбит/с каждый)
- **Автопереключение при ручной проверке** — если при проверке скорости результат ниже порога, автоматически переключает сервер
- **Поддержка VLESS и Trojan** — парсинг подписок и ссылок обоих протоколов
- **Ручное добавление серверов** — вставь одну или несколько ссылок `vless://` или `trojan://`, импорт из файла .txt
- **3-этапное тестирование** — параллельный TCP-пинг (20 потоков) → проверка прокси (2 сек) → замер скорости
- **Фоновая проверка** — автоматически раз в час
- **Подписки** — импорт по URL, автоименование, раздельное управление, выбор активной
- **Стоп-лист** — фильтрация серверов по ключевым словам (например: РФ, Беларусь, Крым)
- **Fetch через прокси** — если URL подписки заблокирован, скачает через рабочий сервер
- **Web-интерфейс** — управление из браузера на `localhost:8080` с автообновлением статуса каждые 15 секунд
- **Автозапуск** — при перезагрузке телефона через Termux:Boot с проверкой соединения
- **Автозапуск после установки** — установщик автоматически подключается и запускает веб-интерфейс
- **Экспорт логов** — ZIP с диагностикой в `Downloads/XrayProxy/`

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
VLESS (TCP, gRPC, WebSocket) с TLS и Reality, а также Trojan (TCP, WebSocket) с TLS.

**Q: Нужен ли root?**
Нет. Всё работает в Termux без root.

**Q: Почему не все серверы работают?**
XrayProxy проверяет серверы в 3 этапа. Те, что не прошли проверку прокси (этап 2), автоматически исключаются. При тесте скрипт подключает первый рабочий сервер сразу, не дожидаясь окончания полного теста.

**Q: Как работает автомониторинг?**
Каждые 2 минуты (настраивается) скрипт замеряет скорость интернета напрямую и через туннель. Если прямая скорость ниже порога — интернет слабый, переключение не происходит. Если туннель медленнее порога — переключает на следующий по скорости сервер. Каскадно перебирает серверы и подписки. Оба порога настраиваемые (по умолчанию 1 Мбит/с).

**Q: Как добавить серверы вручную?**
В CLI пункт `a` — вставляй ссылки `vless://` или `trojan://` по одной. Пункт `f` — импорт из .txt файла. В Web — поле «+🔗» или загрузка файла кнопкой «📄 Из файла».

**Q: Как обновить?**
См. раздел «Обновление» ниже. Подписки, серверы и настройки сохраняются.

**Q: Как отправить логи для помощи?**
В CLI: пункт `x`. В Web: Настройки → Экспорт логов. ZIP-файл появится в `Downloads/XrayProxy/`.

**Q: Termux убивает процесс в фоне?**
Настройки телефона → Приложения → Termux → Батарея → Без ограничений. В Termux: потяни уведомление → Acquire wakelock.

**Q: При установке `termux-setup-storage` не работает?**
Сначала выполни `apt update && apt full-upgrade -y`, потом повтори `termux-setup-storage`.

**Q: Flask не устанавливается (таймаут PyPI)?**
Установщик автоматически пробует зеркала. Если не помогло, выполни вручную:
```bash
pip install flask -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn --break-system-packages
```

## Обновление

### До последней версии

```bash
apt update && apt full-upgrade -y
cd ~
rm -rf ~/xrayproxy ~/xrayproxy.zip
curl -fL --progress-bar --resolve github.com:443:140.82.121.3 -o xrayproxy.zip https://github.com/pico-soft/XrayProxy/releases/latest/download/xrayproxy.zip
unzip -o xrayproxy.zip
bash xrayproxy/install.sh
```

Подписки, серверы, настройки и стоп-лист сохраняются — они хранятся в `~/xproxy/`, а `~/xrayproxy/` это временная папка установщика.

### До конкретной версии

```bash
cd ~
rm -rf ~/xrayproxy ~/xrayproxy.zip
curl -fL --progress-bar --resolve github.com:443:140.82.121.3 -o xrayproxy.zip https://github.com/pico-soft/XrayProxy/releases/download/v2.12/xrayproxy.zip
unzip -o xrayproxy.zip
bash xrayproxy/install.sh
```

### Установка через браузер или получением файла, например, через Telegram (если curl не работает)

Скачай xrayproxy.zip через браузер или получи через мессенджер
Открой Termux и выполни:

```bash
apt update && apt full-upgrade -y && pkg install -y unzip python && termux-setup-storage && sleep 2 && f=$(find ~/storage/downloads ~/storage/shared/Download -name "xrayproxy*.zip" -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-) && if [ -n "$f" ]; then echo "Найден: $f" && cd ~ && rm -rf ~/xrayproxy && unzip -o "$f" && bash xrayproxy/install.sh; else echo "xrayproxy.zip не найден в Downloads"; fi
```

## Лицензия

GPL v3

## Автор

[pico-soft](https://github.com/pico-soft)
