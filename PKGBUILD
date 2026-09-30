# Maintainer: Dr. Abdulmalek Al-Husseini <dr@abdmalek.com>
pkgname=manjaro-care
pkgver=1.1.0
pkgrel=1
pkgdesc="Graphical system maintenance center for Manjaro/Arch Linux — click instead of typing commands (PyQt5)"
arch=('any')
url="https://github.com/DrAbdulmalek/manjaro-care"
license=('MIT')
depends=('python-pyqt5' 'polkit' 'pacman' 'python')
optdepends=(
    'pacman-contrib: لـ paccache (تنظيف الكاش)'
    'pacman-mirrors: لترتيب المرايا حسب السرعة (مانجارو)'
    'reflector: لترتيب المرايا حسب السرعة (آرتش)'
    'reset-net: لوحدة إعادة ضبط الشبكة'
)
# makedepends: أُزيل 'git' — المصدر أرشيف tarball من وسم إصدار
# (لا git clone في أي مرحلة بناء، فراجع docs/PACKAGING.md).
source=("$pkgname-$pkgver.tar.gz::https://github.com/DrAbdulmalek/manjaro-care/archive/refs/tags/v$pkgver.tar.gz")
# ⚠ sha256sums: لا تتركها SKIP في إصدار منشور! بعد وسم الإصدار ولّد
# البصمة الحقيقية:
#   updpkgsums
# أو يدوياً:
#   curl -L "https://github.com/DrAbdulmalek/manjaro-care/archive/refs/tags/v$pkgver.tar.gz" | sha256sum
# التفاصيل الكاملة: docs/PACKAGING.md
sha256sums=('SKIP')  # TODO(owner): استبدلها بالبصمة الفعلية قبل النشر (انظر أعلاه)

prepare() {
    cd "$srcdir/$pkgname-$pkgver"
    # لا تعديلات مطلوبة — سكربت الدخول (manjaro-care) جزء من المصدر نفسه
}

package() {
    cd "$srcdir/$pkgname-$pkgver"

    # ملفات المشروع + سكربت الدخول نفسه (مصدر وحيد، مطابق لما يستخدمه
    # install.sh — يحدد موقعه تلقائياً عبر __file__)
    install -dm755 "$pkgdir/opt/manjaro-care"
    cp -r core modules gui "$pkgdir/opt/manjaro-care/"
    install -Dm755 manjaro-care "$pkgdir/opt/manjaro-care/manjaro-care"

    # نقطة دخول رفيعة في /usr/bin تستدعي الملف أعلاه
    install -Dm755 /dev/stdin "$pkgdir/usr/bin/manjaro-care" << 'ENTRY'
#!/bin/bash
exec /usr/bin/python3 /opt/manjaro-care/manjaro-care "$@"
ENTRY

    # .desktop
    install -Dm644 com.drabdulmalek.manjaro-care.desktop \
        "$pkgdir/usr/share/applications/com.drabdulmalek.manjaro-care.desktop"

    # لا يوجد ملف polkit .policy مخصص عمداً: كل استدعاءات pkexec في
    # الكود تستهدف pacman/systemctl/journalctl/paccache/pacman-mirrors
    # مباشرة، لا manjaro-care نفسه، فسياسة مخصصة بمسار /usr/bin/manjaro-care
    # لن تُطابَق إطلاقاً — نافذة polkit العامة القياسية تكفي وتعمل فعلياً.

    # التوثيق والترخيص
    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
    install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
}