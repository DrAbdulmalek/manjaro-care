#!/bin/bash
# ============================================================
# سكريبت إصلاح ja-netfilter وتجميعه باستخدام JDK 17
# الهدف: تعديل الاستيرادات الداخلية وإزالة tools.jar
# ============================================================

# ألوان للمخرجات
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# تحديد مسار المشروع (عدّل هنا إذا كان في مكان آخر)
PROJECT_DIR="$HOME/Desktop/ja-netfilter-2025.3.0"

echo -e "${GREEN}🔧 بدء إصلاح ja-netfilter في: ${PROJECT_DIR}${NC}"

# 1. التحقق من وجود المجلد
if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${RED}❌ مجلد المشروع غير موجود: $PROJECT_DIR${NC}"
    exit 1
fi

cd "$PROJECT_DIR"

# 2. التحقق من وجود JDK 17 (مطلوب للبناء)
if [ ! -f "/usr/lib/jvm/java-17-openjdk/bin/javac" ]; then
    echo -e "${YELLOW}⚠️ JDK 17 غير مثبت، جاري التثبيت...${NC}"
    sudo pacman -S --needed --noconfirm jdk17-openjdk
fi

# 3. إصلاح ملفات Transformers (استبدال الاستيرادات الداخلية بالعامة)
echo -e "${GREEN}📝 تعديل ملفات Transformers...${NC}"
TRANSFORMER_FILES=(
    "src/main/java/com/janetfilter/plugins/power/ArgsTransformer.java"
    "src/main/java/com/janetfilter/plugins/dns/InetAddressTransformer.java"
    "src/main/java/com/janetfilter/plugins/hideme/VMTransformer.java"
    "src/main/java/com/janetfilter/plugins/hideme/ClassNameTransformer.java"
    "src/main/java/com/janetfilter/plugins/url/HttpClientTransformer.java"
)

for file in "${TRANSFORMER_FILES[@]}"; do
    if [ -f "$file" ]; then
        # استبدال الاستيراد الداخلي بالاستيراد العام
        sed -i 's|import jdk\.internal\.org\.objectweb\.asm\.ClassReader;|import org.objectweb.asm.ClassReader;|g' "$file"
        # استبدال أي مرجع آخر لـ jdk.internal.org.objectweb.asm
        sed -i 's|jdk\.internal\.org\.objectweb\.asm|org.objectweb.asm|g' "$file"
        echo -e "  ✅ تم تعديل: $file"
    else
        echo -e "  ⚠️ الملف غير موجود: $file"
    fi
done

# 4. إزالة اعتمادية tools.jar من pom.xml (تسبب مشاكل مع JDK 17+)
echo -e "${GREEN}🔧 إصلاح pom.xml (إزالة tools.jar)...${NC}"
sed -i '/<dependency>/,/<\/dependency>/{
  /<groupId>com\.sun<\/groupId>/,/<\/dependency>/d
}' pom.xml

# التحقق من صحة pom.xml (اختياري)
if command -v xmllint &>/dev/null; then
    xmllint --noout pom.xml 2>/dev/null && echo -e "${GREEN}✅ pom.xml صالح${NC}" || echo -e "${YELLOW}⚠️ تحذير: قد يكون pom.xml به أخطاء بسيطة${NC}"
else
    echo -e "${YELLOW}⚠️ xmllint غير مثبت، تخطي التحقق من XML${NC}"
fi

# 5. إعادة البناء باستخدام JDK 17
echo -e "${GREEN}🏗️  جاري البناء باستخدام JDK 17...${NC}"
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk
export PATH="$JAVA_HOME/bin:$PATH"

# تنظيف وبناء
./mvnw clean install -DskipTests

# 6. التحقق من نجاح البناء ونسخ الملف
if [ -f "target/ja-netfilter-jar-with-dependencies.jar" ]; then
    echo -e "${GREEN}✅ البناء ناجح!${NC}"
    mkdir -p "$HOME/jetbrains-tools/ja-netfilter"
    cp target/ja-netfilter-jar-with-dependencies.jar "$HOME/jetbrains-tools/ja-netfilter/ja-netfilter.jar"
    echo -e "${GREEN}📦 تم نسخ الملف إلى: $HOME/jetbrains-tools/ja-netfilter/ja-netfilter.jar${NC}"
    ls -lh "$HOME/jetbrains-tools/ja-netfilter/ja-netfilter.jar"
else
    echo -e "${RED}❌ فشل البناء أو الملف الناتج غير موجود${NC}"
    exit 1
fi

# 7. تحديث ملف vmoptions لـ PyCharm (إضافة أعلام add-opens)
echo -e "${GREEN}⚙️ تحديث إعدادات PyCharm (إضافة أعلام add-opens)...${NC}"
mkdir -p "$HOME/.config/JetBrains/PyCharm2026.1"
cat > "$HOME/.config/JetBrains/PyCharm2026.1/pycharm64.vmoptions" << 'EOF'
-Xms128m
-Xmx2048m
-XX:ReservedCodeCacheSize=512m
-XX:+UseG1GC
--add-opens=java.base/org.objectweb.asm=ALL-UNNAMED
--add-opens=java.base/org.objectweb.asm.tree=ALL-UNNAMED
--add-opens=java.base/java.lang=ALL-UNNAMED
--add-opens=java.base/java.util=ALL-UNNAMED
--add-opens=java.base/java.net=ALL-UNNAMED
--add-opens=java.base/java.io=ALL-UNNAMED
--add-opens=java.base/java.nio=ALL-UNNAMED
--add-opens=java.base/sun.net.www=ALL-UNNAMED
--add-opens=java.base/sun.net.www.http=ALL-UNNAMED
--add-opens=java.base/sun.management=ALL-UNNAMED
-javaagent:/home/xorthomson/jetbrains-tools/ja-netfilter/ja-netfilter.jar=jetbrains
EOF

# 8. تنظيف الكاش القديم
echo -e "${GREEN}🧹 تنظيف الكاش القديم...${NC}"
rm -rf "$HOME/.config/JetBrains/PyCharm2026.1/eval"
rm -rf "$HOME/.java/.userPrefs/jetbrains"
rm -rf "$HOME/.local/share/JetBrains/PyCharm2026.1"
rm -rf "$HOME/.cache/JetBrains/PyCharm2026.1"

echo -e "${GREEN}
╔══════════════════════════════════════════════════════════════════╗
║  ✅ اكتمل الإصلاح وإعادة البناء بنجاح!                           ║
╠══════════════════════════════════════════════════════════════════╣
║  الخطوات التالية:                                                ║
║  1. شغّل PyCharm: pycharm                                         ║
║  2. افتح Help → About للتحقق من الترخيص                          ║
║  3. إذا ظهرت أخطاء 'Transform class failed' كما هو متوقع،       ║
║     فراجع البدائل أدناه.                                         ║
╚══════════════════════════════════════════════════════════════════╝
${NC}"

echo -e "${YELLOW}⚠️ تنبيه هام:${NC}"
echo "هذا السكريبت يُصلح البناء ولكنه لا يحل مشكلة التوافق مع PyCharm 2026.1 (JBR 25)."
echo "قد تظل أخطاء 'Transform class failed' قائمة."
echo ""
echo "✅ البدائل العملية (للحصول على بيئة مستقرة):"
echo "  1. استخدم PyCharm 2024.3.5 (آخر إصدار يعمل مع JBR 17):"
echo "       wget -O /tmp/pycharm-2024.3.5.tar.gz https://download.jetbrains.com/python/pycharm-professional-2024.3.5.tar.gz"
echo "       sudo tar -xzf /tmp/pycharm-2024.3.5.tar.gz -C /opt/"
echo "       sudo ln -sf /opt/pycharm-2024.3.5/bin/pycharm.sh /usr/local/bin/pycharm"
echo ""
echo "  2. ثبّت النسخة المجانية الرسمية (تدعم كل ميزات Python الأساسية):"
echo "       yay -S pycharm-community-edition"
echo ""
echo "  3. احصل على ترخيص طلابي مجاني (يدعم Professional):"
echo "       https://www.jetbrains.com/community/education/#students"
echo ""

# اختبار سريع (اختياري)
read -p "هل تريد تشغيل PyCharm مع تصحيح الأخطاء الآن؟ (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    JANF_DEBUG=1 pycharm 2>&1 | grep -E "ja-netfilter|Transform|All plugins|ERROR" | head -30
fi