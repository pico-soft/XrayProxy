# XrayProxy — PROJECT_CONTEXT.md
# Этот файл описывает проект для Claude Code. Читай его первым.

## Суть
SOCKS5/HTTP прокси для Android (Termux) через xray-core. Не создаёт VPN-интерфейс.
Порты: SOCKS5=10828, HTTP=10829. Web на Flask :8080.

**Версия:** 2.19-beta | **Автор:** pico-soft | **GitHub:** github.com/pico-soft/XrayProxy

## Файлы

| Файл | Строк | Описание |
|------|-------|----------|
| xproxy_lib.py | ~1600 | Ядро: парсинг, xray, тесты, мониторинг, smart_download |
| xproxy_cli.py | ~460 | CLI-интерфейс |
| xproxy_web.py | ~490 | Flask Web-интерфейс |
| install.sh | ~270 | Установщик (7 шагов + автозапуск) |
| update.sh | ~100 | Обновление: напрямую → зеркала → VPN → туннель → Downloads |
| setup-boot.sh | ~30 | Настройка Termux:Boot автозапуска |
| xproxy.sh | ~10 | Лаунчер: cli/web/stop/update |
| templates/index.html | ~310 | Главная Web (тёмная тема) |
| templates/task.html | ~50 | Страница прогресса задач |
| blacklist.txt | ~10 | Стоп-лист (москва, россия, ...) |
| README.md | ~240 | README внутри ZIP |
| README-github.md | ~250 | README для главной страницы GitHub |

## Ключевые архитектурные решения

### Протоколы
- VLESS (TCP, gRPC, WebSocket) с TLS и Reality
- Trojan (TCP, WebSocket) с TLS

### smart_download() — универсальное скачивание (6 способов)
1. Напрямую по основному URL
2. Зеркала (ghp.ci, gh-proxy.com)
3. Системный VPN (определяет tun0)
4. Системный прокси (HTTP_PROXY)
5. XrayProxy туннель (SOCKS5 :10828)
6. Из Downloads (рекурсивный поиск по дате, включая подпапки Telegram)

### install_xray() — не перекачивает если уже установлен
- `force=False` (по умолчанию) — пропускает если xray есть
- `force=True` (пункт `u` в CLI) — перекачивает

### measure_direct_speed() — быстрая проверка прямого интернета
- TCP-пинг к DNS (8.8.8.8, 1.1.1.1, 77.88.8.8)
- Файлы 100KB (tele2, OVH) — без Cloudflare напрямую
- Таймаут 5 сек, проверка за 1-2 сек

### check_external_ip() — 4 сервиса
ipify → ifconfig.me → icanhazip → checkip.amazonaws

### run_full_test_with_early_connect() — раннее подключение
- Этап 1: параллельный пинг (20 потоков)
- Этап 2-3: прокси+скорость — первый рабочий (speed>0) подключается СРАЗУ
- По завершении переключается на самый быстрый
- Web авторедирект на главную при `⚡ Подключаю`

### Адаптивный мониторинг (_monitor_loop)
- Каждые 2 мин: прямая скорость → скорость туннеля
- Прямая < порога → интернет слабый, не переключает
- Туннель < порога → ищет замену через ВРЕМЕННЫЙ xray (не ломает текущее)
- Максимум 5 попыток за цикл
- Два настраиваемых порога: direct_speed_threshold, tunnel_speed_threshold (дефолт 1.0)

### Кнопка ⏱ Тест сервера (speed_and_switch)
1. Проверяет прямой интернет — если плохой, стоп
2. Проверяет текущий сервер — если ок, стоп
3. Каскад по ВСЕМ подпискам + ручные серверы
4. Каждый кандидат через temp xray
5. Если ни один не подходит — предлагает обновить подписки

### Web кнопки (порядок)
⚡ Авто | ⏱ Тест сервера | → След | ■ Стоп | ↻ Подписки | 🔍 Полный тест

### Обновление через Web
- Скачивает ZIP (напрямую/туннель/Downloads)
- Показывает копируемое поле с командой: `bash ~/xrayproxy/install.sh`
- Инструкция: Ctrl+C → скопируй → вставь → Enter

## Формат метафайла сервера (servers/N.meta)
```json
{"NAME":"🇦🇹 Австрия","HOST":"at.example.com","PORT":443,"UUID":"...","PROTOCOL":"vless",
 "SECURITY":"reality","SNI":"google.com","FP":"chrome","PBK":"...","SID":"...",
 "FLOW":"xtls-rprx-vision","TYPE":"tcp","PATH":"","SERVICENAME":"","HOST_HEADER":"",
 "PING_MS":119,"SPEED_MBPS":14.6,"SOURCE":"https://...","LAST_TESTED":"2026-05-07 19:45"}
```

## Правила
- Версии: минорные +0.1, мажорные +1.0, формат X.Y-beta
- При бампе обновлять ВСЕ файлы: `sed -i 's/OLD/NEW/g' *.py *.sh *.md templates/*.html`
- Не использовать `.py` отдельным токеном в bash (браузеры ломают) — используй `chr(46)` в Python
- Flask: `threaded=True` обязательно
- Тесты серверов через `_run_temp_xray` (динамический порт)
- Мониторинг тестирует через temp xray, переключает только подтверждённый

## Известные ограничения среды
- GitHub заблокирован у многих пользователей → зеркала + туннель + Downloads
- PyPI заблокирован → 3 зеркала (pypi.org → tuna.tsinghua → bfsu)
- Cloudflare заблокирован напрямую → не используем для measure_direct_speed
- api.ipify.org может быть заблокирован → 4 сервиса проверки IP

## Сборка ZIP
```bash
cd .. && rm -f xrayproxy.zip
mkdir -p /tmp/xrayproxy
cp xproxy_lib.py xproxy_cli.py xproxy_web.py xproxy.sh install.sh update.sh setup-boot.sh blacklist.txt README.md /tmp/xrayproxy/
cp -r templates /tmp/xrayproxy/
cd /tmp && zip -r ~/xrayproxy.zip xrayproxy/ && rm -rf /tmp/xrayproxy
```

## ТЗ на будущее
- [ ] sing-box как альтернативное ядро (Hysteria2, TUIC, ShadowTLS)
- [ ] Shadowsocks парсинг (ss://)
- [ ] Очистка временных _test_* при init()
- [ ] Ротация старых ZIP-логов
