#!/bin/bash
set -e
echo "🔧 GitHub File Uploader - Full Fix Script"
echo "==========================================="

PROJECT_DIR=~/github-file-uploader/github-file-uploader
cd "$PROJECT_DIR"

echo "1️⃣ Killing suspended processes..."
pkill -9 -f "npm run dev|next dev" 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
sleep 2

echo "2️⃣ Fixing Prisma schema for SQLite..."
# إزالة enum FileStatus غير المدعوم في SQLite
sed -i '/^enum FileStatus {/,/^}/d' prisma/schema.prisma
# تحويل الحقول التي تستخدم FileStatus إلى String
sed -i 's/status\s\+FileStatus/status String/g' prisma/schema.prisma

echo "3️⃣ Resetting database..."
npx prisma db push --force-reset

echo "4️⃣ Generating Prisma client..."
npx prisma generate

echo "5️⃣ Updating .env with new key..."
cat > .env << 'ENVEOF'
DATABASE_URL="file:./prisma/dev.db"
ENCRYPTION_KEY="ed32a0ba4f20d60913f405aec29a801202aeddd72ac348e6c0bfd9ad628ef153"
NEXT_PUBLIC_APP_URL="http://localhost:3000"
ENVEOF

echo "6️⃣ Checking port 3000..."
if lsof -i :3000 >/dev/null 2>&1; then
    echo "❌ Port 3000 still in use!"
    exit 1
else
    echo "✅ Port 3000 is free"
fi

echo ""
echo "✅ All fixes applied successfully!"
echo "🚀 Now run: npm run dev"
echo "🌐 Then open: http://localhost:3000"
