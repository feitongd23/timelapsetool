# Skyfire 小程序 v1 + 极简只读 API 设计

日期:2026-07-07。前置:明日展望批次已合入 main(199 tests,per_model_json 数据底座就绪)。
本 spec 是 Plan C 剩余(FastAPI 服务化 + Taro 双端)的第一子项目:**自用版小程序 + 只读 API**。反馈写接口、鉴权、公网部署为第二子项目(等 VPS/部署形态,已挂起不阻塞)。

## 0. 目标与设计参照(用户拍板)

睡前/出门前打开小程序,3 秒内看到:烧不烧(大数字)、预测怎么收敛的(轨迹)、各家模式怎么说(明细)、哪片天区会烧(热力图)、AI 怎么解读。

- **专业密度参照 sunsetbot**:概率/质量/各模式/轨迹全量数字
- **UX 参照 Robinhood**:大数字 hero、干净趋势曲线、卡片极简
- **热力图参照莉景天气**:概率图+质量图双图;**平滑渐变、无分块无锯齿**(2026-07-07 用户明确:不要瓦片感)
- **视觉**:浅色系 + 液态玻璃 + 磨砂 + 扁平(用户跨项目通用审美,mockup 已确认)
- 数据方案:极简只读 API + 真数据(本机/局域网);暗色主题明确否掉

## 1. 总体架构

```
Taro 小程序(微信) --HTTP--> FastAPI 只读 API(Mac 本机 uvicorn :8000)--> SQLite + gridmap
```

- 新目录 `photo-app/skyfire-miniapp/`(Taro 4 + React + TypeScript,独立 package.json;将来同码出 RN App)
- API 新模块 `skyfire/src/skyfire/api.py`,新 CLI 命令 `skyfire serve [--host 0.0.0.0 --port 8000]`
- 监听 0.0.0.0:真机同 WiFi 直连局域网 IP;CORS 全开(微信开发者工具模拟器走浏览器需要);v1 无鉴权(自用局域网,已知取舍)
- 依赖新增:fastapi、uvicorn(pyproject dependencies)

## 2. API v1 契约(只读,两个端点)

### GET /v1/summary?city=beijing

首屏一击全给。返回:

```json
{
  "city": "beijing", "city_name": "北京", "updated_at": "2026-07-07T19:05:00",
  "dates": [
    {
      "date": "2026-07-07", "label": "今天 7月7日",
      "events": [
        {
          "event": "sunrise_glow", "status": "ended", "peak": "04:51",
          "latest": {"checkpoint": "c3", "probability_pct": 12, "…": "…"},
          "trajectory": ["…"], "per_model": {"…": "…"}
        },
        {
          "event": "sunset_glow", "status": "upcoming",
          "peak": "19:45", "best_window": "19:45-20:00",
          "latest": {"checkpoint": "c2", "probability_pct": 62, "quality_pct": 55,
                      "prob_word": "值得留意", "qual_word": "中等",
                      "confidence": "high", "llm_status": "done",
                      "reasoning": "…", "risks": "…", "created_at": "…"},
          "trajectory": [{"checkpoint": "outlook", "probability_pct": 38,
                           "quality_pct": 30, "created_at": "…"}, "…"],
          "per_model": {"ecmwf_ifs025": {"prob": 71, "qual": 64, "cloud_high": 62,
                         "cloud_mid": 18, "cloud_low": 8, "precipitation": 0.0}, "…": "…"}
        }
      ]
    },
    { "date": "2026-07-08", "label": "明天 7月8日", "events": ["…朝霞+晚霞同构…"] }
  ]
}
```

- **以日期为主维度**(用户 2026-07-07 拍板):dates = 今天 + 明天两天,每天固定两个事件 = 朝霞 + 晚霞(只这两类)。`status`: 峰值已过 = `"ended"`(前端标"已结束",内容仍显示末版预测),否则 `"upcoming"`
- 由 sun_window 现算峰值判断 ended;预测数据从 predictions 表读最新版+全轨迹,per_model 直接反序列化 per_model_json
- 无预测数据的事件返回 `latest: null`(前端显示"待检查点");prob_word/qual_word 由后端给(复用 report._prob_word/_qual_word,前端不重复实现口径)
- 纯读库,<50ms

### GET /v1/heatmap?city=beijing&event=sunset_glow&date=2026-07-07&kind=prob|quality

返回 `image/png`(约 600×440)。

- 数据:复用 gridmap 的网格云量拉取(DEFAULT_BBOX/DEFAULT_STEP,约 30km 格距);hourly 变量如缺高中低云分层则扩展拉取字段
- 逐格算 firecloud 规则分 → kind=prob 经 baseline_percent 概率端(含云量甜区修正,confidence 用城市级最新预测的,缺则 medium)、kind=quality 取质量端
- **渲染(无分块无锯齿)**:数值网格(n_rows×n_cols)→ 归一化 → numpy 双三次/双线性插值(PIL `Image.resize(..., BICUBIC)`)放大至输出分辨率 → 颜色映射 LUT 上色(prob=暖色琥珀→红,quality=紫色系)→ 叠北京点标(复用 overlay 点标能力)。平滑渐变,无格子边界
- 时刻:取该事件燃烧时刻 nearest_iso_hour
- **缓存**:内存 dict,键 (city,event,date,kind),TTL 30 分钟(与 tick 同周期);首算 1-2 秒,命中瞬回
- Open-Meteo 失败 → 503(前端重试按钮)

## 3. 小程序 v1(Taro,微信端)

页面结构(浅色磨砂,已确认 mockup):

1. **顶部**:城市(v1 固定北京)+ 更新时间;**日期下拉选择**(今天 7月7日 / 明天 7月8日);其下**朝霞/晚霞两个 tab**(固定只这两个)——已结束的 tab 标"已结束"角标,点开仍显示该事件末版预测(轨迹/模式/解读齐全),数字区淡化处理
2. **Hero 卡**:概率大数字(46-48px)+ 定性词;质量副数字;下嵌轨迹曲线(展望→C1→门控→C2→C3,原生 canvas 手绘折线——最多几个点,不引图表库)+ 一句"昨晚 38% → 现在 62%"
3. **各模式卡**:EC/GFS/ICON/CMA 四行,概率/质量 · 高中低云 · 降水(等宽字体)
4. **双热力图卡**:概率图/质量图并排 `<image>`;**骨架屏懒加载**(首屏先出 1-3 块,热力图后台请求 1-2 秒后浮现);点开全屏预览大图
5. **解读卡**(标题就叫"解读",不带"AI"字样——用户拍板):reasoning + risks;llm_status=pending 显示"解读暂缺,以上为基础数据"
6. **反馈两键:v1 隐藏**(写接口属第二子项目)

交互:下拉刷新;summary 30 秒本地缓存防抖;API 连不上显示"服务未启动"引导页(自用场景)。

配置:`src/config.ts` 里 `API_BASE`(默认 `http://127.0.0.1:8000`,真机改局域网 IP);开发者工具勾"不校验合法域名"。

## 4. 错误处理

- API 侧:未知 city/event/kind → 422;库无数据 → latest:null 而非 500;heatmap 上游失败 → 503 + detail;所有异常不抛栈到客户端(FastAPI exception handler)
- 小程序侧:summary 失败 → 全屏引导页(检查服务/WiFi);heatmap 失败 → 卡片内重试按钮;数据陈旧(updated_at 距今 >2h)→ 顶部小字提醒

## 5. 测试

- API:pytest + FastAPI TestClient——summary 形状(3 events/轨迹排序/per_model 反序列化/无数据 latest:null)、heatmap 返回 PNG magic bytes+缓存命中(第二次调用不触发网格拉取,monkeypatch 计数)、参数校验 422、503 降级
- 热力图渲染:纯函数单测(小网格 → 插值上色 → 尺寸/无 NaN)
- 小程序:开发者工具模拟器 + 真机各一轮手测清单(写进计划)
- 验收 = 真机看到真数据首页 + 平滑热力图浮现

## 6. 不做(第二子项目/以后)

- 反馈写接口(打分/照片/预报不准)+ 反馈两键 UI 接线
- 鉴权、公网暴露、VPS/Tunnel 部署(挂起的部署形态问题)
- 热力图交互版(点格查值/缩放)、地图底图叠加
- 历史案例页、多城市、App(RN)构建

## 7. 用户准备项(并行)

- 装微信开发者工具;注册小程序 AppID(个人主体,免费;游客模式可先开发)
