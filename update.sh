#!/data/data/com.termux/files/usr/bin/bash
# XrayProxy — обновление
# Каскад: напрямую → зеркала → VPN → туннель → Downloads

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; GRAY='\033[0;90m'; NC='\033[0m'

ZIP="$HOME/xrayproxy.zip"
PROXY="socks5h://127.0.0.1:10828"

URLS=(
    "https://github.com/pico-soft/XrayProxy/releases/latest/download/xrayproxy.zip"
    "https://ghp.ci/https://github.com/pico-soft/XrayProxy/releases/latest/download/xrayproxy.zip"
    "https://gh-proxy.com/https://github.com/pico-soft/XrayProxy/releases/latest/download/xrayproxy.zip"
)

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  XrayProxy — обновление              ${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

rm -f "$ZIP"
DOWNLOADED=0

try_curl() {
    local url="$1" proxy="$2" label="$3"
    rm -f "$ZIP"
    local cmd="curl -fL --progress-bar --max-time 45 -o $ZIP"
    [ -n "$proxy" ] && cmd="$cmd -x $proxy"
    cmd="$cmd $url"
    eval $cmd 2>&1
    if [ -f "$ZIP" ] && [ $(stat -c%s "$ZIP" 2>/dev/null || stat -f%z "$ZIP" 2>/dev/null || echo 0) -gt 1000 ]; then
        return 0
    fi
    return 1
}

# Способ 1: напрямую по зеркалам
for i in "${!URLS[@]}"; do
    url="${URLS[$i]}"
    label=$(echo "$url" | awk -F/ '{print $3}' | cut -c1-20)
    echo -e "${CYAN}[$((i+1))/${#URLS[@]}] $label...${NC}"
    if try_curl "$url" "" "$label"; then
        echo -e "  ${GREEN}✓${NC} Скачано ($label)"
        DOWNLOADED=1
        break
    fi
done

# Способ 2: через системный VPN
if [ "$DOWNLOADED" = "0" ]; then
    if ip route 2>/dev/null | grep -q "tun0\|tun1"; then
        echo -e "${CYAN}Обнаружен VPN, пробую...${NC}"
        if try_curl "${URLS[0]}" "" "vpn"; then
            echo -e "  ${GREEN}✓${NC} Скачано через VPN"
            DOWNLOADED=1
        fi
    fi
fi

# Способ 3: через XrayProxy туннель
if [ "$DOWNLOADED" = "0" ]; then
    if curl -sx "$PROXY" --max-time 5 https://ifconfig.me/ip > /dev/null 2>&1; then
        echo -e "${CYAN}Через XrayProxy туннель...${NC}"
        if try_curl "${URLS[0]}" "$PROXY" "tunnel"; then
            echo -e "  ${GREEN}✓${NC} Скачано через туннель"
            DOWNLOADED=1
        fi
    else
        echo -e "  ${GRAY}Туннель не активен${NC}"
    fi
fi

# Способ 4: через переменные окружения прокси
if [ "$DOWNLOADED" = "0" ]; then
    SYS_PROXY="${HTTPS_PROXY:-$HTTP_PROXY}"
    if [ -n "$SYS_PROXY" ]; then
        echo -e "${CYAN}Системный прокси: $SYS_PROXY...${NC}"
        if try_curl "${URLS[0]}" "$SYS_PROXY" "sys-proxy"; then
            echo -e "  ${GREEN}✓${NC} Скачано через системный прокси"
            DOWNLOADED=1
        fi
    fi
fi

# Способ 5: из Downloads
if [ "$DOWNLOADED" = "0" ]; then
    echo -e "${CYAN}Ищу в Downloads...${NC}"
    FOUND=$(find ~/storage/downloads ~/storage/shared/Download -maxdepth 3 -name "xrayproxy*.zip" -type f -exec stat -c '%Y %n' {} \; 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
    if [ -n "$FOUND" ] && [ -f "$FOUND" ]; then
        cp "$FOUND" "$ZIP"
        echo -e "  ${GREEN}✓${NC} $FOUND"
        DOWNLOADED=1
    fi
fi

if [ "$DOWNLOADED" = "0" ]; then
    echo ""
    echo -e "${RED}Не удалось скачать.${NC}"
    echo -e "${YELLOW}Скачай через браузер:${NC}"
    echo -e "  ${CYAN}${URLS[0]}${NC}"
    echo -e "${YELLOW}Потом:${NC} bash ~/xproxy.sh update"
    exit 1
fi

# Распаковка и установка
echo ""
echo -e "${CYAN}Распаковываю...${NC}"
cd "$HOME"
rm -rf "$HOME/xrayproxy"
unzip -o "$ZIP" > /dev/null 2>&1
chmod +x "$HOME/xrayproxy/"*.sh 2>/dev/null

if [ -f "$HOME/xrayproxy/install.sh" ]; then
    echo -e "${GREEN}✓${NC} Запускаю установку..."
    echo ""
    bash "$HOME/xrayproxy/install.sh"
else
    echo -e "${RED}Ошибка распаковки${NC}"
    exit 1
fi
