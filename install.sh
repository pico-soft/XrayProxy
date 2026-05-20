#!/data/data/com.termux/files/usr/bin/bash
# ============================================
# XrayProxy 2.19-beta — установщик
# pico-soft | github.com/pico-soft/XrayProxy
# ============================================

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; GRAY='\033[0;90m'; NC='\033[0m'

PROJECT_DIR="$HOME/xproxy"
LAUNCHER="$HOME/xproxy.sh"

PROJECT_FILES=("xproxy_lib.py" "xproxy_cli.py" "xproxy_web.py" "xproxy.sh" "setup-boot.sh" "update.sh")
TEMPLATE_FILES=("templates/index.html" "templates/task.html")
OPTIONAL_FILES=("blacklist.txt")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  XrayProxy — установка              ${NC}"
echo -e "${CYAN}  pico-soft                            ${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# --- [0] Остановка запущенных процессов ---

if pgrep -f xproxy_web > /dev/null 2>&1 || pgrep -f "xray" > /dev/null 2>&1; then
    echo -e "${YELLOW}Останавливаю запущенные процессы...${NC}"
    pkill -f xproxy_web 2>/dev/null
    pkill -f "xray run" 2>/dev/null
    sleep 1
fi
# Убиваем всё на порту 8080
if command -v fuser >/dev/null 2>&1; then
    fuser -k 8080/tcp 2>/dev/null
elif command -v lsof >/dev/null 2>&1; then
    lsof -ti:8080 | xargs kill 2>/dev/null
else
    # Fallback: ищем python на порту 8080
    for pid in $(ps aux 2>/dev/null | grep -E "python.*8080|xproxy_web" | grep -v grep | awk '{print $2}'); do
        kill "$pid" 2>/dev/null
    done
fi
sleep 1
echo -e "  ${GREEN}✓${NC} Процессы остановлены"

# --- [1/7] Обновление системы ---

echo -e "${CYAN}[1/7] Обновление системы...${NC}"
apt update -y > /dev/null 2>&1
apt full-upgrade -y > /dev/null 2>&1
echo -e "  ${GREEN}✓${NC} Система обновлена"

# --- [2/7] Хранилище ---

echo -e "${CYAN}[2/7] Доступ к хранилищу...${NC}"
if [ ! -d "$HOME/storage" ]; then
    echo -e "  ${YELLOW}Запрашиваю доступ... Нажми «Разрешить» в диалоге.${NC}"
    termux-setup-storage
    sleep 3
    if [ ! -d "$HOME/storage" ]; then
        echo -e "  ${RED}Не удалось. Разреши доступ в настройках Termux и запусти снова.${NC}"
        exit 1
    fi
fi
echo -e "  ${GREEN}✓${NC} Доступ есть"

# --- [3/7] Пакеты ---

echo -e "${CYAN}[3/7] Пакеты...${NC}"
for pkg_name in python curl unzip; do
    if ! command -v $pkg_name >/dev/null 2>&1; then
        echo -e "  ${YELLOW}Устанавливаю $pkg_name...${NC}"
        pkg install -y $pkg_name > /dev/null 2>&1
    fi
done

# Python >= 3.8
PY_OK=$(python3 -c "import sys; print(1 if sys.version_info >= (3,8) else 0)" 2>/dev/null)
if [ "$PY_OK" != "1" ]; then
    echo -e "  ${RED}Нужен Python 3.8+. Выполни: pkg install python${NC}"; exit 1
fi

# Flask — пробуем несколько источников
if ! python3 -c "import flask" 2>/dev/null; then
    echo -e "  ${YELLOW}Устанавливаю Flask...${NC}"
    FLASK_OK=0
    # PyPI напрямую
    pip install flask --break-system-packages -q --timeout 10 2>/dev/null && FLASK_OK=1
    # Зеркало Tsinghua (быстрое из РФ)
    if [ "$FLASK_OK" = "0" ]; then
        echo -e "  ${GRAY}PyPI недоступен, зеркало...${NC}"
        pip install flask --break-system-packages -q --timeout 15 \
            -i https://pypi.tuna.tsinghua.edu.cn/simple \
            --trusted-host pypi.tuna.tsinghua.edu.cn 2>/dev/null && FLASK_OK=1
    fi
    # Зеркало BFSU
    if [ "$FLASK_OK" = "0" ]; then
        pip install flask --break-system-packages -q --timeout 15 \
            -i https://mirrors.bfsu.edu.cn/pypi/web/simple \
            --trusted-host mirrors.bfsu.edu.cn 2>/dev/null && FLASK_OK=1
    fi
    if [ "$FLASK_OK" = "0" ]; then
        echo -e "  ${RED}Не удалось установить Flask.${NC}"
        echo -e "  ${GRAY}Попробуй: pip install flask -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn --break-system-packages${NC}"
    fi
fi
echo -e "  ${GREEN}✓${NC} python3 $(python3 --version 2>&1 | cut -d' ' -f2), curl, unzip, flask"

# --- [4/7] Папки ---

echo -e "${CYAN}[4/7] Структура...${NC}"
mkdir -p "$PROJECT_DIR/servers" "$PROJECT_DIR/templates"
echo -e "  ${GREEN}✓${NC} $PROJECT_DIR"

# --- [5/7] Файлы ---

echo -e "${CYAN}[5/7] Файлы...${NC}"

# Автопоиск ZIP из браузера (xrayproxy.zip, xrayproxy (1).zip, xrayproxy (2).zip и т.д.)
_auto_unzip_from_downloads() {
    # Ищем самый свежий xrayproxy*.zip рекурсивно по ВСЕМ папкам
    local latest=""
    local latest_ts=0

    for dir in "$HOME/storage/downloads" "$HOME/storage/shared/Download" "$HOME"; do
        [ -d "$dir" ] || continue
        while IFS= read -r line; do
            local ts=$(echo "$line" | cut -d' ' -f1)
            local fpath=$(echo "$line" | cut -d' ' -f2-)
            if [ -n "$ts" ] && [ "$ts" -gt "$latest_ts" ] 2>/dev/null; then
                latest_ts="$ts"
                latest="$fpath"
            fi
        done < <(find "$dir" -maxdepth 3 -name "xrayproxy*.zip" -type f -exec stat -c '%Y %n' {} \; 2>/dev/null)
    done

    if [ -n "$latest" ] && [ -f "$latest" ]; then
        echo -e "  ${GREEN}✓${NC} Найден: $latest"
        cd "$HOME"
        rm -rf "$HOME/xrayproxy"
        unzip -o "$latest" > /dev/null 2>&1
        if [ -d "$HOME/xrayproxy" ]; then
            return 0
        fi
    fi
    return 1
}

# Ищем исходники
SOURCE_DIR=""
if [ -f "$SCRIPT_DIR/xproxy_lib.py" ]; then
    SOURCE_DIR="$SCRIPT_DIR"
fi
if [ -z "$SOURCE_DIR" ]; then
    for dir in "$HOME/xrayproxy" "$HOME/XrayProxy" \
               "$HOME/storage/downloads/Telegram/xrayproxy" \
               "$HOME/storage/downloads/xrayproxy" \
               "$HOME/storage/downloads" \
               "$HOME/storage/shared/Download/xrayproxy" \
               "$HOME/storage/shared/Download"; do
        [ -f "$dir/xproxy_lib.py" ] && SOURCE_DIR="$dir" && break
    done
fi
# Если не нашли — пробуем распаковать ZIP из Downloads
if [ -z "$SOURCE_DIR" ]; then
    echo -e "  ${YELLOW}Ищу ZIP в загрузках...${NC}"
    if _auto_unzip_from_downloads; then
        [ -f "$HOME/xrayproxy/xproxy_lib.py" ] && SOURCE_DIR="$HOME/xrayproxy"
    fi
fi
[ -z "$SOURCE_DIR" ] && echo -e "  ${RED}✗ Файлы не найдены. Скачай xrayproxy.zip и положи в Downloads.${NC}" && exit 1
echo -e "  ${GREEN}✓${NC} Источник: $SOURCE_DIR"

# Версии и бэкап
NEW_V=$(grep -m1 'VERSION = ' "$SOURCE_DIR/xproxy_lib.py" | grep -o '"[^"]*"' | tr -d '"')
OLD_V=""
[ -f "$PROJECT_DIR/xproxy_lib.py" ] && OLD_V=$(grep -m1 'VERSION = ' "$PROJECT_DIR/xproxy_lib.py" | grep -o '"[^"]*"' | tr -d '"')

if [ -n "$OLD_V" ] && [ "$OLD_V" != "$NEW_V" ]; then
    echo -e "  ${YELLOW}Обновление: $OLD_V → $NEW_V${NC}"
    for f in "${PROJECT_FILES[@]}"; do
        [ -f "$PROJECT_DIR/$f" ] && cp "$PROJECT_DIR/$f" "$PROJECT_DIR/${f}.${OLD_V}.bak" 2>/dev/null
    done
elif [ -n "$OLD_V" ]; then
    echo -e "  ${GRAY}Переустановка $OLD_V${NC}"
else
    echo -e "  ${GREEN}Первая установка $NEW_V${NC}"
fi

# Копируем
for f in "${PROJECT_FILES[@]}"; do
    [ -f "$SOURCE_DIR/$f" ] && cp "$SOURCE_DIR/$f" "$PROJECT_DIR/$f" && echo -e "  ${GREEN}✓${NC} $f"
done
for f in "${TEMPLATE_FILES[@]}"; do
    [ -f "$SOURCE_DIR/$f" ] && cp "$SOURCE_DIR/$f" "$PROJECT_DIR/$f" && echo -e "  ${GREEN}✓${NC} $f"
done
for f in "${OPTIONAL_FILES[@]}"; do
    if [ ! -f "$PROJECT_DIR/$f" ] && [ -f "$SOURCE_DIR/$f" ]; then
        cp "$SOURCE_DIR/$f" "$PROJECT_DIR/$f"; echo -e "  ${GREEN}✓${NC} $f"
    fi
done
chmod +x "$PROJECT_DIR/xproxy.sh" "$PROJECT_DIR/xproxy_cli.py" "$PROJECT_DIR/xproxy_web.py" "$PROJECT_DIR/setup-boot.sh" 2>/dev/null

# --- [6/7] Лаунчер ---

echo -e "${CYAN}[6/7] Лаунчер...${NC}"
cat > "$LAUNCHER" << 'LAUNCHEREOF'
#!/data/data/com.termux/files/usr/bin/bash
DIR="$HOME/xproxy"
case "${1:-cli}" in
    web) echo "XrayProxy Web → http://localhost:8080"; exec python3 "$DIR/xproxy_web.py" ;;
    stop) python3 -c "import sys;sys.path.insert(0,'$DIR');import xproxy_lib as l;l.init();l.xray_stop() if l.xray_is_running() else None;print('OK')" ;;
    update) exec bash "$DIR/update.sh" ;;
    *) exec python3 "$DIR/xproxy_cli.py" "$@" ;;
esac
LAUNCHEREOF
# Fix $DIR in launcher (heredoc with quotes doesn't expand)
sed -i "s|\$DIR|$PROJECT_DIR|g" "$LAUNCHER"
chmod +x "$LAUNCHER"
echo -e "  ${GREEN}✓${NC} ~/xproxy.sh"

# --- [7/7] Автозапуск ---

echo -e "${CYAN}[7/7] Автозапуск...${NC}"

# Проверяем, установлен ли Termux:Boot
if [ -d "/data/data/com.termux.boot" ] || command -v termux-boot >/dev/null 2>&1; then
    bash "$PROJECT_DIR/setup-boot.sh" 2>/dev/null
    if [ -f "$HOME/.termux/boot/xrayproxy" ]; then
        echo -e "  ${GREEN}✓${NC} Автозапуск настроен"
    else
        echo -e "  ${YELLOW}⚠${NC} Не удалось настроить автозапуск"
    fi
else
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}  ⚠ Автозапуск НЕ настроен!           ${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  Без Termux:Boot XrayProxy не будет"
    echo -e "  запускаться при включении телефона."
    echo ""
    echo -e "  ${CYAN}Как исправить:${NC}"
    echo -e "  1. Установи Termux:Boot из F-Droid:"
    echo -e "     ${BLUE}https://f-droid.org/packages/com.termux.boot/${NC}"
    echo -e "  2. Открой Termux:Boot один раз"
    echo -e "  3. В Termux выполни:"
    echo -e "     ${BLUE}bash ~/xproxy/setup-boot.sh${NC}"
    echo ""
fi

# --- Готово ---

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✓ XrayProxy $NEW_V установлен!     ${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Автоподключение к лучшему серверу (если есть протестированные)
echo -e "${CYAN}Подключаюсь к лучшему серверу...${NC}"
python3 -c "
import sys; sys.path.insert(0, '$PROJECT_DIR')
import xproxy_lib as l
l.init()
b = l.find_fastest_server()
if b:
    l.xray_start_with(b)
    print('  ✓ ' + b.get('NAME', '?'))
    if l.get_auto_monitor():
        l.start_monitor()
else:
    print('  Нет протестированных серверов — нажми Авто в интерфейсе')
" 2>/dev/null

echo ""
echo -e "${CYAN}Запускаю веб-интерфейс...${NC}"
echo -e "  Открой в браузере: ${BLUE}http://localhost:8080${NC}"
echo ""
exec bash "$LAUNCHER" web
