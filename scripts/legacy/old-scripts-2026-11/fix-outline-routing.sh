#!/bin/bash
echo "========================================"
echo "🔧 إصلاح Outline VPN - Routing & DNS"
echo "========================================"

# 1. إيقاف Outline
pkill -9 -f Outline
sleep 2

# 2. تنظيف TUN
sudo ip link delete outline-tun1 2>/dev/null || true
sudo modprobe tun

# 3. DNS
echo "🌐 إصلاح DNS..."
sudo cp /etc/resolv.conf /etc/resolv.conf.outline-backup
sudo tee /etc/resolv.conf << 'DNS'
nameserver 1.1.1.1
nameserver 8.8.8.8
DNS

# 4. IPv6
echo "🚫 تعطيل IPv6..."
sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1 2>/dev/null || true

# 5. صلاحيات Outline
echo "🔐 صلاحيات Outline..."
sudo setcap cap_net_admin+ep /opt/Outline/Outline
sudo chown root:root /opt/Outline/chrome-sandbox
sudo chmod 4755 /opt/Outline/chrome-sandbox

# 6. تنظيف NetworkManager
echo "🧹 تنظيف NetworkManager..."
sudo rm -f /etc/NetworkManager/system-connections/Outline* 2>/dev/null || true
sudo systemctl restart NetworkManager

# 7. التحقق
echo ""
echo "=== التحقق ==="
echo -n "TUN: "
[ -e /dev/net/tun ] && echo "✅" || echo "❌"
echo -n "DNS: "
cat /etc/resolv.conf | grep -q "1.1.1.1" && echo "✅" || echo "❌"
echo -n "IPv6: "
ip -6 addr show 2>/dev/null | grep -q "inet6" && echo "❌ مفعل" || echo "✅ معطل"
echo -n "Outline Cap: "
getcap /opt/Outline/Outline 2>/dev/null | grep -q "cap_net_admin" && echo "✅" || echo "❌"

echo ""
echo "✅ الإصلاح اكتمل!"
echo "الآن شغّل Outline واتصل، ثم تحقّق:"
echo "  curl ifconfig.me"
echo "  ip route | grep -i outline"
