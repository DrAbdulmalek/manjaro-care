#!/bin/bash
# === تحديث نظام تسجيل التيرمينال مع التحسينات ===
# انسخ هذا السكربت كاملاً وشغّله في الطرفية

set -e  # توقف عند أي خطأ

echo "🔄 جاري تحديث نظام تسجيل التيرمينال..."

# 1. إنشاء نسخ احتياطية
echo "💾 إنشاء نسخ احتياطية..."
mkdir -p ~/terminal_logs/.backups
cp ~/.config/terminal-logger/auto-start.sh ~/terminal_logs/.backups/auto-start.sh.bak 2>/dev/null || true
cp ~/.config/terminal-logger/backup-upload.sh ~/terminal_logs/.backups/backup-upload.sh.bak 2>/dev/null || true
cp ~/.zshrc ~/terminal_logs/.backups/zshrc.bak 2>/dev/null || true

# 2. تحديث auto-start.sh لدعم الإيقاف/الاستئناف
echo "📝 تحديث auto-start.sh..."
cat > ~/.config/terminal-logger/auto-start.sh << 'AUTOSTART_EOF'
#!/bin/bash
# === بدء تسجيل تلقائي عند فتح التيرمينال (محدّث) ===

# تجنب التداخل
if [ -z "$SCRIPT_ACTIVE" ] && [ -z "$LOG_PAUSED" ]; then
    export SCRIPT_ACTIVE=1
    
    # إنشاء اسم ملف مع وسوم
    LOG_FILE="$HOME/terminal_logs/active/session_$(date +%Y%m%d_%H%M%S).log"
    
    # كتابة معلومات الجلسة
    {
        echo "# === Session Started: $(date -Iseconds) ==="
        echo "# USER: $USER"
        echo "# HOST: $(hostname)"
        echo "# PWD: $PWD"
        echo "# TAG: ${SESSION_TAG:-untagged}"
        echo "# ========================================="
    } >> "$LOG_FILE"
    
    # بدء التسجيل
    script -q -f "$LOG_FILE" &
    SCRIPT_PID=$!
    echo $SCRIPT_PID > /tmp/terminal_script_pid
    echo "$LOG_FILE" > /tmp/terminal_log_path
fi
AUTOSTART_EOF

chmod +x ~/.config/terminal-logger/auto-start.sh

# 3. تحديث backup-upload.sh مع تنظيف متقدم وتشفير اختياري
echo "🔐 تحديث backup-upload.sh..."
cat > ~/.config/terminal-logger/backup-upload.sh << 'BACKUP_EOF'
#!/bin/bash
# === تنظيف، ضغط، تشفير (اختياري)، ورفع جلسات التيرمينال ===

LOGS_DIR="$HOME/terminal_logs"
ACTIVE_DIR="$LOGS_DIR/active"
BACKUP_DIR="$LOGS_DIR/backup"
CLOUD_DIR="$LOGS_DIR/cloud_ready"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# إعدادات التشفير (غيّر القيمة لـ 1 لتفعيل التشفير)
ENABLE_ENCRYPTION=0
ENCRYPTION_PASS="${TERMINAL_LOG_PASS:-}"

echo "🔄 بدء عملية النسخ الاحتياطي: $TIMESTAMP"

# 1. نقل الملفات القديمة من active إلى backup
find "$ACTIVE_DIR" -name "*.log" -mmin +60 -exec mv {} "$BACKUP_DIR/" \; 2>/dev/null || true

# 2. تنظيف الملفات من البيانات الحساسة
for file in "$BACKUP_DIR"/*.log; do
    [ -f "$file" ] || continue
    
    filename=$(basename "$file")
    clean_file="$CLOUD_DIR/${filename%.log}_clean.log"
    
    echo "🧹 تنظيف: $filename"
    
    # تنظيف متقدم للبيانات الحساسة
    sed -E \
        -e 's/(password|passwd|pass|secret|api[_-]?key|apikey|token|auth|credential|private[_-]?key)[=:][^ ]*/\1=[REDACTED]/gi' \
        -e 's/(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36,}|gho_[a-zA-Z0-9]{36,}|glpat-[a-zA-Z0-9\-_]{20,})/[API_KEY_REDACTED]/g' \
        -e 's/-----BEGIN[^-]+-----/[PRIVATE_KEY_REDACTED]/g' \
        -e 's/\/home\/[^\/]+/\/home\/[USER]/g' \
        -e 's/[0-9]{1,3}(\.[0-9]{1,3}){3}/[IP]/g' \
        -e 's/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/[EMAIL]/g' \
        -e 's/(export|declare)[[:space:]]+[^=]+=[^[:space:]]*/[ENV_VAR_REDACTED]/g' \
        -e 's/(sudo|su)[[:space:]].*password.*/[SUDO_COMMAND_REDACTED]/gi' \
        -e 's/(ssh|scp|sftp)[[:space:]]+[^[:space:]]+@[^[:space:]]+/[SSH_COMMAND_REDACTED]/g' \
        "$file" > "$clean_file"
    
    # ضغط الملف
    gzip -f "$clean_file"
    compressed_file="${clean_file}.gz"
    
    # تشفير اختياري
    if [ "$ENABLE_ENCRYPTION" -eq 1 ] && [ -n "$ENCRYPTION_PASS" ]; then
        echo "🔐 تشفير: $filename"
        gpg --symmetric --cipher-algo AES256 --batch --passphrase "$ENCRYPTION_PASS" "$compressed_file"
        rm -f "$compressed_file"
        final_file="${compressed_file}.gpg"
    else
        final_file="$compressed_file"
    fi
    
    # حذف الملف الأصلي بعد المعالجة
    rm -f "$file"
    
    echo "✅ تم: $filename → $(basename "$final_file")"
done

# 3. رفع للسحابة
if command -v rclone &>/dev/null; then
    if [ -n "$(ls -A "$CLOUD_DIR"/*.gz "$CLOUD_DIR"/*.gpg 2>/dev/null)" ]; then
        echo "📤 جاري الرفع للسحابة..."
        rclone copy "$CLOUD_DIR/" remote:terminal-logs/ --progress --transfers 4
        
        # حذف الملفات بعد الرفع الناجح
        if [ $? -eq 0 ]; then
            rm -f "$CLOUD_DIR"/*.gz "$CLOUD_DIR"/*.gpg 2>/dev/null
            echo "✅ تم الرفع والحذف"
        else
            echo "⚠️  فشل الرفع، احتفظ بالملفات للمحاولة القادمة"
        fi
    else
        echo "ℹ️  لا توجد ملفات جاهزة للرفع"
    fi
else
    echo "⚠️  rclone غير موجود، تخطي الرفع"
fi

# 4. حفظ تاريخ الأوامر
history > "$LOGS_DIR/backup/history_$TIMESTAMP.txt" 2>/dev/null || true
gzip -f "$LOGS_DIR/backup/history_$TIMESTAMP.txt" 2>/dev/null || true

# 5. تنظيف الملفات القديمة (>30 يوم)
find "$LOGS_DIR/backup" -name "*.gz" -mtime +30 -delete 2>/dev/null || true
find "$LOGS_DIR/backup" -name "*.gpg" -mtime +30 -delete 2>/dev/null || true

echo "✅ اكتملت العملية: $TIMESTAMP"
BACKUP_EOF

chmod +x ~/.config/terminal-logger/backup-upload.sh

# 4. إضافة دوال متقدمة لـ .zshrc
echo "🔧 تحديث ~/.zshrc..."

# إزالة الدوال القديمة إذا وجدت
sed -i '/^# === تسجيل جلسات التيرمينال ===$/,/^# === نهاية التسجيل ===$/d' ~/.zshrc 2>/dev/null || true

# إضافة الدوال الجديدة
cat >> ~/.zshrc << 'ZSHRC_EOF'

# === نظام تسجيل التيرمينال - دوال متقدمة ===

# بدء/إيقاف التسجيل يدوياً
pause_log() {
    export LOG_PAUSED=1
    if [ -f /tmp/terminal_script_pid ]; then
        kill $(cat /tmp/terminal_script_pid) 2>/dev/null || true
        rm -f /tmp/terminal_script_pid
    fi
    echo "⏸️  تم إيقاف التسجيل مؤقتاً"
}

resume_log() {
    unset LOG_PAUSED
    source ~/.config/terminal-logger/auto-start.sh 2>/dev/null
    echo "▶️  استئناف التسجيل"
}

# وسم الجلسة الحالية
tag_session() {
    local tag="${1:-untagged}"
    if [ -f /tmp/terminal_log_path ]; then
        echo "# TAG: $tag ($(date -Iseconds))" >> "$(cat /tmp/terminal_log_path)"
        export SESSION_TAG="$tag"
        echo "🏷️  وُسّمت الجلسة بـ: $tag"
    else
        echo "⚠️  لا توجد جلسة نشطة للوسم"
    fi
}

# مراجعة عينة عشوائية قبل الرفع
review_sample() {
    local sample=$(find ~/terminal_logs/backup -name "*_clean.log" -o -name "*.log" 2>/dev/null | shuf -n 1)
    if [ -n "$sample" ] && [ -f "$sample" ]; then
        echo "🔍 مراجعة عينة: $sample"
        echo "================================"
        less -R "$sample"
        echo ""
        read -p "✅ رفع هذا الملف؟ [y/N]: " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            gzip -c "$sample" | rclone rcat remote:terminal-logs/reviewed/$(basename "$sample").gz 2>/dev/null && \
                echo "✅ تم الرفع" || echo "❌ فشل الرفع"
        else
            echo "⏭️  تخطي الملف"
        fi
    else
        echo "ℹ️  لا توجد ملفات للمراجعة"
    fi
}

# تصدير جلسة بصيغة JSON صديقة للـ AI
export_for_ai() {
    local input="${1:-$(ls -t ~/terminal_logs/backup/*_clean.log 2>/dev/null | head -1)}"
    if [ ! -f "$input" ]; then
        echo "❌ الملف غير موجود: $input"
        return 1
    fi
    
    local output="${input%.log}.json"
    echo "🤖 تصدير لـ JSON: $output"
    
    # تحويل السجل لـ JSON منظم
    awk '
    BEGIN { print "["; first=1 }
    {
        if (!first) print ","
        first=0
        gsub(/"/, "\\\"")  # هروب علامات الاقتباس
        type = "output"
        if (/^\$[[:space:]]/) { type = "command"; sub(/^\$[[:space:]]+/, "") }
        else if (/^#/) { type = "comment" }
        else if (/^🏷️|⏸️|▶️/) { type = "system" }
        printf "  {\"line\": \"%s\", \"type\": \"%s\", \"timestamp\": \"%s\"}", $0, type, strftime("%Y-%m-%dT%H:%M:%S")
    }
    END { print "\n]" }
    ' "$input" > "$output"
    
    # ضغط النتيجة
    gzip -f "$output"
    echo "✅ جاهز: ${output}.gz"
}

# تقرير أسبوعي عن استخدام التيرمينال
weekly_report() {
    local week="${1:-1 week ago}"
    echo "📊 تقرير الأسبوع: $(date +%Y-W%V)"
    echo "================================"
    
    echo ""
    echo "📁 جلسات جديدة:"
    find ~/terminal_logs/backup -name "*.gz" -newermt "$week" 2>/dev/null | wc -l | xargs echo "   "
    
    echo ""
    echo "🔤 أكثر الأوامر استخداماً:"
    zcat ~/terminal_logs/backup/*_clean.log.gz 2>/dev/null | \
        grep '^\$ ' | sed 's/^\$ //' | awk '{print $1}' | \
        sort | uniq -c | sort -rn | head -10 | sed 's/^/   /'
    
    echo ""
    echo "🏷️  الوسوم المستخدمة:"
    zcat ~/terminal_logs/backup/*_clean.log.gz 2>/dev/null | \
        grep '^# TAG:' | sed 's/^# TAG: //' | cut -d' ' -f1 | \
        sort | uniq -c | sort -rn | sed 's/^/   /'
    
    echo ""
    echo "💾 حجم النسخ الاحتياطي:"
    du -sh ~/terminal_logs/backup 2>/dev/null | awk '{print "   "$1}'
    
    echo ""
    echo "☁️  حالة السحابة:"
    if command -v rclone &>/dev/null; then
        rclone size remote:terminal-logs/ 2>/dev/null | sed 's/^/   /' || echo "   غير متصل"
    else
        echo "   rclone غير مثبت"
    fi
}

# بحث ذكي في السجلات
searchlog() {
    local query="$1"
    if [ -z "$query" ]; then
        echo "استخدام: searchlog 'كلمة البحث' [وسم]"
        echo "أمثلة:"
        echo "  searchlog pacman"
        echo "  searchlog python learning"
        return 1
    fi
    
    local tag_filter="${2:-}"
    echo "🔍 جاري البحث عن: '$query' ${tag_filter:+في وسم: $tag_filter}"
    echo "================================"
    
    local results=$(grep -r -i "$query" ~/terminal_logs/backup/ ~/terminal_logs/active/ 2>/dev/null | \
        ${tag_filter:+grep -i "# TAG: $tag_filter"} | \
        head -50)
    
    if [ -n "$results" ]; then
        echo "$results" | less -R
    else
        echo "❌ لم يتم العثور على نتائج"
    fi
}

# تنظيف شامل مع تأكيد
termlog-clean() {
    echo "🧹 تنظيف الملفات المؤقتة..."
    echo "سيتم حذف:"
    echo "  - ~/terminal_logs/active/*.log"
    echo "  - ~/terminal_logs/cloud_ready/*"
    read -p "✅ تأكيد الحذف؟ [y/N]: " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        rm -rf ~/terminal_logs/active/*.log ~/terminal_logs/cloud_ready/* 2>/dev/null
        echo "✅ تم التنظيف"
    else
        echo "⏭️  تم الإلغاء"
    fi
}

# حالة النظام مع تفاصيل إضافية
termlog-status() {
    echo "=== 📊 حالة تسجيل التيرمينال ==="
    echo ""
    
    # العدادات
    local active=$(find ~/terminal_logs/active -name "*.log" 2>/dev/null | wc -l)
    local backup=$(find ~/terminal_logs/backup -name "*.gz" -o -name "*.gpg" 2>/dev/null | wc -l)
    local cloud=$(find ~/terminal_logs/cloud_ready -type f 2>/dev/null | wc -l)
    
    echo "📁 نشط: $active ملفات"
    echo "💾 احتياطي: $backup ملفات"
    echo "☁️  للرفع: $cloud ملفات"
    echo ""
    
    # آخر عملية
    echo "🔄 آخر عملية:"
    tail -3 ~/terminal_logs/backup.log 2>/dev/null | sed 's/^/   /' || echo "   لا يوجد سجل"
    echo ""
    
    # حالة rclone
    echo "🌐 Google Drive:"
    if command -v rclone &>/dev/null && rclone listremotes 2>/dev/null | grep -q "remote:"; then
        echo "   ✅ متصل"
        rclone size remote:terminal-logs/ 2>/dev/null | sed 's/^/   /'
    else
        echo "   ❌ غير متصل"
    fi
    echo ""
    
    # جلسة حالية
    if [ -f /tmp/terminal_log_path ]; then
        echo "📝 جلسة حالية: $(cat /tmp/terminal_log_path)"
        [ -n "$SESSION_TAG" ] && echo "   🏷️ الوسم: $SESSION_TAG"
    else
        echo "📝 لا توجد جلسة نشطة"
    fi
}

# تصدير كل السجلات لملف واحد (للتدريب)
export_all_for_training() {
    local output="${1:-~/terminal_logs/training_export_$(date +%Y%m%d).jsonl}"
    echo "🤖 تصدير كل السجلات للتدريب: $output"
    
    > "$output"  # تفريغ الملف
    
    for file in ~/terminal_logs/backup/*_clean.log; do
        [ -f "$file" ] || continue
        echo "📄 معالجة: $(basename "$file")"
        
        awk -v fname="$(basename "$file")" '
        BEGIN { cmd="" }
        /^\$ / { 
            if (cmd != "") {
                gsub(/"/, "\\\"", cmd)
                printf "{\"file\":\"%s\",\"type\":\"command\",\"content\":\"%s\"}\n", fname, cmd
            }
            cmd = substr($0, 3)  # إزالة "$ "
        }
        !/^\$ / && cmd != "" {
            gsub(/"/, "\\\"", $0)
            cmd = cmd "\\n" $0
        }
        END {
            if (cmd != "") {
                gsub(/"/, "\\\"", cmd)
                printf "{\"file\":\"%s\",\"type\":\"command\",\"content\":\"%s\"}\n", fname, cmd
            }
        }
        ' "$file" >> "$output"
    done
    
    gzip -f "$output"
    echo "✅ جاهز للتدريب: ${output}.gz"
    echo "💡 حجم الملف: $(du -h "${output}.gz" | cut -f1)"
}
ZSHRC_EOF

# تطبيق التغييرات
source ~/.zshrc

# 5. تحديث cron للجدولة
echo "⏰ تحديث جدولة المهام..."
# إزالة الجدولة القديمة إن وجدت
crontab -l 2>/dev/null | grep -v "backup-upload.sh" | crontab - 2>/dev/null || true
# إضافة جدولة جديدة
(crontab -l 2>/dev/null; echo "*/30 * * * * $HOME/.config/terminal-logger/backup-upload.sh >> $HOME/terminal_logs/backup.log 2>&1") | crontab -

# 6. تفعيل خدمة cron
sudo systemctl enable --now cronie 2>/dev/null || true

echo ""
echo "✅ اكتمل التحديث بنجاح!"
echo ""
echo "📌 الأوامر الجديدة المتاحة:"
echo "   pause_log          - إيقاف التسجيل مؤقتاً"
echo "   resume_log         - استئناف التسجيل"
echo "   tag_session <وسم>  - وسم الجلسة الحالية"
echo "   review_sample      - مراجعة عينة قبل الرفع"
echo "   export_for_ai      - تصدير جلسة لـ JSON"
echo "   weekly_report      - تقرير أسبوعي"
echo "   searchlog <كلمة>   - بحث في السجلات"
echo "   termlog-clean      - تنظيف مع تأكيد"
echo "   termlog-status     - حالة النظام (محدثة)"
echo "   export_all_for_training - تصدير كل السجلات للتدريب"
echo ""
echo "🔐 لتفعيل التشفير، أضف لـ ~/.zshrc:"
echo "   export TERMINAL_LOG_PASS='كلمة_مرور_قوية'"
echo "   ثم غيّر ENABLE_ENCRYPTION=1 في backup-upload.sh"
echo ""
echo "🚀 ابدأ بـ: termlog-status"
