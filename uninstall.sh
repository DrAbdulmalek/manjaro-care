#!/bin/bash
# ============================================================
# uninstall.sh — إلغاء تثبيت manjaro-care
# الاستخدام: sudo bash uninstall.sh
# ============================================================
set -eu

RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m'

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}يجب تشغيل المُثبّت بصلاحيات الجذر:${NC} sudo bash $0"
    exit 1
fi

echo -e "${BOLD}إلغاء تثبيت manjaro-care...${NC}"

rm -f /usr/bin/manjaro-care
rm -rf /opt/manjaro-care
rm -f /usr/share/applications/com.drabdulmalek.manjaro-care.desktop
rm -rf "${HOME}/.local/share/manjaro-care"

update-desktop-database /usr/share/applications/ 2>/dev/null || true

echo -e "${GREEN}تم إلغاء التثبيت بالكامل.${NC}"