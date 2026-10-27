#!/usr/bin/env bash
set -e

PKG_NAME="lab-monitoring-agent"
PKG_VERSION="1.0.0"
BUILD_DIR="build_deb/${PKG_NAME}_${PKG_VERSION}_all"

rm -rf build_deb
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/usr/bin"
mkdir -p "${BUILD_DIR}/usr/share/applications"
mkdir -p "${BUILD_DIR}/etc/xdg/autostart"
mkdir -p "${BUILD_DIR}/etc/sudoers.d"
mkdir -p "${BUILD_DIR}/etc/systemd/system"

# Salin agent.py sebagai binary /usr/bin/lab-monitoring-agent
cp agent.py "${BUILD_DIR}/usr/bin/lab-monitoring-agent"
chmod 755 "${BUILD_DIR}/usr/bin/lab-monitoring-agent"

# Izinkan perintah shutdown & reboot tanpa password khusus untuk agent monitoring
cat <<'EOF' > "${BUILD_DIR}/etc/sudoers.d/lab-monitoring-agent"
ALL ALL=(root) NOPASSWD: /sbin/shutdown, /usr/sbin/shutdown, /sbin/reboot, /usr/sbin/reboot, /sbin/poweroff, /usr/sbin/poweroff
EOF
chmod 0440 "${BUILD_DIR}/etc/sudoers.d/lab-monitoring-agent"

# Systemd service agar otomatis menyala sejak komputer boot/restart (bahkan sebelum login)
cat <<'EOF' > "${BUILD_DIR}/etc/systemd/system/lab-monitoring-agent.service"
[Unit]
Description=Lab Monitoring Agent Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/bin/lab-monitoring-agent --background
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
EOF

# Buat file DEBIAN/control
cat <<EOF > "${BUILD_DIR}/DEBIAN/control"
Package: ${PKG_NAME}
Version: ${PKG_VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3
Maintainer: Tim IT Lab <it@localhost>
Description: Agent Monitoring Lab Komputer
 Mengirimkan data status hardware, periferal USB, dan performa PC ke server monitoring lab.
EOF

# Script pasca-instalasi / update (otomatis matikan versi lama & jalankan systemd service)
cat <<'EOF' > "${BUILD_DIR}/DEBIAN/postinst"
#!/bin/sh
set -e
mkdir -p /etc/lab_monitoring
chmod 777 /etc/lab_monitoring
chmod 0440 /etc/sudoers.d/lab-monitoring-agent 2>/dev/null || true

# Salin config user yang sudah ada ke /etc/lab_monitoring/config.json agar terbaca oleh systemd service
for ucfg in /home/*/.config/lab_monitoring/config.json; do
    if [ -f "$ucfg" ] && [ ! -f "/etc/lab_monitoring/config.json" ]; then
        cp "$ucfg" /etc/lab_monitoring/config.json 2>/dev/null || true
        chmod 666 /etc/lab_monitoring/config.json 2>/dev/null || true
        break
    fi
done

# Hentikan proses manual versi lama jika sedang berjalan
pkill -f "[p]ython3.*/usr/bin/lab-monitoring-agent" 2>/dev/null || true

# Aktifkan dan jalankan systemd service agar otomatis nyala setiap habis restart
if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload 2>/dev/null || true
    systemctl enable lab-monitoring-agent.service 2>/dev/null || true
    systemctl restart lab-monitoring-agent.service 2>/dev/null || true
fi

echo "=========================================================="
echo " Lab Monitoring Agent berhasil diinstal & diaktifkan!"
echo " Service otomatis berjalan di background setiap komputer menyala."
echo " Jalankan perintah berikut untuk mengatur IP Server:"
echo "   lab-monitoring-agent --config"
echo "=========================================================="
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"

# Script sebelum uninstall / upgrade (DEBIAN/prerm) -> Matikan service & proses python agent
cat <<'EOF' > "${BUILD_DIR}/DEBIAN/prerm"
#!/bin/sh
set -e
if command -v systemctl >/dev/null 2>&1; then
    systemctl stop lab-monitoring-agent.service 2>/dev/null || true
    if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
        systemctl disable lab-monitoring-agent.service 2>/dev/null || true
    fi
fi
pkill -f "[p]ython3.*/usr/bin/lab-monitoring-agent" 2>/dev/null || true
exit 0
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/prerm"

# Script setelah uninstall (DEBIAN/postrm) -> Bersihkan file autostart di tiap user
cat <<'EOF' > "${BUILD_DIR}/DEBIAN/postrm"
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    rm -f /home/*/.config/autostart/lab-monitoring-agent.desktop 2>/dev/null || true
    rm -f /root/.config/autostart/lab-monitoring-agent.desktop 2>/dev/null || true
    if command -v systemctl >/dev/null 2>&1; then
        systemctl daemon-reload 2>/dev/null || true
    fi
fi
if [ "$1" = "purge" ]; then
    rm -rf /etc/lab_monitoring 2>/dev/null || true
    rm -rf /home/*/.config/lab_monitoring 2>/dev/null || true
fi
exit 0
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/postrm"

# Shortcut di Menu Aplikasi Linux untuk mengatur IP Server
cat <<EOF > "${BUILD_DIR}/usr/share/applications/lab-monitoring-agent.desktop"
[Desktop Entry]
Type=Application
Name=Pengaturan Lab Monitoring
Comment=Atur IP Server Monitoring Lab
Exec=/usr/bin/lab-monitoring-agent --config
Icon=utilities-system-monitor
Terminal=false
Categories=Settings;System;
EOF

# Autostart otomatis di background saat user login (fallback jika tanpa systemd)
cat <<EOF > "${BUILD_DIR}/etc/xdg/autostart/lab-monitoring-agent-bg.desktop"
[Desktop Entry]
Type=Application
Name=Lab Monitoring Agent Background
Exec=/usr/bin/lab-monitoring-agent --background
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF

dpkg-deb --build --root-owner-group "${BUILD_DIR}"
mv "build_deb/${PKG_NAME}_${PKG_VERSION}_all.deb" "./${PKG_NAME}_${PKG_VERSION}_all.deb"
rm -rf build_deb

echo "Selesai! Paket .deb berhasil dibuat: ${PKG_NAME}_${PKG_VERSION}_all.deb"
