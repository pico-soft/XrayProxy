#!/data/data/com.termux/files/usr/bin/env python3
"""XrayProxy CLI — pico-soft — v.2.23-beta"""

import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import xproxy_lib as lib

class C:
    R="\033[0;31m"; G="\033[0;32m"; Y="\033[1;33m"; B="\033[0;34m"
    C="\033[0;36m"; GR="\033[0;90m"; N="\033[0m"

def c(color, text): return f"{color}{text}{C.N}"
def inp(text):
    print(c(C.C, text))
    try: return input().strip()
    except: return ""
def confirm(text): return inp(f"{text} (y/n)").lower() in ("y","yes","д","да")

def show_status():
    if lib.xray_is_running():
        print(c(C.G, "● Работает"))
        print(f"  SOCKS5 127.0.0.1:{lib.SOCKS_PORT} / HTTP 127.0.0.1:{lib.HTTP_PORT}")
        ip = lib.check_external_ip()
        if ip: print(f"  IP: {c(C.G, ip)}")
    else: print(c(C.R, "○ Не запущен"))
    if lib.is_monitor_running(): print(c(C.G, "  ↻ Мониторинг активен"))
    elif lib.get_auto_monitor(): print(c(C.GR, "  ↻ Мониторинг: ожидает запуска"))
    if lib.is_background_running(): print(c(C.GR, "  ⟳ Фоновая проверка"))

def show_active():
    url = lib.get_active_subscription()
    if url:
        name = lib.get_subscription_name(url)
        alive = len(lib.get_alive_servers(url))
        total = lib.count_servers_in_sub(url)
        print(f"  📡 {c(C.Y, name)} {c(C.GR, f'[{alive}/{total} живых]')}")
    else: print(c(C.GR, "  📡 Все подписки"))
    lt = lib.get_last_test_time()
    lu = lib.get_last_update_time()
    if lt: print(c(C.GR, f"  Тест: {lt}"))
    if lu: print(c(C.GR, f"  Обновление: {lu}"))

def cmd_auto():
    scope = lib.get_active_scope()
    if scope == "ALL" and not lib.get_subscription_urls():
        print(c(C.Y, "Нет подписок.")); return
    if lib.xray_is_running(): lib.xray_stop()
    best = lib.find_fastest_server(scope)
    if best:
        sv = best.get("SPEED_MBPS", 0)
        print(c(C.G, f"Найден: {best['NAME']} ({sv} Мбит/с)"))
        if lib.xray_start_with(best):
            ip = lib.check_external_ip()
            print(c(C.G, "━"*39))
            if ip: print(c(C.G, f"  ✓ {best['NAME']}\n  IP: {ip}"))
            print(c(C.G, "━"*39))
            if lib.get_auto_monitor() and not lib.is_monitor_running():
                lib.start_monitor()
                print(c(C.GR, "  ↻ Мониторинг запущен"))
            return
    # Тест свежий но серверов нет — обновить подписки
    if lib.is_test_fresh(60):
        print(c(C.Y, "Тест свежий, но нет живых. Обновляю подписки..."))
        cmd_update()
    else:
        print(c(C.Y, "Тест устарел. Тестирую..."))

    servers = lib.get_servers_by_scope(scope)
    if not servers: print(c(C.R, "Нет серверов")); return

    def progress(msg):
        if "✗" in msg or "нет" in msg or "скорость 0" in msg:
            print(f"  {c(C.R, msg)}")
        elif "⚡" in msg:
            print(f"  {c(C.G, msg)}")
        elif "✓" in msg:
            print(f"  {c(C.G, msg)}")
        else:
            print(f"  {msg}")

    result = lib.run_full_test_with_early_connect(servers, progress_cb=progress)

    best = lib.find_fastest_server(scope)
    if best:
        ip = lib.check_external_ip()
        print(c(C.G, "━"*39))
        if ip: print(c(C.G, f"  ✓ {best['NAME']}\n  IP: {ip}"))
        print(c(C.G, "━"*39))
        if lib.get_auto_monitor() and not lib.is_monitor_running():
            lib.start_monitor()
            print(c(C.GR, "  ↻ Мониторинг запущен"))
    elif not result:
        print(c(C.R, "Нет доступных серверов"))

def cmd_next():
    cur = lib.get_current_server()
    if not cur: print(c(C.Y, "Сначала подключись.")); return
    nxt = lib.find_next_server(cur.get("SOURCE", lib.get_active_scope()))
    if not nxt: print(c(C.Y, "Нет серверов.")); return
    print(f"→ {c(C.G, nxt['NAME'])} ({nxt.get('SPEED_MBPS',0)} Мбит/с)")
    if lib.xray_is_running(): lib.xray_stop()
    if lib.xray_start_with(nxt):
        ip = lib.check_external_ip()
        if ip: print(c(C.G, f"✓ IP: {ip}"))

def cmd_select():
    scope = lib.get_active_scope()
    servers = lib.sort_servers_by_speed(lib.get_servers_by_scope(scope))
    if not servers: print(c(C.Y, "Нет серверов.")); return
    for i, m in enumerate(servers, 1):
        p = m.get("PING_MS", -1); s = m.get("SPEED_MBPS", -1)
        ps = c(C.G, f"{p:>4}мс") if p>0 else c(C.GR, "  — ")
        ss = c(C.G, f"{s:>5.1f}Мб") if s>0 else c(C.GR, "  —  ")
        print(f" {c(C.G, f'{i:>2}.')} {m.get('NAME','')[:38]:<40} {ps} {ss}")
    ch = inp("Сервер (0=отмена):")
    if ch.isdigit() and 0<int(ch)<=len(servers):
        sel = servers[int(ch)-1]; print(c(C.G, f"→ {sel['NAME']}"))
        if lib.xray_is_running(): lib.xray_stop()
        if lib.xray_start_with(sel):
            ip = lib.check_external_ip()
            if ip: print(c(C.G, f"IP: {ip}"))

def cmd_update():
    scope = lib.get_active_scope()
    urls = lib.get_subscription_urls() if scope == "ALL" else [scope]
    if not urls: print(c(C.Y, "Нет подписок.")); return
    for url in urls:
        print(c(C.C, f"Обновляю: {lib.get_subscription_name(url)}"))
        ok, added, skip = lib.update_single_subscription(url, progress_cb=lambda m: print(f"  {m}"))
        if ok: print(c(C.G, f"  +{added}")); (print(c(C.GR, f"  -{skip}")) if skip else None)
        else: print(c(C.R, "  Ошибка"))

def cmd_tests(scope=None):
    if scope is None: scope = lib.get_active_scope()
    servers = lib.get_servers_by_scope(scope)
    if not servers: print(c(C.Y, "Нет серверов.")); return

    def progress(msg):
        # Цветной вывод
        if "✗" in msg or "нет" in msg or "скорость 0" in msg:
            print(f"  {c(C.R, msg)}")
        elif "⚡" in msg or "✓ Подключаю" in msg:
            print(f"  {c(C.G, msg)}")
        elif "✓" in msg:
            print(f"  {c(C.G, msg)}")
        else:
            print(f"  {msg}")

    result = lib.run_full_test_with_early_connect(servers, progress_cb=progress)
    if result:
        ip = lib.check_external_ip()
        if ip:
            print(c(C.G, f"  IP: {ip}"))

def cmd_check():
    if not lib.xray_is_running(): print(c(C.R, "Не запущен.")); return
    cur = lib.get_current_server()
    if cur:
        print(c(C.C, "Сервер:"))
        print(f"  {c(C.G, cur.get('NAME','?'))}")
        print(f"  {c(C.B, str(cur['HOST'])+':'+str(cur['PORT']))}")
        print(f"  vless ({cur.get('SECURITY','none')} / {cur.get('TYPE','tcp')})")
        lt = cur.get("LAST_TESTED")
        if lt: print(c(C.GR, f"  Проверен: {lt}"))
    ip = lib.check_external_ip()
    if not ip: print(c(C.R, "✗ Нет связи")); return
    print(c(C.G, f"✓ IP: {ip}"))
    print(c(C.C, "Скорость..."))
    r = lib.measure_current_speed()
    if r:
        mbps, tt = r
        print(c(C.G, f"  {mbps} Мбит/с ({tt:.1f}с)"))
        if cur: lib.update_server_meta(cur["_file"], {"SPEED_MBPS": mbps, "LAST_TESTED": lib._now_str()})
        threshold = lib.get_min_speed_threshold()
        if mbps < threshold:
            print(c(C.Y, f"  ⚠ Ниже порога ({threshold} Мбит/с). Переключаю..."))
            _auto_switch_next()
    else:
        print(c(C.R, "  Нет ответа. Переключаю..."))
        _auto_switch_next()

def _auto_switch_next():
    """Переключается на следующий рабочий сервер."""
    cur = lib.get_current_server()
    scope = cur.get("SOURCE", lib.get_active_scope()) if cur else lib.get_active_scope()
    nxt = lib.find_next_server(scope)
    if not nxt:
        print(c(C.R, "  Нет доступных серверов для переключения."))
        return
    print(f"  → {c(C.G, nxt['NAME'])} ({nxt.get('SPEED_MBPS', 0)} Мбит/с)")
    if lib.xray_is_running(): lib.xray_stop()
    if lib.xray_start_with(nxt):
        ip = lib.check_external_ip()
        if ip: print(c(C.G, f"  ✓ IP: {ip}"))
    else:
        print(c(C.R, "  Не удалось запустить."))

def cmd_add_sub():
    url = inp("URL подписки:")
    if not url: return
    name = lib._name_from_url(url)
    print(f"  Имя: {c(C.G, name)}")
    custom = inp("Своё имя? (Enter=оставить):")
    if custom: name = custom
    lib.add_subscription(url, name)
    print(c(C.G, "Добавлена."))
    if confirm("Обновить и протестировать?"):
        ok, added, _ = lib.update_single_subscription(url, progress_cb=lambda m: print(f"  {m}"))
        if ok:
            print(c(C.G, f"Серверов: {added}"))
            if confirm("Тест?"): cmd_tests(url)
    else:
        ok, added, _ = lib.update_single_subscription(url, progress_cb=lambda m: print(f"  {m}"))
        if ok: print(c(C.G, f"Серверов: {added}"))

def cmd_add_server():
    print(c(C.C, "Вставляй ссылки vless:// или trojan:// по одной."))
    print(c(C.GR, "Пустая строка — завершить."))
    count = 0
    while True:
        uri = inp(f"[{count+1}] Ссылка:")
        if not uri:
            break
        name = lib.add_server_manually(uri)
        if name:
            print(c(C.G, f"  + {name}"))
            count += 1
        else:
            print(c(C.R, "  Не распознана (поддержка: vless://, trojan://)"))
    if count > 0:
        print(c(C.G, f"Добавлено: {count}"))
        if confirm("Протестировать добавленные?"):
            manual = lib.get_active_servers(lib.MANUAL_SOURCE)
            untested = [s for s in manual if s.get("PING_MS", -1) < 0]
            if untested:
                cmd_tests_servers(untested)

def cmd_import_file():
    path = inp("Путь к файлу (txt, по ссылке на строку):")
    if not path:
        return
    added, skipped, errors = lib.import_servers_from_file(path)
    print(c(C.G, f"Добавлено: {added}"))
    if skipped: print(c(C.GR, f"Исключено (стоп-лист): {skipped}"))
    if errors: print(c(C.R, f"Не распознано: {errors}"))
    if added > 0 and confirm("Протестировать?"):
        manual = lib.get_active_servers(lib.MANUAL_SOURCE)
        untested = [s for s in manual if s.get("PING_MS", -1) < 0]
        if untested:
            cmd_tests_servers(untested)

def cmd_tests_servers(servers):
    """Тестирует конкретный список серверов."""
    timeout = lib.get_proxy_check_timeout()
    print(c(C.C, f"\nЭтап 1/3: пинг ({len(servers)})..."))
    alive = lib.run_ping_tests(servers, lambda i,t,n,p: print(f"  [{i}/{t}] {n[:40]:<42} {c(C.G,str(p)+'мс') if p>0 else c(C.R,'нет')}"))
    print(c(C.G, f"Откликнулись: {len(alive)}/{len(servers)}"))
    if not alive: return
    print(c(C.C, f"\nЭтап 2/3: прокси ({len(alive)}, {timeout}с)..."))
    working = lib.run_proxy_checks(alive, lambda i,t,n,ok: print(f"  [{i}/{t}] {n[:40]:<42} {c(C.G,'✓') if ok else c(C.R,'✗')}"))
    print(c(C.G, f"Рабочих: {len(working)}/{len(alive)}"))
    if not working: return
    print(c(C.C, f"\nЭтап 3/3: скорость ({len(working)})..."))
    lib.run_speed_tests(working, lambda i,t,n,s: print(f"  [{i}/{t}] {n[:40]:<42} {c(C.G,str(s)+'Мб/с') if s>0 else c(C.R,'нет')}"))
    print(c(C.G, "Готово."))

def _sub_status_dot(s) -> str:
    ok = s.get("last_update_ok")
    if ok is True:  return c(C.G, "●")
    if ok is False: return c(C.R, "●")
    return c(C.GR, "○")

def cmd_list_subs():
    subs = lib.get_subscriptions()
    if not subs: print(c(C.Y, "Пусто.")); return
    active = lib.get_active_subscription()
    for i, s in enumerate(subs, 1):
        cnt = lib.count_servers_in_sub(s["url"])
        alive = len(lib.get_alive_servers(s["url"]))
        mark = " ●" if s["url"] == active else ""
        print(f"  {c(C.G, f'{i:>2}.')} {_sub_status_dot(s)} {s['name']} {c(C.GR, f'[{alive}/{cnt}]')}{c(C.Y, mark)}")

def cmd_del_sub():
    cmd_list_subs()
    ch = inp("Номер (0=отмена):")
    if ch.isdigit() and int(ch)>0:
        subs = lib.get_subscriptions(); idx = int(ch)-1
        if 0<=idx<len(subs): lib.remove_subscription(subs[idx]["url"]); print(c(C.G, "Удалена."))

def cmd_choose_sub():
    subs = lib.get_subscriptions()
    if not subs: print(c(C.Y, "Пусто.")); return
    active = lib.get_active_subscription()
    print(f"  {c(C.G, '0.')} Все подписки")
    for i, s in enumerate(subs, 1):
        mark = " ●" if s["url"] == active else ""
        print(f"  {c(C.G, f'{i:>2}.')} {_sub_status_dot(s)} {s['name']}{c(C.Y, mark)}")
    ch = inp(">")
    if ch == "0": lib.set_active_subscription(None); print(c(C.G, "Все."))
    elif ch.isdigit() and 0<int(ch)<=len(subs):
        lib.set_active_subscription(subs[int(ch)-1]["url"])
        print(c(C.G, f"→ {subs[int(ch)-1]['name']}"))

def cmd_blacklist():
    while True:
        bl = lib.get_blacklist()
        if bl:
            for i, w in enumerate(bl, 1): print(f"  {c(C.G, f'{i}.')} {w}")
        else: print(c(C.Y, "Пуст."))
        act = inp("a=добавить d=удалить 0=назад:").lower()
        if act=="a":
            w = inp("Слово:")
            if lib.add_to_blacklist(w): print(c(C.G, f"+{w}"))
        elif act=="d":
            ch = inp("Номер:")
            if ch.isdigit() and 0<int(ch)<=len(bl): lib.remove_from_blacklist(bl[int(ch)-1]); print(c(C.G, "OK"))
        elif act=="0": return

def cmd_settings():
    t = lib.get_proxy_check_timeout()
    bg = lib.is_background_running()
    am = lib.get_auto_monitor()
    mi = lib.get_monitor_interval()
    dt = lib.get_direct_speed_threshold()
    tt = lib.get_tunnel_speed_threshold()
    mon = lib.is_monitor_running()

    print(c(C.C, "Настройки:"))
    print(f"  1. Таймаут прокси: {c(C.G, f'{t}с')}")
    print(f"  2. Фоновая проверка (1ч): {c(C.G, 'вкл') if bg else c(C.R, 'выкл')}")
    print(c(C.C, "Автомониторинг:"))
    print(f"  3. Автосоединение: {c(C.G, 'да') if am else c(C.R, 'нет')}")
    print(f"  4. Интервал проверки: {c(C.G, f'{mi}с ({mi//60} мин)')}")
    print(f"  5. Порог прямой скорости: {c(C.G, f'{dt} Мбит/с')}")
    print(f"  6. Порог скорости туннеля: {c(C.G, f'{tt} Мбит/с')}")
    print(f"  7. Мониторинг сейчас: {c(C.G, 'вкл') if mon else c(C.R, 'выкл')}")
    print(f"  8. Лог мониторинга")
    print(f"  0. Назад")

    ch = inp(">")
    if ch=="1":
        v = inp(f"Таймаут ({t}):")
        if v.isdigit() and int(v)>0: lib.set_proxy_check_timeout(int(v)); print(c(C.G, f"→ {v}с"))
    elif ch=="2":
        if bg: lib.stop_background_check(); print(c(C.G, "Выкл."))
        else: lib.start_background_check(); print(c(C.G, "Вкл."))
    elif ch=="3":
        lib.set_auto_monitor(not am)
        print(c(C.G, f"Автосоединение: {'да' if not am else 'нет'}"))
        if not am and not lib.is_monitor_running() and lib.xray_is_running():
            lib.start_monitor()
            print(c(C.GR, "Мониторинг запущен"))
        elif am and lib.is_monitor_running():
            lib.stop_monitor()
            print(c(C.GR, "Мониторинг остановлен"))
    elif ch=="4":
        v = inp(f"Интервал в секундах ({mi}):")
        if v.isdigit() and int(v)>=60: lib.set_monitor_interval(int(v)); print(c(C.G, f"→ {v}с"))
        else: print(c(C.Y, "Минимум 60 секунд"))
    elif ch=="5":
        v = inp(f"Порог прямой скорости Мбит/с ({dt}):")
        try:
            fv = float(v)
            if fv > 0: lib.set_direct_speed_threshold(fv); print(c(C.G, f"→ {fv} Мбит/с"))
        except: print(c(C.R, "Неверное значение"))
    elif ch=="6":
        v = inp(f"Порог скорости туннеля Мбит/с ({tt}):")
        try:
            fv = float(v)
            if fv > 0: lib.set_tunnel_speed_threshold(fv); print(c(C.G, f"→ {fv} Мбит/с"))
        except: print(c(C.R, "Неверное значение"))
    elif ch=="7":
        if mon: lib.stop_monitor(); print(c(C.G, "Остановлен."))
        else: lib.start_monitor(); print(c(C.G, "Запущен."))
    elif ch=="8":
        logs = lib.get_monitor_log()
        if logs:
            print(c(C.C, f"Лог мониторинга (последние {len(logs)} записей):"))
            for l in logs[-20:]:
                if "✓" in l: print(c(C.G, f"  {l}"))
                elif "⚠" in l or "ниже" in l or "Нет" in l: print(c(C.Y, f"  {l}"))
                else: print(f"  {l}")
        else: print(c(C.GR, "Лог пуст."))

def cmd_export():
    print(c(C.C, "Собираю..."))
    p = lib.export_logs()
    if p: print(c(C.G, f"✓ {p}"))
    else: print(c(C.R, "Ошибка"))

def cmd_start():
    cur = lib.get_current_server()
    if not cur: print(c(C.R, "Выбери сервер.")); return
    if lib.xray_start_with(cur):
        print(c(C.G, f"▶ {cur.get('NAME','?')}"))
        if lib.get_auto_monitor() and not lib.is_monitor_running():
            lib.start_monitor()
            print(c(C.GR, "  ↻ Мониторинг запущен"))

def cmd_stop():
    if lib.xray_is_running(): lib.xray_stop(); print(c(C.G, "Остановлен."))
    else: print(c(C.Y, "Не запущен."))
    if lib.is_monitor_running():
        lib.stop_monitor(); print(c(C.GR, "Мониторинг остановлен."))

def show_menu():
    print(); print(c(C.C, "━"*36))
    print(c(C.C, f"  {lib.APP_NAME} v.{lib.VERSION}"))
    show_active(); print(c(C.C, "━"*36))
    show_status(); print()
    print(f"  {c(C.G,'1.')} {c(C.Y,'⚡ Автоподключение')}")
    print(f"  {c(C.G,'2.')} {c(C.Y,'→ Следующий сервер')}")
    print(f"  {c(C.G,'3.')} Выбрать сервер")
    print(f"  {c(C.G,'4.')} Обновить подписки")
    print(f"  {c(C.G,'5.')} Тест серверов")
    print(f"  {c(C.G,'6.')} ▶ Запустить / {c(C.G,'7.')} ■ Остановить")
    print(f"  {c(C.G,'8.')} Проверить соединение")
    print(f"  {c(C.G,'9.')} Добавить подписку")
    print(f"  {c(C.G,'a.')} Добавить серверы (ссылки)")
    print(f"  {c(C.G,'f.')} Импорт из файла (.txt)")
    print(f"  {c(C.G,'s.')} Выбрать подписку")
    print(f"  {c(C.G,'l.')} Подписки / {c(C.G,'d.')} Удалить")
    print(f"  {c(C.G,'b.')} Стоп-лист / {c(C.G,'c.')} Настройки")
    print(f"  {c(C.G,'x.')} Экспорт логов / {c(C.G,'u.')} Обновить xray")
    print(f"  {c(C.G,'0.')} Выход"); print()

def main():
    os.system("clear 2>/dev/null")
    print(c(C.C, "━"*36)); print(c(C.C, f"  {lib.APP_NAME} v.{lib.VERSION}")); print(c(C.C, "━"*36)); print()
    lib.init()
    if not lib.xray_installed():
        print(c(C.Y, "Устанавливаю xray..."))
        if not lib.install_xray(progress_cb=lambda m: print(f"  {m}")): print(c(C.R, "Ошибка.")); return
    if lib.needs_migration() and lib.get_subscription_urls():
        print(c(C.Y, "Мигрирую...")); lib.migrate(progress_cb=lambda m: print(f"  {m}"))

    # Запускаем мониторинг если auto_monitor=True и xray уже работает
    if lib.get_auto_monitor() and lib.xray_is_running() and not lib.is_monitor_running():
        lib.start_monitor()

    h = {"1":cmd_auto,"2":cmd_next,"3":cmd_select,"4":cmd_update,"5":lambda:cmd_tests(),
         "6":cmd_start,"7":cmd_stop,"8":cmd_check,"9":cmd_add_sub,"a":cmd_add_server,
         "f":cmd_import_file,"s":cmd_choose_sub,
         "l":cmd_list_subs,"d":cmd_del_sub,"b":cmd_blacklist,"c":cmd_settings,
         "x":cmd_export,"u":lambda:lib.install_xray(progress_cb=lambda m: print(f"  {m}"), force=True)}
    names = {"1":"auto","2":"next","3":"select","4":"update","5":"test","6":"start","7":"stop",
             "8":"check","9":"add_sub","a":"add_server","f":"import_file","s":"choose_sub",
             "l":"list","d":"del","b":"blacklist","c":"settings","x":"export","u":"update_xray"}

    while True:
        show_menu()
        try: opt = input(c(C.C, "> ")).strip().lower()
        except: break
        if opt == "0":
            lib.log_action("menu", "exit")
            if lib.is_monitor_running(): lib.stop_monitor()
            print(c(C.G, "Пока!")); break
        handler = h.get(opt)
        if handler:
            lib.log_action("menu", names.get(opt, opt))
            try: handler()
            except KeyboardInterrupt: print(c(C.Y, "\nПрервано")); lib.log("interrupted", level="warn")
            except Exception as e: print(c(C.R, f"Ошибка: {e}")); lib.log(f"Error: {e}", level="error")
        else: print(c(C.R, "?"))

if __name__ == "__main__":
    main()
