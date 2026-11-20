#!/bin/bash
# === تحديث نظام تسجيل التيرمينال - نسخة مصححة ===
# ⚠️  شغّل هذا WITHOUT sudo

set -e

echo "🔄 جاري تحديث نظام تسجيل التيرمينال..."

# استخدام $HOME بدلاً من المسارات المطلقة
CONFIG_DIR="$HOME/.config/terminal-logger"
LOGS_DIR="$HOME/terminal_logs"

# 1. إنشاء النسخ الاحتياطية
echo "💾 إنشاء نسخ احتياطية..."
mkdir -p "$LOGS_DIR/.backups"
[ -f "$CONFIG_DIR/auto-start.sh" ] && cp "$CONFIG_DIR/auto-start.sh" "$LOGS_DIR/.backups/auto-start.sh.bak" || true
[ -f "$CONFIG_DIR/backup-upload.sh" ] && cp "$CONFIG_DIR/backup-upload.sh" "$LOGS_DIR/.backups/backup-upload.sh.bak" || true
[ -f "$HOME/.zshrc" ] && cp "$HOME/.zshrc" "$LOGS_DIR/.backups/zshrc.bak" || true

# 2. إنشاء المجلدات
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOGS_DIR"/{active,backup,cloud_ready,screenshots}

# 3. تحديث auto-start.sh
echo "📝 تحديث auto-start.sh..."
cat > "$CONFIG_DIR/auto-start.sh" << 'AUTOSTART_EOF'
#!/bin/bash
# === بدء تسجيل تلقائي عند فتح التيرمينال ===

if [ -z "$SCRIPT_ACTIVE" ] && [ -z "$LOG_PAUSED" ]; then
    export SCRIPT_ACTIVE=1
    LOG_FILE="$HOME/terminal_logs/active/session_$(date +%Y%m%d_%H%M%S).log"
    
    {
        echo "# === Session Started: $(date -Iseconds) ==="
        echo "# USER: $USER"
        echo "# HOST: $(hostname)"
        echo "# PWD: $PWD"
        echo "# TAG: ${SESSION_TAG:-untagged}"
    } >> "$LOG_FILE"
    
    script -q -f "$LOG_FILE" &
    SCRIPT_PID=$!
    echo $SCRIPT_PID > /tmp/terminal_script_pid
    echo "$LOG_FILE" > /tmp/terminal_log_path
fi
AUTOSTART_EOF
chmod +x "$CONFIG_DIR/auto-start.sh"

# 4. تحديث backup-upload.sh
echo "🔐 تحديث backup-upload.sh..."
cat > "$CONFIG_DIR/backup-upload.sh" << 'BACKUP_EOF'
#!/bin/bash
# === تنظيف، ضغط، ورفع جلسات التيرمينال ===

LOGS_DIR="$HOME/terminal_logs"
ACTIVE_DIR="$LOGS_DIR/active"
BACKUP_DIR="$LOGS_DIR/backup"
CLOUD_DIR="$LOGS_DIR/cloud_ready"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

ENABLE_ENCRYPTION=0
ENCRYPTION_PASS="${TERMINAL_LOG_PASS:-}"

echo "🔄 بدء عملية النسخ الاحتياطي: $TIMESTAMP"

# نقل الملفات القديمة
find "$ACTIVE_DIR" -name "*.log" -mmin +60 -exec mv {} "$BACKUP_DIR/" \; 2>/dev/null || true

# تنظيف الملفات
for file in "$BACKUP_DIR"/*.log; do
    [ -f "$file" ] || continue
    filename=$(basename "$file")
    clean_file="$CLOUD_DIR/${filename%.log}_clean.log"
    
    echo "🧹 تنظيف: $filename"
    
    sed -E \
        -e 's/(password|passwd|pass|secret|api[_-]?key|token|auth|credential)[=:][^ ]*/\1=[REDACTED]/gi' \
        -e 's/(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36,})/[API_KEY_REDACTED]/g' \
        -e 's/\/home\/[^\/]+/\/home\/[USER]/g' \
        -e 's/[0-9]{1,3}(\.[0-9]{1,3}){3}/[IP]/g' \
        -e 's/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/[EMAIL]/g' \
        "$file" > "$clean_file"
    
    gzip -f "$clean_file"
    rm -f "$file"
    echo "✅ تم: $filename"
done

# رفع للسحابة
if command -v rclone &>/dev/null; then
    file_count=$(find "$CLOUD_DIR" -type f 2>/dev/null | wc -l)
    if [ "$file_count" -gt 0 ]; then
        echo "📤 جاري الرفع للسحابة..."
        rclone copy "$CLOUD_DIR/" remote:terminal-logs/ --transfers 4 2>&1 | tail -5
        
        if [ $? -eq 0 ]; then
            find "$CLOUD_DIR" -type f -delete 2>/dev/null
            echo "✅ تم الرفع والحذف"
        else
            echo "⚠️  فشل الرفع"
        fi
    else
        echo "ℹ️  لا توجد ملفات للرفع"
    fi
fi

# حفظ التاريخ
history >> "$LOGS_DIR/backup/history_$TIMESTAMP.txt" 2>/dev/null || true
gzip -f "$LOGS_DIR/backup/history_$TIMESTAMP.txt" 2>/dev/null || true

# تنظيف القديم
find "$LOGS_DIR/backup" -name "*.gz" -mtime +30 -delete 2>/dev/null || true

echo "✅ اكتملت العملية: $TIMESTAMP"
BACKUP_EOF
chmod +x "$CONFIG_DIR/backup-upload.sh"

# 5. إضافة دوال لـ .zshrc
echo "🔧 تحديث ~/.zshrc..."

# إزالة الدوال القديمة
sed -i '/# === نظام تسجيل التيرمينال/,/# === نهاية التسجيل ===/d' "$HOME/.zshrc" 2>/dev/null || true

# إضافة الدوال الجديدة (نسخة مبسطة تعمل مع zsh)
cat >> "$HOME/.zshrc" << 'ZSHRC_EOF'

# === نظام تسجيل التيرمينال - دوال ===

setopt NULL_GLOB 2>/dev/null || true

pause_log() {
    export LOG_PAUSED=1
    [ -f /tmp/terminal_script_pid ] && kill $(cat /tmp/terminal_script_pid) 2>/dev/null && rm -f /tmp/terminal_script_pid
    echo "⏸️  تم إيقاف التسجيل"
}

resume_log() {
    unset LOG_PAUSED
    source ~/.config/terminal-logger/auto-start.sh 2>/dev/null
    echo "▶️  استئناف التسجيل"
}

tag_session() {
    local tag="${1:-untagged}"
    [ -f /tmp/terminal_log_path ] && echo "# TAG: $tag ($(date -Iseconds))" >> "$(cat /tmp/terminal_log_path)"
    export SESSION_TAG="$tag"
    echo "🏷️  وسم: $tag"
}

review_sample() {
    local sample=$(find ~/terminal_logs/backup -name "*.log" -o -name "*_clean.log" 2>/dev/null | shuf -n 1)
    [ -n "$sample" ] && [ -f "$sample" ] && less -R "$sample" || echo "ℹ️  لا توجد ملفات"
}

export_for_ai() {
    local input="${1:-$(ls -t ~/terminal_logs/backup/*.log ~/terminal_logs/active/*.log 2>/dev/null | head -1)}"
    [ ! -f "$input" ] && { echo "❌ ملف غير موجود"; return 1; }
    local output="${input%.log}.json"
    echo "🤖 تصدير: $output"
    cat "$input" | jq -R -s -c 'split("\n") | map(select(length>0) | {line: .})' > "$output" 2>/dev/null || \
        awk 'BEGIN{print "["} {printf "  {\"line\": \"%s\"}%s\n", $0, (NR>1?",":"")}' "$input" > "$output"
    echo "✅ جاهز: $output"
}

weekly_report() {
    echo "📊 تقرير الأسبوع: $(date +%Y-W%V)"
    echo "📁 جلسات: $(find ~/terminal_logs/backup -name "*.gz" 2>/dev/null | wc -l)"
    echo "💾 الحجم: $(du -sh ~/terminal_logs/backup 2>/dev/null | cut -f1)"
}

searchlog() {
    local query="$1"
    [ -z "$query" ] && { echo "استخدم: searchlog 'كلمة'"; return 1; }
    grep -r -i "$query" ~/terminal_logs/ 2>/dev/null | head -20 | less -R
}

termlog-clean() {
    echo "🧹 تنظيف..."
    rm -rf ~/terminal_logs/active/*.log ~/terminal_logs/cloud_ready/* 2>/dev/null
    echo "✅ تم"
}

termlog-status() {
    echo "=== 📊 حالة التسجيل ==="
    echo "📁 نشط: $(find ~/terminal_logs/active -name "*.log" 2>/dev/null | wc -l)"
    echo "💾 احتياطي: $(find ~/terminal_logs/backup -type f 2>/dev/null | wc -l)"
    echo "☁️  للرفع: $(find ~/terminal_logs/cloud_ready -type f 2>/dev/null | wc -l)"
    echo "🌐 Drive: $(rclone listremotes 2>/dev/null | grep -q remote: && echo '✅' || echo '❌')"
    [ -f /tmp/terminal_log_path ] && echo "📝 جلسة: $(cat /tmp/terminal_log_path)"
}

export_all_for_training() {
    local output="$HOME/terminal_logs/training_export_$(date +%Y%m%d).jsonl"
    echo "🤖 تصدير للتدريب: $output"
    > "$output"
    for file in ~/terminal_logs/backup/*.log ~/terminal_logs/active/*.log; do
        [ -f "$file" ] || continue
        while IFS= read -r line; do
            [[ "$line" =~ ^\$[[:space:]] ]] && echo "{\"type\":\"command\",\"content\":\"${line#\$ }\"}" >> "$output"
        done < "$file"
    done
    gzip -f "$output"
    echo "✅ جاهز: ${output}.gz"
}
ZSHRC_EOF

# تطبيق التغييرات
source "$HOME/.zshrc"

# 6. تحديث cron
echo "⏰ تحديث الجدولة..."
crontab -l 2>/dev/null | grep -v "backup-upload.sh" | crontab - 2>/dev/null || true
(crontab -l 2>/dev/null; echo "*/30 * * * * $CONFIG_DIR/backup-upload.sh >> $LOGS_DIR/backup.log 2>&1") | crontab -
sudo systemctl enable --now cronie 2>/dev/null || true

echo ""
echo "✅ اكتمل التحديث!"
echo ""
echo "📌 الأوامر المتاحة:"
echo "   termlog-status    pause_log    resume_log"
echo "   tag_session       review_sample"
echo "   export_for_ai     weekly_report"
echo "   searchlog         termlog-clean"
echo "   export_all_for_training"
echo ""
echo "⚠️  ملاحظة: شغّل الأوامر بدون sudo"
