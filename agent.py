#!/usr/bin/env python3
import socket, platform, time, uuid, os, sys, glob, json, subprocess, shutil
import urllib.request, urllib.error

try:
    import psutil
except ImportError:
    psutil = None

def http_get(url, timeout=3):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "LabMonitoringAgent/1.0"
        },
        method="GET"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status

def http_post_json(url, payload, timeout=5):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "LabMonitoringAgent/1.0"
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
        try:
            return resp.status, json.loads(raw)
        except Exception:
            return resp.status, {}

def execute_power_command(cmd):
    if cmd not in ("shutdown", "restart"):
        return
    print(f"[!] Menerima perintah '{cmd}' dari server...")
    try:
        if platform.system() == "Windows":
            flag = "/s" if cmd == "shutdown" else "/r"
            msg = "Komputer akan dimatikan oleh Operator Lab dalam 10 detik." if cmd == "shutdown" else "Komputer akan di-restart oleh Operator Lab dalam 10 detik."
            subprocess.Popen(["shutdown", flag, "/t", "10", "/c", msg])
        else:
            action = "poweroff" if cmd == "shutdown" else "reboot"
            subprocess.Popen(["systemctl", action])
    except Exception:
        pass

def get_config_path():
    local_cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(local_cfg) and os.access(local_cfg, os.W_OK):
        return local_cfg

    if platform.system() == "Windows":
        base_dir = os.environ.get("APPDATA") or os.path.expanduser("~")
        cfg_dir = os.path.join(base_dir, "LabMonitoring")
    else:
        if os.geteuid() == 0 and not os.environ.get("SUDO_USER"):
            cfg_dir = "/etc/lab_monitoring"
        else:
            sudo_user = os.environ.get("SUDO_USER")
            if sudo_user:
                user_home = os.path.expanduser(f"~{sudo_user}")
            else:
                user_home = os.path.expanduser("~")
            cfg_dir = os.path.join(user_home, ".config", "lab_monitoring")

    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, "config.json")

def get_installed_exe_path():
    # Jika dijalankan sebagai .exe di Windows (misal dari Flashdisk), salin otomatis ke %APPDATA%\LabMonitoring
    if platform.system() == "Windows" and getattr(sys, "frozen", False):
        try:
            base_dir = os.environ.get("APPDATA") or os.path.expanduser("~")
            install_dir = os.path.join(base_dir, "LabMonitoring")
            os.makedirs(install_dir, exist_ok=True)
            target_exe = os.path.join(install_dir, "LabMonitoringAgent.exe")
            current_exe = os.path.abspath(sys.executable)
            if os.path.normcase(current_exe) != os.path.normcase(target_exe):
                shutil.copy2(current_exe, target_exe)
            return target_exe
        except Exception:
            return sys.executable
    return sys.executable

def normalize_server_url(raw_input):
    val = (raw_input or "").strip()
    if not val:
        val = "localhost:5000"
    if not val.startswith(("http://", "https://")):
        val = "http://" + val
    val = val.rstrip("/")
    if not val.endswith("/api/monitoring"):
        val = val + "/api/monitoring"
    return val

def extract_host_display(server_url):
    val = (server_url or "http://localhost:5000/api/monitoring").strip()
    if val.endswith("/api/monitoring"):
        val = val[:-len("/api/monitoring")]
    for prefix in ("http://", "https://"):
        if val.startswith(prefix):
            val = val[len(prefix):]
    return val.rstrip("/")

def load_config():
    cfg_path = get_config_path()
    for path in [cfg_path, "/etc/lab_monitoring/config.json"]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    if data.get("server_url"):
                        return data
            except Exception:
                pass
    return None

def save_config(raw_host):
    cfg_path = get_config_path()
    server_url = normalize_server_url(raw_host)
    data = {
        "server_host": extract_host_display(server_url),
        "server_url": server_url
    }
    with open(cfg_path, "w") as f:
        json.dump(data, f, indent=2)
    sudo_uid = os.environ.get("SUDO_UID")
    sudo_gid = os.environ.get("SUDO_GID")
    if sudo_uid and sudo_gid:
        try:
            os.chown(cfg_path, int(sudo_uid), int(sudo_gid))
        except Exception:
            pass
    return data

def setup_autostart():
    try:
        if getattr(sys, "frozen", False):
            target_exe = get_installed_exe_path()
            exec_cmd = f'"{target_exe}" --background'
        else:
            script_path = os.path.abspath(__file__)
            exec_cmd = f'"{sys.executable}" "{script_path}" --background'

        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "LabMonitoringAgent", 0, winreg.REG_SZ, exec_cmd)
            winreg.CloseKey(key)
        else:
            autostart_dir = os.path.expanduser("~/.config/autostart")
            os.makedirs(autostart_dir, exist_ok=True)
            desktop_file = os.path.join(autostart_dir, "lab-monitoring-agent.desktop")
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Lab Monitoring Agent\n"
                f"Exec={exec_cmd}\n"
                "Hidden=false\n"
                "NoDisplay=false\n"
                "X-GNOME-Autostart-enabled=true\n"
            )
            with open(desktop_file, "w") as f:
                f.write(content)
    except Exception:
        pass

def ensure_background_running():
    my_pid = str(os.getpid())
    try:
        if platform.system() == "Linux":
            for pid_dir in glob.glob("/proc/[0-9]*"):
                pid = os.path.basename(pid_dir)
                if pid == my_pid:
                    continue
                try:
                    with open(os.path.join(pid_dir, "cmdline"), "rb") as f:
                        cmdline = f.read().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
                    if ("agent.py" in cmdline or "lab-monitoring-agent" in cmdline) and "--config" not in cmdline:
                        return
                except Exception:
                    pass
        elif psutil:
            for proc in psutil.process_iter(['pid', 'cmdline']):
                if str(proc.info['pid']) == my_pid:
                    continue
                cmdline = " ".join(proc.info.get('cmdline') or [])
                if ("agent.py" in cmdline or "LabMonitoringAgent" in cmdline) and "--config" not in cmdline:
                    return
    except Exception:
        pass

    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        if getattr(sys, "frozen", False):
            target_exe = get_installed_exe_path()
            cmd = [target_exe, "--background"]
        else:
            cmd = [sys.executable, os.path.abspath(__file__), "--background"]
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=True
        )
    except Exception:
        pass

def show_config_dialog(default_host="localhost:5000"):
    try:
        import tkinter as tk
        from tkinter import messagebox

        result = {"saved": None}
        root = tk.Tk()
        root.title("Pengaturan Agent Monitoring")
        root.geometry("400x215")
        root.resizable(False, False)

        frame = tk.Frame(root, padx=16, pady=14)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Alamat Server Monitoring (IP:Port atau Domain):", anchor="w", font=("Sans", 10, "bold")).pack(fill="x")
        tk.Label(frame, text="Contoh: 172.17.80.171:5000 atau https://domain-anda.com", anchor="w", fg="#666666", font=("Sans", 8)).pack(fill="x", pady=(0, 6))

        entry = tk.Entry(frame, font=("Sans", 10))
        entry.insert(0, default_host)
        entry.pack(fill="x", ipady=4, pady=(0, 8))

        autostart_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frame, text="Jalankan otomatis saat komputer menyala", variable=autostart_var, font=("Sans", 9)).pack(anchor="w", pady=(0, 10))

        status_lbl = tk.Label(frame, text="", font=("Sans", 8))
        status_lbl.pack(fill="x")

        def on_test():
            url = normalize_server_url(entry.get())
            try:
                code = http_get(url, timeout=3)
                if code == 200:
                    status_lbl.config(text="Koneksi berhasil ke server.", fg="green")
                else:
                    status_lbl.config(text=f"Server merespons (HTTP {code}).", fg="orange")
            except Exception:
                status_lbl.config(text="Server belum dapat dihubungi.", fg="red")

        def on_save():
            val = entry.get().strip()
            if not val:
                messagebox.showwarning("Input Kosong", "Masukkan alamat server terlebih dahulu.")
                return
            cfg = save_config(val)
            if autostart_var.get():
                setup_autostart()
            result["saved"] = cfg
            root.destroy()

        btn_frame = tk.Frame(frame)
        btn_frame.pack(fill="x", pady=(4, 0))
        tk.Button(btn_frame, text="Cek Koneksi", command=on_test, width=14).pack(side="left")
        tk.Button(btn_frame, text="Simpan & Jalankan", command=on_save, bg="#2563eb", fg="white", width=18).pack(side="right")

        root.mainloop()
        return result["saved"]
    except Exception:
        pass

    if platform.system() == "Linux" and os.environ.get("DISPLAY") and shutil.which("zenity"):
        try:
            res = subprocess.run(
                [
                    "zenity", "--entry",
                    "--title=Pengaturan Agent Monitoring",
                    "--text=Masukkan Alamat Server Monitoring (contoh: 172.17.80.171:5000 atau https://domain.com):",
                    f"--entry-text={default_host}",
                    "--width=400"
                ],
                capture_output=True,
                text=True
            )
            if res.returncode == 0 and res.stdout.strip():
                cfg = save_config(res.stdout.strip())
                setup_autostart()
                return cfg
        except Exception:
            pass

    try:
        print("=== Pengaturan Agent Monitoring ===")
        inp = input(f"Masukkan Alamat Server (IP:Port atau Domain) [{default_host}]: ").strip()
        if not inp:
            inp = default_host
        cfg = save_config(inp)
        setup_autostart()
        print(f"Konfigurasi disimpan ke: {get_config_path()}")
        return cfg
    except EOFError:
        return save_config(default_host)

def get_mac_address():
    mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
    return ":".join([mac[e:e+2] for e in range(0, 11, 2)]).upper()

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def check_network():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False

def get_cpu_percent():
    if psutil:
        try:
            return psutil.cpu_percent(interval=1)
        except Exception:
            pass
    try:
        def read_cpu_times():
            with open("/proc/stat", "r") as f:
                parts = [int(x) for x in f.readline().split()[1:]]
            idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
            total = sum(parts)
            return idle, total

        idle1, total1 = read_cpu_times()
        time.sleep(1)
        idle2, total2 = read_cpu_times()
        total_diff = total2 - total1
        idle_diff = idle2 - idle1
        if total_diff <= 0:
            return 0.0
        return round(100.0 * (total_diff - idle_diff) / total_diff, 1)
    except Exception:
        return 0.0

def get_ram_percent():
    if psutil:
        try:
            return psutil.virtual_memory().percent
        except Exception:
            pass
    try:
        mem_total = 0
        mem_avail = 0
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_avail = int(line.split()[1])
        if mem_total > 0:
            return round(100.0 * (mem_total - mem_avail) / mem_total, 1)
    except Exception:
        pass
    return 0.0

def get_storage_free_gb():
    root_path = os.path.abspath(os.sep)
    if psutil:
        try:
            return round(psutil.disk_usage(root_path).free / (1024**3), 2)
        except Exception:
            pass
    try:
        st = os.statvfs(root_path)
        return round((st.f_bavail * st.f_frsize) / (1024**3), 2)
    except Exception:
        return 0.0

def get_uptime_str():
    try:
        if psutil:
            uptime_seconds = int(time.time() - psutil.boot_time())
        else:
            with open("/proc/uptime", "r") as f:
                uptime_seconds = int(float(f.read().split()[0]))
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        if days > 0:
            return f"{days}h {hours}j {minutes}m"
        return f"{hours}j {minutes}m"
    except Exception:
        return "-"

def get_logged_in_user():
    if psutil:
        try:
            users = psutil.users()
            if users:
                unique_users = sorted(list({u.name for u in users if u.name}))
                if unique_users:
                    return ", ".join(unique_users)
        except Exception:
            pass
    try:
        res = subprocess.run(["who"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            names = sorted(list({line.split()[0] for line in res.stdout.strip().splitlines() if line.split()}))
            if names:
                return ", ".join(names)
    except Exception:
        pass
    return os.environ.get("SUDO_USER") or os.environ.get("USER") or os.environ.get("USERNAME") or "Unknown"

def get_top_process():
    ignore_names = {"System Idle Process", "System", "Registry", "MemCompression"}
    if psutil:
        try:
            top_proc = None
            top_mem = -1.0
            for proc in psutil.process_iter(['name', 'memory_percent']):
                info = proc.info
                name = info.get('name') or ''
                mem = info.get('memory_percent') or 0.0
                if name and name not in ignore_names and mem > top_mem:
                    top_mem = mem
                    top_proc = name
            if top_proc:
                return f"{top_proc} ({top_mem:.1f}%)"
        except Exception:
            pass
    try:
        res = subprocess.run(
            ["ps", "-eo", "comm,%mem", "--sort=-%mem"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            if len(lines) > 1:
                parts = lines[1].strip().rsplit(None, 1)
                if len(parts) == 2:
                    return f"{parts[0]} ({parts[1]}%)"
    except Exception:
        pass
    return "-"

def detect_linux_hardware():
    peripherals = {
        "mouse": False,
        "keyboard": False,
        "audio": False,
        "monitor": False
    }
    usb_drives = []

    is_laptop = False
    try:
        with open("/sys/class/dmi/id/chassis_type", "r") as f:
            if f.read().strip() in {"8", "9", "10", "14"}:
                is_laptop = True
    except Exception:
        pass

    try:
        with open("/proc/bus/input/devices", "r") as f:
            blocks = f.read().strip().split("\n\n")

        port_devices = {}
        for block in blocks:
            lines = block.splitlines()
            name = ""
            phys = ""
            bus = ""
            handlers = ""
            has_rel = False
            ev_val = ""
            for line in lines:
                if line.startswith("I:"):
                    for part in line.split():
                        if part.startswith("Bus="):
                            bus = part.split("=")[1]
                elif line.startswith("N: Name="):
                    name = line.split("=", 1)[1].strip('"')
                elif line.startswith("P: Phys="):
                    phys = line.split("=", 1)[1].strip()
                elif line.startswith("H: Handlers="):
                    handlers = line.split("=", 1)[1].strip()
                elif line.startswith("B: REL="):
                    has_rel = True
                elif line.startswith("B: EV="):
                    ev_val = line.split("=", 1)[1].strip()

            handler_list = handlers.split()
            name_lower = name.lower()
            port_key = phys.split("/")[0] if phys else name

            if port_key not in port_devices:
                port_devices[port_key] = {"is_kbd": False, "is_mouse": False}

            if "kbd" in handler_list and ("sysrq" in handler_list or "leds" in handler_list or ev_val == "120013"):
                if bus in {"0003", "0005"} or "usb" in phys.lower():
                    port_devices[port_key]["is_kbd"] = True
                elif is_laptop and "isa0060" in phys.lower():
                    port_devices[port_key]["is_kbd"] = True

            if any(h.startswith("mouse") for h in handler_list) and has_rel:
                if "touch" not in name_lower and "stylus" not in name_lower:
                    port_devices[port_key]["is_mouse"] = True

        for port_key, flags in port_devices.items():
            if flags["is_kbd"]:
                peripherals["keyboard"] = True
            if flags["is_mouse"] and not flags["is_kbd"]:
                peripherals["mouse"] = True
    except Exception:
        pass

    try:
        if os.path.exists("/proc/asound/cards"):
            with open("/proc/asound/cards", "r") as f:
                content = f.read().strip()
                if content and "no soundcards" not in content.lower():
                    peripherals["audio"] = True
    except Exception:
        pass

    try:
        status_files = glob.glob("/sys/class/drm/*/status")
        if status_files:
            for sf in status_files:
                with open(sf, "r") as f:
                    if f.read().strip() == "connected":
                        peripherals["monitor"] = True
                        break
        else:
            peripherals["monitor"] = True
    except Exception:
        peripherals["monitor"] = True

    try:
        for block_path in sorted(glob.glob("/sys/block/*")):
            dev_name = os.path.basename(block_path)
            if dev_name.startswith(("loop", "ram", "zram", "sr", "dm-")):
                continue
            real_path = os.path.realpath(block_path)
            removable = "0"
            rem_file = os.path.join(block_path, "removable")
            if os.path.exists(rem_file):
                with open(rem_file, "r") as f:
                    removable = f.read().strip()

            if "/usb" in real_path or removable == "1":
                size_file = os.path.join(block_path, "size")
                sectors = 0
                if os.path.exists(size_file):
                    with open(size_file, "r") as f:
                        sectors = int(f.read().strip() or 0)
                if sectors <= 0:
                    continue
                size_gb = round((sectors * 512) / (1024 ** 3), 1)
                vendor = ""
                model = ""
                vendor_file = os.path.join(block_path, "device/vendor")
                model_file = os.path.join(block_path, "device/model")
                if os.path.exists(vendor_file):
                    with open(vendor_file, "r") as f:
                        vendor = f.read().strip()
                if os.path.exists(model_file):
                    with open(model_file, "r") as f:
                        model = f.read().strip()
                label = f"{vendor} {model}".strip() or dev_name
                usb_drives.append(f"{label} ({size_gb} GB)")
    except Exception:
        pass

    connected_devices = []
    try:
        for dev_path in sorted(glob.glob("/sys/bus/usb/devices/*")):
            base = os.path.basename(dev_path)
            if ":" in base or base.startswith("usb"):
                continue
            bclass_file = os.path.join(dev_path, "bDeviceClass")
            bclass = ""
            if os.path.exists(bclass_file):
                with open(bclass_file, "r") as f:
                    bclass = f.read().strip()
            if bclass in {"09", "e0"}:
                continue

            iclasses = set()
            for ic_file in glob.glob(dev_path + ":*/bInterfaceClass"):
                try:
                    with open(ic_file, "r") as f:
                        iclasses.add(f.read().strip())
                except Exception:
                    pass
            if "09" in iclasses or "e0" in iclasses:
                continue

            rem_file = os.path.join(dev_path, "removable")
            rem = ""
            if os.path.exists(rem_file):
                with open(rem_file, "r") as f:
                    rem = f.read().strip()

            if rem == "fixed" and "0e" in iclasses:
                continue

            prod_file = os.path.join(dev_path, "product")
            mfg_file = os.path.join(dev_path, "manufacturer")
            prod = ""
            mfg = ""
            if os.path.exists(prod_file):
                with open(prod_file, "r") as f:
                    prod = f.read().strip()
            if os.path.exists(mfg_file):
                with open(mfg_file, "r") as f:
                    mfg = f.read().strip()

            if rem == "fixed" and "touch" in prod.lower():
                continue

            if mfg and prod and not prod.lower().startswith(mfg.lower()):
                full_name = f"{mfg} {prod}".strip()
            else:
                full_name = (prod or mfg).strip()

            if full_name:
                connected_devices.append(full_name)
    except Exception:
        pass

    return peripherals, usb_drives, connected_devices

def detect_windows_hardware():
    peripherals = {
        "mouse": False,
        "keyboard": False,
        "audio": False,
        "monitor": False
    }
    usb_drives = []
    connected_devices = []

    ps_script = (
        "$ErrorActionPreference='SilentlyContinue';"
        "$kbds = @(Get-CimInstance Win32_Keyboard | Where-Object { $_.Status -eq 'OK' -and $_.Description -notmatch 'PS/2' });"
        "$kbdVidPids = @($kbds | ForEach-Object { if ($_.PNPDeviceID -match '(VID_[0-9A-F]{4}&PID_[0-9A-F]{4})') { $matches[1] } });"
        "$mice = @(Get-CimInstance Win32_PointingDevice | Where-Object { "
        "$_.Status -eq 'OK' -and $_.Name -notmatch 'Touch|Screen' -and "
        "(-not ($_.PNPDeviceID -match '(VID_[0-9A-F]{4}&PID_[0-9A-F]{4})' -and $kbdVidPids -contains $matches[1])) "
        "});"
        "$m = $mice.Count -gt 0;"
        "$k = $kbds.Count -gt 0;"
        "$a = @(Get-CimInstance Win32_SoundDevice | Where-Object { $_.Status -eq 'OK' }).Count -gt 0;"
        "$mon = @(Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -eq 'Monitor' -and $_.Status -eq 'OK' }).Count -gt 0;"
        "$u = @(Get-CimInstance Win32_DiskDrive | Where-Object { $_.InterfaceType -eq 'USB' } | ForEach-Object { \"$($_.Caption) ($([math]::Round($_.Size / 1GB, 1)) GB)\" });"
        "$devs = @(Get-CimInstance Win32_PnPEntity | Where-Object { "
        "$_.Status -eq 'OK' -and $_.PNPDeviceID -match '^USB\\\\VID_' -and "
        "$_.PNPClass -notin @('USB','Bluetooth','System','Net') -and "
        "$_.Name -notmatch 'Composite Device|Root Hub|Host Controller|Generic USB Hub|Touch|Integrated Camera' "
        "} | Select-Object -ExpandProperty Name -Unique);"
        "@{mouse=$m; keyboard=$k; audio=$a; monitor=$mon; usb_drives=$u; connected_devices=$devs} | ConvertTo-Json -Compress"
    )
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=creationflags
        )
        if res.returncode == 0 and res.stdout.strip():
            parsed = json.loads(res.stdout.strip())
            peripherals["mouse"] = bool(parsed.get("mouse", False))
            peripherals["keyboard"] = bool(parsed.get("keyboard", False))
            peripherals["audio"] = bool(parsed.get("audio", False))
            peripherals["monitor"] = bool(parsed.get("monitor", False))
            raw_usb = parsed.get("usb_drives") or []
            if isinstance(raw_usb, str):
                usb_drives = [raw_usb]
            elif isinstance(raw_usb, list):
                usb_drives = [str(x) for x in raw_usb if x]
            raw_devs = parsed.get("connected_devices") or []
            if isinstance(raw_devs, str):
                connected_devices = [raw_devs]
            elif isinstance(raw_devs, list):
                connected_devices = [str(x) for x in raw_devs if x]
    except Exception:
        pass

    return peripherals, usb_drives, connected_devices

def get_peripherals_and_usb():
    if platform.system() == "Windows":
        return detect_windows_hardware()
    return detect_linux_hardware()

def get_system_metrics():
    peripherals, usb_drives, connected_devices = get_peripherals_and_usb()

    return {
        "mac_address": get_mac_address(),
        "local_ip": get_local_ip(),
        "hostname": socket.gethostname(),
        "os_version": platform.system() + " " + platform.release(),
        "cpu_percent": get_cpu_percent(),
        "ram_percent": get_ram_percent(),
        "storage_free_gb": get_storage_free_gb(),
        "is_online": check_network(),
        "uptime": get_uptime_str(),
        "active_user": get_logged_in_user(),
        "top_process": get_top_process(),
        "peripherals": peripherals,
        "usb_drives": usb_drives,
        "connected_devices": connected_devices
    }

def resolve_initial_config():
    args = sys.argv[1:]
    current_cfg = load_config()
    default_host = current_cfg.get("server_host", "localhost:5000") if current_cfg else "localhost:5000"

    if "--server" in args:
        idx = args.index("--server")
        if idx + 1 < len(args):
            cfg = save_config(args[idx + 1])
            ensure_background_running()
            return cfg

    is_frozen_interactive = getattr(sys, "frozen", False) and ("--background" not in args)
    if ("--config" in args) or (current_cfg is None) or is_frozen_interactive:
        cfg = show_config_dialog(default_host=default_host)
        if ("--config" in args) or is_frozen_interactive:
            if cfg:
                ensure_background_running()
            sys.exit(0)
        if cfg:
            return cfg
        if current_cfg:
            return current_cfg
        return save_config(default_host)

    return current_cfg

if __name__ == "__main__":
    script_file_path = os.path.abspath(__file__)
    config = resolve_initial_config()
    print(f"Agent monitoring berjalan -> Server: {config['server_url']}")
    print(f"File konfigurasi: {get_config_path()}")
    print("Tekan Ctrl+C untuk berhenti.")

    while True:
        # Jika file agent sudah dihapus/di-uninstall dari sistem, hentikan proses di RAM otomatis
        if not getattr(sys, "frozen", False) and not os.path.exists(script_file_path):
            sys.exit(0)

        latest_cfg = load_config()
        if latest_cfg and latest_cfg.get("server_url"):
            server_url = latest_cfg["server_url"]
        else:
            server_url = config["server_url"]

        data = get_system_metrics()
        waktu_sekarang = time.strftime('%H:%M:%S')

        try:
            status_code, resp_data = http_post_json(server_url, data, timeout=5)
            p = data["peripherals"]
            print(f"[{waktu_sekarang}] Update: {data['hostname']} | IP: {data['local_ip']} | Mouse: {p['mouse']} | Kbd: {p['keyboard']}")
            if isinstance(resp_data, dict) and resp_data.get("command"):
                execute_power_command(resp_data.get("command"))
        except Exception as e:
            print(f"[{waktu_sekarang}] Gagal terhubung ke {server_url}")

        time.sleep(3)
