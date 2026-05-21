# feitongraphy 网站 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 feitongraphy 摄影团单页网站，包含 Hero、宣言、Expedition 001活动展示、About、加入五个 section。

**Architecture:** 单个 `feitongraphy.html` 文件，内联所有 CSS 和 JS，零外部依赖（除可选 Google Fonts）。页面为全长竖向滚动，IntersectionObserver 驱动进场动画，JS 处理表单假提交和 parallax。

**Tech Stack:** HTML5, CSS3 (custom properties, grid, flexbox), Vanilla JS (IntersectionObserver, scroll events)

---

## 文件结构

| 文件 | 说明 |
|------|------|
| `/Users/feitong/photo-app/feitongraphy.html` | 唯一输出文件，包含全部 HTML + `<style>` + `<script>` |

---

## Task 1: 项目骨架 + CSS 基础变量

**Files:**
- Create: `/Users/feitong/photo-app/feitongraphy.html`

- [ ] **Step 1: 创建 HTML 骨架和 CSS 变量**

创建 `/Users/feitong/photo-app/feitongraphy.html`，内容如下：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>feitongraphy</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Noto+Serif+SC:wght@400;700&display=swap" rel="stylesheet">
<style>
/* ── Variables ── */
:root {
  --bg: #FAFAF8;
  --ink: #111111;
  --sub: #888888;
  --hero-h: 100svh;
  --font-en: 'Playfair Display', Georgia, serif;
  --font-zh: 'Noto Serif SC', 'PingFang SC', 'STSong', serif;
  --font-sans: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
  --ease: cubic-bezier(0.16, 1, 0.3, 1);
  --gap: clamp(40px, 8vw, 120px);
}

/* ── Reset ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--font-zh);
  -webkit-font-smoothing: antialiased;
  overflow-x: hidden;
}
img { display: block; width: 100%; }
a { color: inherit; text-decoration: none; }

/* ── Scroll-reveal base ── */
.reveal {
  opacity: 0;
  transform: translateY(24px);
  transition: opacity 0.8s var(--ease), transform 0.8s var(--ease);
}
.reveal.visible {
  opacity: 1;
  transform: translateY(0);
}
.reveal-delay-1 { transition-delay: 0.1s; }
.reveal-delay-2 { transition-delay: 0.2s; }
.reveal-delay-3 { transition-delay: 0.3s; }
.reveal-delay-4 { transition-delay: 0.4s; }
</style>
</head>
<body>

<!-- sections go here -->

<script>
// IntersectionObserver for scroll-reveal
const observer = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.classList.add('visible');
      observer.unobserve(e.target);
    }
  });
}, { threshold: 0.12 });

document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
</script>
</body>
</html>
```

- [ ] **Step 2: 在浏览器打开验证骨架**

```bash
open /Users/feitong/photo-app/feitongraphy.html
```

期望：白色空白页，无报错。

- [ ] **Step 3: Commit**

```bash
cd /Users/feitong/photo-app && git add feitongraphy.html && git commit -m "feat: feitongraphy - project scaffold and CSS variables"
```

---

## Task 2: Hero Section

**Files:**
- Modify: `/Users/feitong/photo-app/feitongraphy.html`

- [ ] **Step 1: 在 `<!-- sections go here -->` 处插入 Hero HTML**

```html
<!-- ══ HERO ══ -->
<section id="hero">
  <div class="hero-bg" id="heroBg"></div>
  <div class="hero-overlay"></div>
  <nav class="hero-nav">
    <span class="hero-logo">feitongraphy</span>
    <div class="hero-nav-links">
      <a href="#expedition">活动</a>
      <a href="#about">关于</a>
      <a href="#join">加入</a>
    </div>
  </nav>
  <div class="hero-text">
    <h1 class="hero-h1">
      <span>我们去地图</span>
      <span>结束的地方</span>
    </h1>
    <p class="hero-sub">Where maps end.</p>
  </div>
  <div class="hero-scroll">
    <svg width="24" height="40" viewBox="0 0 24 40" fill="none">
      <rect x="1" y="1" width="22" height="38" rx="11" stroke="rgba(255,255,255,0.5)" stroke-width="1.5"/>
      <circle class="scroll-dot" cx="12" cy="10" r="3" fill="white"/>
    </svg>
    <span>scroll</span>
  </div>
</section>
```

- [ ] **Step 2: 在 `<style>` 末尾追加 Hero CSS**

```css
/* ── Hero ── */
#hero {
  position: relative;
  width: 100%;
  height: var(--hero-h);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.hero-bg {
  position: absolute;
  inset: -10%;
  background-image: url('https://images.unsplash.com/photo-1508739773434-c26b3d09e071?w=1920&q=80');
  /* ↑ PLACEHOLDER — 替换为冰封岩柱+发光圆环照片的实际 URL 或 base64 */
  background-size: cover;
  background-position: center;
  will-change: transform;
}

.hero-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    rgba(0,0,0,0.25) 0%,
    rgba(0,0,0,0.1) 40%,
    rgba(0,0,0,0.55) 100%
  );
}

.hero-nav {
  position: absolute;
  top: 0; left: 0; right: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 32px 48px;
  z-index: 10;
}

.hero-logo {
  font-family: var(--font-en);
  font-size: 15px;
  font-weight: 400;
  color: rgba(255,255,255,0.9);
  letter-spacing: 0.08em;
}

.hero-nav-links {
  display: flex;
  gap: 36px;
}

.hero-nav-links a {
  font-family: var(--font-sans);
  font-size: 13px;
  color: rgba(255,255,255,0.7);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  transition: color 0.2s;
}

.hero-nav-links a:hover { color: white; }

.hero-text {
  position: relative;
  z-index: 10;
  padding: 0 48px;
  margin-top: 40px;
}

.hero-h1 {
  font-family: var(--font-zh);
  font-size: clamp(52px, 9vw, 120px);
  font-weight: 700;
  color: white;
  line-height: 1.05;
  display: flex;
  flex-direction: column;
}

.hero-h1 span:nth-child(2) {
  padding-left: clamp(40px, 6vw, 100px);
}

.hero-sub {
  margin-top: 20px;
  font-family: var(--font-en);
  font-style: italic;
  font-size: clamp(16px, 2vw, 22px);
  color: rgba(255,255,255,0.6);
  letter-spacing: 0.05em;
  padding-left: 4px;
}

.hero-scroll {
  position: absolute;
  bottom: 40px;
  right: 48px;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: rgba(255,255,255,0.5);
  font-family: var(--font-sans);
  font-size: 10px;
  letter-spacing: 0.15em;
  text-transform: uppercase;
}

.scroll-dot {
  animation: scrollPulse 2s ease-in-out infinite;
}

@keyframes scrollPulse {
  0%, 100% { transform: translateY(0); opacity: 1; }
  50% { transform: translateY(8px); opacity: 0.4; }
}
```

- [ ] **Step 3: 在 `<script>` 中 `observer` 代码之前追加 Parallax JS**

```js
// Hero parallax
const heroBg = document.getElementById('heroBg');
window.addEventListener('scroll', () => {
  const y = window.scrollY;
  if (heroBg && y < window.innerHeight * 1.5) {
    heroBg.style.transform = `translateY(${y * 0.3}px)`;
  }
}, { passive: true });
```

- [ ] **Step 4: 浏览器验证**

```bash
open /Users/feitong/photo-app/feitongraphy.html
```

期望：全屏深色图片背景（占位图），白色超大中文标题，右下角滚动提示，顶部导航。

- [ ] **Step 5: Commit**

```bash
cd /Users/feitong/photo-app && git add feitongraphy.html && git commit -m "feat: feitongraphy - hero section with parallax"
```

---

## Task 3: Manifesto Section

**Files:**
- Modify: `/Users/feitong/photo-app/feitongraphy.html`

- [ ] **Step 1: 在 Hero section 之后插入 Manifesto HTML**

```html
<!-- ══ MANIFESTO ══ -->
<section id="manifesto">
  <div class="mf-grid">
    <div class="mf-left">
      <p class="mf-line reveal"><span class="mf-zh">不是旅行团</span><span class="mf-en">Not a tour group.</span></p>
      <p class="mf-line reveal reveal-delay-1"><span class="mf-zh">是同频的人</span><span class="mf-en">People who see the same thing.</span></p>
    </div>
    <div class="mf-right reveal reveal-delay-2">
      <p class="mf-body-zh">我们相信，最好的照片发生在没有人的地方。每一条线路都经过深度踩点，每一次出发都是为了找到那些需要耐心才能等到的光线。</p>
      <p class="mf-body-en">We believe the best photographs happen where no one else has been. Every route is deeply scouted. Every departure is in pursuit of light that only patience can find.</p>
    </div>
  </div>
</section>
```

- [ ] **Step 2: 在 `<style>` 末尾追加 Manifesto CSS**

```css
/* ── Manifesto ── */
#manifesto {
  padding: var(--gap) 48px;
  min-height: 60vh;
  display: flex;
  align-items: center;
}

.mf-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 80px;
  max-width: 1400px;
  width: 100%;
  align-items: end;
}

.mf-left {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.mf-line {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mf-zh {
  font-family: var(--font-zh);
  font-size: clamp(32px, 5vw, 64px);
  font-weight: 700;
  color: var(--ink);
  line-height: 1.1;
}

.mf-en {
  font-family: var(--font-en);
  font-style: italic;
  font-size: clamp(16px, 2vw, 24px);
  color: var(--sub);
}

.mf-right {
  padding-bottom: 8px;
  border-left: 1px solid rgba(0,0,0,0.1);
  padding-left: 48px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.mf-body-zh {
  font-family: var(--font-zh);
  font-size: 16px;
  line-height: 1.9;
  color: var(--ink);
}

.mf-body-en {
  font-family: var(--font-en);
  font-style: italic;
  font-size: 14px;
  line-height: 1.8;
  color: var(--sub);
}
```

- [ ] **Step 3: 浏览器验证**

刷新页面，滚动到 Manifesto：期望看到左侧超大中英双语对，右侧细线分隔的理念段落，滚动进场动画生效。

- [ ] **Step 4: Commit**

```bash
cd /Users/feitong/photo-app && git add feitongraphy.html && git commit -m "feat: feitongraphy - manifesto section"
```

---

## Task 4: Expedition 001 Section

**Files:**
- Modify: `/Users/feitong/photo-app/feitongraphy.html`

- [ ] **Step 1: 在 Manifesto 之后插入 Expedition HTML**

```html
<!-- ══ EXPEDITION ══ -->
<section id="expedition">
  <div class="exp-header reveal">
    <div class="exp-label">EXPEDITION 001</div>
    <h2 class="exp-title">红土纪</h2>
    <div class="exp-meta">
      <span>美西 · 犹他州 · 航拍与徒步 · 7天</span>
      <span class="exp-meta-en">American Southwest · Utah · Aerial &amp; Hiking · 7 Days</span>
    </div>
  </div>

  <!-- Theme Block 1: 纹理研究 -->
  <div class="theme-block theme-block--right">
    <div class="theme-img-wrap reveal">
      <img src="https://images.unsplash.com/photo-1518173946687-a4c8892bbd9f?w=1200&q=80"
           alt="纹理研究"
           class="theme-img">
      <!-- ↑ PLACEHOLDER — 替换为黑白球状岩或粉紫旋纹照片 URL -->
    </div>
    <div class="theme-copy reveal reveal-delay-1">
      <div class="theme-num">01</div>
      <div class="theme-title-zh">纹理研究</div>
      <div class="theme-title-en">Texture &amp; Form</div>
      <p class="theme-desc-zh">亿年挤压留下的密码，近到可以用指尖阅读。</p>
      <p class="theme-desc-en">Codes pressed into stone over a billion years, close enough to read with your fingertips.</p>
    </div>
  </div>

  <!-- Theme Block 2: 大地之眼 -->
  <div class="theme-block theme-block--left">
    <div class="theme-copy reveal">
      <div class="theme-num">02</div>
      <div class="theme-title-zh">大地之眼</div>
      <div class="theme-title-en">Scale &amp; Solitude</div>
      <p class="theme-desc-zh">当人只有蚂蚁大小，色彩才开始说话。</p>
      <p class="theme-desc-en">When a person shrinks to the size of an ant, color begins to speak.</p>
    </div>
    <div class="theme-img-wrap reveal reveal-delay-1">
      <img src="https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?w=1200&q=80"
           alt="大地之眼"
           class="theme-img">
      <!-- ↑ PLACEHOLDER — 替换为航拍彩色 badlands + 孤身人照片 URL -->
    </div>
  </div>

  <!-- Theme Block 3: 地层叙事 -->
  <div class="theme-block theme-block--right">
    <div class="theme-img-wrap reveal">
      <img src="https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=1200&q=80"
           alt="地层叙事"
           class="theme-img">
      <!-- ↑ PLACEHOLDER — 替换为航拍峡谷河流照片 URL -->
    </div>
    <div class="theme-copy reveal reveal-delay-1">
      <div class="theme-num">03</div>
      <div class="theme-title-zh">地层叙事</div>
      <div class="theme-title-en">Geological Time</div>
      <p class="theme-desc-zh">河流用百万年划开了石头的心脏。</p>
      <p class="theme-desc-en">A river spent a million years opening the heart of stone.</p>
    </div>
  </div>

  <!-- Theme Block 4: 孤立系 -->
  <div class="theme-block theme-block--left">
    <div class="theme-copy reveal">
      <div class="theme-num">04</div>
      <div class="theme-title-zh">孤立系</div>
      <div class="theme-title-en">One Thing Alone</div>
      <p class="theme-desc-zh">一根针，对抗整片天空。</p>
      <p class="theme-desc-en">One needle. Against the whole sky.</p>
    </div>
    <div class="theme-img-wrap reveal reveal-delay-1">
      <img src="https://images.unsplash.com/photo-1542401886-65d6c61db217?w=1200&q=80"
           alt="孤立系"
           class="theme-img">
      <!-- ↑ PLACEHOLDER — 替换为黑色石针或白岩孤树照片 URL -->
    </div>
  </div>
</section>
```

- [ ] **Step 2: 在 `<style>` 末尾追加 Expedition CSS**

```css
/* ── Expedition ── */
#expedition {
  padding: var(--gap) 0;
  background: var(--bg);
}

.exp-header {
  padding: 0 48px;
  margin-bottom: clamp(60px, 8vw, 120px);
}

.exp-label {
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.2em;
  color: var(--sub);
  text-transform: uppercase;
  margin-bottom: 12px;
}

.exp-title {
  font-family: var(--font-zh);
  font-size: clamp(48px, 8vw, 100px);
  font-weight: 700;
  line-height: 1.0;
  color: var(--ink);
  margin-bottom: 20px;
}

.exp-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--sub);
  letter-spacing: 0.05em;
}

.exp-meta-en {
  font-family: var(--font-en);
  font-style: italic;
  font-size: 13px;
}

/* Theme blocks */
.theme-block {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 70vh;
  margin-bottom: 2px;
}

.theme-block--right .theme-img-wrap { order: 1; }
.theme-block--right .theme-copy     { order: 2; }
.theme-block--left  .theme-img-wrap { order: 2; }
.theme-block--left  .theme-copy     { order: 1; }

.theme-img-wrap {
  overflow: hidden;
  max-height: 80vh;
}

.theme-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.8s var(--ease);
}

.theme-img-wrap:hover .theme-img {
  transform: scale(1.04);
}

.theme-copy {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: clamp(40px, 6vw, 100px);
  gap: 16px;
}

.theme-num {
  font-family: var(--font-en);
  font-size: 11px;
  letter-spacing: 0.2em;
  color: var(--sub);
}

.theme-title-zh {
  font-family: var(--font-zh);
  font-size: clamp(28px, 4vw, 52px);
  font-weight: 700;
  line-height: 1.1;
  color: var(--ink);
}

.theme-title-en {
  font-family: var(--font-en);
  font-style: italic;
  font-size: clamp(16px, 2vw, 24px);
  color: var(--sub);
  margin-top: -8px;
}

.theme-desc-zh {
  font-family: var(--font-zh);
  font-size: 15px;
  line-height: 1.9;
  color: var(--ink);
  margin-top: 8px;
}

.theme-desc-en {
  font-family: var(--font-en);
  font-style: italic;
  font-size: 13px;
  line-height: 1.8;
  color: var(--sub);
}
```

- [ ] **Step 3: 浏览器验证**

滚动到 Expedition：期望看到大标题「红土纪」+元信息行，4个交替左右排列的主题板块，图片 hover 放大效果，进场动画。

- [ ] **Step 4: Commit**

```bash
cd /Users/feitong/photo-app && git add feitongraphy.html && git commit -m "feat: feitongraphy - expedition 001 section"
```

---

## Task 5: About Section

**Files:**
- Modify: `/Users/feitong/photo-app/feitongraphy.html`

- [ ] **Step 1: 在 Expedition section 之后插入 About HTML**

```html
<!-- ══ ABOUT ══ -->
<section id="about">
  <div class="about-inner">
    <div class="about-quote reveal">
      <span class="about-quote-mark">"</span>
      <blockquote>
        <p class="about-quote-zh">摄影是一种态度，不是一种技术。</p>
        <p class="about-quote-en">Photography is an attitude, not a technique.</p>
      </blockquote>
    </div>
    <div class="about-body reveal reveal-delay-2">
      <p class="about-text-zh">
        feitongraphy 是一个以深度自然风光摄影为核心的小众团队。我们不走热门景点，只走值得用镜头丈量的地方——每一条路线都经过实地踩点，在最合适的光线条件下抵达最少人知道的位置。
      </p>
      <p class="about-text-en">
        feitongraphy is a small, selective group built around deep landscape photography. We don't chase popular destinations — we seek places worth measuring with a lens. Every route is personally scouted, timed to light, reached only by those willing to go further.
      </p>
      <p class="about-easter">
        <span class="about-easter-label">关于名字</span>
        feitongraphy 藏着 photography — 这不是巧合。
      </p>
    </div>
  </div>
</section>
```

- [ ] **Step 2: 在 `<style>` 末尾追加 About CSS**

```css
/* ── About ── */
#about {
  padding: var(--gap) 48px;
  background: var(--ink);
  color: white;
}

.about-inner {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 80px;
  max-width: 1400px;
  align-items: start;
}

.about-quote {
  position: sticky;
  top: 80px;
}

.about-quote-mark {
  font-family: var(--font-en);
  font-size: 120px;
  line-height: 0.7;
  color: rgba(255,255,255,0.1);
  display: block;
  margin-bottom: -20px;
}

.about-quote-zh {
  font-family: var(--font-zh);
  font-size: clamp(22px, 3vw, 36px);
  font-weight: 700;
  line-height: 1.4;
  color: white;
  margin-bottom: 12px;
}

.about-quote-en {
  font-family: var(--font-en);
  font-style: italic;
  font-size: clamp(14px, 1.5vw, 20px);
  color: rgba(255,255,255,0.5);
  line-height: 1.6;
}

.about-body {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.about-text-zh {
  font-family: var(--font-zh);
  font-size: 16px;
  line-height: 2.0;
  color: rgba(255,255,255,0.85);
}

.about-text-en {
  font-family: var(--font-en);
  font-style: italic;
  font-size: 14px;
  line-height: 1.9;
  color: rgba(255,255,255,0.45);
}

.about-easter {
  margin-top: 16px;
  padding-top: 24px;
  border-top: 1px solid rgba(255,255,255,0.12);
  font-family: var(--font-zh);
  font-size: 13px;
  color: rgba(255,255,255,0.4);
  line-height: 1.8;
}

.about-easter-label {
  display: block;
  font-size: 10px;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: rgba(255,255,255,0.25);
  margin-bottom: 6px;
  font-family: var(--font-sans);
}
```

- [ ] **Step 3: 浏览器验证**

滚动到 About：期望黑底白字，左侧大引言 sticky，右侧双语正文，底部名字彩蛋。

- [ ] **Step 4: Commit**

```bash
cd /Users/feitong/photo-app && git add feitongraphy.html && git commit -m "feat: feitongraphy - about section"
```

---

## Task 6: Join Section + Footer

**Files:**
- Modify: `/Users/feitong/photo-app/feitongraphy.html`

- [ ] **Step 1: 在 About section 之后插入 Join HTML**

```html
<!-- ══ JOIN ══ -->
<section id="join">
  <div class="join-header reveal">
    <div class="join-label">BECOME A MEMBER</div>
    <h2 class="join-title">加入我们</h2>
  </div>

  <div class="join-grid">
    <!-- 申请表 -->
    <div class="join-col reveal">
      <div class="join-col-title">申请加入 <span>Apply</span></div>
      <form class="join-form" id="joinForm">
        <div class="form-field">
          <label>姓名 / Name</label>
          <input type="text" name="name" placeholder="你的名字" required>
        </div>
        <div class="form-field">
          <label>邮箱 / Email</label>
          <input type="email" name="email" placeholder="your@email.com" required>
        </div>
        <div class="form-field">
          <label>为什么想加入？/ Why join?</label>
          <textarea name="why" placeholder="一句话就够了" rows="3" required></textarea>
        </div>
        <button type="submit" class="join-btn">提交申请</button>
      </form>
      <div class="join-thanks" id="joinThanks" style="display:none">
        <p class="join-thanks-zh">收到了。我们会与你联系。</p>
        <p class="join-thanks-en">Received. We'll be in touch.</p>
      </div>
    </div>

    <!-- 社交媒体 -->
    <div class="join-col reveal reveal-delay-1">
      <div class="join-col-title">社交媒体 <span>Social</span></div>
      <div class="social-list">
        <a class="social-item" href="#" target="_blank">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg>
          <span>@feitongraphy</span>
        </a>
        <a class="social-item" href="#" target="_blank">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 4l16 8-16 8V4z"/></svg>
          <span>小红书 · feitongraphy</span>
        </a>
        <a class="social-item" href="#" target="_blank">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <span>微信公众号 · feitongraphy</span>
        </a>
      </div>
    </div>

    <!-- 邮件 -->
    <div class="join-col reveal reveal-delay-2">
      <div class="join-col-title">邮件联系 <span>Email</span></div>
      <p class="join-email-desc">有任何问题，或者只是想打个招呼。</p>
      <p class="join-email-desc-en">Questions, collabs, or just saying hello.</p>
      <a class="join-email-addr" href="mailto:hello@feitongraphy.com">hello@feitongraphy.com</a>
    </div>
  </div>

  <footer class="site-footer">
    <span>© 2026 feitongraphy</span>
    <span>feiton<em>graphy</em></span>
  </footer>
</section>
```

- [ ] **Step 2: 在 `<style>` 末尾追加 Join + Footer CSS**

```css
/* ── Join ── */
#join {
  padding: var(--gap) 48px;
  background: var(--bg);
}

.join-header {
  margin-bottom: clamp(48px, 6vw, 80px);
}

.join-label {
  font-family: var(--font-sans);
  font-size: 11px;
  letter-spacing: 0.2em;
  color: var(--sub);
  text-transform: uppercase;
  margin-bottom: 12px;
}

.join-title {
  font-family: var(--font-zh);
  font-size: clamp(36px, 5vw, 72px);
  font-weight: 700;
  color: var(--ink);
}

.join-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  gap: 60px;
  align-items: start;
}

.join-col-title {
  font-family: var(--font-zh);
  font-size: 18px;
  font-weight: 700;
  color: var(--ink);
  margin-bottom: 28px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(0,0,0,0.1);
}

.join-col-title span {
  font-family: var(--font-en);
  font-style: italic;
  font-weight: 400;
  font-size: 14px;
  color: var(--sub);
  margin-left: 8px;
}

/* Form */
.join-form { display: flex; flex-direction: column; gap: 20px; }

.form-field { display: flex; flex-direction: column; gap: 6px; }

.form-field label {
  font-family: var(--font-sans);
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--sub);
}

.form-field input,
.form-field textarea {
  background: transparent;
  border: none;
  border-bottom: 1px solid rgba(0,0,0,0.15);
  padding: 10px 0;
  font-family: var(--font-zh);
  font-size: 15px;
  color: var(--ink);
  outline: none;
  resize: none;
  transition: border-color 0.2s;
}

.form-field input:focus,
.form-field textarea:focus {
  border-bottom-color: var(--ink);
}

.form-field input::placeholder,
.form-field textarea::placeholder {
  color: rgba(0,0,0,0.25);
}

.join-btn {
  margin-top: 8px;
  align-self: flex-start;
  background: var(--ink);
  color: white;
  border: none;
  padding: 14px 32px;
  font-family: var(--font-zh);
  font-size: 14px;
  cursor: pointer;
  letter-spacing: 0.05em;
  transition: opacity 0.2s;
}

.join-btn:hover { opacity: 0.75; }

.join-thanks {
  padding: 24px 0;
}

.join-thanks-zh {
  font-family: var(--font-zh);
  font-size: 16px;
  color: var(--ink);
  margin-bottom: 6px;
}

.join-thanks-en {
  font-family: var(--font-en);
  font-style: italic;
  font-size: 14px;
  color: var(--sub);
}

/* Social */
.social-list { display: flex; flex-direction: column; gap: 20px; }

.social-item {
  display: flex;
  align-items: center;
  gap: 14px;
  font-family: var(--font-zh);
  font-size: 14px;
  color: var(--ink);
  opacity: 0.7;
  transition: opacity 0.2s;
}

.social-item:hover { opacity: 1; }

/* Email */
.join-email-desc {
  font-family: var(--font-zh);
  font-size: 15px;
  line-height: 1.8;
  color: var(--ink);
  margin-bottom: 6px;
}

.join-email-desc-en {
  font-family: var(--font-en);
  font-style: italic;
  font-size: 13px;
  color: var(--sub);
  margin-bottom: 24px;
}

.join-email-addr {
  font-family: var(--font-en);
  font-size: 16px;
  color: var(--ink);
  border-bottom: 1px solid rgba(0,0,0,0.2);
  padding-bottom: 3px;
  transition: border-color 0.2s;
}

.join-email-addr:hover { border-color: var(--ink); }

/* Footer */
.site-footer {
  margin-top: clamp(60px, 8vw, 120px);
  padding-top: 24px;
  border-top: 1px solid rgba(0,0,0,0.1);
  display: flex;
  justify-content: space-between;
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--sub);
}

.site-footer em {
  font-family: var(--font-en);
  font-style: italic;
}
```

- [ ] **Step 3: 在 `<script>` 末尾追加表单假提交 JS**

```js
// Form fake submit
const joinForm = document.getElementById('joinForm');
const joinThanks = document.getElementById('joinThanks');
if (joinForm) {
  joinForm.addEventListener('submit', (e) => {
    e.preventDefault();
    joinForm.style.display = 'none';
    joinThanks.style.display = 'block';
  });
}
```

- [ ] **Step 4: 浏览器验证**

滚动到 Join：期望三栏布局（表单 / 社交 / 邮件），提交表单后表单消失显示感谢文字，Footer 正常显示。

- [ ] **Step 5: Commit**

```bash
cd /Users/feitong/photo-app && git add feitongraphy.html && git commit -m "feat: feitongraphy - join section and footer"
```

---

## Task 7: 移动端响应式

**Files:**
- Modify: `/Users/feitong/photo-app/feitongraphy.html`

- [ ] **Step 1: 在 `<style>` 末尾追加移动端媒体查询**

```css
/* ── Mobile (≤768px) ── */
@media (max-width: 768px) {
  :root { --gap: 60px; }

  .hero-nav { padding: 24px 20px; }
  .hero-nav-links { display: none; }
  .hero-text { padding: 0 20px; }
  .hero-scroll { right: 20px; }

  #manifesto { padding: var(--gap) 20px; }
  .mf-grid { grid-template-columns: 1fr; gap: 40px; }
  .mf-right { border-left: none; padding-left: 0; border-top: 1px solid rgba(0,0,0,0.1); padding-top: 32px; }

  .exp-header { padding: 0 20px; }
  .theme-block { grid-template-columns: 1fr; min-height: auto; }
  .theme-block--right .theme-img-wrap,
  .theme-block--right .theme-copy,
  .theme-block--left .theme-img-wrap,
  .theme-block--left .theme-copy { order: unset; }
  .theme-block { display: flex; flex-direction: column; }
  .theme-img-wrap { max-height: 60vw; }
  .theme-copy { padding: 32px 20px; }

  #about { padding: var(--gap) 20px; }
  .about-inner { grid-template-columns: 1fr; gap: 40px; }
  .about-quote { position: static; }

  #join { padding: var(--gap) 20px; }
  .join-grid { grid-template-columns: 1fr; gap: 48px; }
}
```

- [ ] **Step 2: 浏览器验证（移动端模拟）**

在 Chrome DevTools 中切换到 iPhone 375px 宽：期望所有 section 单列显示，无横向溢出，字体可读。

- [ ] **Step 3: Commit**

```bash
cd /Users/feitong/photo-app && git add feitongraphy.html && git commit -m "feat: feitongraphy - mobile responsive layout"
```

---

## Task 8: 替换占位图片

**Files:**
- Modify: `/Users/feitong/photo-app/feitongraphy.html`

- [ ] **Step 1: 替换 Hero 背景图**

在 `feitongraphy.html` 中找到注释 `↑ PLACEHOLDER — 替换为冰封岩柱+发光圆环照片`，将 `background-image: url('...')` 中的 URL 换成实际图片地址（可以是本地 file:// 路径或托管 URL）。

- [ ] **Step 2: 替换 4 个主题板块的 img src**

依次找到 4 处 `↑ PLACEHOLDER` 注释，将 `<img src="...">` 的 URL 替换为：
- 纹理研究 → 黑白球状岩或粉紫旋纹照片
- 大地之眼 → 航拍彩色 badlands + 孤身人照片
- 地层叙事 → 航拍峡谷河流照片
- 孤立系 → 黑色石针或白岩孤树照片

- [ ] **Step 3: 最终全页验证**

```bash
open /Users/feitong/photo-app/feitongraphy.html
```

从顶部滚动到底部，逐一检查：
- [ ] Hero 图片正确、标题排版对齐
- [ ] Manifesto 进场动画顺滑
- [ ] 4 个主题板块照片显示正常，hover 放大生效
- [ ] About 黑底白字，sticky 引言
- [ ] Join 表单提交后显示感谢
- [ ] 移动端宽度无溢出

- [ ] **Step 4: Final Commit**

```bash
cd /Users/feitong/photo-app && git add feitongraphy.html && git commit -m "feat: feitongraphy - replace placeholder images, final polish"
```
