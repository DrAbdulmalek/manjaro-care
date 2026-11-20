#!/usr/bin/env python3
# ==============================================================================
# Manjaro Control Center — مركز تحكم مانجارو
# واجهة رسومية بسيطة لكل الأوامر والإعدادات
# ==============================================================================

import subprocess
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk


class ManjaroControlCenter:
    def __init__(self, root):
        self.root = root
        self.root.title("🐧 مركز تحكم مانجارو v1.0")
        self.root.geometry("900x700")
        self.root.configure(bg='#1e1e2e')

        # إنشاء التبويبات
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # تبويبات الأقسام
        self.tabs = {
            '🏠 الرئيسية': self.create_home_tab(),
            '🔄 النظام': self.create_system_tab(),
            '🔐 الأمان': self.create_security_tab(),
            '🎨 المظهر': self.create_appearance_tab(),
            '🛠️ الأدوات': self.create_tools_tab(),
            '📝 السجلات': self.create_logs_tab(),
        }

        for name, frame in self.tabs.items():
            self.notebook.add(frame, text=name)

        # شريط الحالة
        self.status_bar = ttk.Label(root, text="جاهز", relief='sunken', anchor='w')
        self.status_bar.pack(fill='x', padx=10, pady=5)

    def run_command(self, command, description):
        """تشغيل أمر وعرض النتيجة"""
        self.status_bar.config(text=f"جاري: {description}...")
        self.root.update()

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                messagebox.showinfo("✅ نجاح", f"{description}\n\n{result.stdout[:500]}")
                self.status_bar.config(text="✅ اكتمل بنجاح")
            else:
                messagebox.showerror("❌ خطأ", f"{description}\n\n{result.stderr[:500]}")
                self.status_bar.config(text="❌ فشل")
        except subprocess.TimeoutExpired:
            messagebox.showwarning("⏱️ مهلة", "الأمر استغرق وقتاً طويلاً")
            self.status_bar.config(text="⏱️ مهلة انتهت")
        except Exception as e:
            messagebox.showerror("❌ خطأ", str(e))
            self.status_bar.config(text="❌ خطأ")

    def create_home_tab(self):
        """الصفحة الرئيسية"""
        frame = ttk.Frame(self.notebook)

        # ترحيب
        welcome = ttk.Label(frame, text="🐧 مركز تحكم مانجارو", font=('Arial', 24, 'bold'))
        welcome.pack(pady=20)

        info = ttk.Label(frame, text="جميع أدواتك في مكان واحد", font=('Arial', 12))
        info.pack(pady=10)

        # أزرار سريعة
        quick_frame = ttk.LabelFrame(frame, text="⚡ إجراءات سريعة", padding=10)
        quick_frame.pack(fill='x', padx=20, pady=10)

        buttons = [
            ("🔄 تحديث النظام", "sudo pacman -Syu --noconfirm", "تحديث النظام"),
            ("🧹 تنظيف النظام", "sudo pacman -Sc --noconfirm && sudo pacman -Rns $(pacman -Qtdq) --noconfirm", "تنظيف النظام"),
            ("💾 نسخة احتياطية", "timeshift --create --comments 'Manual Backup'", "إنشاء نسخة احتياطية"),
            ("🔍 فحص التثبيت", "bash ~/verify-setup.sh", "فحص التثبيت"),
            ("🚀 إعادة التشغيل", "sudo reboot", "إعادة التشغيل"),
        ]

        for text, cmd, desc in buttons:
            btn = ttk.Button(quick_frame, text=text, command=lambda c=cmd, d=desc: self.run_command(c, d))
            btn.pack(fill='x', pady=2)

        # معلومات النظام
        info_frame = ttk.LabelFrame(frame, text="📊 معلومات النظام", padding=10)
        info_frame.pack(fill='both', expand=True, padx=20, pady=10)

        # جلب المعلومات
        try:
            info_text = subprocess.check_output("uname -a && echo '' && free -h && echo '' && df -h /", shell=True, text=True)
            info_display = scrolledtext.ScrolledText(info_frame, height=10, wrap='word')
            info_display.insert('1.0', info_text)
            info_display.config(state='disabled')
            info_display.pack(fill='both', expand=True)
        except:
            ttk.Label(info_frame, text="تعذر جلب المعلومات").pack()

        return frame

    def create_system_tab(self):
        """تبويب النظام"""
        frame = ttk.Frame(self.notebook)

        # تحديث
        update_frame = ttk.LabelFrame(frame, text="🔄 التحديث والصيانة", padding=10)
        update_frame.pack(fill='x', padx=20, pady=10)

        updates = [
            ("تحديث كامل", "sudo pacman -Syu --noconfirm"),
            ("تحديث المرايا", "sudo pacman-mirrors --fasttrack 10 --api"),
            ("تنظيف cache", "sudo pacman -Sc --noconfirm"),
            ("إزالة حزم يتيمة", "sudo pacman -Rns $(pacman -Qtdq) --noconfirm"),
            ("تحديث AUR", "yay -Syu --noconfirm"),
        ]

        for text, cmd in updates:
            ttk.Button(update_frame, text=text, command=lambda c=cmd: self.run_command(c, text)).pack(fill='x', pady=2)

        # خدمات
        service_frame = ttk.LabelFrame(frame, text="⚙️ الخدمات", padding=10)
        service_frame.pack(fill='x', padx=20, pady=10)

        services = [
            ("تفعيل Docker", "sudo systemctl enable --now docker"),
            ("تفعيل libvirtd", "sudo systemctl enable --now libvirtd"),
            ("تفعيل OneDrive", "systemctl --user enable --now onedrive"),
            ("تفعيل SSH", "sudo systemctl enable --now sshd"),
        ]

        for text, cmd in services:
            ttk.Button(service_frame, text=text, command=lambda c=cmd: self.run_command(c, text)).pack(fill='x', pady=2)

        return frame

    def create_security_tab(self):
        """تبويب الأمان"""
        frame = ttk.Frame(self.notebook)

        # جدار ناري
        firewall_frame = ttk.LabelFrame(frame, text="🔥 الجدار الناري (UFW)", padding=10)
        firewall_frame.pack(fill='x', padx=20, pady=10)

        firewall_cmds = [
            ("تفعيل الجدار", "sudo ufw enable"),
            ("تعطيل الجدار", "sudo ufw disable"),
            ("عرض الحالة", "sudo ufw status verbose"),
            ("سماح SSH", "sudo ufw allow ssh"),
            ("سماح RustDesk", "sudo ufw allow 21115:21119/tcp"),
        ]

        for text, cmd in firewall_cmds:
            ttk.Button(firewall_frame, text=text, command=lambda c=cmd: self.run_command(c, text)).pack(fill='x', pady=2)

        # أمان
        security_frame = ttk.LabelFrame(frame, text="🔐 أدوات الأمان", padding=10)
        security_frame.pack(fill='x', padx=20, pady=10)

        security_cmds = [
            ("تثبيت Fail2Ban", "sudo pacman -S --noconfirm fail2ban"),
            ("تفعيل Fail2Ban", "sudo systemctl enable --now fail2ban"),
            ("فحص كلمات المرور", "sudo pacman -S --noconfirm john"),
            ("مسح السجلات", "sudo journalctl --vacuum-time=7d"),
        ]

        for text, cmd in security_cmds:
            ttk.Button(security_frame, text=text, command=lambda c=cmd: self.run_command(c, text)).pack(fill='x', pady=2)

        return frame

    def create_appearance_tab(self):
        """تبويب المظهر"""
        frame = ttk.Frame(self.notebook)

        # سمات
        theme_frame = ttk.LabelFrame(frame, text="🎨 السمات والأيقونات", padding=10)
        theme_frame.pack(fill='x', padx=20, pady=10)

        theme_cmds = [
            ("تثبيت WhiteSur", "yay -S --noconfirm whitesur-gtk-theme"),
            ("تثبيت Tela Icons", "yay -S --noconfirm tela-icon-theme"),
            ("تثبيت خطوط ويندوز", "yay -S --noconfirm ttf-ms-win11-auto"),
            ("تثبيت Noto Emoji", "sudo pacman -S --noconfirm noto-fonts-emoji"),
        ]

        for text, cmd in theme_cmds:
            ttk.Button(theme_frame, text=text, command=lambda c=cmd: self.run_command(c, text)).pack(fill='x', pady=2)

        # سطح المكتب
        desktop_frame = ttk.LabelFrame(frame, text="🖥️ سطح المكتب", padding=10)
        desktop_frame.pack(fill='x', padx=20, pady=10)

        desktop_cmds = [
            ("إعادة تحميل Plasma", "kquitapp5 plasmashell && kstart5 plasmashell"),
            ("إعادة تحميل KDE", "qdbus org.kde.Shell /Shell reloadConfig"),
        ]

        for text, cmd in desktop_cmds:
            ttk.Button(desktop_frame, text=text, command=lambda c=cmd: self.run_command(c, text)).pack(fill='x', pady=2)

        return frame

    def create_tools_tab(self):
        """تبويب الأدوات"""
        frame = ttk.Frame(self.notebook)

        # أدوات سريعة
        tools_frame = ttk.LabelFrame(frame, text="🛠️ أدوات سريعة", padding=10)
        tools_frame.pack(fill='x', padx=20, pady=10)

        tools = [
            ("فتح VS Code", "code ."),
            ("فتح Neovim", "nvim"),
            ("فتح btop", "alacritty -e btop"),
            ("فتح Timeshift", "timeshift-gtk"),
            ("فتح Virt-Manager", "virt-manager"),
            ("فتح Wine Config", "winecfg"),
        ]

        for text, cmd in tools:
            ttk.Button(tools_frame, text=text, command=lambda c=cmd: self.run_command(c, text)).pack(fill='x', pady=2)

        # إصلاحات
        fix_frame = ttk.LabelFrame(frame, text="🔧 إصلاحات شائعة", padding=10)
        fix_frame.pack(fill='x', padx=20, pady=10)

        fixes = [
            ("إصلاح db.lck", "sudo rm -f /var/lib/pacman/db.lck"),
            ("إصلاح Docker", "sudo systemctl restart docker"),
            ("إصلاح KVM", "sudo modprobe kvm_intel"),
            ("إصلاح VirtualBox", "sudo vboxreload"),
            ("إصلاح Wine", "wineboot --init"),
        ]

        for text, cmd in fixes:
            ttk.Button(fix_frame, text=text, command=lambda c=cmd: self.run_command(c, text)).pack(fill='x', pady=2)

        return frame

    def create_logs_tab(self):
        """تبويب السجلات"""
        frame = ttk.Frame(self.notebook)

        # عرض السجلات
        log_frame = ttk.LabelFrame(frame, text="📝 سجلات النظام", padding=10)
        log_frame.pack(fill='both', expand=True, padx=20, pady=10)

        self.log_display = scrolledtext.ScrolledText(log_frame, wrap='word', height=20)
        self.log_display.pack(fill='both', expand=True)

        # أزرار السجلات
        btn_frame = ttk.Frame(log_frame)
        btn_frame.pack(fill='x', pady=10)

        logs = [
            ("سجل pacman", "tail -100 /var/log/pacman.log"),
            ("سجل النظام", "journalctl -b -n 100"),
            ("سجل الأخطاء", "journalctl -p 3 -b -n 100"),
            ("سجل Docker", "journalctl -u docker -n 50"),
            ("مسح السجلات", "sudo journalctl --vacuum-time=7d"),
        ]

        for text, cmd in logs:
            ttk.Button(btn_frame, text=text, command=lambda c=cmd: self.show_log(c)).pack(side='left', padx=2)

        return frame

    def show_log(self, command):
        """عرض السجل في النافذة"""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            self.log_display.delete('1.0', 'end')
            self.log_display.insert('1.0', result.stdout)
            self.status_bar.config(text="✅ تم عرض السجل")
        except Exception as e:
            messagebox.showerror("❌ خطأ", str(e))

# ═══════════════════════════════════════════════════════════════
# تشغيل التطبيق
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    root = tk.Tk()
    app = ManjaroControlCenter(root)
    root.mainloop()
