from flask import Flask, request, jsonify, render_template, send_file
from datetime import datetime
import json, os

app = Flask(__name__)

# Menyimpan data di memori (Sebagai pengganti database MySQL/Laravel)
computers_data = {}
pending_commands = {}

@app.route('/')
def index():
    # Menampilkan halaman HTML dashboard
    return render_template('index.html')

@app.route('/agent.deb')
def download_deb():
    deb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lab-monitoring-agent_1.0.0_all.deb')
    return send_file(deb_path, as_attachment=True, download_name='lab-monitoring-agent_1.0.0_all.deb')

@app.route('/api/command', methods=['POST'])
def send_command():
    body = request.json or {}
    mac = body.get('mac_address')
    cmd = body.get('command')

    if not mac or cmd not in ('shutdown', 'restart'):
        return jsonify({"status": "error", "message": "Perintah tidak valid"}), 400

    pending_commands[mac] = cmd
    print(f"[!] Antrean perintah '{cmd}' ditambahkan untuk MAC: {mac}")
    return jsonify({"status": "success", "mac_address": mac, "command": cmd}), 200

@app.route('/api/monitoring', methods=['GET', 'POST'])
def monitoring():
    if request.method == 'POST':
        data = request.json or {}
        mac = data.get('mac_address', 'unknown')
        
        data.setdefault('is_online', True)
        data.setdefault('uptime', '-')
        data.setdefault('active_user', '-')
        data.setdefault('top_process', '-')
        data.setdefault('peripherals', {
            'mouse': False,
            'keyboard': False,
            'audio': False,
            'monitor': False
        })
        data.setdefault('usb_drives', [])
        data.setdefault('connected_devices', [])

        # Tambahkan waktu terakhir data diterima
        data['last_seen'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Hapus entri duplikat lama jika berasal dari IP lokal yang sama namun MAC lama sempat berubah
        incoming_ip = data.get('local_ip')
        if incoming_ip and incoming_ip != '127.0.0.1':
            stale_macs = [m for m, d in computers_data.items() if m != mac and d.get('local_ip') == incoming_ip]
            for old_mac in stale_macs:
                computers_data.pop(old_mac, None)

        # Simpan atau update data PC berdasarkan MAC Address
        computers_data[mac] = data
        
        # Ambil perintah shutdown/restart jika ada di antrean untuk PC ini
        cmd = pending_commands.pop(mac, None)
        
        print(f"[+] Update dari: {data.get('hostname')} ({data.get('local_ip')})")
        return {"status": "success", "command": cmd}, 200
        
    elif request.method == 'GET':
        # Logika penentuan status untuk dashboard
        now = datetime.now()
        result = []
        
        for mac, data in computers_data.items():
            last_seen_dt = datetime.strptime(data['last_seen'], '%Y-%m-%d %H:%M:%S')
            diff_seconds = (now - last_seen_dt).total_seconds()
            
            # Jika lebih dari 30 detik tidak ada ping = Offline
            if diff_seconds > 30:
                data['status'] = 'Offline'
            # Jika CPU atau RAM di atas 90% = Warning
            elif data.get('cpu_percent', 0) > 90 or data.get('ram_percent', 0) > 90:
                data['status'] = 'Warning'
            else:
                data['status'] = 'Online'

            data['pending_command'] = pending_commands.get(mac)
            result.append(data)
            
        return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
