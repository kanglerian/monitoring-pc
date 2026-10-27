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

# Salin agent.py sebagai binary /usr/bin/lab-monitoring-agent
cp agent.py "${BUILD_DIR}/usr/bin/lab-monitoring-agent"
chmod 755 "${BUILD_DIR}/usr/bin/lab-monitoring-agent"

# Buat file DEBIAN/control (Hanya butuh python3 bawaan Ubuntu, tanpa dependensi eksternal)
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

# Script pasca-instalasi
cat <<'EOF' > "${BUILD_DIR}/DEBIAN/postinst"
#!/bin/sh
set -e
mkdir -p /etc/lab_monitoring
chmod 777 /etc/lab_monitoring
echo "=========================================================="
echo " Lab Monitoring Agent berhasil diinstal!"
echo " Jalankan perintah berikut untuk mengatur IP Server:"
echo "   lab-monitoring-agent --config"
echo " Atau buka 'Pengaturan Lab Monitoring' di Menu Aplikasi."
echo "=========================================================="
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"

# Script sebelum uninstall (DEBIAN/prerm) -> Matikan proses background yang masih berjalan di RAM
cat <<'EOF' > "${BUILD_DIR}/DEBIAN/prerm"
#!/bin/sh
set -e
pkill -f "/usr/bin/lab-monitoring-agent" 2>/dev/null || true
pkill -f "lab-monitoring-agent" 2>/dev/null || true
exit 0
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/prerm"

# Script setelah uninstall (DEBIAN/postrm) -> Bersihkan file autostart di tiap user
cat <<'EOF' > "${BUILD_DIR}/DEBIAN/postrm"
#!/bin/sh
set -e
rm -f /home/*/.config/autostart/lab-monitoring-agent.desktop 2>/dev/null || true
rm -f /root/.config/autostart/lab-monitoring-agent.desktop 2>/dev/null || true
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

# Autostart otomatis di background saat user login
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
