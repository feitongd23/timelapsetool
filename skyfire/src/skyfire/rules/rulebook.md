# skyfire 预测规则表(强制过堂)

版本管理的活文件:文献知识、用户经验、真实案例教训、复盘总结的唯一汇合点
(2026-07-10 由 129 条合并规则生成,四路蒸馏自:领域知识文档×2、23 个闭环
案例与笔记、用户历次口径原话、提示词与代码现行阈值;含冲突裁决)。

用法约定:
- 每次预测,代码层与 LLM 层必须逐条对照本表;复盘的产出是对本表的补丁,不是笔记。
- 优先级:用户口径 > 案例实锤 > 文献 > 代码现行;P0=曾造成真实漏报/用户亲口强调。
- [hard]=代码强制(条件动作可机判),LLM 仍须在 factors 里复核;[soft]=LLM 逐条表态。
- 注入 LLM 提示词时剔除"来源"行与雾/彩虹两节(llm._rulebook)。


## 卫星判读

- sat-ir-brightness-not-amount [hard·P0] 云的量/厚/高三维必须分通道读:量=卫星覆盖比例(面积占比)、厚=可见光反射率、高=红外亮温;禁止用B13红外亮度均值推算云量或厚度(红外白只等于冷/高,薄卷云照样白)。
  来源: 合并: ir-brightness-not-cloud-amount / infrared-dimension-discipline / ir-brightness-not-amount — knowledge §3.2要点③/§3.8; 2026-06-26红外陷阱(2分)用户血泪教训; 2026-07-09漏报根因①
- sat-warm-top-full-cover-detect [hard·P0] 红外判读窗内最暖亮温<292K说明无晴天像元→判满盖(暖顶),box_cloudiness强制按≥90处理;暖顶(约280-290K)中低云在红外近乎隐形,7/9曾把满盖读成34%。
  来源: 合并: ir-full-cover-warm-top-detection / warm-top-cloud-ir-underestimate / b13-warm-top-underread — 2026-07-09漏报根因①(报52/48实际0分); knowledge §5.6; 用户拍板2026-07-10; 2026-07-05待办d | 阈值: 292K强制≥90;暖顶段280-290K
- sat-ir-vis-divergence-take-higher [hard·P0] B13红外云量与VIS/云掩膜/预报中低云量背离超30个百分点时以高值为准,标注暖顶中云陷阱,并置位冲突标志触发双情景推送。
  来源: 合并: ir-warm-midcloud-trap / b13-warm-top-underread交叉验证段 — 2026-07-09(34% vs 满盖实况); 2026-06-26红外陷阱; MEMORY skyfire-coldstart-progress.md | 阈值: 30pp
- sat-cloudpct-second-source [hard·P0] 卫星云量禁止单通道读数直接进分,必须有第二来源(可见光/云掩膜/预报分层/地面观测)交叉验证。
  来源: cloudpct-needs-second-source — 2026-07-09(单靠B13读数进链,实际0分)
- sat-vis-mandatory-daytime [hard·P1] 白昼判读必须同时使用可见光与红外帧,禁止只凭红外判云形态。
  来源: vis-plus-ir-mandatory-daytime — 2026-07-09单通道误读; 历史高分案例(2020-09-01/2023-09-19/2024-05-06)判读均依赖VIS纹理
- sat-vis-ir-combined-dense-vs-broken [soft·P1] 判任何一片云必须VIS×IR合看并区分致密/破碎:IR冷+VIS中等亮有纹理破口=理想画布;VIS大片刺白均匀=光学厚密盖偏堵(即使IR冷);VIS暗灰+IR暖=薄或低画布弱;IR冷亮致密成片=堵光云墙,冷亮疏松带缝=可燃云幕。
  来源: 合并: vis-ir-combined-reading ×2 / cold-bright-dense-vs-broken — knowledge §3.8/§5判读表; 2024-05-16(2分,致密锋面带) vs 2022-06-07(8分,破口状冷云)
- sat-overrides-forecast-20pp [hard·P0] 卫星实测云量与点预报背离超20个百分点时以卫星为准——低估幕和高估幕两个方向都骗过预报。
  来源: satellite-overrides-point-forecast — 低估: 2026-01-07(9分,报6%实测44.8%)/2026-06-03/2024-09-30/2026-05-31;高估: 2026-06-26(2分,报51%实测25%); 用户口径"云量决定性因子且预报严重不可信" | 阈值: 20pp
- sat-motion-trend-required [soft·P1] 判读必须用连帧(≥2帧)判云系动向并外推:裂开=转好/压过来=转差,禁止单帧静态定论;上游有连续云系压来时禁止得出"届时维持不变"的外推结论。
  来源: 合并: satellite-motion-trend-required / animation-frames-before-peak / animation-30-60min-trend / no-static-extrapolation-under-approach / time-trend-extrapolation — knowledge §3.7/§5.4; 2020-09-01/2023-09-19案例; 2026-07-09复盘; spec 2026-07-03 §5.4 | 阈值: 峰值前30-60min连帧
- sat-frame-time-align [hard·P1] 判读帧时序必须对准燃烧时刻:晚霞红外看日落后、可见光看日落前,朝霞镜像,朝霞VIS要等日出后60-90分钟才读得了厚度。
  来源: frame-time-align-burn-moment — Plan D-2 case_frame_times; 2026-06-26待办(b) | 阈值: 朝霞VIS≥日出+60min
- sat-winter-snow-confusion [soft·P2] 冬季雪盖地表在红外显冷蓝白易与高云混淆,禁单凭红外判雪区云量。
  来源: winter-snow-infrared-confusion — Plan D-2已知局限(skyfire-coldstart-progress.md)
- sat-box-cloudiness-in-outputs [hard·P1] 案例卡与复盘payload必须显示卫星实测box_cloudiness,与预报云量并排对照,不得只列预报百分数。
  来源: satellite-cloud-in-case-card — 2026-06-26纠正后待办(a)

## 云结构与画布

- cloud-canvas-gate-min15 [hard·P0] 画布是硬门槛:燃烧时刻云量<15等于没画布,质量与概率都封顶20;中高云覆盖<20%(万里无云/只剩大云洞)直接判不烧。
  来源: 合并: canvas-required-veto / cloud-below-15-cap-20 — src/skyfire/percent.py:24-25,33-35; knowledge §2-B/§3.2 | 阈值: 15封顶20;中高云<20%否
- cloud-amount-inverted-u [hard·P1] 云量与质量呈倒U:30-70甜区质量+10概率+15;15-30画布偏薄按0.6→1.0线性折减;>90闷盖风险质量×0.75概率封顶20。⚠冲突: percent.py现行>90折减无高云豁免 vs 高云满盖是画布——裁决:>90折减仅对中低云主导(blocker>30)生效,纯高云满盖豁免。
  来源: 合并: canvas-cover-inverted-u / cloud-sweet-zone-30-70 / cloud-15-30-linear-taper / cloud-above-90-damp — src/skyfire/percent.py:24-37; knowledge §3.2; 2026-07-07根因① | 阈值: 15/30/70/90;+10/+15;×0.75
- cloud-high-canvas-never-zero [hard·P0] 高云满盖是画布不是遮挡:canvas禁止因cloud_high高(甚至100%)而归零或重罚,满盖惩罚只对中低云主导闷盖生效;点预报高云40-80%且低云<20不得触发"云太厚"压分。
  来源: 合并: high-cloud-never-zeroes-canvas / canvas-high-cloud-never-zero / canvas-full-cover-no-hard-zero / canvas-overcast-only-blocker-penalty / forecast-highcloud-not-scary — 2026-05-06(10分)用户复盘硬伤(a); 2026-07-07漏报根因①(EC/ICON正确报高云100%被打0); src/skyfire/scoring/firecloud.py:44-49; 2026-06-21(实测28%薄卷云被43%吓退); 2024-05-06(预报高云78%仍9分) | 阈值: blocker>30才触发惩罚
- cloud-canvas-formula [hard·P1] 画布分公式:canvas=cloud_high+0.5×cloud_mid(卷云权重高于中云);<5记0、5-40线性升至10、40-70满分。
  来源: canvas-formula-high-full-mid-half — src/skyfire/scoring/firecloud.py:29-43; spec 2026-07-03 §5.1 | 阈值: 下限5%;最佳区40-70%
- cloud-structure-over-quantity [soft·P0] 结构>云量:34-37%连贯中高云带能烧9分、36%零碎积云只有2分;判读必须三选一表态(连贯带/零碎积云/糊死均匀层云)并给VIS纹理依据,禁止只引用云量百分数定案;零碎小块不给画布分,均匀满盖无破口封顶低分并推送明示。
  来源: 合并: structure-over-quantity / structure-over-amount / canvas-coherent-sheet-not-fragments / uniform-overcast-no-burn — 2024-05-06(9分) vs 2026-06-10(2分)跨案例; 2026-05-06(10分)用户复盘"有结构的画布非糊死均匀层云"; src/skyfire/llm.py:103-104; knowledge §3.2要点①
- cloud-sparse-high-can-burn [soft·P1] 稀疏薄高云(实测15-30%)只要位置正、通道全开也能烧8分,禁止把量少直接读成料不足。
  来源: sparse-high-cloud-can-burn — 2025-09-28(8分,实测20.3%,规则只给2.6); 2025-09-30(8分,实测22%) | 阈值: 15-30%
- cloud-midlow-full-cover-is-lid [soft·P0] 满盖中低云幕(含暖顶中云、雨层云成片均匀中低灰无纹理无破口)是盖子不是画布:既当不了画布又堵光路,概率质量双杀;判读必须区分"高云满盖=画布"与"中低云满盖=盖子"两种满盖并明确归类。
  来源: 合并: warm-mid-full-cover-is-lid / ns-uniform-mush — 2026-07-09空报(B13读34%实为满盖暖顶中云,实际0分)+用户原话同日; knowledge §5.6
- cloud-overcast-zero-scale [hard·P0] 阴天完全没有日落(满盖中低云、无任何光路)=0分;事前满足同条件的预测概率封顶5%、质量封顶10%,禁止输出中间值。
  来源: overcast-no-sunset-zero — 用户原话2026-07-09/10"阴天一点日落都没有是属于0分的那种"(7/9空报: 报52/48实际0) | 阈值: box>90%且走廊无放晴窗;概率≤5%/质量≤10%
- cloud-height-tiers [soft·P2] 云高分层:低云<2km基本不利(盖顶遮挡点亮短暂),中云2-6km(高积云)是壮观火烧云主力幕布,高云>6km色彩最纯净且日落后仍可亮约30分钟;最炽烈大烧云底往往偏低但持续<20分钟——窗口与推送节奏据此区分。
  来源: 合并: cloud-height-tiers / cloud-height-tier-quality / big-burn-short-window — knowledge §3.1; spec 2026-07-03 §5.1 | 阈值: 2000m/6000m分界;大烧<20min;高云余晖约30min
- cloud-type-preference [soft·P2] 云型加成:高积云/卷积云/卷云(鱼鳞、波浪、条带、有破口)最佳画布;均匀层云/层积云铺满与积雨云砧板为差云型。
  来源: cloud-type-preference ×2 — knowledge §3.3/§5判读表(sunsethue)
- cloud-local-low-tiers [hard·P1] 本地低云盖顶时地面看不到高云画布,按低云覆盖三档打折:≤40→1.0、40-70→0.7、>70→0.25。
  来源: local-low-cover-tiers — src/skyfire/scoring/firecloud.py:69-75 | 阈值: 40/70
- cloud-layer-rh-inference [hard·P1] 缺分层云量时用各气压层RH反演互校:300-200mb RH50-70有高云、500-700mb 60-80有中云、925-800mb 80-90有低云、>90该层满盖;高空RH高=可能有画布(利好)与地表RH高=坏(利空)方向相反,必须两个独立变量禁混用。
  来源: 合并: layer-rh-cloud-inference / aloft-rh-cloud-inversion — knowledge §3.5(US20170109634A1专利做法) | 阈值: 高云300-200mb RH50-70;中云500-700mb 60-80;低云925-800mb 80-90;>90满盖
- cloud-position-geometry [soft·P1] 云幕必须位于能受光的方位:云堆在背光侧或只堵在取光线上游时无幕可染。
  来源: canvas-position-geometry — 2026-06-26(2分,厚云团挡58°取火线上游头顶空); 2026-07-05(4分,头顶云背光)
- cloud-value-priority [hard·P1] 燃烧时刻云量取数优先级固定:projected_cloud_pct(卫星外推)→sat_cloud_pct(实测)→不做云量修正。
  来源: cloud-value-priority-projected-first — src/skyfire/percent.py:22; knowledge §3.2
- cloud-big-burn-pattern [soft·P1] 大烧高发形态=满天中高云幕(高云80-100%)+西侧通道低云稀少+卫星实测云量30-70%:此时"云太多"不是利空,判读必须表态识别该形态。
  来源: big-burn-pattern-recognition — src/skyfire/llm.py:116-118; 2026-07-07中大烧案例(实际7.5分) | 阈值: 高云80-100%/实测30-70%
- cloud-antisolar-sector-downweight [soft·P2] 扇区法评估云况时太阳对侧扇区降权——对侧云被戏剧性照亮的概率低。
  来源: 合并: sector-antisolar-downweight / opposite-sector-downweight — knowledge §6(US20170109634A1扇区法)

## 透光通道

- channel-directional-hard-gate [hard·P0] 透光通道是硬门槛:晚霞沿日落方位(西)、朝霞沿日出方位(东)取走廊采样(现行100-400km、步长约25km),堵死则头顶云再好也不烧。⚠缺口: 现行只采100-400km,但7/5案例(50km低云100%堵→4分)证明0-100km近程必须补采——裁决:采样扩至0-400km并配near-field封顶规则。
  来源: 合并: channel-gate-directional / sunset-west-sunrise-east / channel-sample-range-100-400km — knowledge §2-A/§5/§6; src/skyfire/scoring/firecloud.py:52-66; spec 2026-07-03 §4/§5.1; 2026-07-05(4分)案例 | 阈值: 走廊0-400km(现行100-400km,待改);步长约25km
- channel-judge-low-plus-thick-mid [hard·P0] 通道判堵看低云+光学厚中云墙,不看总云量:高云盖顶不挡低角度平射光不算堵;满盖致密中云墙(高层云/雨层云无破口)同样封死进光口。⚠冲突: 旧口径(firecloud.py:64及2026-05-06等多案例)只看低云 vs 7/9复盘中云墙也算堵——裁决:用户2026-07-10拍板中云墙纳入为新口径,高云豁免保留。
  来源: 合并: channel-use-low-cloud-not-total / channel-block-judge-by-low-not-total / channel-block-low-cloud-only / corridor-judge-low-mid-not-total / channel-must-sample-mid-cloud / channel-mid-cloud-wall-blocks / midcloud-wall-counts-as-block / midlow-wall-is-block — 2026-07-09根因②+用户拍板2026-07-10; 高云豁免案例2026-05-06/2023-09-19/2022-06-07/2024-05-06; 中云墙案例2024-05-16/2026-06-26; 用户原话2026-07-09"西北方向连续不断的乌云" | 阈值: low>60;中云墙total≥90且mid≥60连续2段(待回测标定);高云豁免low<20且mid<40
- channel-block-ratio-formula [hard·P1] 堵点比例过半近似一票否决:通道系数=max(0.1, 1−1.8×堵点比例)。
  来源: 合并: channel-point-blocked-low60 / channel-half-blocked-veto — src/skyfire/scoring/firecloud.py:63-66; spec 2026-07-03 §5.1 | 阈值: 比例50%;下限0.1;斜率1.8
- channel-near-field-low-cap [hard·P0] 近程(0-50km)低云≥80%堵死光路是没烧起来的头号杀手:头顶云底吃不到光,最多地平线橙带,质量封顶约30%(≈4分档),不因远端放晴抬分。
  来源: 合并: near-field-lowcloud-cap / near-low-cloud-kills — 2026-07-05(4分,50km低云100%堵,用户口径纠正,case_notes#24,系统28%方向正确为校标); 2026-06-10晚霞(2分,50km低云88) | 阈值: low≥80@0-50km→质量≤30
- channel-far-wall-veto [hard·P1] 通道200-300km段的实心低云墙封死进光,近端假通透不能当通道开。
  来源: far-lowcloud-wall-veto — 2026-06-10朝霞(2分,近端低云仅5%假通透); 2026-06-10晚霞(2分,250km低云100) | 阈值: low≥85@200-300km
- channel-far-400km-tolerated [soft·P1] 350-400km外才出现的低云堵不构成否决,近程干净时仍可能真烧。
  来源: far-400km-block-tolerated — 2026-07-07(7.5分,400km才堵、50-150km低云≈0仍烧成)
- channel-near-far-separate-verdict [soft·P1] 通道必须分近程(0-100km)/远程(100-500km)逐段(50/100/150/200/250/300km)分别给通/堵结论:远通近堵一律判"只亮地平线"场景压质量;同覆盖率下离太阳越近的低云越致命按距离加权。
  来源: 合并: corridor-near-far-separate / corridor-full-profile-review / near-sun-low-cloud-fatal — 2026-05-06(300-400km放晴=满分要素) vs 2026-07-05(远通近堵=4分); 2024-05-16(2分,点预报只看头顶漏掉64°方向云墙); knowledge §5判读2
- channel-scattered-holes-not-open [soft·P0] 零散云洞不等于通道开:通道开需要成片连续的放晴区,零散云洞最多判"局部漏光"。
  来源: scattered-holes-not-open-channel — 用户原话2026-07-09"只是有零散的云洞在西侧但西北方向是连续不断的乌云"(实际0分)
- channel-open-not-sufficient [soft·P1] 通道开只保证进光不保证烧:必须再单独判头顶云是否处在受光角度,禁以通道开直接推高分。
  来源: channel-open-not-sufficient — 2026-07-05(4分,远端通道敞开只点亮地平线,头顶云背光未受染)
- channel-azimuth-ephemeris-verified [hard·P0] 判读图上的通道线/扇区方位必须等于天文历计算的太阳方位角真值:渲染后自动比对,偏差>5°图作废自动重绘并记录告警,校验失败的图禁止送LLM判读;禁止手写/写死常数方位角;渲染管线加单元测试。
  来源: 合并: channel-azimuth-ephemeris-check / channel-line-must-match-azimuth / azimuth-line-verified / azimuth-true-value-only — 2026-07-09漏报根因⑤(通道线画错30°); 用户拍板2026-07-10 | 阈值: 偏差>5°(事故案例30°)
- channel-missing-data-not-open [hard·P0] 通道方位剖面数据拉空或失败禁止默认1.0视为通。⚠冲突: 代码现行全缺数据时系数按1.0(硬门槛失效,历史ρ=0.026)——裁决:复盘口径胜,禁静默当通畅。
  来源: 合并: channel-data-missing-not-open / channel-missing-data-not-neutral — knowledge §7病因1; src/skyfire/scoring/firecloud.py:60-63现行反例
- channel-canvas-separate-variables [hard·P1] 通道(太阳方向远处近地平线)与云幕(观测地头顶)在空间上分离:必须分别取数、分别评估、分别表态,禁止用一个总云量标量同时概括两者。
  来源: 合并: no-single-scalar-cloud / channel-canvas-spatially-separate — knowledge §2关键推论(现有模型的致命简化)
- channel-pressure-trend [soft·P2] 气压趋势判通道开合:气压回升(雨后转晴)=通道正在打开给正修正;气压下降(云系逼近)=通道正在关闭给负修正——单帧云量不够必须看时间趋势。
  来源: pressure-trend-modifier ×2 — knowledge §3.7(SunsetWx核心因子)/§6
- channel-transparency-not-standalone [soft·P1] 空气通透只是必要条件:进光被堵或无幕可染时通透救不了分,禁止把通透列为独立加分理由。
  来源: transparency-not-standalone-plus — 2024-05-16(2分,AOD0.23); 2026-06-26(2分,AOD0.19); 2026-06-10晚霞(2分,AOD0.13)
- channel-sunrise-caution [soft·P2] 朝霞常伴天气转折(西边云系正逼近)且数据源较弱,真假阳性都更多:置信上限压低,判读表态天气是否在转折。
  来源: 合并: morning-glow-caution / sunrise-weather-turn-caution — knowledge §4(朝霞不出门有科学依据)

## 气溶胶与湿度

- aod-mandatory-tier-coefficients [hard·P0] 气溶胶是每次预测必查因子,按AOD分档取质量系数:<0.3→1.0、0.3-0.6→0.85、0.6-1.0→0.6、≥1.0→0.3,重霾/沙尘不给高分。⚠冲突: 中间档知识库约0.8/0.5 vs 代码0.85/0.6——裁决:用户只拍板">1.0→0.3",中间档暂用代码现行值待回测标定。
  来源: 合并: aerosol-graded-coefficient / aod-tier-coefficients / aod-above-1-quality-cap / aod-mandatory-factor — 用户拍板2026-07-10原话示例; 用户原话2026-07-09"你忘记把气溶胶考虑进去了"; src/skyfire/scoring/firecloud.py:78-87; knowledge §3.4(Corfidi); 2026-07-09(AOD1.4当天实际0分); 正例2026-05-06满分AOD0.41 | 阈值: 档界0.3/0.6/1.0;系数1.0/0.85/0.6/0.3(中间档待回测)
- aod-missing-not-neutral [hard·P0] AOD缺失或过期禁止按中性1.0处理:先走CAMS/美使馆PM2.5兜底,仍无则质量系数取min(最近有效值对应系数, 0.7),置信降一档,推送标注"气溶胶数据缺口"。⚠冲突: 代码现行aod=None→系数1.0——裁决:用户2026-07-10拍板推翻,必须改。
  来源: 合并: aod-missing-not-neutral ×3 / aod-burn-time-actual-required / aod-missing-neutral-current(反例) — 2026-07-09漏报根因③(AOD1.4缺失/过期被当中性); 用户拍板2026-07-10; src/skyfire/scoring/firecloud.py:79-80现行反例 | 阈值: 时效6h(候选12h,取严待回测);无数据系数≤0.7
- aod-echo-audit-fields [hard·P0] 每次预测输出必须回显实际进入质量链的aod_used与aod_age审计字段,字段缺失即报警拦截——防止AOD静默丢失不进链。
  来源: aod-must-echo-in-output — 2026-07-09(AOD1.4没进链,用户2026-07-10复盘)
- aod-moderate-discount-only [soft·P1] AOD 0.4-0.9只是色彩饱和度折扣不构成否决(0.59烧9分、0.84烧7.5分"AOD骗了预报"),禁据此压到不烧档。
  来源: aod-moderate-discount-only — 2025-08-29(9分,AOD0.59); 2026-07-07(7.5分,AOD0.84被误当闷堵); 2026-05-06(10分,AOD0.41) | 阈值: 0.4-0.9
- aod-surface-rh-degrade [hard·P1] 地表RH>85%近饱和(成雾/低云压色)明显变差降档,40-60%最佳;方向与高空RH相反禁混用(见cloud-layer-rh-inference)。
  来源: surface-rh-degrade ×2 — knowledge §3.5 | 阈值: 劣化线85%;最佳40-60%
- aod-humidity-mute-colors [soft·P1] 空气脏(高AOD/雾霾)与湿度高都把颜色洗淡,几何再完美也只给中低分;地表RH≥75%即表态"湿度压色"降一档饱和度预期。
  来源: 合并: air-humidity-mute-colors / humidity-saturation-discount — src/skyfire/llm.py:107; knowledge §3.4/§5配方步骤4-5; 2026-06-10朝霞(2分,RH79%) | 阈值: RH≥75%标注
- aod-autumn-winter-prior [soft·P2] 秋冬环流弱霾产出低常有更好的霞:季节先验只调预期不改门槛,不替代实测AOD。
  来源: autumn-winter-clean-prior — knowledge §3.4

## 降水

- precip-three-tier-gate [hard·P0] 降水三档口径:<0.5mm不触发否决且属雨后初晴利好;0.5-1.0mm降水系数0.2;≥1.0mm或走廊/本地正在降水→一票否决归零;积雨云(红外极冷+砧状扩展)同为否决级。⚠冲突: 代码>0.5→0.2一刀切 vs 案例0.4mm高分与知识"正降水否决"——裁决:合并为三档。
  来源: 合并: precip-active-veto / precip-veto-0p5mm / micro-precip-is-bonus / heavy-precip-veto / cb-anvil-veto — src/skyfire/scoring/firecloud.py:90-91; 2024-05-14(9分,0.4mm)/2026-07-07(7.5分,0.4mm)/2026-06-03(6分,0.1mm); knowledge §3.6/§5.6 | 阈值: 0.5mm/1.0mm;中间档系数0.2
- precip-rain-just-ended-bonus [hard·P0] "正在下"与"刚下完"是相反信号:燃烧窗口前雨已停且连帧见云裂开=雨后初晴经典大烧时机,给通道与M_air正修正(空气洗净+破碎云幕),禁误套降水否决。
  来源: 合并: rain-just-ended-bonus / rain-clear-bonus — knowledge §3.6; 北京雨后火烧云案例(CMA); src/skyfire/llm.py:107
- precip-post-rain-offsets-aod [soft·P1] 雨后初晴的湿润洗空可抵消偏高AOD的浑浊,两者同现时禁止叠加扣分。
  来源: post-rain-offsets-aod — 2026-07-07(7.5分,AOD0.84+降水0.4mm,雨后托亮残云)
- precip-cloud-reading-four-points [soft·P1] 降水云判读四要点:Cb极冷亮砧状快速扩展、Ns成片均匀中低灰糊死、暖顶雨云红外低估、雨系未到不等于届时无云;必须表态雨系位置/移向/到达时序及其对画布与光路的影响。
  来源: precip-cloud-reading — knowledge §5降水云判读(2026-07-05用户质疑"要下雨却报低云量"引出)
- precip-forecast-distrust-ir [soft·P1] 任一模式报燃烧窗口降水时,不得信红外实测的低云量数字(暖顶雨云顶温280-290K红外贡献小被显著低估),雨险警惕升级。
  来源: precip-forecast-ir-distrust — src/skyfire/llm.py:106-107; knowledge §5.6暖顶低云陷阱 | 阈值: 暖顶亮温段280-290K

## 模式共识与分数结构

- consensus-multiplicative-gate [hard·P1] 总分必须是门槛乘法结构:画布×通道×本地低云×气溶胶×降水连乘,任一硬门槛不满足因子趋零直接压垮总分,禁止改成线性加权求和。
  来源: 合并: multiplicative-gate-structure / score-multiplicative-gate — knowledge §0/§6(三家方法论共识); src/skyfire/scoring/firecloud.py:94-98
- consensus-quality-prob-separate [hard·P1] 质量分(能烧多好,按条件期望算)与概率/置信度(多模式一致性)必须分离:模式间分歧只进置信度,禁止把分歧平均进质量分搅糊。
  来源: quality-probability-separation — knowledge §6/§7病因3
- consensus-median-skill-weighted [hard·P1] 多模式共识用中位数而非算术平均(防单模式规则性零分拖垮均值);全模式样本≥30后按1/(MAE+5)技能加权;confidence由原始分层云量分歧计算而非规则分一致性——一致得零不等于高置信。
  来源: 合并: consensus-median-not-mean / consensus-median-and-raw-confidence — src/skyfire/consensus.py:20-29; 2026-07-07漏报根因④(0.5/0.8/0/0把均值压到0.3+一致得零假high) | 阈值: 技能加权激活: 全模式样本≥30
- consensus-2v2-dual-scenario [hard·P0] 模式双峰硬分歧(派内极差小、派间关键层云量差>50pp)禁止用中位数/均值劈出不存在的幻影中间场景:卫星可信(帧新鲜且非满盖盲区)时由实况仲裁选边;否则输出双情景(各自云量结构/分数/概率/触发判据)+低置信,推送标"模式硬分歧"。⚠阈值冲突: 40pp vs 50pp——裁决:50pp(多数源+代码提示词现行),40pp留作回测候选。
  来源: 合并: model-split-dual-scenario ×2 / model-split-no-median / no-median-on-2v2-divergence — 2026-07-09漏报根因④(报52/48实际0分); 用户拍板2026-07-10; src/skyfire/llm.py:118-123 | 阈值: >50pp(候选40pp待回测)
- consensus-far-divergence-conservative [hard·P0] 远期硬分歧必须保守:距燃烧>6h且关键层极差>50pp时谁对未定,概率封顶baseline+15pp、置信给low、解读必须含"待临近实况确认",禁用大胆律。
  来源: 合并: far-lead-conservative / far-hard-divergence-conservative — 2026-07-09 c1=58%过高复盘(五五开分歧押成58%反面教材,12c9359批次); src/skyfire/llm.py:118-123 | 阈值: 6h/50pp/+15pp
- consensus-confidence-by-spread [hard·P1] 置信度由模式分歧宽度定档(规则分0-10尺度):模式数<2→degraded;极差≤1.5→high、≤3.0→medium、>3.0→low(分歧大明确输出"模式打架")。
  来源: confidence-by-spread — src/skyfire/consensus.py:31-38; spec 2026-07-03 §5.3 | 阈值: 1.5/3.0;模式数<2→degraded
- consensus-prob-formula [hard·P1] 免费层概率% = 修正后质量% × 一致性系数(high 1.0/medium 0.85/low 0.7/degraded 0.6)。
  来源: prob-confidence-multiplier — src/skyfire/percent.py:11,32 | 阈值: 1.0/0.85/0.7/0.6
- consensus-quality-rule-x10 [hard·P1] 免费层基线质量% = clamp(规则分×10),再走燃烧时刻云量修正链,不得与卫星实况脱钩。
  来源: quality-equals-rule-x10 — src/skyfire/percent.py:18-31; spec 2026-07-05 §3; 2026-07-07漏报根因③ | 阈值: ×10
- consensus-missing-forecast-not-zero [hard·P0] 点预报云量缺测(None)禁止按0或"无云可烧"处理:改用卫星实测替代,置信degraded。
  来源: missing-forecast-not-zero — 2025-09-30(8分,三层全None被判0,缺测数据骗了预报); 2021-06-18(9分,三项全缺仅应标degraded)
- consensus-conflict-flags-dual-scenario [hard·P0] 云量来源冲突(IR-VIS背离>30pp)、模式2v2硬分歧、AOD缺口任一标志置位时,推送必须双情景(乐观/悲观各自成立条件与概率),禁止合成单一数字。
  来源: dual-scenario-on-conflict — 2026-07-09(报52/48单一概率,实际0分,用户2026-07-10复盘)
- consensus-missing-factor-flag [hard·P1] 任一输入因子缺失:不惩罚质量分但也禁止按满配中性1.0,取保守中间值,置信降档,报告与推送标注哪个因子未知。
  来源: missing-data-confidence-flag — knowledge §6(缺数据不惩罚置信另算)+2026-07-09根因③教训修正
- consensus-per-model-raw-check [soft·P1] 必须逐模式核看per_model_raw(各模式对燃烧时刻高/中/低云与降水的原始预报)并对分歧表态,任一模式报降水即提高雨险警惕,不得只看汇总分。
  来源: per-model-raw-divergence-check — src/skyfire/llm.py:110-111; spec 2026-07-06 §1(2026-07-05实证: LLM看不到GFS报100%云+5mm雨把方向猜反)
- consensus-source-fail-degrade [hard·P2] 预报源超时/失败重试无效→降级为缓存的上一轮单模式EC,标注"数据不全,置信度降级"。
  来源: forecast-fail-single-model-degrade — spec 2026-07-03 §8

## 时间维与数据新鲜度

- fresh-near-satellite-first [hard·P0] 临近窗口燃烧时刻云况以卫星实测/移速外推为准覆盖预报,预报数字只作结构与趋势参考(EC/GFS曾报100%实测25%错4倍)。⚠时窗冲突: 知识库≤2h vs 实现/用户口径≤3h——裁决:≤3h启用实测覆盖,≤2h为强约束。
  来源: 合并: canvas-satellite-over-forecast / cloud-amount-satellite-first / burn-time-cloud-satellite-when-near — 用户口径2026-06-26血泪教训+2026-07-09"必须卫星实测"; knowledge §3.2要点②; src/skyfire/llm.py:104-105 | 阈值: ≤3h启用(≤2h强约束)
- fresh-far-forecast-only [hard·P0] 距燃烧>3h(含c1/outlook 20+小时)禁止拿当前卫星实测或短时外推冒充届时云况——雨系未到不等于届时无云;基线只用多模式预报(cloud_args置空),实测/外推仅作趋势参考;同时禁因"预报不可信"弃用预报,预报是未来时刻唯一前瞻工具。
  来源: 合并: forecast-for-long-lead / no-current-sat-as-burntime / outlook-c1-no-satellite-baseline / far-time-trust-forecast-trend / forecast-irreplaceable-prior — 2026-07-05午间实战修复(C1曾拿上午实测冒充8小时后)+同日实证(上午14% vs GFS日落100%两者都对); spec 2026-07-06 §2; 用户口径2026-07-05定论 | 阈值: >3h禁实测替代
- fresh-forecast-prior-nowcast-extrapolate [hard·P0] 时间维方法论固定三段式:预报打前瞻底子→提前几小时盯卫星连帧动向与移速→把云趋势外推到燃烧时刻;C2/C3必须执行外推(estimate_shift/extrapolated_corridor)并把外推后的燃烧时刻云量结构喂给判读,推送注明是否结合实时云图。
  来源: 合并: forecast-prior-nowcast-extrapolate / time-trend-extrapolation — 用户口径2026-07-05读图方法论定论+2026-07-09原话; knowledge §3.2要点②/§5.4
- fresh-quality-sync-nowcast [hard·P0] 临近窗口质量分必须吸收卫星实况修正,禁止quality与nowcast脱钩各说各话:实况canvas判读≥良而轨迹quality<40→强制复核禁直接按低分发布;最终质量=预报底分×实况修正,不一致时以实况链为准并标注。
  来源: 合并: quality-sync-nowcast / quality-must-track-satellite / quality-coupled-to-satellite — 2026-07-07漏报根因③(轨迹质量长期压33-40,卫星58%只给prob+15pp); be8a873修正实现; MEMORY skyfire-coldstart-progress.md | 阈值: quality<40触发复核;档位15/30/90(be8a873实现值)
- fresh-data-freshness-labels [hard·P0] 每次预测输出必须标注所用各数据新鲜度(预报起报时间/卫星帧龄/AOD观测时刻),过期数据不得静默当实时用,超时效自动标注并降置信。
  来源: data-freshness-label-required — 2026-07-09漏报复盘; 用户拍板2026-07-10; spec 2026-07-03 §5.4帧龄监控
- fresh-frame-age-40min [hard·P1] 卫星最新帧帧龄超过40分钟必须在输出中降级标注,不拿旧图冒充实况(Himawari发布本身延迟20-30分钟)。
  来源: frame-age-40min-degrade — spec 2026-07-03 §5.4 | 阈值: 40min
- fresh-missing-frames-2h [hard·P1] 卫星缺帧超过2小时降级为纯模式预报,明确标注"缺实况校验,置信度降级"。
  来源: missing-frames-2h-forecast-only — spec 2026-07-03 §8 | 阈值: 2h
- fresh-nearest-hour-rounding [hard·P1] 峰值时刻取预报小时数据用就近取整(分钟≥30进位到下一小时),禁止截断到整点(04:47曾被截到04:00读数偏近一小时)。
  来源: nearest-hour-rounding — spec 2026-07-06 §1 | 阈值: 30分钟进位
- fresh-gated-llm-15pp [hard·P1] 检查点之间每30分钟免费层重算,只有概率/质量摆动超过15pp才唤LLM,否则只更新数字沿用上次解读。
  来源: gated-llm-15pp-swing — spec 2026-07-05 §2门控加跑 | 阈值: 15pp
- fresh-liveweight-curve [soft·P2] 综合判断中实况权重随临近上升:约30%@T-6h、60%@T-2h、T-1h起以实况外推为主导模式只做背景;偏差大时以实况为准并标注"实况推翻预报"。
  来源: liveweight-rises-near-window — spec 2026-07-03 §5.4权重曲线 | 阈值: 约30%@T-6h/60%@T-2h/主导@T-1h
- fresh-extrapolation-self-verify [hard·P1] 每次外推预判连同时间戳落库,窗口过后用实际到达的卫星帧自动评判命中/落空,形成外推命中率统计,外推算法迭代以此为依据。
  来源: extrapolation-self-verification — spec 2026-07-03 §5.4外推准度自验证

## LLM 判读纪律

- llm-mandatory-rulebook-pass [hard·P0] 每次预测强制全表过堂:hard规则逐条机判、soft规则LLM逐条表态,并留存过堂记录;任一hard未机判或soft未表态则禁止发布。
  来源: mandatory-rulebook-pass — 用户2026-07-10拍板原话
- llm-rulebook-versioned [hard·P0] 规则表纳入版本管理:每条预测记录写入rulebook_version字段;规则增删改必须递增版本号并留变更记录。
  来源: rulebook-versioned — 用户2026-07-10拍板原话
- llm-no-score-anchoring [hard·P0] LLM判读禁被锚定:提示词禁止注入规则分上限/"40铁律";LLM必须先独立逐项陈述图上与数据证据(画布/通道/气溶胶/降水)再给数字,与基线差异大须写明改判理由,禁止无理由贴基线;单条硬规则只在其condition明确触发时才可作封顶依据,结论须列支持与反对证据。
  来源: 合并: llm-no-single-rule-anchoring / llm-no-rule-score-anchor / no-baseline-anchoring — 7/7漏报根因(40铁律+baseline锚定,MEMORY); 规则分0.0-2.6 vs 实际8-10分系统性背离9例(2022-06-07/2023-09-19/2024-05-06/2025-08-29/2025-09-28/2025-09-30/2026-01-07/2026-05-06/2021-06-18)
- llm-forty-scale-not-ceiling [soft·P0] "质量40以下不算烧"是事后判级刻度不是事前预测上限:<40普通日落底色、40云底局部真染色门槛、60-79中烧、80+大烧、满分整片云幕烧透;大烧配方成立(连贯画布+通道通+空气洁)时必须敢报>40乃至>80。
  来源: 合并: forty-is-grading-not-ceiling / quality-scale-not-ceiling — 2026-07-07漏报根因⑤(当晚10条预测全≤40); be8a873修正措辞; src/skyfire/llm.py:112-116 | 阈值: 40/60-79/80+档位
- llm-bold-only-when-confirmed [soft·P1] 大胆律(形态到位给60-85)只适用于模式一致、或临近且实况已印证的场合,与远期保守律配对使用缺一不可。
  来源: bold-only-when-confirmed — src/skyfire/llm.py:114-119 | 阈值: 大胆区间60-85
- llm-score-scale-calibration [hard·P0] 评分刻度统一:0=阴天无日落、2=失望、4=比一般还差、5=一般、6=中等偏好、8=明显好、9=刷屏、10=满分;禁止把≤4分案例在复盘中写成"烧了"。
  来源: score-scale-calibration — coldstart.csv评分口径(skyfire-coldstart-progress.md); 用户2026-07-06"4分=比一般日还差"+2026-07-09"阴天0分" | 阈值: 刻度0-10
- llm-burn-level-bands [hard·P1] 推送等级词由质量分硬映射:<20不烧、<40微烧、<60小烧、<80中烧、<90大烧、≥90爆烧,禁止手写等级词与数字脱节。
  来源: burn-level-bands — 推送格式v2 _burn_level(2026-07-07批次) | 阈值: 20/40/60/80/90五档
- llm-orange-band-not-burn [soft·P0] 烧的口径=云底大面积染成橙红(参照2026-05-06满分=整片云幕烧透);地平线橙带+云剪影只是普通日落底色(<40),4分=比一般日还差;事前判出"远通近堵只亮地平线"结构时质量必须下调并注明"预计仅地平线橙带";推送文案两档措辞,禁把橙带渲染成烧。
  来源: 合并: burn-definition-canopy-red / orange-band-not-burn / silhouette-not-burn / horizon-band-wording-ban — 用户口径2026-07-06(7/5案例4分纠正,case_notes#24)+2026-07-09重申"评分铁律"; 已写入_PREDICT_SYSTEM/_EXPLAIN_SYSTEM(e27a093); src/skyfire/llm.py:92/112-113 | 阈值: 40
- llm-six-step-recipe [hard·P0] 每次判读/复盘必须走完六步读图配方并逐条表态:①画布在不在②厚度对不对③通道通不通④空气净不净⑤湿度高不高⑥趋势朝哪;六条全过=可报大烧,任一硬门槛(通道堵/正降水/满盖厚云)不过=不烧,空气脏或湿度高=有几何也只中低分;三关(画布/通道/空气)齐才可能满分级;缺任一表态判读不合格。
  来源: 合并: reading-recipe-mandatory / read-recipe-six-steps / three-gate-checklist — knowledge §5读图配方; spec 2026-07-05 §4(配方进system走prompt caching); 2026-05-06满分复盘(case_notes#1三条件齐)
- llm-four-factors-for-high [soft·P1] 高分(≥8/质量≥80)必须四要素齐备并逐项勾选给依据:通道通+云幕有结构带破口+空气通透+无降水;缺项降档。
  来源: four-factors-for-high-score — 2020-09-01(9分)/2021-06-18(9分)/2024-05-06(9分)/2026-05-06(10分)均四项齐聚 | 阈值: ≥8分触发
- llm-no-silent-fallback [hard·P0] LLM判读失败禁止静默回落基线:写stderr日志+至少重试1次,仍失败则推送标注"本报未经LLM判读(基线值)"。
  来源: no-silent-llm-fallback — 2026-07-07漏报根因⑥(c1 LLM静默失败落基线无日志无重试;llm.py已加stderr日志) | 阈值: 重试≥1次
- llm-inputs-both-layers [hard·P1] LLM输入必须同时含预报层(多模式+规则分)与实况层(卫星实测/外推+趋势)并明示两者分歧,禁止只喂单层。
  来源: llm-inputs-both-layers-with-divergence — spec 2026-07-05 §1关键原则(实证2026-06-26)
- llm-json-contract [hard·P1] 预测LLM只输出固定JSON契约:probability_pct/quality_pct(0-100)、reasoning两三句中文、risks一句最大风险、confidence三档;解析失败或越界按失败降级pending不阻塞链路。
  来源: predict-output-json-contract — src/skyfire/llm.py:125-128; spec 2026-07-05 §4 | 阈值: 0-100
- llm-sonnet-escalation [hard·P1] 疑难自动升级Sonnet三触发:C1与C3分歧>25pp、复盘发现预测vs实际背离≥4分、RAG无相似案例。
  来源: sonnet-escalation-triggers — spec 2026-07-05 §4模型分层; src/skyfire/llm.py:97-98 | 阈值: 25pp/4分
- llm-no-arithmetic [soft·P2] LLM不做基础算术,只做案例类比与多因素权衡;数值计算全部由免费层完成;规则分与LLM修正分同时存档便于事后对比谁更准。
  来源: llm-no-arithmetic — spec 2026-07-03 §5.5
- llm-baseline-reference-not-binding [soft·P1] 免费层baseline数字仅是规则参考:与实况/形态矛盾时以LLM判断为准,可高于或低于基线但须说明依据,不得机械抄基线。
  来源: baseline-reference-not-binding — src/skyfire/llm.py:124; spec 2026-07-05 §3
- llm-degraded-confidence-explained [soft·P1] low/degraded置信本身是"通道云被低估或关键数据缺失"的警示:判读必须解释置信降级的具体原因及其对结论方向的影响,不得无视。
  来源: degraded-confidence-explained — 2024-05-16(2分,置信low正是通道云低估警示); 2021-06-18(9分,degraded只因缺测,数据骗了系统而非天象)
- llm-wording-plain [soft·P2] 面向大众的解读一律用城市名指地点(如"北京上空"),不说"红点/十字/标记处"等图上记号,不用专业缩写。
  来源: wording-city-names-no-jargon — src/skyfire/llm.py:107-109
- llm-review-five-elements [hard·P1] 复盘解读按五段输出(通道/云幕/大气/卫星形态/结论),预报与实际背离时必须点名哪个因子骗了预报;案例笔记五要素缺一不入库:通道实况(通/堵)、云幕(型·高·覆盖·破口)、大气(AOD·RH·是否雨后)、卫星形态一句话、因果结论,可附卫星帧路径与现场照片。
  来源: 合并: explain-five-sections-name-culprit / rag-case-note-fields — src/skyfire/llm.py:87-93(_EXPLAIN_SYSTEM); knowledge §8; spec 2026-07-05 §5反馈闭环
- llm-user-feedback-supreme [hard·P0] 用户实拍反馈与口径是最高权重真值:与规则分、LLM复盘或其他规则冲突时一律以用户为准;llm笔记被user笔记覆盖后不得再被引用为结论。
  来源: user-feedback-supreme — 2026-07-06 AI复盘误读4分为"烧了"被用户纠正盖章; RAG中user笔记权重最高
- llm-retro-trajectory-tracking [hard·P1] 每条案例自动记录"规则分 vs LLM修正分 vs 实际分"与各检查点预测轨迹;回测以"概率%/质量% vs 实际得分"的相关性与命中率为准(纯规则ρ已证伪)。
  来源: retro-quality-vs-actual-tracking — spec 2026-07-03 §9; spec 2026-07-05 §5/§10
- llm-twilight-wording [soft·P2] 太阳落到地平线以下的civil twilight段才是严格意义的火烧云(粉红),日落前多为金黄霞光:峰值窗口以日落后twilight段为核心,文案区分"霞光"与"火烧"。
  来源: twilight-pink-timing — knowledge §1

## 平流雾云海

- fog-three-gate-multiply [hard·P1] 云海指数=成雾分×雾顶分×有光分三关连乘(与火烧云"画布×通道"同构),任一关趋零即无戏,禁止加权求和。
  来源: fog-three-gate-structure — fog-rainbow知识 2026-07-09 §2/§5
- fog-formation-thresholds [hard·P1] 成雾关判据:黎明T−Td≤1℃(=0最佳)、RH≥95%、风0.5-4m/s;风向90-160°(渤海水汽通道)加分;临界值(如RH96%)按连续函数降档不满配。
  来源: fog-formation-thresholds — fog-rainbow知识 §2第一关 | 阈值: T−Td≤1℃;RH≥95%;风0.5-4m/s;风向90-160°加分
- fog-water-source-required [hard·P1] 水汽来源二选一是成雾前提:前日午后透雨≥15mm且入夜前雨停,或连日桑拿天东南暖湿平流;两者皆无成雾分大降。
  来源: fog-water-source-required — fog-rainbow知识 §2第一关 | 阈值: 前日透雨≥15mm且入夜前停
- fog-overnight-rain-wind-veto [hard·P1] 后半夜还在下雨是反指标——当晨城市云海否决;冷空气大风(≥12m/s)同为否决。
  来源: fog-overnight-rain-veto — fog-rainbow知识 §2第一关反指标 | 阈值: 后半夜降水>0;风≥12m/s
- fog-vertical-down-wet-up-dry [hard·P1] "下湿上干"垂直判据(李琛2025,F1=0.81可直接抄):1000/950/925hPa RH中位数≥93%且850hPa以上<60%;850hPa必须干(T−Td≥8℃为利),850hPa也饱和则雾顶被抬成层云+上方遮光,雾顶分与有光分同降。
  来源: 合并: fog-down-wet-up-dry / fog-850-must-be-dry — fog-rainbow知识 §1(李琛等2025/吴洪2000)/§2反指标 | 阈值: 低三层RH≥93%且850以上<60%;850hPa T−Td≥8℃为利
- fog-night-clearing-required [hard·P1] 后半夜放晴触发辐射冷却是黄金剧本必要环节(案例A总云39%→8%):有放晴满配,无放晴仅平流最高只给B档(中低云海)。
  来源: fog-night-clearing-required — fog-rainbow知识 §3案例A/B对照 | 阈值: 后半夜总云≤20%(案例A实测8%,待回测)
- fog-blh-tier-coefficients [hard·P1] 雾顶分按黎明BLH分档(城市视角核心):≤150m极低云海1.0、150-350m中低0.6、350-900m半山/高山0.3、>900m城区在雾里只给0.05。
  来源: fog-blh-tier-coefficients — fog-rainbow知识 §2第二关/§5 | 阈值: 150m/350m/900m
- fog-top-height-crosscheck [hard·P1] 雾顶高度双代理互校:分层RH(仅RH1000≥95%而RH950<85%=贴地雾;饱和层伸到925hPa=雾顶约1km)与BLH+LCL(≈125m×(T−Td))互校并对照观景台海拔;两信号矛盾时降置信并标注。
  来源: 合并: fog-layer-rh-top-crosscheck / fog-lcl-blh-proxy — fog-rainbow知识 §1(Lawrence 2005)/§2第二关 | 阈值: RH1000≥95%且RH950<85%=贴地;饱和至925≈顶1km;LCL≈125m×(T−Td)
- fog-light-gate-continuous [hard·P1] 有光关:雾上必须干净——黎明中高云≤10%给1.0,超出连续降权禁止硬归零(吸取7/7 canvas硬归零教训);日出方位低仰角光路被云墙堵→有光分趋零(火烧云通道判据换东即用);雨后AQI优良加"雾顶白净"标注。
  来源: fog-light-gate-no-hard-zero — fog-rainbow知识 §2第三关/§5 | 阈值: 中高云≤10%满分
- fog-wind-band [hard·P1] 风速带按雾型给分:平流雾2-8m/s最有利,≥12m/s被抬成低云或吹散直接否;辐射雾需静风<2m/s;北京大雾统一前提地面风<4m/s。
  来源: fog-advection-wind-band — fog-rainbow知识 §1(梁爱民2009/吴洪2000) | 阈值: 平流2-8m/s;≥12否;辐射<2;综合<4
- fog-golden-recipe-a-tier [hard·P1] A档满配黄金配方(2022-08-19七年最佳=五环节满配):前日透雨≥15mm+入夜雨停+后半夜放晴+黎明T−Td≤0.5且RH≥98%+微风≤4m/s+BLH≤150m+雾上零中高云——全中才报最高档"城市浮岛",缺任一环节按对应关降档。
  来源: fog-golden-recipe-a-tier — fog-rainbow知识 §3案例A/黄金配方; MEMORY fog-rainbow-expansion(2022-08-19归因五环节满配BLH55-90m) | 阈值: 透雨≥15mm;T−Td≤0.5;RH≥98%;风≤4m/s;BLH≤150m;中高云≈0
- fog-saturation-margin [soft·P2] 饱和度差半口气档次差一级:RH96%/T−Td0.7只得60-73%山前覆盖,RH100%满城——RH在94-98%临界带时必须明确表态覆盖预期(满城/山前局地)而非只报有无,并写入推送。
  来源: fog-saturation-margin — fog-rainbow知识 §3案例C归因 | 阈值: RH 94-98%临界带
- fog-synoptic-type-priors [soft·P2] 北京云海天气型先验:前倾槽型(43%)=雨停后出、维持短、转西北风即散;高压脊型(30%)=桑拿天夜间逆温可连续多日、可D-2预告;偏东风型(27%)多秋冬渤海输送;判读表态所属型。
  来源: fog-synoptic-type-priors — fog-rainbow知识 §1(李琛等2025,46例)
- fog-rarity-framing [soft·P2] 城市A档云海天生小概率(马涛类似条件试了十多次都失败):产品话术按"稀有成就"设计,A档预告带稀有度定位与不确定性说明,禁当常规预报拉满预期。
  来源: fog-rarity-framing — fog-rainbow知识 §3(京报网2024-08-05马涛)
- fog-spot-elevation-mapping [hard·P1] 输出必须按观景台落地:只推荐海拔>BLH+50m的机位;BLH≤120m报国贸/中国尊/奥森塔/景山,120-300m报百望山/香山半山,300-550m报香炉峰/妙峰山,更高档提示无人机;推送带具体机位名。
  来源: fog-spot-elevation-mapping — fog-rainbow知识 §5 | 阈值: 机位海拔>BLH+50m;档位120/300/550m
- fog-dissipation-deadline [hard·P1] 拍摄窗口=日出前30分~日出后90分;日出后1-4小时内必散、10时前必散(实证BLH从90m两小时炸到575m);推送必须带消散倒计时,10时后不再报当日云海。
  来源: fog-dissipation-deadline — fog-rainbow知识 §2拍摄窗口(吴洪2000+案例A实证) | 阈值: 日出−30min至+90min;10:00截止
- fog-forecast-cadence [hard·P1] 云海预测三段节奏:D-1 21:00展望(接明日展望推送)→当日02:00复核→04:30卫星实况终判,终判后才发确定性推送;副高连日型可D-2预告多日窗口。
  来源: fog-forecast-cadence — fog-rainbow知识 §5 | 阈值: 21:00/02:00/04:30
- fog-night-btd-detection [soft·P2] 夜间用葵花3.9−11μm亮温差(BTD)识别雾/低云,黎明可见光确认雾区,METAR ZBAA能见度/BR/云底作实况订正;三源不一致时降置信。
  来源: fog-night-ir-btd-detection — fog-rainbow知识 §5

## 彩虹

- rainbow-sun-elevation-gate [hard·P1] 彩虹几何硬门:太阳高度∈(0°,42°)才可能见平地虹(虹顶仰角=42°−太阳高度);评分5-25°=1.0、25-38°线性降、>38°=0.1;正午绝无平地彩虹;每日按太阳角预生成早/晚彩虹窗。
  来源: rainbow-sun-elevation-gate — fog-rainbow知识 §4/§5(Businger2021、Carlson2022) | 阈值: 有效0-42°;实用<38°;5-25°满分
- rainbow-rain-curtain-channel [hard·P1] 雨幕通道:反日点方位±35°、5-40km内0-2小时要有液态降水;雷达≥20-30dBZ块状对流回波优于层状(对流×1.2、层状×0.6);无雨幕→归零。
  来源: rainbow-rain-curtain-channel — fog-rainbow知识 §4/§5 | 阈值: 方位±35°;5-40km;≥20dBZ
- rainbow-sunlight-channel [hard·P1] 阳光通道:太阳方位±35°、0-50km须放晴(卫星可见光判雨区后界),总云>96%判无光路归零;傍晚虹的西边光路与火烧云西侧通道是同一份卫星判读,管线两用。
  来源: rainbow-sunlight-channel — fog-rainbow知识 §5 | 阈值: 方位±35°;0-50km;总云>96%判无
- rainbow-post-rain-hour [hard·P1] 约90%的彩虹出现在雨停后1小时内:"雨刚停≤1h"直接给高分档;雨团自太阳侧向反日侧移动再×1.2。
  来源: rainbow-post-rain-hour — fog-rainbow知识 §4(Liu 2023昭苏统计)/§5时序通道 | 阈值: 雨停后≤1小时
- rainbow-envelope-conditions [hard·P2] 彩虹包络条件:云量>40%(得有云才有阵雨)且气温>8℃,不满足则潜势降档或不评。
  来源: rainbow-envelope-conditions — fog-rainbow知识 §4(昭苏Liu 2023) | 阈值: 云量>40%;气温>8℃
- rainbow-direction-and-push [hard·P1] 清晨虹在西、傍晚虹在东(东虹日头西虹雨);L3触发推送必须带三要素缺一不发:背对太阳面向方位角X°、虹顶仰角N°(=42°−太阳高度)、窗口约M分钟。
  来源: rainbow-direction-and-push — fog-rainbow知识 §4/§5提前量分档
- rainbow-daily-windows [hard·P1] 北京夏季彩虹窗约05:00-08:30与16:30-19:40,每日按太阳角预生成早/晚窗,窗外时段一律不触发彩虹评估。
  来源: rainbow-daily-windows — fog-rainbow知识 §4 | 阈值: 夏季约05:00-08:30与16:30-19:40(随季节重算)
- rainbow-alert-tiers [hard·P1] 彩虹提前量分档:L1潜势日(D-1~3只进日历禁止推送打扰)→L2就绪(2-6h)→L3触发(0-60min推送带方位);L3链路延迟必须分钟级。
  来源: rainbow-alert-tiers — fog-rainbow知识 §5 | 阈值: L2=2-6h;L3=0-60min
- rainbow-quality-modifiers [soft·P2] 观赏度修正(已过三通道门槛后):雨滴越大越艳(中到大雨强→标双彩虹潜势)、空气/AQI越净越亮、太阳<10°时标注"红虹/最大拱"。
  来源: rainbow-quality-modifiers — fog-rainbow知识 §4/§5质量系数 | 阈值: 太阳<10°→红虹标注
- rainbow-elevation-exception [soft·P2] 高处(山顶/楼顶/无人机)可突破42°太阳高度限制甚至见全圆虹:几何门对高机位放宽并在推送提示。
  来源: rainbow-elevation-exception — fog-rainbow知识 §4
- rainbow-evening-script [soft·P2] 北京傍晚彩虹标准剧本:午后分散对流雨自西/西北东移过城→雨带移到东侧西边放晴→太阳<38°→背对夕阳面向东0-1h内出虹,窗口几分钟到半小时;清晨镜像;雷达拼图无官方API为脆弱点须监控。
  来源: rainbow-evening-script — fog-rainbow知识 §4
