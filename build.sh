#!/bin/bash
# Сборка xrayproxy.zip для GitHub релиза
# Использование: ./build.sh [версия]
# Пример: ./build.sh X.Y-beta

set -e

# grep -oP недоступен на macOS (BSD grep) → Python
OLD=$(python3 -c "import re; print(re.search(r'VERSION = \"([^\"]+)\"', open('xproxy_lib.py').read()).group(1))")

# sed -i требует суффикс на macOS
if [[ "$(uname)" == "Darwin" ]]; then
    sedi() { sed -i "" "$@"; }
else
    sedi() { sed -i "$@"; }
fi

VERSION="${1:-}"
if [ -n "$VERSION" ] && [ "$VERSION" != "$OLD" ]; then
    echo "Бамп: $OLD → $VERSION"
    for f in xproxy_lib.py xproxy_cli.py xproxy_web.py xproxy.sh install.sh README.md templates/index.html templates/task.html update.sh; do
        [ -f "$f" ] && sedi "s/$OLD/$VERSION/g" "$f"
    done
else
    VERSION="$OLD"
    echo "Версия: $VERSION"
fi

echo "Проверка синтаксиса..."
python3 -m py_compile xproxy_lib.py && echo "  ✓ lib"
python3 -m py_compile xproxy_cli.py && echo "  ✓ cli"
python3 -m py_compile xproxy_web.py && echo "  ✓ web"
bash -n install.sh && echo "  ✓ install"
bash -n update.sh && echo "  ✓ update"
bash -n setup-boot.sh && echo "  ✓ boot"

echo "Сборка ZIP..."
rm -rf /tmp/xrayproxy /tmp/xrayproxy.zip
mkdir -p /tmp/xrayproxy/templates
cp xproxy_lib.py xproxy_cli.py xproxy_web.py xproxy.sh \
   install.sh update.sh setup-boot.sh blacklist.txt README.md \
   /tmp/xrayproxy/
cp templates/index.html templates/task.html /tmp/xrayproxy/templates/
cd /tmp
zip -r xrayproxy.zip xrayproxy/ > /dev/null
mv xrayproxy.zip "$OLDPWD/"
rm -rf /tmp/xrayproxy
cd "$OLDPWD"

echo ""
echo "✓ xrayproxy.zip ($VERSION) готов"
echo "  Размер: $(du -h xrayproxy.zip | cut -f1)"
echo ""
echo "Загрузи на GitHub:"
echo "  1. Releases → Edit → удали старый ZIP → загрузи новый"
echo "  2. README: скопируй README-github.md"
