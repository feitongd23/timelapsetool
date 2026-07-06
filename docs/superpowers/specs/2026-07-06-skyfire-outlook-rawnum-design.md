# Skyfire 每晚明日展望 + LLM 喂原始预报数字 设计

日期:2026-07-06。前置:Plan A/B/C-1/C-2/D/D-2 已全部合入 main,系统上线运行(launchd 每 30min tick,177 tests)。
本 spec 覆盖上一批复盘定下的待办 ②每晚四模式明日展望 与 ③LLM payload 喂燃烧时刻原始预报数字(见 2026-07-05 晚用户拍板的设计要点),外加一个相关小 bug(iso_hour 截断)。

## 0. 目标与动机

1. **明日展望**:每晚一条推送,覆盖**明日日出+明日日落**,每模式一行(概率%/质量%/高中低云量/降水),外加 AI 解读——用户睡前一眼看到明天两场天象值不值得起早/蹲点。
2. **LLM 喂原始数字**:2026-07-05 实测,LLM 因看不到"GFS 报日落 100% 云+5mm 雨"把干冷气团方向猜反。checkpoint payload 目前只有规则分与 per_model_pct,没有各模式原始云量/降水——补上,让 LLM 直接看到模式间的原始分歧。
3. **iso_hour 就近取整**:峰值 04:47 目前被截断到 04:00 取数(`strftime("%H:00")`),预报读数偏了近一小时;改为就近取整(04:47→05:00)。

**用户已拍板的两个关键决策**:
- 展望**并入朝霞 C1 时刻**(前一晚 20:00-22:00 窗口),不新增 20:30 时点——避免同一晚两条重叠推送。
- 实现取**双跑合推**:朝霞 c1 照常跑 + 明日晚霞新跑 `checkpoint='outlook'`,各调一次 Sonnet,合成一条推送。完全复用 run_checkpoint/predict_pct,不改 LLM 契约。

## 1. LLM 喂原始数字(所有检查点生效)

- 新纯函数 `nearest_iso_hour(dt) -> str`(建议放 suntimes.py):分钟 ≥30 进位到下一小时,格式 `%Y-%m-%dT%H:00`。`compute_prediction` 与 backfill 中现有 `strftime("%Y-%m-%dT%H:00")` 处全部换用。
- `compute_prediction` 从已拉取的 `forecasts` 提取燃烧小时各模式原始值,`PredictionResult` 新增字段:
  ```python
  per_model_raw: dict[str, dict]
  # {"ecmwf_ifs025": {"cloud_high": 80, "cloud_mid": 20, "cloud_low": 10,
  #                   "precipitation": 0.0}, ...}  # 值可为 None(缺数据)
  ```
- `run_checkpoint` 把 `per_model_raw` 放进 LLM payload(payload 已 json.dumps 直达提示词),并放进返回的 rec dict——推送格式化(§4 各模式行)从 rec 取数。
- `_PREDICT_SYSTEM` 提示词补一句语义说明:per_model_raw 是各气象模式对燃烧时刻高/中/低云量%与降水 mm 的原始预报,重点看模式间分歧与雨险(预报有降水时警惕红外低估暖顶雨云)。

## 2. 明日展望(并入朝霞 C1 时刻,双跑合推)

- **触发**:tick 中朝霞 c1 到点时(现有 due_checkpoint 逻辑不动),除跑朝霞 c1 外,同时对**同一天的晚霞**(= 朝霞峰值所在日期的日落)跑 `checkpoint='outlook'`。
- **outlook 的行为与 c1 完全一致**,仅两点:
  - 基线只用预报、不用卫星外推:`cloud_args` 判定从 `checkpoint == "c1"` 改为 `checkpoint in ("c1", "outlook")`(距燃烧 20+ 小时,外推无意义;knowledge §3.2 远期信预报)。
  - 落库 checkpoint 值为 `'outlook'`。
- 卫星帧照常喂 LLM(与朝霞 c1 同时刻,HSD 段缓存共享,零额外下载);payload 的 hours_to_peak 会自然告诉 LLM 距离很远。
- **判重**:outlook 进唯一索引(date, city, event, checkpoint),每晚只跑一次。
- **半失败语义(实现取舍,2026-07-07 审查后修正)**:outlook 失败时朝霞节照推、晚霞节标缺失;**当晚不补跑**(下轮 tick 在 c1 判重处直接跳过该 event),晚霞信息由次日 11:00 的晚霞 C1 推送自然补上。推送缺失文案与此一致:"数据缺失(后续检查点自动补上)"。
- **已接受的调试路径边缘**:手动 `--cp outlook` 预跑后,当晚合推的晚霞节会显示"数据缺失"(不回读已存行)——仅调试路径可达,接受不修。
- **不动的部分**:晚霞当天 11:00 C1、两事件的 C2/C3、gated 门控链全部不变。晚霞的 gated 依然要求当天 c1 已跑(outlook 不算 c1)——夜间对次日日落做卫星外推无意义,维持现状。
- **手动命令**:`skyfire checkpoint --cp outlook` 可手动跑(调试/补跑)。

### 每晚一条推送的完整节奏(北京)

| 时刻 | 内容 |
|---|---|
| ~20:00(朝霞C1窗口) | **明日展望**:明日朝霞(c1)+ 明日晚霞(outlook)合推 |
| 次日 ~11:00 | 晚霞 C1(当天中午更新) |
| 日落/日出 T-2h、T-40min | C2、C3 |
| 检查点之间 | gated(概率摆动 >15pp 才推) |

## 3. 存储迁移

- predictions 表 CHECK 约束加 `'outlook'`。SQLite 不能改 CHECK,需重建表迁移:`connect()` 时检测 `sqlite_master.sql` 是否含 outlook,不含则 `CREATE predictions_new → INSERT SELECT → DROP → RENAME → 重建索引`。幂等,老数据保留。
- 唯一索引 WHERE 子句加 `'outlook'`:`WHERE checkpoint IN ('c1','c2','c3','outlook')`。
- 新列 `per_model_json TEXT`(缺列则 `ALTER TABLE ADD COLUMN`):每次落库写
  ```json
  {"ecmwf_ifs025": {"prob": 35, "qual": 40, "cloud_high": 80, "cloud_mid": 20,
                    "cloud_low": 10, "precipitation": 0.0}, ...}
  ```
  ——将来小程序每模式单独显示(上批待办 c)的现成数据底座,本期只存不读。
- `add_prediction` 增加 `per_model_json` 参数;`run_checkpoint` 组装并传入。

## 4. 推送格式(新 `format_outlook_report(rec_sunrise, rec_sunset)`)

任一参数可为 None(该节显示"数据缺失(后续检查点自动补上)")。各模式缩写用固定映射 EC/GFS/ICON/CMA(实现时发现按 `_` 截断会得到 ECMWF,与本节示例不符,以本节示例为准)。

```
标题: 明日展望 朝霞35% 晚霞60% — 北京

明日朝霞 日出 04:50(其前约15分钟最佳)
概率 35%(机会不大) · 质量 40%(偏弱)
各模式(概率/质量 · 高中低云% · 降水):
EC 35/40 · 高80 中20 低10 · 无雨
GFS 20/30 · 高100 中40 低30 · 雨5mm
ICON …
CMA …
空气(气溶胶AOD …): …
可信度: …
解读: …
风险: …

明日晚霞 日落 19:46(其后约15分钟最佳)
…同结构
```

- 各模式行的原始数字来自 per_model_raw,概率/质量来自 per_model_pct;降水 <0.1mm 显示"无雨",否则"雨X.Xmm"。
- 模式分歧由各模式行 + 现有"可信度"行(low=各家模式结论分歧大)体现,不另加分歧行。
- 单事件推送(c1/c2/c3/gated)的 `format_pct_report` 保持现状(不加原始数字行,避免高频推送过长)。

## 5. 错误处理与降级

- 双跑其一抛 HTTPError/ValueError:捕获后另一半照常落库+推送,失败节标注;当晚不补跑(见 §2 半失败语义),次日常规检查点补上。
- LLM 失败/无 key:照旧降级为免费层基线数字,llm_status='pending',catchup 可补。
- 迁移在 connect() 内自动执行,幂等;迁移失败抛异常(不静默吞——库坏了必须知道)。
- launchd/部署零改动(tick 接口不变)。

## 6. 测试(TDD)

- `nearest_iso_hour`:xx:29→本小时、xx:30→下一小时、跨日边界(23:47→次日00:00)。
- `compute_prediction` 假 client:per_model_raw 各模式原始值正确提取、缺数据模式为 None 值。
- `run_checkpoint`:payload 含 per_model_raw;outlook 基线不用卫星外推(cloud_args 为 None);per_model_json 正确落库。
- store 迁移:旧 schema 库(CHECK 无 outlook、无 per_model_json 列)打开后自动迁移,老数据行保留,重复打开幂等;新库直接建含 outlook 的 schema。
- tick:朝霞 c1 到点时双跑并合成一条推送;outlook 判重(已存在不再跑);单边失败另一边照推。
- `format_outlook_report`:双节完整格式;单边 None 显示数据缺失;降水显示规则。

## 7. 成本

每晚多一次 Sonnet 5 调用(~$0.02),月增 <$1。当前全系统 ≈$0.2/天。

## 7.5 会话内追加(不在原 spec,用户当场要求)

- `skyfire latest` 只读命令:零成本查看最近 N 条预测记录(store.recent_predictions + CLI 格式化输出)。

## 8. 不做(留下批)

- 红外暖云低估校正(上批待办 d)。
- 小程序前端/FastAPI 服务化(per_model_json 已备好数据)。
- VPS 部署(等用户提供 IP,零代码改动)。
