#!/data/data/com.termux/files/usr/bin/env python3
"""XrayProxy Web — pico-soft — v.2.24-beta"""

import sys, os, json, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from flask import Flask, render_template, request, redirect, url_for, jsonify
except ImportError:
    print("Flask не установлен. Попробуй:")
    print("  pip install flask --break-system-packages")
    print("Если PyPI недоступен:")
    print("  pip install flask -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn --break-system-packages")
    sys.exit(1)

import xproxy_lib as lib

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))
app.secret_key = "xproxy_local"

_task = {"running": False, "type": "", "progress": [], "done": False}
_lock = threading.Lock()
_task_id = 0

def tlog(m):
    with _lock: _task["progress"].append(m)

def get_task_snapshot():
    with _lock: return dict(_task)

def run_bg(func, name="task", force=False):
    global _task_id
    with _lock:
        if _task["running"] and not force: return False
        _task_id += 1
        my_id = _task_id
        _task.update({"running": True, "type": name, "progress": [], "done": False})
    def w():
        try: func()
        except Exception as e: tlog(f"Ошибка: {e}")
        finally:
            with _lock:
                if _task_id == my_id:
                    _task.update({"running": False, "done": True})
    threading.Thread(target=w, daemon=True).start(); return True

@app.route("/")
def index():
    running = lib.xray_is_running()
    cur = lib.get_current_server()
    ip = lib.check_external_ip() if running else None
    scope = lib.get_active_scope()
    return render_template("index.html",
        version=lib.VERSION, app_name=lib.APP_NAME,
        is_running=running, current=cur, external_ip=ip,
        socks_port=lib.SOCKS_PORT, http_port=lib.HTTP_PORT,
        servers=lib.sort_servers_by_speed(lib.get_servers_by_scope(scope)),
        alive_servers=lib.sort_servers_by_speed(lib.get_alive_servers(scope)),
        subs=lib.get_subscriptions(),
        active_url=lib.get_active_subscription(),
        active_name=lib.get_subscription_name(lib.get_active_subscription()) if lib.get_active_subscription() else "Все",
        timeout=lib.get_proxy_check_timeout(),
        bg_running=lib.is_background_running(),
        monitor_running=lib.is_monitor_running(),
        auto_monitor=lib.get_auto_monitor(),
        monitor_interval=lib.get_monitor_interval(),
        direct_threshold=lib.get_direct_speed_threshold(),
        tunnel_threshold=lib.get_tunnel_speed_threshold(),
        monitor_log=lib.get_monitor_log()[-10:],
        blacklist=lib.get_blacklist(),
        last_test=lib.get_last_test_time(),
        last_update=lib.get_last_update_time(),
        task=get_task_snapshot())

@app.route("/connect/<int:idx>")
def connect(idx):
    scope = lib.get_active_scope()
    servers = lib.sort_servers_by_speed(lib.get_servers_by_scope(scope))
    if 0 <= idx < len(servers):
        if lib.xray_is_running(): lib.xray_stop()
        lib.xray_start_with(servers[idx])
    return redirect("/")

@app.route("/auto_connect")
def auto_connect():
    scope = lib.get_active_scope()

    # Если есть протестированные серверы — подключаемся сразу
    best = lib.find_fastest_server(scope)
    if best:
        if lib.xray_is_running(): lib.xray_stop()
        lib.xray_start_with(best)
        if lib.get_auto_monitor() and not lib.is_monitor_running():
            lib.start_monitor()
        return redirect("/")

    def do():
        # Обновить подписки если тест свежий но серверов нет
        if lib.is_test_fresh(60):
            urls = lib.get_subscription_urls() if scope=="ALL" else [scope]
            for url in urls:
                tlog(f"Обновляю: {lib.get_subscription_name(url)}...")
                lib.update_single_subscription(url, progress_cb=tlog)

        s = lib.get_servers_by_scope(scope)
        if not s: tlog("Нет серверов"); return

        # Тест с ранним подключением
        lib.run_full_test_with_early_connect(s, progress_cb=tlog)

        # После завершения теста — переключиться на самый быстрый
        best = lib.find_fastest_server(scope)
        if best:
            cur = lib.get_current_server()
            # Переключаем только если нашли сервер быстрее текущего
            if not cur or best.get("SPEED_MBPS", 0) > cur.get("SPEED_MBPS", 0):
                if lib.xray_is_running(): lib.xray_stop()
                lib.xray_start_with(best)
                tlog(f"⚡ Лучший: {best.get('NAME','?')} ({best.get('SPEED_MBPS',0)} Мбит/с)")
            if lib.get_auto_monitor() and not lib.is_monitor_running():
                lib.start_monitor()

    run_bg(do, "auto"); return redirect("/task")

@app.route("/next_server")
def next_server():
    cur = lib.get_current_server()
    if cur:
        nxt = lib.find_next_server(cur.get("SOURCE", lib.get_active_scope()))
        if nxt:
            if lib.xray_is_running(): lib.xray_stop()
            lib.xray_start_with(nxt)
    return redirect("/")

@app.route("/stop")
def stop():
    lib.xray_stop()
    if lib.is_monitor_running(): lib.stop_monitor()
    return redirect("/")

@app.route("/start")
def start():
    cur = lib.get_current_server()
    if cur:
        lib.xray_start_with(cur)
        if lib.get_auto_monitor() and not lib.is_monitor_running():
            lib.start_monitor()
    return redirect("/")

@app.route("/run_tests")
def run_tests():
    scope = lib.get_active_scope()
    def do():
        s = lib.get_servers_by_scope(scope)
        if not s: tlog("Нет серверов"); return
        lib.run_full_test_with_early_connect(s, progress_cb=tlog)
    run_bg(do, "test"); return redirect("/task")

@app.route("/task")
def task_page(): return render_template("task.html", version=lib.VERSION, app_name=lib.APP_NAME, task=get_task_snapshot())

@app.route("/task_status")
def task_status():
    with _lock: return jsonify(_task)

@app.route("/add_sub", methods=["POST"])
def add_sub():
    url = request.form.get("url","").strip(); name = request.form.get("name","").strip()
    if url:
        lib.add_subscription(url, name or None)
        def do():
            tlog(f"Загружаю: {url[:50]}...")
            ok, added, skip = lib.update_single_subscription(url, progress_cb=tlog)
            if ok: tlog(f"+{added} серверов")
            else: tlog("Ошибка загрузки")
        run_bg(do, "add_sub"); return redirect("/task")
    return redirect("/")

@app.route("/add_server", methods=["POST"])
def add_server():
    uri = request.form.get("uri","").strip()
    if uri:
        name = lib.add_server_manually(uri)
        if name:
            return redirect("/")
    return redirect("/")

@app.route("/add_servers_batch", methods=["POST"])
def add_servers_batch():
    uris = request.form.get("uris","").strip()
    if not uris:
        return redirect("/")

    def do():
        added, skipped, errors = lib.import_servers_batch(uris)
        tlog(f"Добавлено: {added}")
        if skipped: tlog(f"Исключено (стоп-лист): {skipped}")
        if errors: tlog(f"Не распознано: {errors}")
        if added > 0:
            manual = [s for s in lib.get_active_servers(lib.MANUAL_SOURCE) if s.get("PING_MS", -1) < 0]
            if manual:
                tlog(f"Тестирую {len(manual)} серверов...")
                alive = lib.run_ping_tests(manual, lambda i,t,n,p: tlog(f"[{i}/{t}] {n[:30]} {'OK '+str(p) if p>0 else 'нет'}"))
                if alive:
                    wrk = lib.run_proxy_checks(alive, lambda i,t,n,ok: tlog(f"[{i}/{t}] {n[:30]} {'✓' if ok else '✗'}"))
                    if wrk:
                        lib.run_speed_tests(wrk, lambda i,t,n,s: tlog(f"[{i}/{t}] {n[:30]} {s}Мб/с" if s>0 else f"[{i}/{t}] {n[:30]} 0"))
        tlog("✓ Готово")
    run_bg(do, "import"); return redirect("/task")

@app.route("/import_file", methods=["POST"])
def import_file():
    f = request.files.get("file")
    if not f or not f.filename:
        return redirect("/")
    text = f.read().decode("utf-8", errors="ignore")
    if not text.strip():
        return redirect("/")

    def do():
        added, skipped, errors = lib.import_servers_batch(text)
        tlog(f"Файл: {f.filename}")
        tlog(f"Добавлено: {added}")
        if skipped: tlog(f"Исключено (стоп-лист): {skipped}")
        if errors: tlog(f"Не распознано: {errors}")
        if added > 0:
            manual = [s for s in lib.get_active_servers(lib.MANUAL_SOURCE) if s.get("PING_MS", -1) < 0]
            if manual:
                tlog(f"Тестирую {len(manual)} серверов...")
                alive = lib.run_ping_tests(manual, lambda i,t,n,p: tlog(f"[{i}/{t}] {n[:30]} {'OK '+str(p) if p>0 else 'нет'}"))
                if alive:
                    wrk = lib.run_proxy_checks(alive, lambda i,t,n,ok: tlog(f"[{i}/{t}] {n[:30]} {'✓' if ok else '✗'}"))
                    if wrk:
                        lib.run_speed_tests(wrk, lambda i,t,n,s: tlog(f"[{i}/{t}] {n[:30]} {s}Мб/с" if s>0 else f"[{i}/{t}] {n[:30]} 0"))
        tlog("✓ Готово")
    run_bg(do, "import_file"); return redirect("/task")

@app.route("/del_sub/<int:idx>")
def del_sub(idx):
    subs = lib.get_subscriptions()
    if 0<=idx<len(subs): lib.remove_subscription(subs[idx]["url"])
    return redirect("/")

@app.route("/set_active_sub/<idx>")
def set_active_sub(idx):
    try:
        idx = int(idx)
    except ValueError:
        return redirect("/")
    if idx == -1 or idx < 0:
        lib.set_active_subscription(None)
    else:
        subs = lib.get_subscriptions()
        if 0<=idx<len(subs): lib.set_active_subscription(subs[idx]["url"])
    return redirect("/")

@app.route("/update_subs")
def update_subs():
    scope = lib.get_active_scope()
    def do():
        urls = lib.get_subscription_urls() if scope=="ALL" else [scope]
        for url in urls:
            tlog(f"Обновляю: {lib.get_subscription_name(url)}...")
            ok, added, _ = lib.update_single_subscription(url, progress_cb=tlog)
            if ok: tlog(f"+{added}")
            else: tlog("Ошибка")
    run_bg(do, "update"); return redirect("/task")

# --- Настройки ---

@app.route("/set_timeout", methods=["POST"])
def set_timeout():
    try: lib.set_proxy_check_timeout(int(request.form.get("timeout", "2")))
    except: pass
    return redirect("/")

@app.route("/toggle_bg")
def toggle_bg():
    if lib.is_background_running(): lib.stop_background_check()
    else: lib.start_background_check()
    return redirect("/")

@app.route("/toggle_monitor")
def toggle_monitor():
    if lib.is_monitor_running():
        lib.stop_monitor()
    else:
        lib.start_monitor()
    return redirect("/")

@app.route("/toggle_auto_monitor")
def toggle_auto_monitor():
    new_val = not lib.get_auto_monitor()
    lib.set_auto_monitor(new_val)
    if new_val and lib.xray_is_running() and not lib.is_monitor_running():
        lib.start_monitor()
    elif not new_val and lib.is_monitor_running():
        lib.stop_monitor()
    return redirect("/")

@app.route("/set_monitor_interval", methods=["POST"])
def set_monitor_interval():
    try: lib.set_monitor_interval(int(request.form.get("interval", "300")))
    except: pass
    return redirect("/")

@app.route("/set_direct_threshold", methods=["POST"])
def set_direct_threshold():
    try: lib.set_direct_speed_threshold(float(request.form.get("speed", "1.0")))
    except: pass
    return redirect("/")

@app.route("/set_tunnel_threshold", methods=["POST"])
def set_tunnel_threshold():
    try: lib.set_tunnel_speed_threshold(float(request.form.get("speed", "1.0")))
    except: pass
    return redirect("/")

@app.route("/monitor_log")
def monitor_log_api():
    return jsonify(lib.get_monitor_log())

# --- Стоп-лист ---

@app.route("/add_blacklist", methods=["POST"])
def add_blacklist():
    w = request.form.get("word","").strip()
    if w: lib.add_to_blacklist(w)
    return redirect("/")

@app.route("/del_blacklist/<int:idx>")
def del_blacklist(idx):
    bl = lib.get_blacklist()
    if 0<=idx<len(bl): lib.remove_from_blacklist(bl[idx])
    return redirect("/")

# --- API ---

@app.route("/check_speed")
def check_speed():
    """Быстрая проверка — возвращает текущую скорость без переключения."""
    r = lib.measure_current_speed()
    cur = lib.get_current_server()
    if r and cur:
        mbps, tt = r
        lib.update_server_meta(cur["_file"], {"SPEED_MBPS": mbps, "LAST_TESTED": lib._now_str()})
        lib.set_last_test_time()
        threshold = lib.get_tunnel_speed_threshold()
        if mbps < threshold:
            return jsonify({"mbps": mbps, "time": round(tt, 2), "slow": True, "threshold": threshold})
        return jsonify({"mbps": mbps, "time": round(tt, 2), "slow": False, "threshold": threshold})
    return jsonify({"mbps": 0, "time": 0, "slow": True, "threshold": 0})

@app.route("/speed_and_switch")
def speed_and_switch():
    """Проверяет скорость, каскадно перебирает все серверы всех подписок."""
    def do():
        threshold = lib.get_tunnel_speed_threshold()
        direct_thr = lib.get_direct_speed_threshold()

        # --- Шаг 1: проверяем прямой интернет ---
        tlog("⏱ Проверяю интернет...")
        direct = lib.measure_direct_speed(timeout=8)
        if direct is None or direct < direct_thr:
            speed_str = f"{direct} Мбит/с" if direct else "нет ответа"
            tlog(f"⚠ Прямой интернет: {speed_str} (порог: {direct_thr})")
            tlog("Проблемы с интернетом. Проверь подключение к сети.")
            return
        tlog(f"Интернет: {direct} Мбит/с ✓")

        # --- Шаг 2: проверяем текущий сервер ---
        cur = lib.get_current_server()
        if cur and lib.xray_is_running():
            tlog("Проверяю текущий сервер...")
            r = lib.measure_current_speed()
            if r:
                mbps, tt = r
                lib.update_server_meta(cur["_file"], {"SPEED_MBPS": mbps, "LAST_TESTED": lib._now_str()})
                lib.set_last_test_time()
                tlog(f"Текущий: {mbps} Мбит/с (порог: {threshold})")
                if mbps >= threshold:
                    tlog("✓ Скорость в норме")
                    return
            else:
                tlog("Текущий сервер не отвечает")

        # --- Шаг 3: каскадный перебор по всем подпискам ---
        tlog(f"Ищу быстрый сервер (порог: {threshold} Мбит/с)...")

        all_sub_urls = lib.get_subscription_urls()
        cur_source = cur.get("SOURCE", "") if cur else ""

        # Порядок: текущая подписка первой, потом остальные, потом ручные
        ordered = []
        if cur_source and cur_source in all_sub_urls:
            ordered.append(cur_source)
        for u in all_sub_urls:
            if u not in ordered:
                ordered.append(u)
        if lib.MANUAL_SOURCE not in ordered:
            ordered.append(lib.MANUAL_SOURCE)

        found = False
        total_checked = 0

        for sub_url in ordered:
            sub_name = lib.get_subscription_name(sub_url) if sub_url != lib.MANUAL_SOURCE else "Ручные серверы"
            alive = lib.sort_servers_by_speed(lib.get_alive_servers(sub_url))

            if not alive:
                continue

            tlog(f"📡 {sub_name} ({len(alive)} живых)")

            for srv in alive:
                if cur and srv.get("HOST") == cur.get("HOST") and \
                   int(srv.get("PORT", 0)) == int(cur.get("PORT", 0)):
                    continue

                total_checked += 1
                tlog(f"  [{total_checked}] {srv.get('NAME','')[:30]}...")

                ok = lib.quick_proxy_check(srv)
                if not ok:
                    tlog(f"    ✗ не работает")
                    continue

                speed = lib.test_speed_via_server(srv)
                lib.update_server_meta(srv["_file"], {"SPEED_MBPS": speed, "LAST_TESTED": lib._now_str()})

                if speed <= 0:
                    tlog(f"    ✗ скорость 0")
                    continue

                tlog(f"    {speed} Мбит/с")

                if speed >= threshold:
                    if lib.xray_is_running():
                        lib.xray_stop()
                    lib.xray_start_with(srv)
                    lib.invalidate_ip_cache()
                    lib.set_last_test_time()
                    tlog(f"✓ Подключено: {srv.get('NAME','')} ({speed} Мбит/с)")
                    if lib.get_auto_monitor() and not lib.is_monitor_running():
                        lib.start_monitor()
                    found = True
                    break
                else:
                    tlog(f"    ниже порога...")

            if found:
                break

        if not found:
            if total_checked == 0:
                tlog("⚠ Нет живых серверов.")
            else:
                tlog(f"⚠ Проверено {total_checked} серверов — ни один не выше порога ({threshold} Мбит/с)")
            tlog("")
            tlog("Рекомендуется:")
            tlog("  1. Обновить подписки (кнопка ↻)")
            tlog("  2. Запустить полный тест (кнопка 🔍)")
            tlog("  3. Нажать ⚡ Авто")

    lib.cancel_full_test()
    run_bg(do, "speedtest", force=True)
    return redirect("/task")

@app.route("/export_logs")
def export_logs():
    p = lib.export_logs()
    return jsonify({"ok": bool(p), "path": p or ""})

@app.route("/run_update")
def run_update():
    def do():
        import subprocess as sp
        url = "https://github.com/pico-soft/XrayProxy/releases/latest/download/xrayproxy.zip"
        zip_path = str(lib.HOME / "xrayproxy.zip")
        proxy = f"socks5h://127.0.0.1:{lib.SOCKS_PORT}"

        # Способ 1: напрямую
        tlog("Скачиваю напрямую...")
        r = sp.run(["curl", "-fL", "--max-time", "30", "-o", zip_path, url],
                    capture_output=True, text=True)
        ok = r.returncode == 0 and lib.Path(zip_path).exists() and lib.Path(zip_path).stat().st_size > 1000

        # Способ 2: через туннель
        if not ok:
            tlog("Напрямую не удалось. Через туннель...")
            sp.run(["rm", "-f", zip_path])
            r = sp.run(["curl", "-fL", "--max-time", "60", "-x", proxy, "-o", zip_path, url],
                        capture_output=True, text=True)
            ok = r.returncode == 0 and lib.Path(zip_path).exists() and lib.Path(zip_path).stat().st_size > 1000

        # Способ 3: из Downloads
        if not ok:
            tlog("Ищу в Downloads...")
            sp.run(["rm", "-f", zip_path])
            import glob
            candidates = sorted(
                glob.glob(str(lib.HOME / "storage/downloads/xrayproxy*.zip")) +
                glob.glob(str(lib.HOME / "storage/shared/Download/xrayproxy*.zip")),
                key=lambda f: lib.Path(f).stat().st_mtime, reverse=True)
            if candidates:
                import shutil
                shutil.copy2(candidates[0], zip_path)
                tlog(f"Найден: {lib.Path(candidates[0]).name}")
                ok = True

        if not ok:
            tlog("Не удалось скачать. Скачай ZIP через браузер и нажми ⬆ снова.")
            return

        # Распаковка
        tlog("Распаковываю...")
        sp.run(["rm", "-rf", str(lib.HOME / "xrayproxy")])
        r = sp.run(["unzip", "-o", zip_path, "-d", str(lib.HOME)], capture_output=True, text=True)
        if r.returncode != 0:
            tlog("Ошибка распаковки")
            return

        tlog("✓ Скачано и распаковано!")
        import stat
        for f in (lib.HOME / "xrayproxy").glob("*.sh"):
            f.chmod(f.stat().st_mode | stat.S_IEXEC)
        tlog("")
        tlog("Для установки обновления:")
        tlog("  1. Переключись в Termux")
        tlog("  2. Нажми Ctrl+C (остановить Flask)")
        tlog("  3. Скопируй и выполни команду ниже:")
        tlog("UPDATE_CMD:bash ~/xrayproxy/install.sh")
    run_bg(do, "update")
    return redirect("/task")

@app.route("/refresh_alive")
def refresh_alive():
    scope = lib.get_active_scope()
    alive = lib.get_alive_servers(scope)
    data = [{"name": s.get("NAME"), "host": s.get("HOST"), "port": s.get("PORT"),
             "ping": s.get("PING_MS"), "speed": s.get("SPEED_MBPS"),
             "tested": s.get("LAST_TESTED")} for s in lib.sort_servers_by_speed(alive)]
    return jsonify(data)

@app.route("/status")
def status_api():
    """Возвращает актуальный статус для автообновления страницы."""
    running = lib.xray_is_running()
    cur = lib.get_current_server()
    ip = lib.check_external_ip() if running else None
    return jsonify({
        "running": running,
        "server_name": cur.get("NAME", "") if cur else "",
        "server_host": f"{cur['HOST']}:{cur['PORT']}" if cur else "",
        "server_speed": cur.get("SPEED_MBPS", 0) if cur else 0,
        "external_ip": ip or "",
        "last_test": lib.get_last_test_time() or "",
        "last_update": lib.get_last_update_time() or "",
        "monitor_running": lib.is_monitor_running(),
    })

def main():
    lib.init()
    if not lib.xray_installed():
        print("Устанавливаю xray..."); lib.install_xray(progress_cb=print)
    if lib.needs_migration() and lib.get_subscription_urls():
        print("Мигрирую..."); lib.migrate(progress_cb=print)

    # Автоподключение при старте
    if not lib.xray_is_running():
        best = lib.find_fastest_server()
        if best:
            print(f"  Подключаю: {best.get('NAME', '?')}")
            lib.xray_start_with(best)

    # Автозапуск мониторинга
    if lib.get_auto_monitor() and lib.xray_is_running() and not lib.is_monitor_running():
        lib.start_monitor()

    print(f"\n  {lib.APP_NAME} v.{lib.VERSION} — Web\n  http://localhost:8080\n")
    app.run(host="127.0.0.1", port=8080, debug=False, threaded=True)

if __name__ == "__main__":
    main()
