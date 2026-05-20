#!/data/data/com.termux/files/usr/bin/bash
# XrayProxy — настройка автозапуска при загрузке через Termux:Boot
mkdir -p ~/.termux/boot
python3 << 'PYEND'
import os
path = os.path.expanduser("~/.termux/boot/xrayproxy")
# Имя файла конструируем программно, чтобы избежать искажений
web_script = "xproxy_web" + chr(46) + "py"
boot_log = "~/xproxy/boot" + chr(46) + "log"
lines = [
    "#!/data/data/com.termux/files/usr/bin/bash",
    "termux-wake-lock",
    "sleep 10",
    "cd ~/xproxy",
    'python3 -c "'
    "import xproxy_lib as l;"
    "l.init();"
    "b=l.find_fastest_server();"
    "b and l.xray_start_with(b);"
    "l.start_monitor() if l.get_auto_monitor() else None"
    f'" >> {boot_log} 2>&1',
    f"python3 {web_script} >> {boot_log} 2>&1 &",
]
with open(path, "w") as f:
    f.write("\n".join(lines) + "\n")
os.chmod(path, 0o755)
print("OK")
PYEND
echo "---"
cat ~/.termux/boot/xrayproxy
