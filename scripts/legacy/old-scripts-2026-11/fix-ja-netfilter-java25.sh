#!/bin/bash
# ============================================================================
# ja-netfilter Java 25 Compatibility Fix Script
# يستبدل استيراد ASM الداخلي بالاستيراد العام ويعيد البناء بـ JDK 17
# ============================================================================

set -e  # إيقاف السكريبت عند أي خطأ

# ألوان للمخرجات
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔧 بدء إصلاح ja-netfilter...${NC}"

# ============================================================
# 1. التحقق من المتطلبات والمسار
# ============================================================

# استخدام $HOME بدلاً من ~ للتوسيع الصحيح
PROJECT_DIR="$HOME/Desktop/ja-netfilter-2025.3.0"

if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${RED}❌ مجلد المشروع غير موجود: $PROJECT_DIR${NC}"
    echo -e "${YELLOW}💡 تأكد أن ja-netfilter مستخرج في ~/Desktop/ja-netfilter-2025.3.0${NC}"
    exit 1
fi

# التحقق من وجود JDK 17
if [ ! -f "/usr/lib/jvm/java-17-openjdk/bin/javac" ]; then
    echo -e "${YELLOW}⚠️  JDK 17 غير مثبت، جاري التثبيت...${NC}"
    sudo pacman -S --needed --noconfirm jdk17-openjdk
fi

cd "$PROJECT_DIR"

# ============================================================
# 2. قائمة الملفات المستهدفة للإصلاح
# ============================================================

TRANSFORMERS=(
    "src/main/java/com/janetfilter/plugins/power/ArgsTransformer.java"
    "src/main/java/com/janetfilter/plugins/dns/InetAddressTransformer.java"
    "src/main/java/com/janetfilter/plugins/hideme/VMTransformer.java"
    "src/main/java/com/janetfilter/plugins/hideme/ClassNameTransformer.java"
    "src/main/java/com/janetfilter/plugins/url/HttpClientTransformer.java"
)

# ============================================================
# 3. تطبيق الإصلاحات: استبدال الاستيراد الداخلي بالعام
# ============================================================

echo -e "${GREEN}📝 جاري تعديل ملفات Transformers...${NC}"

for file in "${TRANSFORMERS[@]}"; do
    filepath="$PROJECT_DIR/$file"
    
    if [ -f "$filepath" ]; then
        echo -e "  ✅ $file"
        
        # استبدال الاستيراد الداخلي بالاستيراد العام
        sed -i 's|import jdk\.internal\.org\.objectweb\.asm\.ClassReader;|import org.objectweb.asm.ClassReader;|g' "$filepath"
        
        # استبدال أي مراجع أخرى لـ jdk.internal.org.objectweb.asm في نفس الملف
        sed -i 's|jdk\.internal\.org\.objectweb\.asm|org.objectweb.asm|g' "$filepath"
    else
        echo -e "${RED}  ⚠️  الملف غير موجود: $filepath${NC}"
    fi
done

# ============================================================
# 4. إصلاح pom.xml: إزالة اعتمادية tools.jar القديمة
# ============================================================

echo -e "${GREEN}🔧 إصلاح pom.xml (إزالة tools.jar)...${NC}"

# إزالة كتلة الاعتمادية لـ com.sun:tools بالكامل
sed -i '/<dependency>/,/<\/dependency>/{
  /<groupId>com\.sun<\/groupId>/,/<\/dependency>/d
}' pom.xml

# التحقق من صحة البنية (اختياري)
if command -v xmllint &> /dev/null; then
    if xmllint --noout pom.xml 2>/dev/null; then
        echo -e "  ✅ pom.xml صالح"
    else
        echo -e "${YELLOW}  ⚠️  تحذير: قد يكون pom.xml به أخطاء طفيفة${NC}"
    fi
fi

# ============================================================
# 5. إعادة البناء بـ JDK 17
# ============================================================

echo -e "${GREEN}🏗️  جاري البناء بـ JDK 17...${NC}"

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk
export PATH="$JAVA_HOME/bin:$PATH"

# تنظيف وبناء
./mvnw clean install -DskipTests

# ============================================================
# 6. نسخ الناتج وتحديث المسار
# ============================================================

if [ -f "target/ja-netfilter-jar-with-dependencies.jar" ]; then
    echo -e "${GREEN}✅ البناء ناجح!${NC}"
    
    # إنشاء مجلد الوجهة إذا لم يكن موجوداً
    mkdir -p "$HOME/jetbrains-tools/ja-netfilter"
    
    # نسخ الملف
    cp target/ja-netfilter-jar-with-dependencies.jar "$HOME/jetbrains-tools/ja-netfilter/ja-netfilter.jar"
    
    echo -e "${GREEN}📦 تم نسخ الملف إلى: $HOME/jetbrains-tools/ja-netfilter/ja-netfilter.jar${NC}"
    echo -e "${GREEN}📏 الحجم: $(ls -lh "$HOME/jetbrains-tools/ja-netfilter/ja-netfilter.jar" | awk '{print $5}')${NC}"
else
    echo -e "${RED}❌ فشل البناء أو الملف الناتج غير موجود${NC}"
    exit 1
fi

# ============================================================
# 7. تحديث ملف إعدادات PyCharm (اختياري)
# ============================================================

echo -e "${GREEN}⚙️  تحديث إعدادات PyCharm...${NC}"

mkdir -p "$HOME/.config/JetBrains/PyCharm2026.1"

cat > "$HOME/.config/JetBrains/PyCharm2026.1/pycharm64.vmoptions" << 'EOF'
-Xms128m
-Xmx2048m
-XX:ReservedCodeCacheSize=512m
-XX:+UseG1GC
-XX:SoftRefLRUPolicyMSPerMB=50
-XX:CICompilerCount=2
-XX:+HeapDumpOnOutOfMemoryError
-XX:-OmitStackTraceInFastThrow
-ea
-Dsun.io.useCanonCaches=false
-Djdk.http.auth.tunneling.disabledSchemes=""
-Djdk.attach.allowAttachSelf=true
-Djdk.module.illegalAccess.silent=true
-Dkotlinx.coroutines.debug=off
--add-opens=java.base/org.objectweb.asm=ALL-UNNAMED
--add-opens=java.base/org.objectweb.asm.tree=ALL-UNNAMED
-javaagent:/home/xorthomson/jetbrains-tools/ja-netfilter/ja-netfilter.jar=jetbrains
EOF

echo -e "${GREEN}✅ تم تحديث ملف: ~/.config/JetBrains/PyCharm2026.1/pycharm64.vmoptions${NC}"

# ============================================================
# 8. تنظيف الكاش القديم
# ============================================================

echo -e "${GREEN}🧹 تنظيف الكاش القديم...${NC}"
rm -rf "$HOME/.config/JetBrains/PyCharm2026.1/eval"
rm -rf "$HOME/.java/.userPrefs/jetbrains"
rm -rf "$HOME/.local/share/JetBrains/PyCharm2026.1"
rm -rf "$HOME/.cache/JetBrains/PyCharm2026.1"

# ============================================================
# 9. الخلاصة
# ============================================================

echo -e "${GREEN}
╔════════════════════════════════════════════════════╗
║  ✅ اكتمل إصلاح ja-netfilter وإعادة البناء بنجاح!  ║
╠════════════════════════════════════════════════════╣
║  الخطوات التالية:                                   ║
║  1. شغّل PyCharm بالأمر: pycharm                   ║
║  2. راقب السجل لأخطاء 'Transform class failed'     ║
║  3. إذا ظهرت أخطاء، قد تحتاج لتعديلات إضافية      ║
╚════════════════════════════════════════════════════╝
${NC}"

# اختبار سريع (اختياري)
echo -e "${YELLOW}🧪 تشغيل اختبار سريع (اضغط Ctrl+C للإلغاء)...${NC}"
JANF_DEBUG=1 pycharm 2>&1 | grep -E "ja-netfilter|Transform|All plugins|ERROR" | head -20 || true