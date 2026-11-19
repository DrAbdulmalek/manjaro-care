#!/bin/bash
# ============================================================================
# ja-netfilter Java 25 Compatibility Fix Script - FIXED VERSION
# ============================================================================

set -e

# ألوان للمخرجات
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# استخدام $HOME بدلاً من ~ للتوسيع الصحيح
PROJECT_DIR="$HOME/Desktop/ja-netfilter-2025.3.0"

echo -e "${GREEN}🔧 بدء إصلاح ja-netfilter...${NC}"
echo -e "📁 مسار المشروع: $PROJECT_DIR"

# ============================================================
# 1. التحقق من المتطلبات
# ============================================================

if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${RED}❌ مجلد المشروع غير موجود: $PROJECT_DIR${NC}"
    echo -e "${YELLOW}💡 هل المشروع في مسار مختلف؟ عدل المتغير PROJECT_DIR في بداية السكريبت${NC}"
    exit 1
fi

if [ ! -f "/usr/lib/jvm/java-17-openjdk/bin/javac" ]; then
    echo -e "${YELLOW}⚠️  JDK 17 غير مثبت، جاري التثبيت...${NC}"
    sudo pacman -S --needed --noconfirm jdk17-openjdk
fi

# ============================================================
# 2. قائمة الملفات المستهدفة للإصلاح
# ============================================================

TRANSFORMERS=(
    "plugins/power/ArgsTransformer.java"
    "plugins/dns/InetAddressTransformer.java"
    "plugins/hideme/VMTransformer.java"
    "plugins/hideme/ClassNameTransformer.java"
    "plugins/url/HttpClientTransformer.java"
)

# ============================================================
# 3. تطبيق الإصلاحات
# ============================================================

echo -e "${GREEN}📝 جاري تعديل ملفات Transformers...${NC}"

for file in "${TRANSFORMERS[@]}"; do
    filepath="$PROJECT_DIR/src/main/java/com/janetfilter/$file"
    
    if [ -f "$filepath" ]; then
        echo -e "  ✅ $file"
        # استبدال الاستيراد الداخلي بالاستيراد العام
        sed -i 's|import jdk\.internal\.org\.objectweb\.asm\.ClassReader;|import org.objectweb.asm.ClassReader;|g' "$filepath"
        sed -i 's|jdk\.internal\.org\.objectweb\.asm|org.objectweb.asm|g' "$filepath"
    else
        echo -e "${RED}  ⚠️  الملف غير موجود: $filepath${NC}"
    fi
done

# ============================================================
# 4. إصلاح pom.xml (إزالة tools.jar)
# ============================================================

echo -e "${GREEN}🔧 إصلاح pom.xml...${NC}"
sed -i '/<dependency>/,/<\/dependency>/{
  /<groupId>com\.sun<\/groupId>/,/<\/dependency>/d
}' "$PROJECT_DIR/pom.xml"

# ============================================================
# 5. إعادة البناء بـ JDK 17
# ============================================================

echo -e "${GREEN}🏗️  جاري البناء بـ JDK 17...${NC}"
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk
export PATH="$JAVA_HOME/bin:$PATH"

cd "$PROJECT_DIR"
./mvnw clean install -DskipTests

# ============================================================
# 6. نسخ الناتج
# ============================================================

if [ -f "target/ja-netfilter-jar-with-dependencies.jar" ]; then
    echo -e "${GREEN}✅ البناء ناجح!${NC}"
    mkdir -p "$HOME/jetbrains-tools/ja-netfilter"
    cp target/ja-netfilter-jar-with-dependencies.jar "$HOME/jetbrains-tools/ja-netfilter/ja-netfilter.jar"
    echo -e "${GREEN}📦 تم نسخ الملف إلى: $HOME/jetbrains-tools/ja-netfilter/ja-netfilter.jar${NC}"
else
    echo -e "${RED}❌ فشل البناء أو الملف الناتج غير موجود${NC}"
    exit 1
fi

# ============================================================
# 7. تحديث ملف إعدادات PyCharm
# ============================================================

echo -e "${GREEN}⚙️  تحديث إعدادات PyCharm...${NC}"
mkdir -p "$HOME/.config/JetBrains/PyCharm2026.1"

cat > "$HOME/.config/JetBrains/PyCharm2026.1/pycharm64.vmoptions" << 'EOF'
-Xms128m
-Xmx2048m
-XX:ReservedCodeCacheSize=512m
-XX:+UseG1GC
--add-opens=java.base/org.objectweb.asm=ALL-UNNAMED
--add-opens=java.base/org.objectweb.asm.tree=ALL-UNNAMED
-javaagent:/home/xorthomson/jetbrains-tools/ja-netfilter/ja-netfilter.jar=jetbrains
EOF

echo -e "${GREEN}✅ اكتمل الإصلاح!${NC}"
echo -e "${YELLOW}🧪 شغّل: pycharm للتحقق${NC}"
