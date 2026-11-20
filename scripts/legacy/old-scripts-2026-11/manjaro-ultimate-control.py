#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manjaro Ultimate Control Center — مركز التحكم الشامل
الإصدار: 2.0 Pro (مصحح + محسّن)
يجمع: إدارة النظام + تحويل ويندوز 11 + تسجيل التيرمينال + مراقبة حية
"""

import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
import psutil

# ─── إعداد المظهر العام ──────────────────────────────────────────────────────
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ─── ثوابت التطبيق ────────────────────────────────────────────────────────────
HOME = Path.home()
LOGS_DIR = HOME / "terminal_logs"
CONFIG_DIR = HOME / ".config" / "manjaro-ultimate-control"
PLUGIN_DIR = HOME / ".local" / "share" / "manjaro-ultimate-control" / "plugins"

# ─── فئة التطبيق الرئيسي ──────────────────────────────────────────────────────
class ManjaroUltimateApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("🐧 Manjaro Ultimate Control Center — مركز التحكم الشامل")
        self.geometry("1200x750")
        self.minsize(1000, 650)

        # تهيئة المجلدات
        self._init_directories()

        # إنشاء الهيكل الرئيسي (Grid)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ─── الشريط الجانبي ──────────────────────────────────────────────────
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color="#1e293b")
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        # الشعار
        self.logo_label = ctk.CTkLabel(
            self.sidebar,
            text="🐧 التحكم الشامل",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#4ade80"
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=20)

        # ─── أزرار التنقل ────────────────────────────────────────────────────
        nav_buttons = [
            ("📊 لوحة المعلومات", "dashboard"),
            ("🔧 النظام والصيانة", "system"),
            ("🎨 تحويل لـ Windows 11", "win11"),
            ("📝 تسجيل التيرمينال", "terminal"),
            ("🔐 الأمان", "security"),
            ("🛠️ أدوات متقدمة", "tools"),
        ]

        for idx, (text, frame_name) in enumerate(nav_buttons, start=1):
            btn = ctk.CTkButton(
                self.sidebar,
                text=text,
                command=lambda f=frame_name: self.show_frame(f),
                fg_color="transparent",
                border_width=1,
                border_color="#334155",
                hover_color="#334155",
                anchor="w"
            )
            btn.grid(row=idx, column=0, padx=15, pady=5, sticky="ew")

        # ─── شاشة العرض الرئيسية ─────────────────────────────────────────────
        self.main_view = ctk.CTkFrame(self, corner_radius=15, fg_color="#0f172a")
        self.main_view.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.main_view.grid_columnconfigure(0, weight=1)

        self.current_frame = None
        self.show_frame("dashboard")

        # ─── شريط الحالة السفلي ──────────────────────────────────────────────
        self.status_bar = ctk.CTkFrame(self, height=40, fg_color="#1e293b")
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 10))

        self.status_label = ctk.CTkLabel(
            self.status_bar,
            text="✅ جاهز",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        )
        self.status_label.pack(side="left", padx=15)

        self.clock_label = ctk.CTkLabel(
            self.status_bar,
            text=f"🕐 {datetime.now().strftime('%H:%M:%S')}",
            font=ctk.CTkFont(size=11),
            text_color="#3b82f6"
        )
        self.clock_label.pack(side="right", padx=15)

        # تحديث الساعة كل ثانية
        self._update_clock()

        # بدء مراقبة النظام في الخلفية
        self._start_system_monitor()

    # ─── تهيئة المجلدات ──────────────────────────────────────────────────────
    def _init_directories(self):
        """إنشاء المجلدات المطلوبة"""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        (LOGS_DIR / "active").mkdir(exist_ok=True)
        (LOGS_DIR / "backup").mkdir(exist_ok=True)
        (LOGS_DIR / "cloud_ready").mkdir(exist_ok=True)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)

    # ─── عرض الإطار ──────────────────────────────────────────────────────────
    def show_frame(self, frame_type):
        if self.current_frame:
            self.current_frame.destroy()

        self.current_frame = ctk.CTkScrollableFrame(
            self.main_view,
            fg_color="transparent",
            scrollbar_button_color="#334155",
            scrollbar_button_hover_color="#475569"
        )
        self.current_frame.pack(fill="both", expand=True, padx=10, pady=10)

        frame_methods = {
            "dashboard": self._render_dashboard,
            "system": self._render_system_view,
            "win11": self._render_win11_view,
            "terminal": self._render_terminal_view,
            "security": self._render_security_view,
            "tools": self._render_tools_view,
        }

        if frame_type in frame_methods:
            frame_methods[frame_type]()

    # ─── لوحة المعلومات ──────────────────────────────────────────────────────
    def _render_dashboard(self):
        title = ctk.CTkLabel(
            self.current_frame,
            text="📊 لوحة المعلومات الحية",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#4ade80"
        )
        title.pack(anchor="w", pady=(0, 20))

        # بطاقات الإحصائيات
        stats_frame = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        stats_frame.pack(fill="x", pady=10)

        self.stats_labels = {}
        stats_config = [
            ("🔥 المعالج", "cpu", "#ef4444"),
            ("💾 الذاكرة", "ram", "#3b82f6"),
            ("💿 القرص", "disk", "#22c55e"),
            ("⏱️ التشغيل", "uptime", "#f59e0b"),
        ]

        for idx, (label, key, color) in enumerate(stats_config):
            card = ctk.CTkFrame(stats_frame, fg_color="#1e293b", corner_radius=10)
            card.grid(row=0, column=idx, padx=10, pady=5, sticky="ew")
            stats_frame.columnconfigure(idx, weight=1)

            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(pady=(10, 4))
            val_label = ctk.CTkLabel(card, text="...", font=ctk.CTkFont(size=22, weight="bold"), text_color=color)
            val_label.pack(pady=(0, 10))
            self.stats_labels[key] = val_label

        # أزرار سريعة
        quick_frame = ctk.CTkFrame(self.current_frame, fg_color="#1e293b", corner_radius=10)
        quick_frame.pack(fill="x", pady=20)

        ctk.CTkLabel(quick_frame, text="⚡ إجراءات سريعة", font=ctk.CTkFont(size=14, weight="bold"), text_color="#4ade80").pack(anchor="w", padx=15, pady=(10, 5))

        quick_actions = [
            ("🔄 تحديث النظام", "pamac checkupdates && pamac upgrade --no-confirm", True),
            ("🧹 تنظيف الحزم", "sudo pacman -Rns $(pacman -Qtdq) --noconfirm 2>/dev/null || echo 'لا توجد حزم يتيمة'", True),
            ("💾 نسخة احتياطية", "timeshift --create --comments 'UI Backup'", True),
            ("📊 فحص التثبيت", "bash ~/verify-setup.sh 2>/dev/null || echo 'الملف غير موجود'", False),
        ]

        for text, cmd, need_pkexec in quick_actions:
            ctk.CTkButton(
                quick_frame,
                text=text,
                command=lambda c=cmd, p=need_pkexec: self._run_command(c, use_pkexec=p),
                fg_color="#22c55e",
                hover_color="#16a34a"
            ).pack(side="left", padx=10, pady=10)

        # سجل الإخراج
        self.log_output = ctk.CTkTextbox(self.current_frame, height=150, fg_color="#0a0a0a", text_color="#4ade80", font=ctk.CTkFont(family="monospace", size=10))
        self.log_output.pack(fill="x", pady=10)
        self._log("✅ مركز التحكم جاهز — " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # ─── النظام والصيانة ─────────────────────────────────────────────────────
    def _render_system_view(self):
        self._create_section_title("🔧 أدوات صيانة وتحسين النظام")

        actions = [
            ("🔄 تحديث النظام الكامل", "pamac checkupdates && pamac upgrade --no-confirm", True),
            ("🧹 تنظيف الحزم اليتيمة", "sudo pacman -Rns $(pacman -Qtdq) --noconfirm 2>/dev/null || echo 'لا توجد حزم يتيمة'", True),
            ("💿 تحسين أداء الـ SSD", "sudo fstrim -av", True),
            ("💾 إنشاء نسخة احتياطية (Timeshift)", "timeshift --create --comments 'Manual UI Backup'", True),
            ("📋 عرض نقاط الاستعادة", "timeshift --list", False),
            ("🗑️ تنظيف Journal القديم", "sudo journalctl --vacuum-time=7d", True),
            ("📊 معلومات النظام", "neofetch 2>/dev/null || fastfetch 2>/dev/null || echo 'neofetch غير مثبت'", False),
        ]

        for text, cmd, need_pkexec in actions:
            self._create_action_button(text, cmd, need_pkexec)

    # ─── تحويل ويندوز 11 ─────────────────────────────────────────────────────
    def _render_win11_view(self):
        self._create_section_title("🎨 تحويل الواجهة إلى Windows 11 (KDE)")

        win_actions = [
            ("🪟 تثبيت ثيمات Fluent و Windows 11", "pamac build plasma5-themes-fluent-git --no-confirm 2>/dev/null || yay -S plasma5-themes-fluent-git --noconfirm 2>/dev/null || echo 'يحتاج AUR'", False),
            ("🎨 تثبيت أيقونات Papirus", "sudo pacman -S papirus-icon-theme --needed --noconfirm", True),
            ("🔤 تثبيت خطوط Windows 11", "yay -S ttf-ms-win11-auto --noconfirm 2>/dev/null || echo 'يحتاج AUR'", False),
            ("⚙️ تطبيق تخطيط شريط المهام المركزي", "echo '💡 اضبطها يدوياً من إعدادات اللوحة في KDE → شريط المهام → محاذاة: وسط'", False),
            ("🌙 تفعيل الوضع الداكن", "lookandfeeltool --apply org.kde.breezedark.desktop 2>/dev/null || echo 'يحتاج KDE'", False),
        ]

        for text, cmd, need_pkexec in win_actions:
            self._create_action_button(text, cmd, need_pkexec, color="#2b5797")

    # ─── تسجيل التيرمينال ────────────────────────────────────────────────────
    def _render_terminal_view(self):
        self._create_section_title("📝 إدارة سجلات ومدخلات التيرمينال")

        # أزرار التحكم في التسجيل
        control_frame = ctk.CTkFrame(self.current_frame, fg_color="#1e293b", corner_radius=10)
        control_frame.pack(fill="x", pady=10)

        ctk.CTkButton(
            control_frame,
            text="▶️ بدء/استئناف تسجيل الجلسة",
            fg_color="#22c55e",
            hover_color="#16a34a",
            command=lambda: self._run_command(f"mkdir -p {LOGS_DIR}/active && script -q -f {LOGS_DIR}/active/session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", use_pkexec=False)
        ).pack(side="left", padx=10, pady=10)

        ctk.CTkButton(
            control_frame,
            text="⏸️ إيقاف التسجيل مؤقتاً",
            fg_color="#f59e0b",
            hover_color="#d97706",
            command=lambda: self._run_command("pkill -f 'script -q -f'", use_pkexec=False)
        ).pack(side="left", padx=10, pady=10)

        ctk.CTkButton(
            control_frame,
            text="📚 دمج وتصدير السجلات الشامل",
            fg_color="#3b82f6",
            hover_color="#2563eb",
            command=lambda: self._merge_logs()
        ).pack(side="left", padx=10, pady=10)

        ctk.CTkButton(
            control_frame,
            text="🗑️ تنظيف السجلات المؤقتة",
            fg_color="#ef4444",
            hover_color="#dc2626",
            command=lambda: self._run_command(f"rm -rf {LOGS_DIR}/active/*.log {LOGS_DIR}/cloud_ready/*.gz 2>/dev/null", use_pkexec=False)
        ).pack(side="left", padx=10, pady=10)

        # معلومات عن السجلات
        info_frame = ctk.CTkFrame(self.current_frame, fg_color="#1e293b", corner_radius=10)
        info_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(info_frame, text="📊 حالة سجلات التيرمينال", font=ctk.CTkFont(size=14, weight="bold"), text_color="#4ade80").pack(anchor="w", padx=15, pady=10)

        # حساب الإحصائيات
        try:
            active_count = len(list((LOGS_DIR / "active").glob("*.log")))
            backup_count = len(list((LOGS_DIR / "backup").glob("*.gz"))) + len(list((LOGS_DIR / "backup").glob("*.log")))
            total_size = subprocess.run(f"du -sh {LOGS_DIR} 2>/dev/null | cut -f1", shell=True, capture_output=True, text=True).stdout.strip() or "0B"
        except:
            active_count = backup_count = 0
            total_size = "غير متاح"

        stats_text = f"📁 نشط: {active_count} ملفات | 💾 احتياطي: {backup_count} ملفات | 📦 الحجم الكلي: {total_size}"
        ctk.CTkLabel(info_frame, text=stats_text, font=ctk.CTkFont(size=12), text_color="#94a3b8").pack(anchor="w", padx=15, pady=(0, 10))

        # سجل الإخراج
        self.log_output = ctk.CTkTextbox(self.current_frame, height=200, fg_color="#0a0a0a", text_color="#4ade80", font=ctk.CTkFont(family="monospace", size=10))
        self.log_output.pack(fill="both", expand=True, pady=10)

    # ─── الأمان ──────────────────────────────────────────────────────────────
    def _render_security_view(self):
        self._create_section_title("🔐 الأمان والحماية")

        security_actions = [
            ("🔥 تفعيل جدار الحماية (UFW)", "sudo ufw enable && sudo ufw status verbose", True),
            ("🚫 تعطيل جدار الحماية", "sudo ufw disable", True),
            ("📊 عرض حالة الجدار", "sudo ufw status verbose", True),
            ("🦠 تحديث قواعد ClamAV", "sudo freshclam", True),
            ("🔍 فحص مجلد Downloads", "clamscan -r ~/Downloads/ 2>/dev/null | tail -5", False),
            ("🔑 فتح KeePassXC", "keepassxc &", False),
            ("📋 فحص التحديثات الأمنية", "checkupdates 2>/dev/null || sudo pacman -Qu", False),
        ]

        for text, cmd, need_pkexec in security_actions:
            self._create_action_button(text, cmd, need_pkexec)

    # ─── أدوات متقدمة ───────────────────────────────────────────────────────
    def _render_tools_view(self):
        self._create_section_title("🛠️ أدوات متقدمة")

        tools_actions = [
            ("🔬 فتح Radare2", "xterm -e 'radare2 --help' &", False),
            ("🎯 فتح Cutter (واجهة r2)", "cutter &", False),
            ("🐳 حالة Docker", "sudo systemctl status docker | head -8", True),
            ("🐳 تفعيل Docker", "sudo systemctl enable --now docker && sudo usermod -aG docker $USER", True),
            ("🖥️ تفعيل libvirtd (KVM)", "sudo systemctl enable --now libvirtd && sudo usermod -aG libvirt,kvm $USER", True),
            ("🖥️ فتح Virt-Manager", "virt-manager &", False),
            ("📡 فحص دعم KVM", "kvm-ok 2>/dev/null || lscpu | grep -i 'vmx\\|svm'", False),
        ]

        for text, cmd, need_pkexec in tools_actions:
            self._create_action_button(text, cmd, need_pkexec)

    # ─── دوال مساعدة ────────────────────────────────────────────────────────
    def _create_section_title(self, text):
        label = ctk.CTkLabel(
            self.current_frame,
            text=text,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#4ade80"
        )
        label.pack(anchor="w", pady=(0, 15))

    def _create_action_button(self, text, command, need_pkexec=False, color="#22c55e"):
        btn = ctk.CTkButton(
            self.current_frame,
            text=text,
            command=lambda c=command, p=need_pkexec: self._run_command(c, use_pkexec=p),
            fg_color=color,
            hover_color=self._darken_color(color)
        )
        btn.pack(pady=5, padx=20, fill="x")

    def _darken_color(self, hex_color):
        """تغميق اللون للـ hover"""
        try:
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
            return f"#{max(0, r-30):02x}{max(0, g-30):02x}{max(0, b-30):02x}"
        except:
            return hex_color

    def _run_command(self, cmd, use_pkexec=False):
        """تنفيذ أمر في خيط منفصل مع معالجة الصلاحيات"""
        def thread_run():
            try:
                self._log(f"⚙️ جاري: {cmd[:80]}...", "#60a5fa")
                self.status_label.configure(text="⏳ جاري التنفيذ...", text_color="#f59e0b")

                # استخدام pkexec للأوامر التي تحتاج صلاحيات
                if use_pkexec and not cmd.startswith("pkexec"):
                    cmd = f"pkexec {cmd}"

                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env={**os.environ, "TERM": "xterm"}
                )
                stdout, stderr = process.communicate(timeout=180)

                if stdout.strip():
                    self._log(stdout.strip()[:1000])
                if stderr.strip():
                    self._log(f"⚠️ {stderr.strip()[:1000]}", "#fbbf24")

                status = "✅" if process.returncode == 0 else "⚠️"
                self._log(f"{status} اكتمل — كود الخروج: {process.returncode}", "#4ade80" if process.returncode == 0 else "#fbbf24")
                self.status_label.configure(text="✅ اكتمل", text_color="#4ade80")

            except subprocess.TimeoutExpired:
                self._log("⏱️ انتهت مهلة الأمر (180 ثانية)", "#fbbf24")
                self.status_label.configure(text="⏱️ مهلة انتهت", text_color="#fbbf24")
            except Exception as e:
                self._log(f"❌ خطأ: {str(e)}", "#f87171")
                self.status_label.configure(text="❌ خطأ", text_color="#f87171")

        threading.Thread(target=thread_run, daemon=True).start()

    def _merge_logs(self):
        """دمج سجلات التيرمينال"""
        def thread_merge():
            try:
                self._log("🔄 جاري دمج السجلات...", "#60a5fa")
                output_file = LOGS_DIR / f"merged_{datetime.now().strftime('%Y%m%d')}.log"

                with open(output_file, 'w', encoding='utf-8') as outfile:
                    for subdir in ['active', 'backup']:
                        dir_path = LOGS_DIR / subdir
                        if dir_path.exists():
                            for log_file in dir_path.glob("*.log"):
                                with open(log_file, 'r', encoding='utf-8', errors='ignore') as infile:
                                    outfile.write(f"\n# === {log_file.name} ===\n")
                                    outfile.write(infile.read())
                            for gz_file in dir_path.glob("*.gz"):
                                import gzip
                                try:
                                    with gzip.open(gz_file, 'rt', encoding='utf-8', errors='ignore') as infile:
                                        outfile.write(f"\n# === {gz_file.name} ===\n")
                                        outfile.write(infile.read())
                                except:
                                    pass

                size = subprocess.run(f"du -h {output_file} | cut -f1", shell=True, capture_output=True, text=True).stdout.strip()
                self._log(f"✅ تم الدمج: {output_file} ({size})", "#4ade80")
                self.status_label.configure(text="✅ تم الدمج", text_color="#4ade80")

            except Exception as e:
                self._log(f"❌ فشل الدمج: {str(e)}", "#f87171")

        threading.Thread(target=thread_merge, daemon=True).start()

    def _log(self, text, color="#4ade80"):
        """إضافة سجل إلى الكونسول"""
        if hasattr(self, 'log_output'):
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_output.insert("end", f"[{timestamp}] {text}\n", color)
            self.log_output.see("end")

    def _update_clock(self):
        """تحديث الساعة كل ثانية"""
        self.clock_label.configure(text=f"🕐 {datetime.now().strftime('%H:%M:%S')}")
        self.after(1000, self._update_clock)

    def _start_system_monitor(self):
        """بدء مراقبة النظام في الخلفية"""
        def monitor():
            while True:
                try:
                    cpu = psutil.cpu_percent(interval=0.5)
                    ram = psutil.virtual_memory().percent
                    disk = psutil.disk_usage('/').percent
                    uptime_s = psutil.boot_time()
                    uptime = datetime.now() - datetime.fromtimestamp(uptime_s)
                    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
                    minutes = remainder // 60

                    if hasattr(self, 'stats_labels'):
                        self.stats_labels["cpu"].configure(text=f"{cpu:.1f}%", text_color="#ef4444" if cpu > 80 else "#4ade80")
                        self.stats_labels["ram"].configure(text=f"{ram:.1f}%", text_color="#f59e0b" if ram > 85 else "#3b82f6")
                        self.stats_labels["disk"].configure(text=f"{disk:.1f}%", text_color="#f59e0b" if disk > 90 else "#22c55e")
                        self.stats_labels["uptime"].configure(text=f"{hours}h {minutes}m")
                except:
                    pass
                threading.Event().wait(5)

        threading.Thread(target=monitor, daemon=True).start()

# ─── تشغيل التطبيق ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        app = ManjaroUltimateApp()
        app.mainloop()
    except Exception as e:
        print(f"❌ خطأ فادح: {e}")
        import traceback
        traceback.print_exc()
