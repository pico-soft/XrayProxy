#!/data/data/com.termux/files/usr/bin/bash
# XrayProxy 2.24-beta — pico-soft
# Usage: bash xproxy.sh [web|stop]

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$DIR/xproxy_cli.py" ] || DIR="$HOME/xproxy"

case "${1:-cli}" in
    web)
        echo "XrayProxy Web → http://localhost:8080"
        exec python3 "$DIR/xproxy_web.py"
        ;;
    stop)
        python3 -c "
import sys; sys.path.insert(0, '$DIR')
import xproxy_lib as lib; lib.init()
if lib.xray_is_running(): lib.xray_stop(); print('Остановлен.')
else: print('Не запущен.')
"
        ;;
    *)
        exec python3 "$DIR/xproxy_cli.py" "$@"
        ;;
esac
