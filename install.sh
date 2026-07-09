#!/bin/bash
# ============================================================
# install.sh — مُثبّت manjaro-care
# ينسخ المشروع، يضبط الصلاحيات، ينشأ نقطة الدخول، يثبّت القائمة
# الاستخدام:  sudo bash install.sh
# ============================================================
set -eu

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/manjaro-care"

echo -e "${CYAN}${BOLD}"
echo "══════════════════════════════════════════════════"
echo "  manjaro-care v1.1.0 — المُثبّت"
echo "══════════════════════════════════════════════════"
echo -e "${NC}"

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}يجب تشغيل المُثبّت بصلاحيات الجذر:${NC} sudo bash $0"
    exit 1
fi

CURRENT_USER="${SUDO_USER:-$USER}"
echo -e "المستخدم: ${BOLD}${CURRENT_USER}${NC}"
echo ""

# ── 1. نسخ ملفات المشروع ──
echo -e "${BOLD}[1/4] تثبيت ملفات المشروع...${NC}"
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "${SCRIPT_DIR}/core" "$INSTALL_DIR/core"
cp -r "${SCRIPT_DIR}/modules" "$INSTALL_DIR/modules"
cp -r "${SCRIPT_DIR}/gui" "$INSTALL_DIR/gui"
# سكربت الدخول نفسه (manjaro-care الموجود في جذر المشروع) — مصدر
# وحيد يُستخدم مباشرة، بدل توليد نسخة مكرَّرة inline هنا وفي PKGBUILD.
# هو "يحدد موقعه" تلقائياً عبر __file__، فيعمل بشكل صحيح من أي مسار تثبيت.
cp "${SCRIPT_DIR}/manjaro-care" "$INSTALL_DIR/manjaro-care"
chmod 755 "$INSTALL_DIR/manjaro-care"
echo -e "  ${GREEN}${INSTALL_DIR}/${NC}"

# ── 2. إنشاء نقطة دخول رفيعة في /usr/bin ──
echo -e "${BOLD}[2/4] إنشاء نقطة الدخول...${NC}"
cat > /usr/bin/manjaro-care << 'ENTRY'
#!/bin/bash
exec /usr/bin/python3 /opt/manjaro-care/manjaro-care "$@"
ENTRY
chmod 755 /usr/bin/manjaro-care
echo -e "  ${GREEN}/usr/bin/manjaro-care${NC}"

# ── 3. تثبيت ملف .desktop ──
echo -e "${BOLD}[3/4] تثبيت ملف القائمة...${NC}"
cp "${SCRIPT_DIR}/com.drabdulmalek.manjaro-care.desktop" /usr/share/applications/
chmod 644 /usr/share/applications/com.drabdulmalek.manjaro-care.desktop
update-desktop-database /usr/share/applications/ 2>/dev/null || true
echo -e "  ${GREEN}تم تثبيت القائمة${NC}"
# ملاحظة: لا يوجد ملف polkit .policy مخصص عمداً — كل استدعاءات pkexec
# تستهدف أدوات نظام قياسية (pacman, systemctl, journalctl...) مباشرة،
# فتظهر نافذة مصادقة polkit العامة القياسية. ربط سياسة مخصصة بمسار
# /usr/bin/manjaro-care لن يُطابق أياً من هذه الاستدعاءات الفعلية.

# ── 4. فحص التبعيات ──
echo -e "${BOLD}[4/4] فحص التبعيات...${NC}"
MISSING=()
for pkg in python-pyqt5 polkit pacman; do
    if ! /usr/bin/pacman -Qi "$pkg" &>/dev/null; then
        MISSING+=("$pkg")
    fi
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo -e "  ${YELLOW}حزم مفقودة: ${MISSING[*]}${NC}"
    echo -e "  ${YELLOW}ثبّتها: sudo pacman -S ${MISSING[*]}${NC}"
else
    echo -e "  ${GREEN}كل التبعيات متوفرة${NC}"
fi

if [[ -x /usr/bin/kbuildsycoca6 ]]; then
    su - "${CURRENT_USER}" -c "/usr/bin/kbuildsycoca6" 2>/dev/null || true
fi

echo ""
echo -e "${CYAN}${BOLD}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  تم التثبيت بنجاح!${NC}"
echo -e "${CYAN}${BOLD}══════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BOLD}التشغيل:${NC}"
echo -e "  ${GREEN}manjaro-care${NC}"
echo -e "  أو ابحث عن ${GREEN}\"Manjaro Care\"${NC} في قائمة التطبيقات"
