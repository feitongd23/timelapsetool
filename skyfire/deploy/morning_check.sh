#!/bin/zsh
# 晨间健康检查(北京早8:30,Open-Meteo日配额刚过UTC零点重置):
# 生成当日全国地图 + 记录预测/推送健康状况,供次日人工确认。
export PATH="$HOME/.local/node/bin:$PATH"
BIN=/Users/feitong/photo-app/skyfire/.venv/bin/skyfire
LOG=/tmp/skyfire.morningcheck.log
DB=/Users/feitong/photo-app/skyfire/data/skyfire.db
{
  echo "===== $(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M') 晨检 ====="
  echo "[地图] 生成全国图:"
  $BIN maps --city beijing 2>&1 | grep -vE "RuntimeWarning|return self.func" | tail -2
  echo "[地图文件] $(ls /Users/feitong/photo-app/skyfire/data/maps/ 2>/dev/null | wc -l | tr -d ' ') 张"
  echo "[今日预测] 最近5条:"
  sqlite3 "$DB" "SELECT datetime(created_at,'+8 hours'), event, checkpoint, probability_pct||'/'||quality_pct FROM predictions WHERE date>=date('now') ORDER BY id DESC LIMIT 5" 2>/dev/null
  echo ""
} >> "$LOG" 2>&1
