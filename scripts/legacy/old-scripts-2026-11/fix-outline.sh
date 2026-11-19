#!/bin/bash
echo "🔧 إصلاح Outline VPN..."

# 1. إيقاف Outline
pkill -9 -f Outline
sleep 2

# 2. وحدة TUN
sudo modprobe tun
sudo mkdir -p /dev/net
sudo mknod /dev/net/tun c 10 200 2>/dev/null || true
sudo chmod 0666 /dev/net/tun

# 3. Chrome Sandbox
sudo chown root:root /opt/Outline/chrome-sandbox
sudo chmod 4755 /opt/Outline/chrome-sandbox

# 4. صلاحيات TUN
sudo setcap cap_net_admin+ep /opt/Outline/Outline

# 5. تنظيف إعدادات الشبكة القديمة
sudo ip link delete outline-tun1 2>/dev/null || true

# 6. التحقق
echo ""
echo "=== التحقق ==="
echo -n "TUN device: "
ls -la /dev/net/tun 2>/dev/null || echo "❌"
echo -n "chrome-sandbox: "
ls -la /opt/Outline/chrome-sandbox 2>/dev/null || echo "❌"
echo -n "Outline capabilities: "
getcap /opt/Outline/Outline 2>/dev/null || echo "❌"

echo ""
echo "✅ الإصلاح اكتمل!"
echo "الآن شغّل Outline من القائمة أو: /opt/Outline/Outline --no-sandbox &"
