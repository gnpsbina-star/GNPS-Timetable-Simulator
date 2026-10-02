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
# Teacher leave records stay on this computer: never publish substitution history,
# and drop it from the published copy if it was committed before.
git rm --cached --quiet --ignore-unmatch substitutions_history.json substitutions_history.json.tmp
git commit -m "Updated Timetable $(date '+%Y-%m-%d %H:%M:%S')"
git push

echo ""
echo "✅ SUCCESS: Your changes are now live online on Vercel!"
