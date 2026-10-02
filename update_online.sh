#!/bin/bash
# ----------------------------------------------------
# 1-Click Timetable Synchronizer & Online Publisher
# ----------------------------------------------------
cd "$(dirname "$0")"

echo "🔄 Step 1: Synchronizing master data and verifying 0 clashes..."
python3 sync_master_data.py
python3 generate_timetable.py --verify || { echo "❌ Aborting: Clashes detected!"; exit 1; }

echo ""
echo "🚀 Step 2: Uploading updates to GitHub & Vercel..."
git add .
git commit -m "Updated Timetable $(date '+%Y-%m-%d %H:%M:%S')"
git push

echo ""
echo "✅ SUCCESS: Your changes are now live online on Vercel!"
