# feitongraphy 摄影团网站 · 设计文档

**日期：** 2026-05-21  
**项目：** feitongraphy — 个人小众自然风光摄影团网站  
**单文件实现：** `feitongraphy.html`（纯 HTML + CSS + JS，无框架依赖）

---

## 一、定位

面向对摄影感兴趣的陌生人，目标：让第一次访问的人马上明白这是什么、为什么值得加入。  
功能优先级：展示形象 > 活动展示 > 招募加入。

---

## 二、视觉语言

| 属性 | 值 |
|------|-----|
| 背景 | `#FAFAF8`（近白，微暖） |
| 主文字 | `#111111` |
| 辅助文字 | `#888888` |
| 强调色 | 无（色彩来自照片本身） |
| 字体 | 英文：`'Editorial New'` fallback `Georgia, serif`；中文：`'PingFang SC', 'Noto Serif SC', serif` |
| 排版风格 | 超大标题、不对称网格、大量留白、中英文交叉排列 |

**视觉节奏：** Hero（暗/冷）→ 宣言（白/大字）→ 活动（暖/照片主导）→ 关于（简洁）→ 加入（极简）

---

## 三、页面结构

### 1. Hero — 全屏
- **照片：** 冰封岩柱 + 发光圆环（暗蓝雪景），base64 内嵌或外链
- **叠层文字：**
  ```
  feitongraphy          （左上，小号 logo）
  
  
         我们去地图     （居中偏左，超大字，白色）
         结束的地方
  
         Where maps end.（副标，小号，白色半透明）
  ```
- 右下角：向下滚动提示箭头（细线）

### 2. 宣言 — Manifesto
- 白底，大量留白
- 左右不对称排版：
  ```
  不是旅行团               Not a tour group.
  是同频的人               People who see the same thing.
  ```
- 右侧小字：一段 3-4 行的中文理念陈述（参考 majestic-nature.com 风格，讲摄影哲学而非自我介绍）

### 3. Expedition 001 · 红土纪
- **标题区：**
  ```
  EXPEDITION 001
  红土纪
  
  美西 · 犹他州 · 航拍与徒步 · 7天
  American Southwest · Utah · Aerial & Hiking · 7 Days
  ```
- **主题板块（4块）**，每块：大图（全宽或 60% 宽）+ 侧边竖排中文主题名 + 右侧双语短文案（2-3 句，诗意，无地名）
  
  | 主题 | 对应照片 | 英文标题 |
  |------|---------|---------|
  | 纹理研究 | 黑白球状岩 / 粉紫旋纹 | Texture & Form |
  | 大地之眼 | 航拍彩色 badlands + 孤身人 | Scale & Solitude |
  | 地层叙事 | 航拍峡谷河流 / 灰峡谷航拍 | Geological Time |
  | 孤立系 | 黑色石针 / 白岩孤树 | One Thing Alone |

- 文案示例（供参考，实现时写入）：
  - 纹理研究：「亿年挤压留下的密码，近到可以用指尖阅读。/ Codes pressed into stone over a billion years, close enough to read with your fingertips.」
  - 大地之眼：「当人只有蚂蚁大小，色彩才开始说话。/ When a person shrinks to the size of an ant, color begins to speak.」
  - 地层叙事：「河流用百万年划开了石头的心脏。/ A river spent a million years opening the heart of stone.」
  - 孤立系：「一根针，对抗整片天空。/ One needle. Against the whole sky.」

### 4. About — 关于
- 参考 majestic-nature.com：简短、哲学性、专业感
- 内容：摄影理念（自然风光、小众线路、深度踩点）+ feitongraphy 名字由来彩蛋
- 排版：左侧大号数字或引言，右侧正文，双语

### 5. Join — 加入
- 三栏并排：
  - **申请表**：姓名、邮箱、一句话「你为什么想加入」、提交
  - **社交媒体**：图标 + handle（Instagram / 小红书 / 微信，占位符）
  - **邮件联系**：邮箱地址 + 一句话
- 底部：版权行 `© 2026 feitongraphy`

---

## 四、交互与动效

- 滚动进入动画：`opacity 0→1 + translateY 20px→0`，用 `IntersectionObserver`
- Hero 视差：背景图轻微 parallax（`transform: translateY`）
- 主题板块照片：hover 时轻微放大（`scale 1→1.03`，`overflow:hidden` 裁切）
- 导航：无固定顶栏，页面内 anchor 跳转

---

## 五、技术约束

- 单 HTML 文件，零外部依赖（除 Google Fonts 可选）
- 照片以外链引用（用户已有图片 URL 或 base64）
- 中英文字体优先系统字体栈，确保无网络时可读
- 移动端响应：断点 768px，单列布局

---

## 六、不做的事

- 不做后端 / 表单实际提交（提交后显示感谢文字即可）
- 不做深色模式切换
- 不做多页路由
- 不做地图组件
