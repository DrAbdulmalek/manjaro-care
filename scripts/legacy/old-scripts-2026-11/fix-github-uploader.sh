#!/bin/bash
echo "🔧 Fixing github-file-uploader..."

cd ~/github-file-uploader

# 1. إصلاح Prisma schema لـ SQLite
sed -i '/^enum FileStatus {/,/^}/d' prisma/schema.prisma

# 2. إعادة تعيين قاعدة البيانات
npx prisma db push --force-reset

# 3. تحديث Next.js
npm install next@latest

# 4. إعادة التشغيل
echo "✅ جاهز! شغّل: npm run dev"
