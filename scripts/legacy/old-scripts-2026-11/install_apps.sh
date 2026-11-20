#!/bin/bash
#==============================================================================
# سكريبت تثبيت تطبيقات مانجارو - xorthomson
# التاريخ: $(date +%Y-%m-%d)
#==============================================================================

set -e  # إيقاف السكريبت عند أي خطأ

# الألوان للعرض
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# دالة للطباعة الملونة
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}
print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}
print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}
print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# التحقق من صلاحيات الروت (لـ pacman)
if [[ $EUID -ne 0 ]] && [[ "$1" != "--no-sudo" ]]; then
   print_warning "سيُطلب منك كلمة المرور لـ sudo عند الحاجة"
fi

# التحقق من وجود yay أو paru (مدير AUR)
check_aur_helper() {
    if command -v yay &> /dev/null; then
        AUR_HELPER="yay"
        print_success "تم العثور على: yay"
    elif command -v paru &> /dev/null; then
        AUR_HELPER="paru"
        print_success "تم العثور على: paru"
    else
        print_error "لم يتم العثور على yay أو paru!"
        print_status "جاري تثبيت yay..."
        # تثبيت yay إذا لم يكن موجوداً
        if ! command -v git &> /dev/null || ! command -v base-devel &> /dev/null; then
            sudo pacman -S --needed git base-devel --noconfirm
        fi
        cd /tmp
        git clone https://aur.archlinux.org/yay.git
        cd yay
        makepkg -si --noconfirm
        cd ..
        rm -rf yay
        AUR_HELPER="yay"
        print_success "تم تثبيت yay بنجاح"
    fi
}

# تحديث النظام أولاً
update_system() {
    print_status "جاري تحديث النظام..."
    sudo pacman -Syu --noconfirm
    print_success "تم تحديث النظام"
}

# تثبيت حزم المستودعات الرسمية
install_official_packages() {
    print_status "جاري تثبيت الحزم الرسمية..."
    
    OFFICIAL_PACKAGES=(
        shotwell          # منظم صور
        scribus           # نشر مكتبي
        handbrake         # تحويل فيديو
        vlc               # مشغل وسائط
        foliate           # قارئ كتب إلكترونية [[67]]
        minder            # خرائط ذهنية [[97]]
        xournalpp         # تدوين على PDF [[59]]
        homebank          # إدارة مالية شخصية [[106]]
        newsflash         # قارئ RSS [[125]]
        apostrophe        # محرر Markdown [[132]]
        fragments         # واجهة Transmission [[86]]
        transmission-gtk  # عميل التورنت الأساسي (لـ Fragments)
    )
    
    sudo pacman -S --needed "${OFFICIAL_PACKAGES[@]}" --noconfirm
    print_success "تم تثبيت الحزم الرسمية"
}

# تثبيت حزم AUR
install_aur_packages() {
    print_status "جاري تثبيت حزم AUR..."
    
    AUR_PACKAGES=(
        logseq-desktop-bin  # قاعدة معرفة - إصدار ثنائي جاهز [[14]]
        planify             # إدارة مهام [[115]]
        deskflow-git        # مشاركة ماوس/كيبورد (بديل Synergy) [[43]]
        upscayl-bin         # تكبير صور بالذكاء الاصطناعي [[89]]
    )
    
    # استخدام --mflags="--skipinteg" لتسريع البناء إذا لزم
    $AUR_HELPER -S --needed "${AUR_PACKAGES[@]}" --noconfirm
    print_success "تم تثبيت حزم AUR"
}

# إعدادات إضافية اختيارية
optional_setup() {
    print_status "جاري تطبيق الإعدادات الإضافية..."
    
    # تمكين خدمات الخلفية لـ Deskflow إذا لزم
    if $AUR_HELPER -Q deskflow-git &> /dev/null; then
        print_status "Deskflow مثبت: تذكر تشغيله من القائمة وتكوين الشبكة"
    fi
    
    # إعداد مجلدات افتراضية لـ Logseq
    if $AUR_HELPER -Q logseq-desktop-bin &> /dev/null; then
        mkdir -p ~/Documents/Logseq
        print_status "تم إنشاء مجلد افتراضي لـ Logseq: ~/Documents/Logseq"
    fi
    
    print_success "اكتملت الإعدادات الإضافية"
}

# عرض قائمة التطبيقات المثبتة
show_installed() {
    echo -e "\n${GREEN}════════════════════════════════════════${NC}"
    echo -e "${GREEN}✓ اكتمل التثبيت بنجاح!${NC}"
    echo -e "${GREEN}════════════════════════════════════════${NC}\n"
    
    echo "📋 التطبيقات التي تم تثبيتها:"
    echo "┌─────────────────────────────────┐"
    printf "│ %-35s │\n" "📷 Shotwell"
    printf "│ %-35s │\n" "📐 Scribus"
    printf "│ %-35s │\n" "🎬 HandBrake"
    printf "│ %-35s │\n" "▶️  VLC"
    printf "│ %-35s │\n" "🧠 Logseq"
    printf "│ %-35s │\n" "📚 Foliate"
    printf "│ %-35s │\n" "🗺️  Minder"
    printf "│ %-35s │\n" "✍️  Xournal++"
    printf "│ %-35s │\n" "💰 Homebank"
    printf "│ %-35s │\n" "✅ Planify"
    printf "│ %-35s │\n" "📰 NewsFlash"
    printf "│ %-35s │\n" "📝 Apostrophe"
    printf "│ %-35s │\n" "🖱️  Deskflow"
    printf "│ %-35s │\n" "🧩 Fragments"
    printf "│ %-35s │\n" "🤖 Upscayl"
    echo "└─────────────────────────────────┘"
    
    echo -e "\n💡 ${YELLOW}ملاحظات هامة:${NC}"
    echo "  • Logseq: افتح التطبيق واختر مجلد العمل لأول مرة"
    echo "  • Deskflow: يحتاج تكوين الشبكة بين الأجهزة (راجع: [[41]])"
    echo "  • Fragments: يحتاج تشغيل transmission-gtk في الخلفية"
    echo "  • Upscayl: أول تشغيل قد يستغرق وقتاً لتحميل نماذج الذكاء الاصطناعي"
    echo -e "\n🚀 للاستخدام: ابحث عن اسم التطبيق في قائمة التطبيقات أو شغله من الطرفية"
}

# دالة المساعدة
show_help() {
    echo "استخدام: $0 [خيارات]"
    echo ""
    echo "الخيارات:"
    echo "  --no-update     تخطي تحديث النظام"
    echo "  --only-official تثبيت الحزم الرسمية فقط"
    echo "  --only-aur      تثبيت حزم AUR فقط"
    echo "  --help          عرض هذه المساعدة"
    echo ""
    echo "مثال: $0 --no-update"
}

# ==================== البرنامج الرئيسي ====================
main() {
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  🚀 سكريبت تثبيت تطبيقات مانجارو  ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}\n"
    
    # معالجة المعاملات
    SKIP_UPDATE=false
    ONLY_OFFICIAL=false
    ONLY_AUR=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-update) SKIP_UPDATE=true; shift ;;
            --only-official) ONLY_OFFICIAL=true; shift ;;
            --only-aur) ONLY_AUR=true; shift ;;
            --help) show_help; exit 0 ;;
            *) print_error "خيار غير معروف: $1"; show_help; exit 1 ;;
        esac
    done
    
    # التحقق من مدير AUR
    check_aur_helper
    
    # التحديث (ما لم يُطلب تخطيه)
    if [[ "$SKIP_UPDATE" == false ]]; then
        update_system
    fi
    
    # التثبيت حسب الخيارات
    if [[ "$ONLY_AUR" == false ]]; then
        install_official_packages
    fi
    
    if [[ "$ONLY_OFFICIAL" == false ]]; then
        install_aur_packages
    fi
    
    # الإعدادات الإضافية
    optional_setup
    
    # العرض النهائي
    show_installed
}

# تشغيل البرنامج الرئيسي
main "$@"
