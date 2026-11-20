#!/bin/bash

# =============================================================================
# سكريبت تثبيت إضافات PyCharm على Manjaro Linux
# تم التعديل لتعطيل ja-netfilter مؤقتاً وتجنب الأخطاء
# =============================================================================

# --- 1. تعطيل أي Java agents خارجية (مثل ja-netfilter) لهذه الجلسة ---
unset JAVA_TOOL_OPTIONS
unset _JAVA_OPTIONS
# إذا كنت تستخدم متغيرات أخرى مثل JDK_JAVA_OPTIONS، أضفها هنا
# unset JDK_JAVA_OPTIONS

# --- 2. قائمة معرفات الإضافات المراد تثبيتها ---
# هذه المعرفات مستخرجة من متجر JetBrains الرسمي
PLUGINS=(
  "7219"      # Symfony Support
  "7499"      # GitToolBox
  "8006"      # Material Theme UI
  "8286"      # SequenceDiagram
  "9238"      # JetForcer | The Smartest Force.com IDE
  "9564"      # React Native Console
  "9739"      # Yaoqiang BPMN Editor
  "9863"      # AEM Support
  "10080"     # Rainbow Brackets
  "10695"     # SystemVerilog
  "10925"     # Database Tools and SQL for WebStorm & RustRover
  "12132"     # LeetCode Editor Pro (Marketplace Edition)
  "12437"     # ZenUML Support
  "12626"     # OrchidE - Ansible Language Support
  "12867"     # Hybris Integration (SAP Commerce Developers Toolset)
  "13151"     # OfficeFloor
  "13156"     # Android WiFiADB
  "13441"     # Laravel Idea
  "13838"     # RDF and SPARQL
  "13841"     # BashSupport Pro
  "14384"     # Toolset
  "14512"     # Elasticsearch
  "14557"     # JDK VisualGC
  "14718"     # Flutter Storm
  "14723"     # RestfulBox
  "14821"     # PlantUML Studio
  "14896"     # Code With Me
  "15189"     # Firebase Rules
  "15457"     # Gitlab CI Pipeline Dashboard
  "16141"     # k6
  "16682"     # Applet Runner
  "18232"     # Typed Django Template
  "22202"     # GitLab CICD - Pipelines & Jobs, Builds Run Cancel Retry View Log
  "25039"     # OpenCV Image Viewer (PixelLens)
)

# --- 3. مسار تطبيق PyCharm (تم التحقق منه بـ `which pycharm`) ---
PYCHARM_BIN="/usr/local/bin/pycharm"

# --- 4. التحقق من وجود PyCharm ---
if [ ! -f "$PYCHARM_BIN" ]; then
    echo "❌ خطأ: لم يتم العثور على PyCharm في المسار '$PYCHARM_BIN'."
    echo "   تأكد من تثبيته بشكل صحيح."
    exit 1
fi

# --- 5. تأكيد إغلاق PyCharm ---
echo "⚠️  تنبيه: يجب إغلاق PyCharm بالكامل قبل المتابعة."
read -p "   هل PyCharm مغلق حالياً؟ (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ يرجى إغلاق PyCharm ثم إعادة تشغيل السكريبت."
    exit 1
fi

# --- 6. تنفيذ التثبيت ---
echo "🚀 جاري تثبيت ${#PLUGINS[@]} إضافة على PyCharm..."
echo "   (قد تستغرق هذه العملية بضع دقائق، لا تقاطعها)"
echo ""

# تشغيل أمر التثبيت
"$PYCHARM_BIN" installPlugins "${PLUGINS[@]}"

# --- 7. التحقق من نتيجة التثبيت ---
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ تم تثبيت الإضافات بنجاح."
    echo "   يمكنك الآن فتح PyCharm والذهاب إلى File → Settings → Plugins للتأكد."
    echo ""
    echo "ℹ️  تذكير:"
    echo "   - بعض الإضافات مدفوعة وتحتاج إلى ترخيص منفصل."
    echo "   - إضافات PHP مثل Symfony Support / Laravel Idea لن تكون مفيدة في PyCharm."
else
    echo ""
    echo "❌ حدث خطأ أثناء التثبيت. قد تكون بعض الإضافات غير متوافقة مع نسختك."
    echo "   جرب تثبيت الإضافات يدوياً من داخل PyCharm (Marketplace)."
fi

exit 0
