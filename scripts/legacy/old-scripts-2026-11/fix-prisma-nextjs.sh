#!/bin/bash
set -e
echo "🔧 GitHub Uploader - Prisma + Next.js Fix"
echo "==========================================="

PROJECT=~/github-file-uploader/github-file-uploader
cd "$PROJECT"

echo "1️⃣ Killing processes..."
pkill -9 -f "next dev|npm run dev" 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
sleep 2

echo "2️⃣ Fixing Prisma schema for SQLite..."
cp prisma/schema.prisma prisma/schema.prisma.bak
sed -i '/^enum FileStatus {/,/^}/d' prisma/schema.prisma
sed -i 's/status\s\+FileStatus/status String/g' prisma/schema.prisma

echo "3️⃣ Resetting DB and generating client..."
npx prisma db push --force-reset
npx prisma generate

echo "4️⃣ Clearing Next.js cache..."
rm -rf .next node_modules/.cache

echo "5️⃣ Checking port..."
if lsof -i :3000 >/dev/null 2>&1; then
    echo "❌ Port 3000 busy!"
    exit 1
fi

echo ""
echo "✅ All fixes applied!"
echo "🚀 Now run: npm run dev"
echo "🌐 Then: http://localhost:3000"
