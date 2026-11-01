# Makefile لـ manjaro-care-cli

.PHONY: install uninstall test clean help

INSTALL_DIR = /opt/manjaro-care-cli
BIN_DIR = /usr/local/bin

help:
	@echo "manjaro-care-cli - أداة صيانة شاملة لنظام Manjaro"
	@echo ""
	@echo "الاستخدام:"
	@echo "  make install      - تثبيت التطبيق"
	@echo "  make uninstall    - إزالة التطبيق"
	@echo "  make test         - اختبار التطبيق"
	@echo "  make clean        - تنظيف الملفات المؤقتة"
	@echo "  make help         - عرض هذه المساعدة"
	@echo ""

install:
	@echo "📦 تثبيت manjaro-care-cli..."
	@sudo mkdir -p $(INSTALL_DIR)
	@sudo cp -r ./* $(INSTALL_DIR)/
	@sudo chmod +x $(INSTALL_DIR)/manjaro-care-cli
	@sudo chmod +x $(INSTALL_DIR)/modules/*.sh
	@sudo ln -sf $(INSTALL_DIR)/manjaro-care-cli $(BIN_DIR)/mcare
	@sudo mkdir -p $(INSTALL_DIR)/reports
	@sudo mkdir -p $(INSTALL_DIR)/backups
	@echo "✅ تم التثبيت بنجاح"
	@echo "الاستخدام: sudo mcare doctor"

uninstall:
	@echo "🗑️  إزالة manjaro-care-cli..."
	@sudo rm -rf $(INSTALL_DIR)
	@sudo rm -f $(BIN_DIR)/mcare
	@echo "✅ تم الإزالة"

test:
	@echo "🧪 اختبار manjaro-care-cli..."
	@sudo ./test.sh

clean:
	@echo "🧹 تنظيف الملفات المؤقتة..."
	@rm -f *.tmp *.swp *~
	@rm -rf reports/*.tmp
	@echo "✅ تم التنظيف"

lint:
	@echo "🔍 فحص الكود..."
	@shellcheck manjaro-care-cli || true
	@shellcheck modules/*.sh || true
	@echo "✅ اكتمل الفحص"

format:
	@echo "📝 تنسيق الكود..."
	@shfmt -w manjaro-care-cli || true
	@shfmt -w modules/*.sh || true
	@echo "✅ تم التنسيق"

docs:
	@echo "📚 إنشاء التوثيق..."
	@pandoc README.md -o README.pdf || echo "pandoc غير مثبت"
	@echo "✅ تم إنشاء التوثيق"

release:
	@echo "🚀 إنشاء إصدار جديد..."
	@read -p "رقم الإصدار: " version; \
	git tag -a v$$version -m "الإصدار $$version"; \
	git push origin v$$version
	@echo "✅ تم إنشاء الإصدار"
