#!/bin/zsh
# 每日对表存档:经 Wayback SPN 代抓 sunsetbot 当日晚霞中东部图(本机直连被墙)。
# 精准之争要有据:我方图 vs sunsetbot vs 用户实测,三方留档供复盘对表。
# SPN 匿名限速:两次抓取间隔≥40s。GFS晚霞最新报=当日00z,EC保底=前日12z。
OUT=/Users/feitong/photo-app/skyfire/data/compare
mkdir -p "$OUT"
D=$(date +%Y%m%d)
D1=$(date -v-1d +%Y%m%d)
for spec in "GFS:${D}00" "EC:${D1}12"; do
  MODEL="${spec%%:*}"; INIT="${spec##*:}"
  URL="https://www.sunsetbot.top/static/media/map/${MODEL}_%E4%B8%AD%E4%B8%9C_${D}_set_${INIT}z.jpg"
  SAVED=$(curl -s -m 90 "https://web.archive.org/save/${URL}" -o /dev/null -w "%{redirect_url}")
  sleep 45
  # 存档后直接从 archive.org 取回落盘
  curl -s -m 90 -L "https://web.archive.org/web/2/${URL}" -o "$OUT/sunsetbot_${MODEL}_${D}_set.jpg"
  [ -s "$OUT/sunsetbot_${MODEL}_${D}_set.jpg" ] && echo "✓ sunsetbot ${MODEL} ${D}" || rm -f "$OUT/sunsetbot_${MODEL}_${D}_set.jpg"
done
# 同步留一份我方当日图,三方对表齐活
cp /Users/feitong/photo-app/skyfire/data/maps/beijing_$(date +%F)_sunset_glow_quality_*.png "$OUT/" 2>/dev/null
