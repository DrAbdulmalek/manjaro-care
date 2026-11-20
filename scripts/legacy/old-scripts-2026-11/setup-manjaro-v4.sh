#!/usr/bin/env bash
# ==============================================================================
#  setup-manjaro.sh — إعداد شامل لمانجارو (نسخة مُحسّنة v4)
#  استُخلص من محادثة تحليل Build 4200 + مراجعة الأخطاء العملية
#  التشغيل:  chmod +x setup-manjaro-v4.sh && ./setup-manjaro-v4.sh
# ==============================================================================
set -euo pipefail
IFS=$'\n\t'

# ── ألوان ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log_info()  { echo -e "${GREEN}[✔]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[⚠]${NC} $*"; }
log_error() { echo -e "${RED}[✘]${NC} $*"; }
log_step()  { echo -e "\n${BOLD}${CYAN}══════ $* ══════${NC}"; }

# ── دوال مساعدة ───────────────────────────────────────────────────────────────
install_pkg() {
    local pkgs=("$@")
    for p in "${pkgs[@]}"; do
        if pacman -Qi "$p" &>/dev/null; then
            log_info "مثبّت مسبقاً: $p"
        else
            sudo pacman -S --noconfirm --needed "$p" 2>/dev/null \
                && log_info "تم تثبيت: $p" \
                || log_warn "فشل: $p (تخطّي)"
        fi
    done
}

install_aur() {
    local pkgs=("$@")
    if ! command -v yay &>/dev/null; then
        log_warn "yay غير موجود — تخطّي AUR: $*"
        return 0
    fi
    for p in "${pkgs[@]}"; do
        if pacman -Qi "$p" &>/dev/null; then
            log_info "مثبّت مسبقاً (AUR): $p"
        else
            yay -S --noconfirm --needed "$p" 2>/dev/null \
                && log_info "تم تثبيت (AUR): $p" \
                || log_warn "فشل (AUR): $p (تخطّي)"
        fi
    done
}

# ── التحقق من الصلاحيات ───────────────────────────────────────────────────────
if [[ "$EUID" -eq 0 ]]; then
    log_error "لا تشغّل السكريبت كـ root مباشرة. شغّله كمستخدم عادي."
    exit 1
fi

echo -e "${BOLD}"
cat << 'EOF'
  ╔══════════════════════════════════════════════╗
  ║   إعداد مانجارو الشامل — نسخة محسّنة v4    ║
  ║   الهندسة العكسية + التطوير + الافتراضية    ║
  ╚══════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# ── 0. إصلاح قفل قاعدة بيانات pacman ─────────────────────────────────────────
log_step "0. إصلاح بيئة pacman"

# إصلاح db.lck الحالي
if [[ -f /var/lib/pacman/db.lck ]]; then
    log_warn "تم اكتشاف db.lck — جاري الحذف..."
    sudo rm -f /var/lib/pacman/db.lck
fi

# دالة لإعادة المحاولة مع إصلاح db.lck تلقائياً أثناء التثبيت
safe_pacman() {
    local max_retries=5
    local attempt=1
    while (( attempt <= max_retries )); do
        if sudo pacman "$@"; then
            return 0
        fi
        if [[ -f /var/lib/pacman/db.lck ]]; then
            log_warn "db.lck ظهر مجدداً — إصلاح وإعادة المحاولة ($attempt/$max_retries)..."
            sudo rm -f /var/lib/pacman/db.lck
            sleep $(( attempt * 3 ))   # تأخير متصاعد: 3، 6، 9، 12 ثانية
        fi
        (( attempt++ ))
    done
    log_warn "فشل الأمر بعد $max_retries محاولات"
    return 1
}

# ── 1. تحديث المرايا وقاعدة البيانات ─────────────────────────────────────────
log_step "1. تحديث المرايا وقاعدة البيانات"

sudo pacman-mirrors --fasttrack 10 --api 2>/dev/null \
    || sudo pacman-mirrors --country Germany,Turkey,France --api 2>/dev/null \
    || log_warn "فشل تحديث المرايا — متابعة..."

safe_pacman -Syy --noconfirm
safe_pacman -Syu --noconfirm

# ── 2. تثبيت yay إذا لم يكن موجوداً ──────────────────────────────────────────
log_step "2. التحقق من yay (مدير AUR)"

if ! command -v yay &>/dev/null; then
    log_info "تثبيت yay..."
    install_pkg git base-devel
    TMPYAY=$(mktemp -d)
    git clone https://aur.archlinux.org/yay.git "$TMPYAY/yay" --depth=1
    (cd "$TMPYAY/yay" && makepkg -si --noconfirm)
    rm -rf "$TMPYAY"
    log_info "تم تثبيت yay بنجاح"
fi

# ── 3. أدوات الهندسة العكسية ──────────────────────────────────────────────────
log_step "3. أدوات الهندسة العكسية"

install_pkg \
    radare2 gdb binutils ltrace strace binwalk ghidra \
    hexedit bless xxd bsdiff xdelta3 vbindiff patchelf \
    go rust git

install_aur cutter detect-it-easy edb-debugger

# angr: تثبيت الاعتمادية أولاً ثم الحزمة
log_info "تثبيت angr + اعتمادياته..."
pip install --user msgspec 2>/dev/null \
    || yay -S --noconfirm python-msgspec 2>/dev/null \
    || log_warn "فشل تثبيت msgspec"
install_aur angr angr-management

# qiling: عبر pip فقط (غير موجود في AUR بشكل موثوق)
log_info "تثبيت qiling عبر pip..."
pip install --user qiling 2>/dev/null \
    && log_info "تم تثبيت qiling" \
    || log_warn "فشل تثبيت qiling — يمكن تثبيته لاحقاً: pip install --user qiling"

# gotch: بناء من المصدر
if ! command -v gotch &>/dev/null; then
    log_info "بناء gotch من المصدر..."
    TMPGOTCH=$(mktemp -d)
    if git clone --depth=1 https://github.com/DanteLorenzo/gotch.git "$TMPGOTCH/gotch" 2>/dev/null; then
        (cd "$TMPGOTCH/gotch" && go build . && sudo mv gotch /usr/local/bin/)
        log_info "تم تثبيت gotch في /usr/local/bin"
    else
        log_warn "فشل بناء gotch (تخطّي)"
    fi
    rm -rf "$TMPGOTCH"
fi

# ── 4. أدوات التطوير ──────────────────────────────────────────────────────────
log_step "4. أدوات التطوير"

install_pkg nodejs npm docker docker-compose python python-pip

# تفعيل Docker وإضافة المستخدم
sudo systemctl enable --now docker 2>/dev/null || true
if ! groups "$USER" | grep -q docker; then
    sudo usermod -aG docker "$USER"
    log_warn "أُضيف المستخدم لمجموعة docker — سجّل خروجاً ودخولاً لتفعيله"
fi

install_aur sublime-text-4 visual-studio-code-bin github-cli

# ── 5. Neovim + LazyVim ───────────────────────────────────────────────────────
log_step "5. Neovim + LazyVim"

# الحزم الأساسية — tree-sitter مضاف للتلوين اللغوي المتقدم
install_pkg \
    neovim git curl wget unzip nodejs npm python python-pip \
    ripgrep fd fzf lazygit gcc make tree-sitter

# تثبيت pynvim — محاولة متعددة للتوافق مع بيئات مختلفة
log_info "تثبيت pynvim..."
pip install --user pynvim --quiet 2>/dev/null \
    || pip install --break-system-packages pynvim --quiet 2>/dev/null \
    || log_warn "فشل تثبيت pynvim"

# تثبيت حزمة neovim لـ Node
sudo npm install -g neovim --quiet 2>/dev/null \
    || log_warn "فشل تثبيت neovim npm package"

# النسخ الاحتياطي + تثبيت LazyVim
log_info "إعداد LazyVim..."

# نسخ احتياطي فقط إذا كان المجلد حقيقياً (وليس رابطاً رمزياً)
if [[ -d "$HOME/.config/nvim" && ! -L "$HOME/.config/nvim" ]]; then
    local_bak="$HOME/.config/nvim.bak.$(date +%s)"
    mv "$HOME/.config/nvim" "$local_bak"
    log_info "نسخة احتياطية: $local_bak"
fi

if [[ -d "$HOME/.local/share/nvim" && ! -L "$HOME/.local/share/nvim" ]]; then
    mv "$HOME/.local/share/nvim" "$HOME/.local/share/nvim.bak.$(date +%s)"
fi

if [[ ! -d "$HOME/.config/nvim" ]]; then
    git clone --depth=1 https://github.com/LazyVim/starter "$HOME/.config/nvim"
    rm -rf "$HOME/.config/nvim/.git"

    # تثبيت الإضافات تلقائياً بدون تدخل (headless)
    log_info "جاري تثبيت إضافات LazyVim (2-3 دقائق)..."
    nvim --headless "+Lazy! sync" +qa 2>/dev/null \
        && log_info "LazyVim جاهز بالكامل ✓" \
        || log_warn "nvim --headless لم يكتمل — شغّل 'nvim' مرة واحدة يدوياً"

    log_info "اختصارات سريعة:"
    log_info "  Space+e → File Explorer | Space+f → بحث | Space+g → Git"
else
    log_info "Neovim config موجود مسبقاً — لم يتم التعديل"
fi

# ── 6. محررات النصوص والملفات ─────────────────────────────────────────────────
log_step "6. برامج التحرير والوسائط"

install_pkg kwrite gthumb digikam
install_aur notepadqq masterpdfeditor xournalpp pdfsam

# ── 7. Wine ───────────────────────────────────────────────────────────────────
log_step "7. Wine (تشغيل برامج ويندوز)"

install_pkg wine winetricks wine-mono wine-gecko

log_info "تهيئة Wine (win10)..."
timeout 30 winecfg -v win10 2>/dev/null || log_warn "فشل تهيئة Wine"
timeout 30 winetricks corefonts -q 2>/dev/null || log_warn "فشل تثبيت خطوط Wine"

# ── 8. التواصل والمزامنة ──────────────────────────────────────────────────────
log_step "8. التواصل والمزامنة"

install_pkg telegram-desktop
install_aur \
    jetbrains-toolbox \
    rustdesk-bin \
    outline-client-appimage-git \
    onedrive-abraunegg

# تفعيل OneDrive كخدمة في الخلفية
if command -v onedrive &>/dev/null; then
    systemctl --user enable onedrive 2>/dev/null \
        && log_info "OneDrive مفعّل كخدمة مستخدم" \
        || log_warn "يمكن تفعيل OneDrive يدوياً: systemctl --user enable onedrive"
fi

# ── 9. الوسائط المتعددة ───────────────────────────────────────────────────────
log_step "9. الوسائط المتعددة"

install_pkg vlc gimp firefox chromium yt-dlp

# ── 10. أدوات صيانة النظام ────────────────────────────────────────────────────
log_step "10. أدوات صيانة النظام"

install_pkg timeshift reflector btop htop

# ── 11. السمات والأيقونات ─────────────────────────────────────────────────────
log_step "11. السمات والأيقونات"

install_aur \
    tela-icon-theme \
    whitesur-gtk-theme \
    qogir-gtk-theme-git \
    fluent-icon-theme-git \
    arc-kde-git \
    joplin-desktop \
    python-pillow \
    ttf-ms-win11-auto \
    noto-fonts-emoji

# ── 12. الافتراضية: KVM + VirtualBox ─────────────────────────────────────────
log_step "12. الافتراضية (KVM + VirtualBox)"

# التحقق من دعم الافتراضية في المعالج
if grep -E -q 'vmx|svm' /proc/cpuinfo; then
    log_info "المعالج يدعم الافتراضية (vmx/svm) ✓"
else
    log_warn "الافتراضية غير مكتشفة في /proc/cpuinfo"
    log_warn "تأكد من تفعيل Intel VT-x أو AMD-V في إعدادات BIOS/UEFI"
fi

# تثبيت headers النواة الحالية
KERNEL_PKG=$(pacman -Q 2>/dev/null \
    | grep -E '^linux[0-9]* ' \
    | grep -v 'headers\|docs\|api' \
    | head -1 \
    | cut -d' ' -f1 || true)

if [[ -n "$KERNEL_PKG" ]]; then
    log_info "نواة النظام: $KERNEL_PKG"
    install_pkg "${KERNEL_PKG}-headers"
else
    log_warn "تعذّر تحديد نواة النظام — تخطّي تثبيت headers"
fi

install_pkg \
    qemu-full libvirt virt-manager virt-viewer edk2-ovmf dnsmasq iptables \
    virtualbox virtualbox-host-dkms

# تفعيل خدمات الافتراضية
sudo systemctl enable --now libvirtd 2>/dev/null \
    && log_info "libvirtd مفعّل" || log_warn "فشل تفعيل libvirtd"

sudo virsh net-start default    2>/dev/null || true
sudo virsh net-autostart default 2>/dev/null || true
sudo usermod -aG libvirt,kvm,vboxusers "$USER" 2>/dev/null || true

# محاولة تحميل وحدات KVM بدون إعادة تشغيل
if ! lsmod | grep -q kvm; then
    log_info "محاولة تحميل وحدات KVM..."
    sudo modprobe kvm 2>/dev/null || true
    if grep -q vmx /proc/cpuinfo; then
        sudo modprobe kvm_intel 2>/dev/null \
            && log_info "تم تحميل kvm_intel — يمكنك تشغيل virt-manager الآن" \
            || log_warn "فشل تحميل kvm_intel — أعد التشغيل لتفعيله"
    elif grep -q svm /proc/cpuinfo; then
        sudo modprobe kvm_amd 2>/dev/null \
            && log_info "تم تحميل kvm_amd — يمكنك تشغيل virt-manager الآن" \
            || log_warn "فشل تحميل kvm_amd — أعد التشغيل لتفعيله"
    fi
else
    log_info "وحدات KVM محمّلة مسبقاً ✓"
fi

# تأكيد تحميل vboxdrv إذا كان VirtualBox مثبتاً
if command -v VBoxManage &>/dev/null; then
    sudo modprobe vboxdrv 2>/dev/null \
        && log_info "تم تحميل vboxdrv ✓" \
        || log_warn "vboxdrv يحتاج إعادة تشغيل لأول مرة (DKMS)"
fi

# ── 13. تحسينات الأداء ────────────────────────────────────────────────────────
log_step "13. تحسينات الأداء"

SYSCTL_FILE="/etc/sysctl.d/99-manjaro-optimize.conf"
if ! grep -q "vm.swappiness" "$SYSCTL_FILE" 2>/dev/null; then
    {
        echo "vm.swappiness=10"
        echo "vm.vfs_cache_pressure=50"
        echo "net.core.rmem_max=16777216"
        echo "net.core.wmem_max=16777216"
    } | sudo tee -a "$SYSCTL_FILE" >/dev/null
    sudo sysctl -p "$SYSCTL_FILE" 2>/dev/null || true
    log_info "تم تطبيق تحسينات الأداء"
fi

# ── 14. تنظيف نهائي ───────────────────────────────────────────────────────────
log_step "14. تنظيف النظام"

# إزالة الحزم اليتيمة
ORPHANS=$(pacman -Qtdq 2>/dev/null || true)
if [[ -n "$ORPHANS" ]]; then
    # shellcheck disable=SC2086
    sudo pacman -Rns --noconfirm $ORPHANS 2>/dev/null \
        && log_info "تم إزالة الحزم اليتيمة" \
        || log_warn "فشل إزالة بعض الحزم اليتيمة"
else
    log_info "لا توجد حزم يتيمة"
fi

# تنظيف الـ cache
sudo pacman -Sc --noconfirm 2>/dev/null || true
log_info "تم تنظيف cache pacman"

# ── 15. سكريبت التحقق ────────────────────────────────────────────────────────
log_step "15. إنشاء سكريبت التحقق"

cat > "$HOME/verify-setup.sh" << 'VERIFY'
#!/usr/bin/env bash
# سكريبت التحقق من التثبيت
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'

chk() {
    command -v "$1" &>/dev/null \
        && echo -e "  ${GREEN}✅${NC} $1" \
        || echo -e "  ${RED}❌${NC} $1"
}

chk_svc() {
    systemctl is-active --quiet "$1" \
        && echo -e "  ${GREEN}✅${NC} $1 (running)" \
        || echo -e "  ${YELLOW}⚠${NC}  $1 (stopped)"
}

echo -e "${BOLD}══ الهندسة العكسية ══${NC}"
chk radare2; chk gdb; chk ghidra; chk binwalk
chk hexedit; chk bless; chk xxd; chk bsdiff
chk xdelta3; chk vbindiff; chk gotch
python3 -c "import qiling" 2>/dev/null \
    && echo -e "  ${GREEN}✅${NC} qiling" \
    || echo -e "  ${RED}❌${NC} qiling"

echo ""
echo -e "${BOLD}══ التطوير ══${NC}"
chk code; chk node; chk npm; chk git
chk docker; chk go; chk cargo; chk nvim

echo ""
echo -e "${BOLD}══ المحررات ══${NC}"
chk notepadqq; chk kwrite; chk code

echo ""
echo -e "${BOLD}══ ويندوز ══${NC}"
chk wine; chk winetricks

echo ""
echo -e "${BOLD}══ الخدمات ══${NC}"
chk_svc docker; chk_svc libvirtd

echo ""
echo -e "${BOLD}══ الافتراضية ══${NC}"
chk virt-manager; chk VBoxManage; chk qemu-system-x86_64
grep -E -q 'vmx|svm' /proc/cpuinfo \
    && echo -e "  ${GREEN}✅${NC} CPU يدعم الافتراضية" \
    || echo -e "  ${YELLOW}⚠${NC}  CPU: تحقق من BIOS/UEFI"
lsmod | grep -q kvm \
    && echo -e "  ${GREEN}✅${NC} وحدات KVM محمّلة" \
    || echo -e "  ${YELLOW}⚠${NC}  KVM: شغّل 'sudo modprobe kvm_intel' أو أعد التشغيل"
lsmod | grep -q vboxdrv \
    && echo -e "  ${GREEN}✅${NC} vboxdrv محمّل" \
    || echo -e "  ${YELLOW}⚠${NC}  vboxdrv: يحتاج إعادة تشغيل"

echo ""
echo -e "${BOLD}══ النظام ══${NC}"
chk timeshift; chk reflector; chk yt-dlp; chk vlc; chk btop
chk onedrive; chk telegram-desktop
VERIFY

chmod +x "$HOME/verify-setup.sh"
log_info "تم إنشاء ~/verify-setup.sh"

# ── ملخص نهائي ────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}"
cat << 'EOF'
  ╔══════════════════════════════════════════════════════╗
  ║            ✅  اكتمل الإعداد بنجاح!  v4             ║
  ╚══════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${BOLD}📌 خطوات ما بعد التثبيت:${NC}"
echo "  1. أعد تشغيل الجهاز أو سجّل خروجاً ودخولاً"
echo "     (لتفعيل: Docker / VirtualBox / OneDrive)"
echo ""
echo "  2. تحقق من وحدات KVM:"
echo "     lsmod | grep kvm"
echo "     (إذا لم تظهر → sudo modprobe kvm_intel  أو  kvm_amd)"
echo "     (إذا فشل modprobe → فعّل VT-x/AMD-V من BIOS ثم أعد التشغيل)"
echo ""
echo "  3. تحقق من التثبيت:"
echo "     bash ~/verify-setup.sh"
echo ""
echo -e "${BOLD}🔧 أوامر أساسية:${NC}"
echo "  radare2 <ملف>         → تحليل ثنائي (CLI)"
echo "  cutter                → واجهة رسومية لـ radare2"
echo "  ghidra                → هندسة عكسية متقدمة"
echo "  bless <ملف>           → محرر Hex رسومي"
echo "  vbindiff f1 f2        → مقارنة ملفين ثنائيين"
echo "  wine program.exe      → تشغيل برامج ويندوز"
echo "  virt-manager          → إدارة الأجهزة الافتراضية"
echo "  timeshift --create    → نسخة احتياطية"
echo "  nvim                  → محرر LazyVim (Space+e/f/g/q)"
echo "  btop                  → مراقبة النظام"
echo ""
