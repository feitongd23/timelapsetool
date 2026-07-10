# skyfire 预测规则表(强制过堂)

版本管理的活文件:文献知识、用户经验、真实案例教训、复盘总结的唯一汇合点
(2026-07-10 由 129 条合并规则生成,四路蒸馏自:领域知识文档×2、23 个闭环
案例与笔记、用户历次口径原话、提示词与代码现行阈值;含冲突裁决)。
2026-07-10 六路一手文献扩展(约60个来源实读:Corfidi/Hulburt 1953/Lee 暮光系列/
GOES-R与JMA云掩膜ATBD/KMA AMV ATBD/Foroosh 2002/Farnebäck/pySTEPS/SunsetWx/
sunsetbot/李召麒/北京市气象局官方成因/PlanIt云层距离/US10459119B2):
+31条新知识入各节、11条修订提案见'修订提案'节、34条现行规则获文献佐证见'文献佐证'节。

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

- sat-night-low-cloud-b07-btd [hard·文献] 夜间暖顶低云/层云的正规检测靠B07(3.9μm)与B13发射率差:水滴云3.9μm发射率低于11μm,夜间(T10.4−T3.9)超清天差+offset判水云;GOES-R雾算法用伪发射率ems(3.9)=R_obs(3.9)/B(3.9,BT11),SEVIRI标定最优阈值0.7(技能0.69优于BTD法0.59),ems<0.9常对应雾/低层云。B07在HSD免费,现行管线未用,7/9漏掉的暖顶低云正是此类目标。
  来源: Pavolonis 2010, GOES-R ABI Fog/Low Cloud ATBD v1.0 §3.4.2 (star.nesdis.noaa.gov); Imai & Yoshida 2016 MSC Tech Note 61 §2.4.4; Heidinger & Straka 2012 ABI ATBD §3.4.1.3.2 ULST; CIMSS Quick Guide Night Fog BTD; 溯源Ellrod 1995 WaF 10:606 | 阈值: ems(3.9)最优0.7、雾/低层云<0.9;ULST: e4_clear−e4>0.10(陆);限T10.4>240K;不适用BT11>290K
- sat-terminator-b07-caution [hard·文献] 燃烧窗口恰在晨昏线,3.9μm混入太阳反射分量信号紊乱:GOES-R雾算法明言SZA>80°时3.9μm『erratic』;JMA把85≤SZA≤93定义为twilight换用含太阳项的白天型阈值;NWC-SAF用时间恢复法(1小时前判低/中云且|Δ1h(T10.8)|<1.0K且|Δ1h(T10.8−T8.7)|<0.5K则维持判定)。禁止在晨昏段直接套用夜间BTD阈值或反推符号。
  来源: Pavolonis 2010 Fog ATBD §1.11.2.4/§4.3.2; NWC-SAF 2019 Cloud ATBD v2.1 §2.2.1.2.5 (nwcsaf.org); Imai & Yoshida 2016 §2.3 | 阈值: 晨昏区间SZA 80-93°;维持判据|Δ1h(T10.8)|<1.0K且|Δ1h(T10.8−T8.7)|<0.5K(陆)
- sat-tempir-cooling-approach [hard·文献] 压境云系不依赖运动矢量也能测:逐像元时间红外差测试(TEMPIR)——当前帧比前帧(10-15min)11μm亮温骤降超过(两帧清天亮温漂移+2.0K)即判新云到达;云墙推进时前缘像元必然快速变冷,无需先解位移场,是FFT外推shift恒(0,0)盲区的独立补丁。
  来源: Heidinger & Straka 2012 ABI Cloud Mask ATBD v3.0 §3.4.1.2.3 TEMPIR + Table 3; Imai & Yoshida 2016 §2.2.1(t−10min与t−60min两帧时间变率) | 阈值: 单像元降温阈值2.0K+清天漂移项;触发占比10-20%起回测
- sat-uniformity-lid-vs-broken [hard·文献] 满盖须再分『均匀层云盖』与『破碎云幕』,定量指标为3×3像元B13亮温标准差:雾/低层云形成于稳定环境BT空间高度均匀(GOES-R雾概率LUT σ分箱仅0.10-1.00K,σ越小雾概率越高;ABI清天均匀性测试TUT阈值陆1.1K);σ小+暖顶=层状盖子(概率质量双杀),σ大或有暖破口=破碎/对流云(可能可燃)。
  来源: Pavolonis 2010 Fog ATBD §1.11.2.1.3/§1.11.2.2.2; Heidinger & Straka 2012 ABI ATBD §3.4.1.5.2 TUT | 阈值: 参考陆面清天均匀性1.1K;雾LUT σ范围0.10-1.00K;lid/broken分界1-1.5K起回测
- sat-split-window-cirrus-b15 [soft·文献] 薄卷云(好画布)与光学厚云(堵光)可用分裂窗BTD(B13−B15,11−12μm)区分:半透明卷云因光谱透过率差产生正BTD(PFMFT,承Inoue 1985),阈值参照清天BTD动态推算,CALIPSO标定判云阈值陆约2.5K;显著为正=半透明卷云画布,近0+冷+均匀=光学厚云墙。B15在HSD免费,是sat-vis-ir-combined-dense-vs-broken的夜间替代维度(2026-06-26红外陷阱同型场景)。
  来源: Heidinger & Straka 2012 ABI Cloud Mask ATBD §3.4.1.2.4 PFMFT + Table 3; Imai & Yoshida 2016 §2.4.5式(44)-(48) | 阈值: PFMFT判云陆2.5K/海0.8K(相对清天动态修正);限BT11<310K、σ3×3>0.3K
- sat-inversion-midcloud-misclass [soft·文献] 强逆温下卫星红外测高系统性失真:NWC-SAF明列『强逆温时很低云会被分类为中云』『低云上覆薄卷云会被判成中云』,业务补救是逆温时用T8.7−T10.8(B11−B13)重分类;北京秋冬夜间辐射逆温常见,届时『中云』读数可能实为低云,通道判堵应按更不利情形复核。
  来源: NWC-SAF 2019 Cloud ATBD v2.1 §3.3 + §3.2.1.2.2.4 (nwcsaf.org) | 阈值: 逆温判据层间ΔT>3K;重分类T8.7−T10.8<−1.2−(1/cosθsat−1)K且T10.8>低/中分界−5K
- sat-day-b07-reflectance-water-cloud [soft·文献] 白天与晨昏水滴云的第二探测器是3.9μm反射率:水云强反射太阳3.9μm使T3.9−T10.4显著超清天日间差(JMA白天/twilight水云测试,阈值含cos(θsunZ)太阳项);注意白天BTD符号与夜间相反(白天3.9偏暖=小粒径反射,夜间3.9偏冷=低发射率),禁混用。日落前1-2小时走廊低云识别可与VIS互证。
  来源: Imai & Yoshida 2016 MSC Tech Note 61 §2.4.3式(29)-(33); CIMSS Quick Guide(昼夜符号翻转) | 阈值: JMA日间动态阈值(含太阳项与反照率项);限T10.4>240K
- sat-vis-shadow-height-cue [soft·文献] 可见光暗影是被现行判读忽略的云高/云厚判据:『暗影只在可见光图上出现,可识别相对高度及云类别,还可区分低云和雾』『云越厚、云顶越高,暗影越宽』;低云投暗影、大范围雾区四周无暗影。燃烧窗口前后太阳角最低、暗影最明显,正是该判据最灵的时段。
  来源: 李梦《浅谈卫星云图在气象观测业务中的应用现状》工程技术发展2023, DOI:10.12238/etd.v4i1.6341(文章页已直连验证存在)
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

- cloud-multilayer-occlusion-lowest-opaque [hard·文献] 多层云共存时,能被点燃的画布=自下而上第一层不透光云的云底;其上所有云层被遮挡不计画布,通道几何与窗口按该层高度计算(PlanIt例二:同有6km高云+4km不透光中云时『可能形成火烧云的只能是中云』);sunsetbot亦把层间照明遮挡关系与云底高度列为独立因子。现行canvas公式(high+0.5×mid)无遮挡关系建模;7/9满盖暖顶中云=『最低不透光层是盖子』的典型情形。
  来源: PlanIt巧摄第十册《云层距离》实例二; sunsetbot.top详情页因素清单(Wayback 2025-11-09存档) | 阈值: 『不透光』判据候选:该层光学厚且覆盖≥80%(待回测标定)
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

- fresh-near-satellite-first [hard·P0] T-2/T-1 检查点必须强制结合实时云图+四模式预测云图,两者并用谁都不许单干(基线权重:T-2 实况0.5、T-1 实况0.6);实况读数被标满盖修正/外推不可信时按修正后口径用。用户口径2026-07-10改写(原'临近以卫星为准覆盖预报'在7/9被误读卫星反噬)。
  来源: 合并: canvas-satellite-over-forecast / cloud-amount-satellite-first / burn-time-cloud-satellite-when-near — 用户口径2026-06-26血泪教训+2026-07-09"必须卫星实测"; knowledge §3.2要点②; src/skyfire/llm.py:104-105 | 阈值: ≤3h启用(≤2h强约束)
- fresh-far-forecast-only [hard·P0] 距燃烧>3h:实时云图外推可参考但只作次要修正(基线权重0.3,>6h降至0.15),主要认定标准=四个模式的预测云图;禁止拿实况外推冒充届时云况当主判据。用户口径2026-07-10改写。
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
- fresh-liveweight-curve [hard·P0] 实况权重梯度已定死并落码(engine._sat_weight):>6h→0.15、3-6h→0.3、1.5-3h→0.5、≤1.5h→0.6;c1/outlook封顶0.3;位移峰质量低减半。用户口径2026-07-10拍板,数值待案例回测微调。
  来源: liveweight-rises-near-window — spec 2026-07-03 §5.4权重曲线 | 阈值: 约30%@T-6h/60%@T-2h/主导@T-1h
- fresh-extrapolation-self-verify [hard·P1] 每次外推预判连同时间戳落库,窗口过后用实际到达的卫星帧自动评判命中/落空,形成外推命中率统计,外推算法迭代以此为依据。
  来源: extrapolation-self-verification — spec 2026-07-03 §5.4外推准度自验证


## 外推与运动估计(2026-07-10 文献扩展)

- nowcast-fwd-bwd-consistency-qc [hard·文献] 每个运动矢量必须做前向(t0→t1)与后向(t1→t0)双向估计并检验闭合性:真实位移应满足v_back≈−v_fwd,不闭合的矢量判不可信不得进入外推;JMA/EUMETSAT业务AMV质量控制(Holmlund 1998 QI)核心即此类一致性检验。
  来源: Shimoji 2014 §2(forward/backward QC by QI); KMA ATBD §3.2.5(五项一致性检验加权成QI) | 阈值: 候选|v_fwd+v_back|>max(1px, 0.3×|v_fwd|)判不可信(文献为连续QI函数,硬阈值待回测)
- nowcast-phasecorr-hann-window [hard·文献] 相位相关前必须对两帧加Hann窗:DFT周期延拓假设使图像边界产生虚假相关能量(Foroosh误差分析'border errors'),OpenCV phaseCorrelate流程第一步就是加Hanning窗;现行drift.py裸fft2无窗,392×683非方形小图边界效应更明显。
  来源: OpenCV imgproc.hpp phaseCorrelate文档+createHanningWindow(github.com/opencv/opencv 4.x源码); Foroosh et al. 2002 §IV
- nowcast-phasecorr-response-gate [hard·文献] 『外推不可信』的第一判据=相关峰质量,必须随矢量一起输出:OpenCV response=主峰5×5邻域相关能量占比(单峰归一化为1,多峰变小——多峰正是多层云各向异动/原地生消/纹理弱的指纹);Foroosh证明相干峰功率对应两图重合面积比例。response低→外推不进打分链,cloud-value-priority跳过projected档回落sat实测并置双情景标志。
  来源: OpenCV imgproc.hpp phaseCorrelate文档(response语义原文); Foroosh et al. 2002 §II-A | 阈值: response阈值随外推自验证库(fresh-extrapolation-self-verify)统计命中率后标定
- nowcast-optflow-tvl1-params [soft·文献] 若允许引OpenCV依赖,卫星云图稠密运动场首选TV-L1光流(Zach 2007,L1数据项+全变分正则,粗到细warping抗大位移):SEVIRI有效云反照率上TV-L1在全部21个例优于Farnebäck(15min预报abs bias 4.37% vs 5.43%),DWD已业务化;云图调优参数可直接抄。
  来源: Urbich, Trentmann & Zempila 2018, Remote Sensing 10(6):955, doi:10.3390/rs10060955 | 阈值: lambda=0.03/theta=0.3/tau=0.1/gamma=0.1/epsilon=0.01/外迭代2/内迭代10/Nwarps=3/Nscales=3/scale_step=0.5(SEVIRI 15min标定,Himawari 10min需微调回测)
- nowcast-optflow-fallback-farneback-lk [soft·文献] TV-L1之外两个可落地次选:①Farnebäck两帧稠密光流(邻域二次多项式拟合,逐点残差e(x)是现成反向置信度;弱点=平滑假设抹掉多层云边界);②pySTEPS业务默认dense_lucaskanade(Shi-Tomasi角点+金字塔LK+3σ离群剔除+IDW插值成稠密场,对纹理稀疏云图比逐点法稳)。
  来源: Farnebäck 2003, SCIA 2003 LNCS 2749:363-370 (ida.liu.se); pysteps.motion.lucaskanade.dense_lucaskanade文档 (pysteps.readthedocs.io) | 阈值: pySTEPS默认: nr_std_outlier=3/k_outlier=30/size_opening=3px/decl_scale=20px
- nowcast-growth-decay-residual-check [hard·文献] 外推只搬运不生消是拉格朗日持续性方案的原理性上限:『模型误差主要来自云的新生/增长/衰减/消亡,它们违反定常假设』;对流新生云会原地变亮直接违反强度守恒(7/9『压境云系原地增强』即此类)。可落地判据:把t−10帧按估出矢量场warp到t与实况比对,判读窗/走廊内云量残差超阈值→置『生消主导,外推不可信』标志→外推降级+双情景;残差落库,即fresh-extrapolation-self-verify的具体实现。
  来源: Pulkkinen et al. 2019, GMD 12:4185(原句initiation/growth/decay violate steady-state); Urbich et al. 2018 §4 | 阈值: 回代残差阈值待回测(参照文献良好平流情形abs bias约4-7pp,超此量级疑生消)
- nowcast-nwp-wind-prior-crosscheck [hard·文献] 模式引导风是运动估计的先验、交叉校验与兜底三用:KMA业务用NWP风定搜索窗中心(±30m/s窗宽防大窗伪峰),QI第五项即矢量与预报风一致性;PlanIt/李召麒预报流程亦明示看云动方向速度验证。skyfire镜像用法:①矢量测不出(低于分辨率/response低/前后向不闭合)时用画布层对应气压层(700hPa中云/300-500hPa高云)Open-Meteo风矢换算px/帧兜底外推并标注『外推=模式风』;②图像shift≈0而该层风明显非零时判图像外推失效,以风矢平流为准降置信;警惕搜索窗束缚过紧使观测矢量退化成模式风本身。(合并候选2条:amv-nwp-wind-prior-fallback/motion-windfield-crosscheck)
  来源: KMA ATBD §3.2.4-3.2.5; PlanIt巧摄第十册注意事项; 李召麒知乎专栏步骤3 | 阈值: 候选|图像shift|≈0且该层引导风≥5m/s判失效(待回测);KMA参照窗宽±30m/s
- nowcast-multilayer-per-channel-vectors [soft·文献] 多层云各层动向不同,单一2D矢量场原理上无法表达:夏季『薄卷云盖在中低云上』高频出现,业务AMV都因此层选择系统性出错(CALIPSO对比证实)。判据:B13红外(高云主导)与可见光帧(白昼低云纹理)各自估矢量场,同区两场背离大→置『多层异动』标志→分层外推+双情景(对应7/9满盖暖顶中云+高层卷云叠置,与consensus-conflict-flags-dual-scenario联动)。
  来源: Shimoji 2014 §5(Figure 7/8 CALIPSO对比,夏季multi-layer致层选择困难) | 阈值: 通道间矢量夹角/模差阈值待回测

## 大气光学几何(2026-07-10 文献扩展)

- optics-aod-altitude-type-distinguish [soft·文献] 柱AOD单值不区分气溶胶所在高度,而高度决定效果方向:平流层/抬升层气溶胶(火山、抬升沙尘)使暮光变红产生afterglow(平流层AOD仅0.042-0.169时chromaticity已明确向红端移动),边界层霾在暮光段只起调暗压色作用;画作R/G比与火山/沙尘AOD同升(Zerefos)。沙尘输送日与静稳霾日同为高AOD不应同罚。
  来源: Lemon et al. 2025, Environ. Res. Lett. 20:024060, doi:10.1088/1748-9326/ada2ae(已检索验证真实存在); Zerefos et al. 2014, Atmos. Chem. Phys. 14:2987 | 阈值: 平流层气溶胶增红文献区间AOD 0.042-0.169(550nm);减半幅度待回测标定
- optics-aod-canvas-height-modulate [soft·文献] AOD惩罚应随画布云高调制:染红云底的平射光若切点高于霾层顶则基本不受边界层AOD影响(Corfidi原文:云必须高到截获未经边界层衰减的阳光);高卷云画布受同一AOD的实际压色小于中低云画布,现行AOD系数对画布高度一刀切存在系统性偏差(高云日被多罚、低云日被少罚)。
  来源: Corfidi, S.F. (NOAA/SPC), The Colors of Sunset and Twilight, spc.noaa.gov/publications/corfidi/sunset/ | 阈值: 上浮半档(文献无定量,回测标定)
- optics-burn-peak-depression-3p9 [soft·文献] 最大红化时刻的定量锚点:暮光日侧红/紫光在太阳凹角≈3.9°达峰(Lee多站实测时序统计),即北京夏季约日落后20-23分钟,朝霞镜像为日出前同量;为『第二波上色』推送节奏提供物理锚,并把llm-twilight-wording细化为『峰值在凹角3.5-4°附近』。现行规则表无此定量锚点。
  来源: Lee & Hernández-Andrés 2003, Applied Optics 42:445 (Table 2凹角统计,峰值≈−3.9°) | 阈值: 峰值凹角3.5-4°(北京≈日落后18-24min);预期终点凹角6°
- optics-channel-ray-height-filter [hard·文献] 走廊逐段判堵必须引入光线离地高度几何,不能距离一刀切:地球曲率下光线高度h≈d²/2R(日落0°时100km→0.8km、200km→3.1km、300km→7.1km;太阳每降1°切点上游移约111km),300km外低云在光路之下不构成堵;配合切点距离d≈√(2Rh)(2km→160km/4km→226km/6km→277km/10km→357km),每个堵点段应标注其杀伤的画布层:近程0-100km堵杀低/中云画布、200-300km伤中云、300-400km才伤高云。这统一解释channel-far-400km-tolerated与channel-far-wall-veto的适用边界;7/9根因③的通道阈值回测应按(距离段×画布高度)分层统计。(合并候选2条:channel-ray-height-geometry/corridor-tangent-geometry-per-height)
  来源: PlanIt巧摄第十册《云层距离》(实例数据); 球面几何标准公式h≈d²/2R、d≈√(2Rh)(R=6371km); Corfidi NOAA/SPC机制引文 | 阈值: h(d)≈d²/12742km;切点d≈√(2Rh);太阳每降1°切点上移约111km
- optics-corridor-depression-zones [soft·文献] 走廊各距离段应耦合『受光时窗』:专利按太阳压角分区——近区(Zone1)太阳约−3°时受光,远区(Zone3)到−9°仍被照亮,日落后色彩窗口最长约45分钟;远端云主导日落后深红段、近端云主导日落前后金橙段。现行走廊各距离段均权、无时序权重,属可升级点。
  来源: US10459119B2 (Kuhns), patents.google.com/patent/US10459119B2 | 阈值: −3°/−9°/约45min
- optics-terrain-masking-corridor [soft·文献] 地形遮挡应纳入通道判断:SkyCandy专利构建含周边地形的3D光路模型做masking(『落基山有低云而用户在山谷则完全无色』);李召麒对云边界326km的判断特意加『考虑到山的因素勉强上垒』。北京晚霞光路(西/西北)正跨太行山-燕山,现行走廊只看云不看地形。
  来源: US10459119B2(terrain masking原文); 李召麒知乎专栏实例(326km) | 阈值: 收紧10-20%(文献未给数值,待标定)

## 天气形势分型(2026-07-10 文献扩展)

- synoptic-rain-tail-west-clear [soft·文献] 北京超级晚霞头号高发形势=大范围降水刚结束、本地位于降水云团尾部(头顶残留大面积形态丰富云幕)+以西大片晴空区(日落光无遮挡)+雨后能见度提升;检测到该形势应上调概率并触发临近关注推送(北京市气象局官方成因解读原文)。
  来源: 尤焕苓/齐晨(北京市气象局),北京日报客户端2024-09-30 xinwen.bjd.com.cn/content/s66fa82a6e4b0c25b287c2b98.html(腾讯转载news.qq.com/rain/a/20240930A07PF300)
- synoptic-cold-vortex-multiday-prior [soft·文献] 东北冷涡是北京5-6月晚霞高发天气型:冷涡活跃期控制华北时反复出现『短时雷阵雨-雨后速晴』循环,后部偏北气流带来通透天空(冷涡蓝)+不稳定扰动生成层积云/淡积云画布,可连续多日出晚霞(2026年6月北京15天出现晚霞景观)。
  来源: 新华网2026-06-09 news.cn/politics/20260609/ed0e84783f6f4f65b8e178c77a5245a0/c.html; 新华网2026-07-02; 信欣(中国天气网),北京日报《冷涡滤镜下的北京》 | 阈值: 活跃期5-6月;2026年6月实测基率15/30天(约50%)作展望先验参考

## 系统与验证方法(2026-07-10 文献扩展)

- system-glow-two-types-sky-vs-cloud [soft·文献] 霞分两类且预报路径不同:天空霞(无云幕,靠霾/气溶胶散射漫天红光,『预报日出日落时段有霾基本可判天空霞』)与云霞(火烧云,需云幕,按天气系统移动规律预报)。skyfire预测目标是云霞;复盘评分不得把无云幕的天空霞计为火烧云命中;霾+少云日可作『天空霞』低档提示而非火烧云概率。与高AOD压云霞不冲突(高AOD正是天空霞成因)。
  来源: 戴云伟(华风气象传媒),光明科普云2024-05-16 kepu.gmw.cn/2024-05/16/content_37332884.htm
- system-visibility-independent-check [soft·文献] 地面能见度是独立于AOD的挡光核验因子,也是雾的直接观测:李召麒把『看能见度』列为预报必经步骤(北京看IAP 325m气象塔实拍),『光路上不能有雾霾、水汽、沙尘等挡光因素』;sunsetbot浑浊度口径也含『AOD/大气浑浊度(或者雾)』。现行体系只有AOD+RH,没有能见度观测这一路,可作aod-missing-not-neutral的第三兜底源。
  来源: 李召麒知乎专栏步骤4; 周到上海2019-10-31李召麒专访(static.zhoudaosh.com转载); sunsetbot.top详情页 | 阈值: 候选<10km警示、<5km重罚(文献未给数值,待标定)
- system-quality-duration-sky-area [soft·文献] sunsetbot鲜艳度显式包含skyfire质量分没有的三维度:持续时间、亮度与颜色、占据本地天空的面积;其0.8-1.0档(不完美大烧)扣分理由即『云量没有最高、大气偏污、持续时间偏短、有低云遮挡』,1.5-2.0(优质大烧)特征『范围广、云量大(不一定满云量)、颜色明亮、持续时间长、大气通透』。
  来源: sunsetbot.top详情页九档定义(Wayback 2025-11-09存档;直连超时按上游存档记录保留) | 阈值: sunsetbot分档:0.05-0.2小烧/0.4-0.6中烧/0.8-1.0不完美大烧/1.0-1.5典型大烧/1.5-2.0优质大烧/2.0-2.5世纪大烧
- system-retro-photo-rg-aod-proxy [soft·文献] 复盘照片可量化对账AOD:天空区R/G通道比值是红化程度/气溶胶的经济代理(500年画作研究R/G与火山AOD序列相关,Hydra现场实验画家R/G与同址太阳光度计AOD吻合);建议把用户实拍(photos表/chat-photo-auto-archive流程)天空R/G作为复盘存档字段与aod_used对账,为AOD分档系数积累本地校准样本。仅作相对/趋势指标,禁止直接反演绝对AOD(Wullenweber et al. 2022 Climate of the Past 18:2345对绝对反演有质疑,该条为摘要级次级证据)。
  来源: Zerefos et al. 2014, Atmos. Chem. Phys. 14:2987-3015, acp.copernicus.org/articles/14/2987/2014; 次级: Wullenweber et al. 2022, Climate of the Past 18:2345 | 阈值: 仅相对指标;样本≥20例后启动标定
- system-backtest-confusion-matrix [soft·文献] 回测统计应采用sunsetbot公开做法:按预报结果归一化+按观测结果归一化的双向分档混淆矩阵(其基于上海2022.6-2023.12 ERA-5,并诚实标注再分析回测是上限『实际GFS表现只会更差』);双向归一能分别暴露空报结构与漏报结构(7/9正是0分档漏报),信息量大于单一相关系数/命中率。
  来源: sunsetbot.top详情页准确率(Disclaimer)节(Wayback 2025-11-09存档)
- system-threshold-evidence-grading [hard·文献] 规则表须增加证据等级字段,把无外部佐证的内部经验数字统一标E级并列回测优先级:通道判堵全套数字(low>60、中云墙total≥90且mid≥60×2段、系数斜率1.8、下限0.1、low≥80@0-50km、low≥85@200-300km——7/9根因③点名,检索SunsetWx与两件专利均无判堵百分比)、远期保守律6h/50pp/+15pp(出自7/9复盘拍板,ECMWF FUG仅定性)、IR-VIS背离30pp、卫星覆盖预报20pp、2v2缺口50pp,方向多有文献背书但数字全部系统内经验;优先回测60判堵线/1.8斜率/0.1下限三个最敏感数,用llm-retro-trajectory-tracking积累『走廊剖面-实际得分』对与reliability diagram校准。(合并候选2条:channel-block-thresholds-uncorroborated/far-lead-conservative-internal)
  来源: 负结果检索:sunsetwx.com/about-the-model与US10459119B2已读均无判堵百分比;ECMWF Forecast User Guide §8.1.2仅定性;现行值出自src/skyfire/scoring/firecloud.py与2026-07-09/10复盘拍板 | 阈值: 首批回测:60判堵线、1.8斜率、0.1下限、50pp缺口、+15pp封顶

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

## 修订提案(文献挑战现行阈值,标注可直改/待回测)

- REVISE-window-end-depression-geometry [hard·文献] 现行cloud-height-tiers『高云>6km日落后仍可亮约30分钟』固定分钟数→文献建议按太阳凹角×画布云高×云位几何机算:天顶h高的云在凹角δ=arccos(R/(R+h))入影(10km卷云≈3.2°≈日落后17-20min、4km≈2.0°≈10-12min、1.5km≈1.2°≈6-8min,云位偏西每100km晚约0.9°);日落方向远处画布可亮至太阳-6.1°(4km)/-7.5°(6km)甚至-9°(≈40-50min)。固定30分钟对天顶高云系统性偏晚、对远端高云偏早。出处:Lee & Hernández-Andrés 2003 Applied Optics 42:445(实测凹角0.2-8.5°、峰值3.9°);PlanIt巧摄第十册《云层距离》;US10459119B2;Corfidi NOAA/SPC。几何公式确定可直接改代码,-6.1/-7.5°档位建议回测校验。(合并候选3条:afterglow-window-by-depression-geometry/window-end-by-canvas-height/burn-window-sun-depression-by-height)
  来源: Lee & Hernández-Andrés 2003, Applied Optics 42:445; PlanIt巧摄第十册 planitphoto.cn/pdfs/10.PlanIt_Cloud_Distance.pdf; US10459119B2; Corfidi NOAA/SPC | 阈值: 天顶10km≈17-20min/4km≈10-12min/1.5km≈6-8min;远端4km→-6.1°、6km→-7.5°~-9°;硬终点δ8.5°≈45-50min
- REVISE-sat-cloudfrac-mask-not-linear-bt [hard·文献] 现行box_cloudiness用B13亮温线性刻度gray=(310-BT)/130均值折算→文献:云量必须=云掩膜逐像元二元判云后的面积占比;红外亮度是温度/发射率/高度混合量,暖顶低云(280-290K)线性刻度只得0.15-0.23,7/9满盖被读成34%即此病;需连续『云性』标量应改用参照晴天的ETROP当量发射率ε=(I−I_clear)/(I_bb−I_clear)。出处:Heidinger & Straka 2012 GOES-R ABI Cloud Mask ATBD v3.0 §3.4;Imai & Yoshida 2016 JMA MSC Tech Note 61。算法结构明确可直接改代码,判云offset需少量回测标定。
  来源: Heidinger & Straka 2012, GOES-R ABI Cloud Mask ATBD v3.0 (star.nesdis.noaa.gov); Imai & Yoshida 2016, JMA MSC Technical Note No.61 | 阈值: ETROP判云阈值海0.10/陆0.30;掩膜四级输出cloudy/probably-cloudy/probably-clear/clear
- REVISE-sat-clear-bt-dynamic-292k [hard·文献] 现行满盖判定固定292K(夏)/283K(春秋)季节常数→文献一致做法为动态晴空参照:T10.4<T_sfc_clear+dT_elv+offset(NWP地表温度+海拔订正−6.49K/km+比对标定offset),或近5-14天滚动晴空合成;『阈值从不全局成立』,固定常数在异常暖/冷日与春秋过渡期系统性失效(北京11µm晴空地表亮温冬夏差40K+:夏错判暖顶云、冬把冷晴地表误判满盖)。出处:Imai & Yoshida 2016 §2.4.2式(18)-(20);Heidinger & Straka 2012 §3.4.1.2.1;WMO/CIRA SAT-28第6章(引Rossow & Garder 1993 ISCCP五步晴空合成)。可直接改代码(Open-Meteo已有地表温度),margin 4-6K需回测;292/283K降级为fallback并标注降置信。(合并候选2条:sat-clear-sky-bt-dynamic-not-fixed/ir-fixed-292k-vs-dynamic-clear-sky)
  来源: Imai & Yoshida 2016, JMA MSC Tech Note 61 §2.4.2; Heidinger & Straka 2012, ABI Cloud Mask ATBD §3.4.1.2.1; WMO/CIRA SAT-28 Ch.6 (rammb.cira.colostate.edu) | 阈值: margin初值4-6K回测;高度订正−6.49K/km;JMA雪邻域附加−5.0K;现行292K vs 文献逐点动态
- REVISE-motion-local-vectors-not-global [hard·文献] 现行estimate_shift整幅单一全局整像素FFT相位相关→业务AMV标准做法:分块局部矢量场(KMA现业目标块24×24px、搜索窗按NWP风±30m/s配置)+小5×5/大15×15双尺度目标箱+前向/后向匹配四张相关面平均消伪峰;单一大箱在静止背景主导时锁死零位移伪峰是文献明示的已知失效模式(7/9压境云系测不出根因②部分即此);走廊各采样点须用所在块局部矢量回溯,废止全图单一shift。出处:KMA/NMSC COMS AMV ATBD v1.1 §3.2(Nieman et al. 1997);Shimoji 2014, 12th Int. Winds Workshop(JMA Himawari-8 AMV)。架构性改造可直接按文献参数落地,块尺寸/搜索半径在skyfire分辨率下需回测换算。(合并候选3条:amv-block-matching-local-vectors/sat-motion-multibox-fwd-bwd-xcorr/amv-dual-scale-fb-surface-averaging)
  来源: KMA/NMSC COMS AMV ATBD v1.1 §3.2 (nmsc.kma.go.kr); Shimoji 2014, 12th International Winds Workshop (eumetsat.int) | 阈值: 目标块24×24px(KMA)或5×5/15×15双尺度(JMA,2km红外≈10km/30km);搜索半径≤最大可信风速(±30m/s)换算px
- REVISE-phasecorr-subpixel-and-zero-shift [hard·文献] 现行drift.py:18整像素unravel_index(argmax)且shift=(0,0)被解读为云系静止→文献:离散DFT相位相关只对整数位移成立,位移<1px/帧必然返回0——是『测不出』不是『没移动』(7/9根因②:10min帧距+2km像素把压境云系量化成零位移);修法①主峰5×5加权质心(OpenCV phaseCorrelate业务做法)或Foroosh侧峰比值闭式解Δx=C(x0+1,y0)/(C(x0+1,y0)±C(x0,y0));②上采样互相关(因子≥10,0.1px≈200m精度);③加长基线30-60min重估;仍测不出→输出『位移低于分辨率,外推不可信』,禁得出『届时维持不变』。出处:Foroosh, Zerubia & Berthod 2002 IEEE TIP 11(3):188;OpenCV modules/imgproc/src/phasecorr.cpp weightedCentroid;Guizar-Sicairos et al. 2008 Optics Letters 33:156;KMA ATBD(<2.5m/s慢速矢量按0.4×风速打折QI)。可直接改代码无需回测。(合并候选3条:phasecorr-subpixel-mandatory/amv-subresolution-motion-not-static/motion-subpixel-or-optical-flow)
  来源: Foroosh et al. 2002, IEEE Trans. Image Processing 11(3):188-200 (cs.ucf.edu/~foroosh/subreg.pdf); OpenCV phasecorr.cpp源码; Guizar-Sicairos et al. 2008, Optics Letters 33:156; KMA AMV ATBD §3.2.5 | 阈值: 质心窗5×5(OpenCV默认);上采样因子≥10;基线30-60min;|v|<1px/帧触发
- REVISE-motion-three-frame-confidence [hard·文献] 现行sat-motion-trend-required只要求≥2帧判动向→文献:2帧只能给出矢量,矢量的置信度需连续3帧产生的2个矢量做时间一致性检验(方向/速度/矢量三项,KMA原文『checks temporal direction consistency between two vectors retrieved from the continuous three satellite imagery』);外推要参与打分必须拉3帧,两段矢量不一致则外推降级标注。出处:KMA/NMSC COMS AMV ATBD v1.1 §3.2.5(Holmlund 1998 QI体系)。可直接改代码,像素域一致性阈值待回测。
  来源: KMA/NMSC COMS AMV ATBD v1.1 §3.2.5; Holmlund 1998, Wea. Forecasting 13:1093(经ATBD引用) | 阈值: KMA QI系数参照(tdc=4/tsc=2.5/tvc=3/svc=3);skyfire像素域阈值待回测
- REVISE-channel-length-by-canvas-height [hard·文献] 现行走廊固定0-400km一把尺→文献:所需无云距离按画布云高机算(切线几何d≈√(2Rh)):低云画布只需查0-300km(300km外堵点不计堵,与现行channel-far-400km-tolerated互证);中云画布须查至360km(精确677km)、高云画布至500km(精确829km)——画布位于日落方向地平线远处时,现行400km上限在400-830km段存在堵墙漏检盲区;且『中云会遮住高云,可能形成火烧云的只能是中云』。出处:李召麒《如何在拍照前预报晚霞?》知乎科学摄影专栏(2019);PlanIt巧摄第十册《云层距离》(4km→226/677km、6km→276/829km实例,PDF已确认真实存在)。几何公式可直接改代码;远段数据可得性与堵点权重需回测。(合并候选2条:channel-length-by-canvas-height/channel-horizon-canvas-830km)
  来源: 李召麒《如何在拍照前预报晚霞?》知乎·科学摄影专栏(Wayback 2022-12-12存档); PlanIt巧摄第十册 planitphoto.cn/pdfs/10.PlanIt_Cloud_Distance.pdf | 阈值: 保守:2km→300km/3km→360km/6km→500km;精确:4km→677km/6km→829km;现行上限400km vs 文献829km
- REVISE-aod-worst-tier-boundary [hard·文献] 现行最重惩罚档≥1.0才触发(→0.3),0.6-1.0统一0.6→sunsetbot公开AOD口径最重档界在0.8(>0.8『非常污,可能有比较重的霾』,0.6-0.8『相当的污』);建议0.8-1.0区间系数下探(候选0.45-0.5)或至少推送标注『重霾,色彩饱和度大打折』;其0.4-0.6仅『有点污』同时印证现行aod-moderate-discount-only不动否决线。出处:sunsetbot.top详情页AOD分档(Wayback 2025-11-09存档;本次直连超时境外不可达,按上游存档精读记录保留)。须以22案例回测后才改代码。
  来源: sunsetbot.top/detailed/ AOD分档(Wayback 2025-11-09存档); Corfidi NOAA/SPC(dust and haze机理) | 阈值: 文献最重档界0.8 vs 现行1.0;下探幅度回测定夺
- REVISE-precip-cb-veto-narrow [soft·文献] 现行precip-three-tier-gate把积雨云(红外极冷+砧状扩展)整体列为否决级→李召麒把积雨云明确列入S级大晚霞云型(与层积云/高层云/锋面云/卷积云并列,持续约20min):远处不在本地降水的受光Cb可以是壮观画布;否决应收窄为『本地/走廊正在降水、或砧盖压顶』,雨系已过/远处受光Cb按画布评估(与precip-rain-just-ended-bonus同向)。出处:李召麒知乎专栏S级云型清单。判读口径修订可直接改提示词,建议留复盘观察期验证。
  来源: 李召麒《如何在拍照前预报晚霞?》知乎·科学摄影专栏(Wayback存档)
- REVISE-canvas-low-cloud-conditional [hard·文献] 现行cloud-canvas-formula低云权重0、cloud-height-tiers称低云<2km基本不利→北京官方口径相反(前提=西侧光路全开):『大面积、成片的中层或低层云(层积云、高积云等)是最优质的天然幕布』『云底高度上升、破碎增加,质量下降』(北京市气象局尤焕苓/齐晨);朱定真确认2024-05-14火烧云即层积云。建议:通道确认开(雨尾西晴/冷涡后部型)时canvas补低云项+α×cloud_low(α=0.3-0.5),通道未确认开维持现行盖子/遮挡逻辑。与Corfidi『低云罕见纯色』存在张力,必须按云底高度分层回测北京案例后才改代码。出处:北京日报客户端2024-09-30;朱定真澎湃转载。注:本次合并整条候选零丢弃,仅剔除打不开的三级引用1条(科普中国2018搜索快照)。
  来源: 尤焕苓/齐晨(北京市气象局),北京日报客户端2024-09-30 xinwen.bjd.com.cn/content/s66fa82a6e4b0c25b287c2b98.html; 朱定真,澎湃 m.thepaper.cn/newsDetail_forward_27385812 | 阈值: α候选0.3-0.5(回测标定);触发前提=通道判定为开
- REVISE-humidity-mute-trigger-85 [soft·文献] 现行aod-humidity-mute-colors地表RH≥75%即表态『湿度压色』降一档→官方专家口径:未饱和水汽增艳(戴云伟『水汽含量越大,霞的颜色越鲜艳,且富于红色』;朱定真『水汽充足对晚霞形成有利』),仅近饱和成雾/低云才劣化(与现行aod-surface-rh-degrade的85%线一致);建议触发线75%→85%,75-85%区间改中性并表态。出处:戴云伟《绝美晚霞竟然可以预测》光明科普云2024-05-16;朱定真澎湃转载。需回测(复核2026-06-10 RH79%仅2分案例的真实致败因子是否为湿度)后改。
  来源: 戴云伟,光明科普云2024-05-16 kepu.gmw.cn/2024-05/16/content_37332884.htm; 朱定真,澎湃转载 | 阈值: 75%→85%(回测后改)

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

## 文献佐证(现行规则的外部证据,2026-07-10)

- aod-direction: 现行aod-mandatory-tier-coefficients惩罚方向(边界层霾压色不增艳、≥1.0重罚)获Corfidi NOAA/SPC与Lemon et al. 2025 ERL 20:024060(已验证真实存在)双源支持;雨后洗空抵消AOD亦获Corfidi背书;中间档0.85/0.6与档界0.3/0.6/1.0无文献定量,维持待回测(已有0.41→10分/0.59→9分/0.84→7.5分/1.4→0分四锚点,样本够时改拟合连续折减函数)。(合并候选2条)
  来源: Corfidi NOAA/SPC spc.noaa.gov/publications/corfidi/sunset/; Lemon et al. 2025, ERL 20:024060, doi:10.1088/1748-9326/ada2ae
- aod-low-band-flat: 现行AOD<0.3档统一系数1.0获Lee实测支持(最鲜艳暮光色出现在中低AOD而非零AOD,'most vivid for modest aerosol optical depths',实测鲜艳区AOD440约0.03-0.18):档内不必再细分,判读与复盘禁把『AOD极低』单独当增艳理由。
  来源: Lee 2015, Applied Optics 54:B194; Lee 2017, Applied Optics 56:G179 (opg.optica.org)
- cloud-height-type: 现行cloud-height-tiers与cloud-type-preference获Corfidi原文支持:『猩红橙红最常出现在卷云和高积云层,层云/层积云等低云罕见』『云必须够高才能截获未经边界层衰减的阳光』『清洁空气是鲜艳日落的主要成分』——注意其把高积云(中云)与卷云并列为纯色主力,支持『中云是主力幕布』表述。(合并候选2条)
  来源: Corfidi, S.F. (NOAA/SPC), The Colors of Sunset and Twilight, spc.noaa.gov/publications/corfidi/sunset/
- twilight-window-physics: 现行llm-twilight-wording与civil twilight观赏窗获物理支持:纯空气对0.47μm散射效率是0.64μm的3-4倍(云底染红选色机制,Corfidi);一次散射理论只在凹角0-6°与观测吻合、>7°失效(Hulburt 1953 JOSA 43:113)——窗口终点按凹角6-7°机算(北京≈日落后30-40min)。
  来源: Corfidi NOAA/SPC; Hulburt 1953, JOSA 43:113 (opg.optica.org)
- sat-lid-252k-nwcsaf: 现行『满盖且均温>252K=中低云盖子』获NWC-SAF GEO-CT业务云型分层法支持(中/高云分界公式代入北京夏季廓线≈254K、冬季≈248K,252K恰落区间内);建议升级为NWP温度动态三分界线替代固定252K。
  来源: NWC-SAF 2019, GEO Cloud ATBD v2.1 §3.2.1.2.2.4 (nwcsaf.org)
- night-ir-floor: 现行sat-cloudpct-second-source与sat-warm-top-full-cover-detect两条P0规则获GOES-R雾算法原文支持:『标准云掩膜夜间不被使用,因它并非为夜间低云检测设计』——夜间纯红外云量只能当下限(floor),禁作『云不多』的证据。
  来源: Pavolonis 2010, GOES-R Fog ATBD §1.11.2.1.4原文
- winter-snow-day-only: 现行sat-winter-snow-confusion获JMA与NWC-SAF支持(『夜间不可能做雪检测』,雪检测限SZA<85°);补充操作细节:JMA做法是近4日内检出过雪即持续标雪面,掩膜跨昼夜沿用。
  来源: Imai & Yoshida 2016 §2.3/§2.4.1; NWC-SAF 2019 Cloud ATBD §3.2.2.5
- semilagrangian-backward: 现行extrapolated_corridor『反向回溯采样』结构获短临外推标准方案支持(后向半拉格朗日,Germann & Zawadzki 2002,只在最后一步插值避免数值扩散);但矢量场化后多步外推必须沿矢量场中点法逐步积分轨迹,而非单矢量直线平移shift×frames。
  来源: pysteps.extrapolation.semilagrangian文档(引Germann & Zawadzki 2002); Pulkkinen et al. 2019, GMD 12:4185
- extrap-lead-cap-3h: 现行fresh-far-forecast-only的3h线获定量支持:光流外推误差随提前量根函数增长,120-240min后NWP反超(Urbich 2018);pySTEPS验证2h内可靠、3h后明显失锐——建议细化为≤2h全权重、2-3h降权标注、>3h维持禁令三档。
  来源: Urbich et al. 2018, Remote Sensing 10(6):955 §4+附录A2; Pulkkinen et al. 2019, GMD 12:4185
- layer-rh-top-weighted: 现行cloud-layer-rh-inference(高空RH=利好、地表RH=利空、禁混用)获SunsetWx官方方法论完全同构支持:湿度取地面到200mb全层且高层权重最大、近地面权重大幅调低。
  来源: SunsetWx, About the Model, sunsetwx.com/about-the-model/
- pressure-trend-fropa: 现行channel-pressure-trend获SunsetWx支持(气压及其时间变化是第二高权重因子,专用于识别锋面过境FROPA)与Corfidi旁证(最艳日落常在急流扰动过境后的升降转换带);建议优先级P2→P1并把锋面位置/过境时序列为显式因子。
  来源: SunsetWx About the Model; Corfidi NOAA/SPC
- overcast-precip-poor: 现行cloud-overcast-zero-scale与precip正降水否决获SunsetWx官方硬规则支持:『接近100%总云覆盖、或预计日落时段有降水的地区直接评最低档poor』。
  来源: SunsetWx About the Model原文
- burn-duration-20-35min: 现行cloud-height-tiers『大烧<20min/高云余晖约30min』获李召麒实测分级独立确认(S级火烧云中低/中高云持续约20min;A级粉霞丝滑高云约35min);与system-quality-duration-sky-area、REVISE-window-end联动输出持续时间。
  来源: 李召麒知乎专栏晚霞分级段
- prob-quality-separate: 现行consensus-quality-prob-separate获莉景天气产品口径支持(概率与质量两指标分离『不可等同互换』);另提示概率宜带空间带宽表达(周边100km同档情况)。
  来源: 周到上海2019-10-31李召麒专访(static.zhoudaosh.com转载)
- target-offset-patent: 现行通道×画布分离变量、antisolar降权、多模式共识三条结构规则获US10459119B2支持(本地target×日落方向偏移点offset云量类别交叉表定色彩等级+反日扇区降权+多源集合+高斯平滑);可把连乘门槛表述对齐为target×offset查表法便于回测。
  来源: US10459119B2, System and method for predicting sunset vibrancy (Kuhns), patents.google.com
- channel-low60-bkn-boundary: 现行low>60判堵线意外获文献旁证:专利用标准云量类别分级,交叉表中偏移点Overcast才压到Few Colors——判堵界应落在Broken档(METAR BKN=5-7/8≈62-87%),60与BKN下界62.5%基本重合;但文献口径是五档梯度而非60/70二值悬崖,7/9根因③的改造方向=阈值不动、曲线化(每段按Clear=1/Few=0.9/Scattered=0.7/Broken=0.35/Overcast=0.1给通量系数)。
  来源: US10459119B2(cloud categories+交叉表)
- warm-top-ir-textbook: 现行sat-warm-top-full-cover-detect、sat-ir-brightness-not-amount、sat-vis-ir-combined、consensus-2v2满盖盲区仲裁获李梦2023(文章页已直连验证)支持:层积云红外呈『均匀灰色条带、云顶温度较高』(7/9根因①的直接文献印证——线性刻度必把满盖层积云读成低覆盖)、卷云VIS深灰具穿透性(VIS暗≠无云)、『高云很厚则不能看到中低云』(俯视盲区);红外见大片均匀灰/灰白无纹理成片=暖顶满盖候选,须触发292K检测+VIS复核链。(合并候选2条)
  来源: 李梦《浅谈卫星云图在气象观测业务中的应用现状》工程技术发展2023, DOI:10.12238/etd.v4i1.6341
- coherent-sheet-official: 现行cloud-structure-over-quantity『连贯带>零碎积云』获北京市气象局官方支持(『大面积、成片的云是最优质天然幕布』『破碎程度增加质量下降』)。
  来源: 尤焕苓/齐晨,北京日报客户端2024-09-30
- golden-hour-window: 现行峰值窗口与twilight口径获官方引用支持:黄金时刻=太阳+6°至−4°(约日出日落前后半小时)。
  来源: 尤焕苓/齐晨引用,腾讯转载news.qq.com/rain/a/20240930A07PF300
- warm-low-ir-blind: 现行sat-ir-brightness-not-amount/sat-vis-mandatory-daytime/precip-forecast-distrust-ir获教科书级铁证:低层水云与地表热对比不足,单红外窗区系统性漏检;ISCCP类算法设计上『宁漏云不误报』;正解=白昼VIS反射测试+昼夜3.9−11µm双通道差——建议把夜间BTD低云检测从雾模块推广到火烧云链路(与sat-night-low-cloud-b07-btd同向)。
  来源: WMO/CIRA SAT-28第6章; Himawari-8夜间雾检测, Asia-Pacific J. Atmos. Sci. 2018, doi:10.1007/s13143-018-0093-0; Ellrod 1995 WaF 10:606
- ir-vis-take-higher: 现行sat-ir-vis-divergence-take-higher方向获WMO SAT-28支持(红外单通道算法cloud-conservative漏云不误报,红外读数是云量下界,背离时高值更近真值;ISCCP约10%像元为部分云被整判);30pp触发线无外部数值(标E级,见system-threshold-evidence-grading,积累样本后用背离幅度vs实际得分做ROC标定)。
  来源: WMO/CIRA SAT-28第6章; UCAR Climate Data Guide ISCCP页
- layer-rh-patent-verbatim: 现行cloud-layer-rh-inference四组阈值(高云300-200mb RH50-70/中云500-700mb 60-80/低云925-800mb 80-90/>90满盖)与US20170109634A1逐字吻合——是规则表全部数字阈值中唯一逐字有一手出处的一组;『成云临界RH随高度降低』方向与GCM参数化文献(Walcek 1994,二手引述)一致;注意专利是经验方案非同行评审,标『专利经验值』。
  来源: US20170109634A1 (patents.google.com,阈值原文逐字)
- corridor-range-patent: 现行走廊0-400km量级与0-100km近程补采获US10459119B2云距分档支持(低对低约129-161km/低对高约402km/高对高约563km,与切线几何自洽):低云判堵有效作用带在0-160km(权重应集中于此);纯高云画布远端候选延至500km+(已并入REVISE-channel-length-by-canvas-height);25km步长无外部佐证标内部经验。
  来源: US10459119B2(Low-to-Low ~80-100mi等原文+地平线距离公式)
- inverted-u-direction: 现行cloud-amount-inverted-u结构与>90折减、高云满盖豁免获SunsetWx方向背书(近100%=Poor、晴空只记Average、高云是vivid必要条件如可投光幕布);30/70/90端点与+10/+15/×0.75系数无外部数值,已有正反案例锚点可做分段回归。
  来源: SunsetWx About the Model原文
- canvas-weighting-direction: 现行cloud-canvas-formula『高云全权重+中云半权重、低云不算画布』获Corfidi与SunsetWx双源方向支持(注意与REVISE-canvas-low-cloud-conditional的北京官方口径张力:后者限定通道全开前提);0.5系数与40-70端点无外部数值标E级。
  来源: Corfidi NOAA/SPC; SunsetWx About the Model
- precip-1mm-etccdi: 现行precip-three-tier-gate两头有据:①『日落窗口降水=Poor』是SunsetWx明文硬规则;②1.0mm否决线恰合气候学湿日标准定义(ETCCDI: RR≥1.0mm);③雨后初晴利好获Corfidi背书;0.5mm分界与0.2中间档系数无外部佐证(现有0.4mm高分案例×2支持继续积累)。
  来源: SunsetWx About the Model; ETCCDI 27项指数定义 etccdi.pacificclimate.org; Corfidi NOAA/SPC
- surface-rh-direction: 现行aod-surface-rh-degrade方向获双源背书:SunsetWx(近地表湿度阻碍透光故大幅降权)与Corfidi(云底下RH升高使污染粒子吸湿增大消光);85%劣化线、40-60%最佳带、75%表态线无外部数值(75%线另见REVISE-humidity-mute-trigger-85建议上调)。
  来源: SunsetWx About the Model; Corfidi NOAA/SPC
- forecast-cloud-unskillful: 现行sat-overrides-forecast-20pp与fresh-near-satellite-first方向获文献支持:总云量是数值/集合预报中技巧最差的要素类之一(『TCC集合预报常未经校准,技巧差于其他要素』);20pp触发线属内部经验,建议用历史『预报vs卫星实测』配对误差分布取分位数重新定线。
  来源: Baran et al., Machine learning for total cloud cover prediction, arXiv:2001.05948
- no-blend-ecmwf: 现行consensus-2v2-dual-scenario禁劈中间值与consensus-median-not-mean获ECMWF官方用户指南支持(『离散大时集合均值可能是不代表任何可能状态的弱型态』,正确做法=聚类/情景呈现+低置信);50pp缺口线无外部数值,与40pp候选一起以双情景触发日事后命中回测。
  来源: ECMWF Forecast User Guide §8.1.2 (confluence.ecmwf.int)
- multiplicative-gate: 现行consensus-multiplicative-gate连乘门槛结构获独立旁证:SunsetWx对满盖/降水用直接判Poor的硬覆盖(等价因子归零)而非线性扣分;专利用分区打分+条件门;禁改线性加权的现行裁决无需动。
  来源: SunsetWx About the Model; US10459119B2
- official-90pct-benchmark: 现行channel-canvas-separate-variables架构与北京市气象服务中心2025年首次业务化晚霞等级预报方法同构(『本地关键要素分析+上游太阳光传输方向透光条件分析』+机器学习),其19期准确率90%+可作skyfire季度命中率对标线(报道已直连验证:2025-06-22起、19期、90%以上均吻合)。
  来源: 北京日报客户端 xinwen.bjd.com.cn/content/s68b45c4ce4b0221b9bec3dd0.html(已直连验证)
- sweet-30-70-sector: 现行cloud-amount-inverted-u的30-70甜区获两个独立中文来源印证(澎湃科普2025;FUN摄影2020且限定为取景方位云量)——并提示甜区判定宜从全箱均值改为日落方位扇区云量(与cloud-antisolar-sector-downweight同向)。
  来源: 澎湃 m.thepaper.cn/newsDetail_forward_31004715 (2025-06-19); 腾讯FUN摄影 news.qq.com/rain/a/20200911A0CCJ300
- rain-ended-west-glow: 现行precip-rain-just-ended-bonus获朱定真官方口径支持(夏季雷雨后日落前后、天空西部是火烧云经典时空);北京同日『先彩虹后晚霞』观测为彩虹管线提供『虹霞接力』联动触发(彩虹L3触发成功的傍晚自动衔接火烧云关注推送)。
  来源: 朱定真,澎湃转载newsDetail_forward_27385812; 北京日报《北京雷雨过后,彩虹晚霞接连登场》
- proverb-westerly-limits: 现行channel-sunrise-caution与channel-pressure-trend获『朝霞不出门』西风带机理科普支持(中纬度系统自西向东移);补充失效情形:副高北抬西伸控制期该谚语不适用——北京盛夏副高边缘时段判读应表态当前受西风带还是副高控制,副高期弱化『西侧云系东移』外推逻辑。
  来源: 澎湃 thepaper.cn/newsDetail_forward_13464226; 辅证:网易转载科普(163.com/dy/article/GDHISAPI0516DHVE.html)
