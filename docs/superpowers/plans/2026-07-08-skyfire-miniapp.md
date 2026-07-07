# Skyfire 微信小程序 v1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Taro 微信小程序自用版:一键登录 → 日期下拉(今/明)×朝霞/晚霞 tab → 大数字 hero+轨迹曲线+模式明细+双热力图(懒加载)+解读卡,消费已上线的三端点 API。

**Architecture:** 手工脚手架 Taro 4 + React + TS(不用交互式 CLI,文件全部显式写出);`src/api/` 一层薄请求库管 token/401 重登/base url;页面两张(login/index),index 由五个展示组件组成;样式为全局 SCSS 设计 token(浅色磨砂玻璃,mockup 已确认)。spec: `docs/superpowers/specs/2026-07-07-skyfire-miniapp-api-design.md` §3。

**Tech Stack:** Node v20.18.1(`~/.local/node/bin`,非交互 shell 需 `export PATH="$HOME/.local/node/bin:$PATH"`)、Taro ~4.x、React 18、TypeScript、SCSS。验证方式 = `npm run build:weapp` 零错误 + 微信开发者工具手测清单(前端无单测,YAGNI;逻辑最重的 request/日期格式化用小型纯函数便于将来补测)。

**工作目录:** `photo-app/skyfire-miniapp/`(新建,独立 npm 项目,git 跟踪但 node_modules/dist 忽略)。

**已知携带项(API 终审注意)**:陈旧提醒用 `latest.created_at`(顶层 updated_at 是服务器 now,永远新鲜);热力图全屏预览直接用同一 PNG URL。

---

### Task 0: 开分支 + 手工脚手架 + 编译通过

**Files:**
- Create: `skyfire-miniapp/package.json`、`skyfire-miniapp/.gitignore`、`skyfire-miniapp/tsconfig.json`、`skyfire-miniapp/babel.config.js`、`skyfire-miniapp/config/index.ts`、`skyfire-miniapp/config/dev.ts`、`skyfire-miniapp/config/prod.ts`、`skyfire-miniapp/project.config.json`、`skyfire-miniapp/src/app.ts`、`skyfire-miniapp/src/app.config.ts`、`skyfire-miniapp/src/app.scss`、`skyfire-miniapp/src/pages/index/index.tsx`、`skyfire-miniapp/src/pages/index/index.config.ts`

- [ ] **Step 1: 开分支**

```bash
cd /Users/feitong/photo-app && git checkout -b feat/skyfire-miniapp main
```

- [ ] **Step 2: 写脚手架文件**

`skyfire-miniapp/package.json`:

```json
{
  "name": "skyfire-miniapp",
  "version": "0.1.0",
  "private": true,
  "description": "火烧云预测小程序(自用)",
  "scripts": {
    "build:weapp": "taro build --type weapp",
    "dev:weapp": "npm run build:weapp -- --watch"
  },
  "dependencies": {
    "@babel/runtime": "^7.24.0",
    "@tarojs/components": "4.0.9",
    "@tarojs/helper": "4.0.9",
    "@tarojs/plugin-framework-react": "4.0.9",
    "@tarojs/plugin-platform-weapp": "4.0.9",
    "@tarojs/react": "4.0.9",
    "@tarojs/runtime": "4.0.9",
    "@tarojs/shared": "4.0.9",
    "@tarojs/taro": "4.0.9",
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@babel/core": "^7.24.0",
    "@tarojs/cli": "4.0.9",
    "@tarojs/webpack5-runner": "4.0.9",
    "@types/react": "^18.2.0",
    "babel-preset-taro": "4.0.9",
    "typescript": "^5.4.0",
    "webpack": "^5.91.0"
  }
}
```

`skyfire-miniapp/.gitignore`:

```
node_modules/
dist/
.swc/
```

`skyfire-miniapp/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src", "config"]
}
```

`skyfire-miniapp/babel.config.js`:

```js
module.exports = {
  presets: [
    ['taro', { framework: 'react', ts: true }]
  ]
}
```

`skyfire-miniapp/config/index.ts`:

```ts
import { defineConfig } from '@tarojs/cli'

export default defineConfig({
  projectName: 'skyfire-miniapp',
  sourceRoot: 'src',
  outputRoot: 'dist',
  framework: 'react',
  compiler: 'webpack5',
  plugins: [],
  designWidth: 750,
  deviceRatio: { 640: 2.34 / 2, 750: 1, 828: 1.81 / 2 },
  mini: {
    postcss: {
      autoprefixer: { enable: true },
      cssModules: { enable: false }
    }
  }
})
```

`skyfire-miniapp/config/dev.ts`:

```ts
export default { mini: {}, defineConstants: {} }
```

`skyfire-miniapp/config/prod.ts`:

```ts
export default { mini: {}, defineConstants: {} }
```

`skyfire-miniapp/project.config.json`(AppID 用户已注册):

```json
{
  "miniprogramRoot": "dist/",
  "projectname": "skyfire",
  "appid": "wxee322fbf6760b4ec",
  "setting": {
    "urlCheck": false,
    "es6": false,
    "postcss": false,
    "minified": false
  },
  "compileType": "miniprogram"
}
```

(`urlCheck: false` = 开发者工具"不校验合法域名",本地 http API 可用。)

`skyfire-miniapp/src/app.ts`:

```ts
import { PropsWithChildren } from 'react'
import './app.scss'

function App({ children }: PropsWithChildren) {
  return children
}

export default App
```

`skyfire-miniapp/src/app.config.ts`:

```ts
export default defineAppConfig({
  pages: ['pages/index/index'],
  window: {
    navigationBarTitleText: '火烧云',
    navigationBarBackgroundColor: '#eef1f6',
    navigationBarTextStyle: 'black',
    backgroundColor: '#eef1f6'
  }
})
```

`skyfire-miniapp/src/app.scss`(设计 token,浅色磨砂;后续组件全部引用这些类):

```scss
page {
  background: #eef1f6;
  color: #1c2733;
  font-size: 28rpx;
}

.glass-card {
  background: rgba(255, 255, 255, 0.72);
  border: 1rpx solid rgba(255, 255, 255, 0.95);
  border-radius: 32rpx;
  padding: 24rpx 32rpx;
  margin-bottom: 20rpx;
}

.t-primary { color: #1c2733; }
.t-secondary { color: #6b7684; }
.t-muted { color: #8a94a2; }
.t-amber { color: #b06a10; }
.t-red { color: #c2542e; }
.mono { font-family: Menlo, Consolas, monospace; }
```

`skyfire-miniapp/src/pages/index/index.tsx`(Task 0 占位,Task 2 重写):

```tsx
import { View, Text } from '@tarojs/components'

export default function Index() {
  return (
    <View className='glass-card'>
      <Text className='t-primary'>skyfire 脚手架 OK</Text>
    </View>
  )
}
```

`skyfire-miniapp/src/pages/index/index.config.ts`:

```ts
export default definePageConfig({
  navigationBarTitleText: '火烧云',
  enablePullDownRefresh: true,
  backgroundTextStyle: 'dark'
})
```

- [ ] **Step 3: 安装依赖并编译**

```bash
cd /Users/feitong/photo-app/skyfire-miniapp
export PATH="$HOME/.local/node/bin:$PATH"
npm install 2>&1 | tail -3
npm run build:weapp 2>&1 | tail -5
```

Expected: install 无 error;build 输出含 `编译成功`/`Compiled successfully`(或无 error 退出码 0),生成 `dist/app.json`。

若 Taro 4.0.9 与 Node 20 有 peer 冲突,允许把全部 `4.0.9` 统一升到最新 4.x patch(`npm view @tarojs/cli version` 查),报告注明版本;不得混版本。
defineAppConfig/definePageConfig 是 Taro 全局宏,若 TS 报未定义,在 `src/` 下加 `global.d.ts`:`/// <reference types="@tarojs/taro" />`。

- [ ] **Step 4: Commit**

```bash
cd /Users/feitong/photo-app
git add skyfire-miniapp
git commit -m "feat(miniapp): Taro4+React+TS 手工脚手架,浅色磨砂设计 token,weapp 编译通过"
```

---

### Task 1: request 库 + 登录页

**Files:**
- Create: `skyfire-miniapp/src/api/client.ts`、`skyfire-miniapp/src/api/types.ts`、`skyfire-miniapp/src/pages/login/index.tsx`、`skyfire-miniapp/src/pages/login/index.config.ts`
- Modify: `skyfire-miniapp/src/app.config.ts`(pages 加 login,并放首位=启动页)

- [ ] **Step 1: types.ts**(对着 API 真实响应写,勿造):

```ts
export interface Latest {
  checkpoint: string
  probability_pct: number
  quality_pct: number
  prob_word: string
  qual_word: string
  confidence: string
  llm_status: string
  reasoning: string | null
  risks: string | null
  created_at: string
}

export interface TrajectoryPoint {
  checkpoint: string
  probability_pct: number
  quality_pct: number
  created_at: string
}

export interface PerModel {
  prob: number
  qual: number
  cloud_high: number | null
  cloud_mid: number | null
  cloud_low: number | null
  precipitation: number | null
}

export interface EventData {
  event: 'sunrise_glow' | 'sunset_glow'
  status: 'ended' | 'upcoming'
  peak: string
  best_window: string
  latest: Latest | null
  trajectory: TrajectoryPoint[]
  per_model: Record<string, PerModel>
}

export interface DateData {
  date: string
  label: string
  events: EventData[]
}

export interface Summary {
  city: string
  city_name: string
  updated_at: string
  dates: DateData[]
}
```

- [ ] **Step 2: client.ts**(token 存取、401 自动重登一次、summary/heatmap):

```ts
import Taro from '@tarojs/taro'
import type { Summary } from './types'

// 开发者工具用 127.0.0.1;真机改成 Mac 局域网 IP(设置→Wi-Fi 查看)
export const API_BASE = 'http://127.0.0.1:8000'

const TOKEN_KEY = 'skyfire_token'

export function getToken(): string { return Taro.getStorageSync(TOKEN_KEY) || '' }

export async function login(): Promise<void> {
  const { code } = await Taro.login()
  const res = await Taro.request({
    url: `${API_BASE}/v1/login`,
    method: 'POST',
    data: { code },
    header: { 'content-type': 'application/json' }
  })
  if (res.statusCode !== 200) {
    throw new Error((res.data && res.data.detail) || `登录失败(${res.statusCode})`)
  }
  Taro.setStorageSync(TOKEN_KEY, res.data.token)
}

async function authedGet<T>(path: string, retried = false): Promise<T> {
  const res = await Taro.request({
    url: `${API_BASE}${path}`,
    method: 'GET',
    header: { 'X-Session': getToken() }
  })
  if (res.statusCode === 401 && !retried) {
    await login()                     // 静默重登一次再试
    return authedGet<T>(path, true)
  }
  if (res.statusCode !== 200) {
    throw new Error((res.data && res.data.detail) || `请求失败(${res.statusCode})`)
  }
  return res.data as T
}

export function fetchSummary(city = 'beijing'): Promise<Summary> {
  return authedGet<Summary>(`/v1/summary?city=${city}`)
}

export function heatmapUrl(event: string, date: string,
                           kind: 'prob' | 'quality', city = 'beijing'): string {
  return `${API_BASE}/v1/heatmap?city=${city}&event=${event}&date=${date}&kind=${kind}`
}
```

(注:`Taro.request` 的 header 带 X-Session 对 `<Image>` 组件无效——heatmap 的 `<Image src>` 无法带自定义头。**解决**:Task 4 用 `Taro.request` 拉 `arraybuffer` + `wx.arrayBufferToBase64` 转 data url 显示。heatmapUrl 仍保留给全屏预览的 downloadFile 备用。)

- [ ] **Step 3: 登录页**

`src/pages/login/index.tsx`:

```tsx
import { useState } from 'react'
import Taro from '@tarojs/taro'
import { Button, Text, View } from '@tarojs/components'
import { getToken, login } from '../../api/client'
import './index.scss'

export default function Login() {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function onLogin() {
    setBusy(true); setErr('')
    try {
      await login()
      Taro.redirectTo({ url: '/pages/index/index' })
    } catch (e: any) {
      setErr(e.message || '登录失败,检查 API 服务是否已启动')
    } finally {
      setBusy(false)
    }
  }

  // 已有 token 直接进首页(401 时首页会静默重登)
  if (getToken()) {
    Taro.redirectTo({ url: '/pages/index/index' })
    return null
  }

  return (
    <View className='login-page'>
      <View className='login-hero'>
        <Text className='login-title'>火烧云</Text>
        <Text className='login-sub t-secondary'>烧不烧,提前知道</Text>
      </View>
      <Button className='login-btn' loading={busy} onClick={onLogin}>
        微信一键登录
      </Button>
      {err && <Text className='login-err t-red'>{err}</Text>}
    </View>
  )
}
```

`src/pages/login/index.scss`:

```scss
.login-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 32rpx;
}
.login-title { font-size: 72rpx; font-weight: 500; }
.login-sub { display: block; margin-top: 12rpx; font-size: 28rpx; }
.login-hero { text-align: center; margin-bottom: 48rpx; }
.login-btn {
  width: 480rpx;
  background: #1c2733;
  color: #fff;
  border-radius: 24rpx;
  font-size: 30rpx;
}
.login-err { margin-top: 24rpx; font-size: 26rpx; }
```

`src/pages/login/index.config.ts`:

```ts
export default definePageConfig({ navigationBarTitleText: '登录' })
```

app.config.ts 的 pages 改为:

```ts
  pages: ['pages/login/index', 'pages/index/index'],
```

- [ ] **Step 4: 编译**

```bash
cd /Users/feitong/photo-app/skyfire-miniapp && export PATH="$HOME/.local/node/bin:$PATH" && npm run build:weapp 2>&1 | tail -3
```

Expected: 编译成功。

- [ ] **Step 5: Commit**

```bash
cd /Users/feitong/photo-app && git add skyfire-miniapp && git commit -m "feat(miniapp): request 库(token/401静默重登)+ 微信一键登录页"
```

---

### Task 2: 首页骨架——日期下拉 × 朝霞/晚霞 tab + hero 大数字

**Files:**
- Rewrite: `skyfire-miniapp/src/pages/index/index.tsx`
- Create: `skyfire-miniapp/src/pages/index/index.scss`、`skyfire-miniapp/src/components/Hero.tsx`

- [ ] **Step 1: index.tsx**(状态与数据流中枢):

```tsx
import { useCallback, useEffect, useState } from 'react'
import Taro, { usePullDownRefresh } from '@tarojs/taro'
import { Picker, Text, View } from '@tarojs/components'
import { fetchSummary } from '../../api/client'
import type { EventData, Summary } from '../../api/types'
import Hero from '../../components/Hero'
import './index.scss'

const EVENT_ZH = { sunrise_glow: '朝霞', sunset_glow: '晚霞' } as const

export default function Index() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [err, setErr] = useState('')
  const [dateIdx, setDateIdx] = useState(0)
  const [eventIdx, setEventIdx] = useState(0)

  const load = useCallback(async () => {
    setErr('')
    try {
      const s = await fetchSummary()
      setSummary(s)
      // 默认选中第一个未结束的事件
      const evs = s.dates[0].events
      const firstUpcoming = evs.findIndex(e => e.status === 'upcoming')
      setEventIdx(firstUpcoming === -1 ? evs.length - 1 : firstUpcoming)
    } catch (e: any) {
      setErr(e.message || '服务未启动?在 Mac 上运行 skyfire serve')
    }
  }, [])

  useEffect(() => { load() }, [load])
  usePullDownRefresh(async () => { await load(); Taro.stopPullDownRefresh() })

  if (err) {
    return (
      <View className='center-page'>
        <Text className='t-secondary'>{err}</Text>
        <Text className='retry t-amber' onClick={load}>点我重试</Text>
      </View>
    )
  }
  if (!summary) return <View className='center-page'><Text className='t-muted'>加载中…</Text></View>

  const dateData = summary.dates[dateIdx]
  const ev: EventData = dateData.events[eventIdx]

  return (
    <View className='index-page'>
      <View className='topbar'>
        <Text className='city t-primary'>{summary.city_name}</Text>
        <Picker mode='selector' range={summary.dates.map(d => d.label)}
                value={dateIdx}
                onChange={e => setDateIdx(Number(e.detail.value))}>
          <Text className='date-picker t-secondary'>{dateData.label} ▾</Text>
        </Picker>
      </View>

      <View className='tabs glass-card'>
        {dateData.events.map((e, i) => (
          <View key={e.event}
                className={`tab ${i === eventIdx ? 'tab-active' : ''}`}
                onClick={() => setEventIdx(i)}>
            <Text>{EVENT_ZH[e.event]}</Text>
            {e.status === 'ended' && <Text className='ended-badge'>已结束</Text>}
          </View>
        ))}
      </View>

      <Hero ev={ev} />
    </View>
  )
}
```

- [ ] **Step 2: Hero.tsx**(大数字+定性词+已结束淡化+时刻行+陈旧提醒):

```tsx
import { Text, View } from '@tarojs/components'
import type { EventData } from '../api/types'

function staleHint(createdAt: string | undefined): string {
  if (!createdAt) return ''
  const ageMs = Date.now() - new Date(createdAt.replace(' ', 'T') + 'Z').getTime()
  return ageMs > 2 * 3600e3 ? `(${Math.round(ageMs / 3600e3)}小时前的预测)` : ''
}

export default function Hero({ ev }: { ev: EventData }) {
  const l = ev.latest
  const when = ev.event === 'sunset_glow' ? '日落' : '日出'
  return (
    <View className={`glass-card hero ${ev.status === 'ended' ? 'hero-ended' : ''}`}>
      {l ? (
        <>
          <View className='hero-num-row'>
            <Text className='hero-num'>{Math.round(l.probability_pct)}</Text>
            <Text className='hero-pct t-muted'>%</Text>
          </View>
          <Text className='hero-words t-secondary'>
            燃烧概率 · {l.prob_word}
            <Text className='t-amber'>  质量 {Math.round(l.quality_pct)}%({l.qual_word})</Text>
          </Text>
          <Text className='hero-meta t-muted'>
            {when} {ev.peak} · 最佳 {ev.best_window} · {l.checkpoint} 版 {staleHint(l.created_at)}
          </Text>
        </>
      ) : (
        <Text className='t-muted'>待检查点生成预测(每晚20点起陆续更新)</Text>
      )}
    </View>
  )
}
```

- [ ] **Step 3: index.scss**:

```scss
.index-page { padding: 24rpx; }
.center-page {
  min-height: 60vh; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 24rpx;
}
.retry { font-size: 30rpx; }
.topbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 20rpx; padding: 0 8rpx;
}
.city { font-size: 34rpx; font-weight: 500; }
.date-picker { font-size: 28rpx; }
.tabs { display: flex; padding: 8rpx; gap: 8rpx; }
.tab {
  flex: 1; text-align: center; padding: 14rpx 0; border-radius: 20rpx;
  color: #8a94a2; font-size: 28rpx; position: relative;
}
.tab-active { background: #fff; color: #1c2733; font-weight: 500; }
.ended-badge {
  font-size: 20rpx; color: #8a94a2; margin-left: 8rpx;
}
.hero-num-row { display: flex; align-items: baseline; }
.hero-num { font-size: 96rpx; font-weight: 500; line-height: 1.1; }
.hero-pct { font-size: 44rpx; margin-left: 6rpx; }
.hero-words { display: block; margin-top: 10rpx; font-size: 26rpx; }
.hero-meta { display: block; margin-top: 10rpx; font-size: 24rpx; }
.hero-ended { opacity: 0.62; }
```

- [ ] **Step 4: 编译 + Commit**

```bash
cd /Users/feitong/photo-app/skyfire-miniapp && export PATH="$HOME/.local/node/bin:$PATH" && npm run build:weapp 2>&1 | tail -3
cd /Users/feitong/photo-app && git add skyfire-miniapp && git commit -m "feat(miniapp): 首页骨架——日期下拉×朝霞晚霞tab,hero大数字/已结束淡化/陈旧提醒(latest.created_at)"
```

---

### Task 3: 轨迹曲线 + 模式明细

**Files:**
- Create: `skyfire-miniapp/src/components/Trajectory.tsx`、`skyfire-miniapp/src/components/ModelRows.tsx`
- Modify: `skyfire-miniapp/src/pages/index/index.tsx`(Hero 下挂两组件)、`index.scss`(补样式)

- [ ] **Step 1: Trajectory.tsx**(原生 Canvas 折线,≤5 点):

```tsx
import { useEffect, useRef } from 'react'
import Taro from '@tarojs/taro'
import { Canvas, Text, View } from '@tarojs/components'
import type { TrajectoryPoint } from '../api/types'

const CP_ZH: Record<string, string> = {
  outlook: '展望', c1: 'C1', gated: '门控', c2: 'C2', c3: 'C3', manual: '手动'
}
const W = 640, H = 150, PAD = 26

export default function Trajectory({ points }: { points: TrajectoryPoint[] }) {
  const idRef = useRef(`traj-${Math.random().toString(36).slice(2, 8)}`)
  useEffect(() => {
    if (points.length < 2) return
    const q = Taro.createSelectorQuery()
    q.select(`#${idRef.current}`).fields({ node: true, size: true }).exec(res => {
      const node = res?.[0]?.node
      if (!node) return
      const dpr = Taro.getSystemInfoSync().pixelRatio || 2
      node.width = W * dpr / 2; node.height = H * dpr / 2
      const ctx = node.getContext('2d')
      ctx.scale(dpr / 2, dpr / 2)
      ctx.clearRect(0, 0, W, H)
      const xs = points.map((_, i) => PAD + (W - 2 * PAD) * i / (points.length - 1))
      const ys = points.map(p => H - PAD - (H - 2 * PAD) * p.probability_pct / 100)
      ctx.strokeStyle = '#e8963c'; ctx.lineWidth = 2.5; ctx.lineJoin = 'round'
      ctx.beginPath()
      xs.forEach((x, i) => i === 0 ? ctx.moveTo(x, ys[i]) : ctx.lineTo(x, ys[i]))
      ctx.stroke()
      xs.forEach((x, i) => {
        ctx.beginPath()
        ctx.fillStyle = i === xs.length - 1 ? '#1c2733' : '#e8963c'
        ctx.arc(x, ys[i], i === xs.length - 1 ? 4.5 : 3.5, 0, Math.PI * 2)
        ctx.fill()
      })
      ctx.fillStyle = '#8a94a2'; ctx.font = '11px sans-serif'; ctx.textAlign = 'center'
      xs.forEach((x, i) => ctx.fillText(CP_ZH[points[i].checkpoint] || points[i].checkpoint, x, H - 8))
    })
  }, [points])

  if (points.length < 2) return null
  const first = points[0], last = points[points.length - 1]
  return (
    <View className='glass-card'>
      <Text className='card-title t-muted'>预测轨迹</Text>
      <Canvas type='2d' id={idRef.current} className='traj-canvas' />
      <Text className='traj-note t-muted'>
        {CP_ZH[first.checkpoint] || first.checkpoint} {Math.round(first.probability_pct)}%
        {' → 最新 '}{Math.round(last.probability_pct)}%,越临近越准
      </Text>
    </View>
  )
}
```

- [ ] **Step 2: ModelRows.tsx**:

```tsx
import { Text, View } from '@tarojs/components'
import type { PerModel } from '../api/types'

const ABBR: Record<string, string> = {
  ecmwf_ifs025: 'EC', gfs_seamless: 'GFS', icon_seamless: 'ICON',
  cma_grapes_global: 'CMA'
}
const n = (v: number | null) => v === null || v === undefined ? '—' : String(Math.round(v))

export default function ModelRows({ perModel }: { perModel: Record<string, PerModel> }) {
  const entries = Object.entries(perModel)
  if (!entries.length) return null
  return (
    <View className='glass-card'>
      <Text className='card-title t-muted'>各模式(概率/质量 · 高中低云 · 降水)</Text>
      {entries.map(([m, v]) => (
        <View key={m} className='model-row mono'>
          <Text className='model-name t-primary'>{ABBR[m] || m.split('_')[0].toUpperCase()}</Text>
          <Text className='t-secondary'>{Math.round(v.prob)}/{Math.round(v.qual)}</Text>
          <Text className='t-secondary'>高{n(v.cloud_high)} 中{n(v.cloud_mid)} 低{n(v.cloud_low)}</Text>
          <Text className={v.precipitation && v.precipitation >= 0.1 ? 't-red' : 't-muted'}>
            {v.precipitation && v.precipitation >= 0.1 ? `雨${v.precipitation.toFixed(1)}mm` : '无雨'}
          </Text>
        </View>
      ))}
    </View>
  )
}
```

- [ ] **Step 3: index.tsx 里 `<Hero ev={ev} />` 之后追加**:

```tsx
      <Trajectory points={ev.trajectory} />
      <ModelRows perModel={ev.per_model} />
```

(相应 import 补上。)index.scss 追加:

```scss
.card-title { display: block; font-size: 24rpx; margin-bottom: 12rpx; }
.traj-canvas { width: 100%; height: 150px; }
.traj-note { display: block; font-size: 22rpx; margin-top: 6rpx; }
.model-row {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 24rpx; line-height: 2.1;
}
.model-name { font-weight: 500; width: 90rpx; }
```

- [ ] **Step 4: 编译 + Commit**

```bash
cd /Users/feitong/photo-app/skyfire-miniapp && export PATH="$HOME/.local/node/bin:$PATH" && npm run build:weapp 2>&1 | tail -3
cd /Users/feitong/photo-app && git add skyfire-miniapp && git commit -m "feat(miniapp): 轨迹曲线(canvas折线)+各模式明细行(EC/GFS/ICON/CMA)"
```

---

### Task 4: 双热力图(懒加载)+ 解读卡

**Files:**
- Create: `skyfire-miniapp/src/components/Heatmaps.tsx`、`skyfire-miniapp/src/components/Reading.tsx`
- Modify: `skyfire-miniapp/src/pages/index/index.tsx`、`index.scss`

- [ ] **Step 1: Heatmaps.tsx**(带 X-Session 拉 arraybuffer→base64;骨架屏;点开全屏预览):

```tsx
import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { Image, Text, View } from '@tarojs/components'
import { API_BASE, getToken } from '../api/client'

async function fetchPng(event: string, date: string, kind: string): Promise<string> {
  const res = await Taro.request({
    url: `${API_BASE}/v1/heatmap?city=beijing&event=${event}&date=${date}&kind=${kind}`,
    method: 'GET',
    responseType: 'arraybuffer',
    header: { 'X-Session': getToken() }
  })
  if (res.statusCode !== 200) throw new Error(`热力图加载失败(${res.statusCode})`)
  return 'data:image/png;base64,' + Taro.arrayBufferToBase64(res.data as ArrayBuffer)
}

export default function Heatmaps({ event, date }: { event: string; date: string }) {
  const [prob, setProb] = useState('')
  const [quality, setQuality] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    setProb(''); setQuality(''); setErr('')
    let alive = true
    Promise.all([fetchPng(event, date, 'prob'), fetchPng(event, date, 'quality')])
      .then(([p, q]) => { if (alive) { setProb(p); setQuality(q) } })
      .catch(e => { if (alive) setErr(e.message) })
    return () => { alive = false }
  }, [event, date])

  const preview = (src: string) => src && Taro.previewImage({ urls: [src] })

  return (
    <View className='glass-card'>
      <View className='hm-titles'>
        <Text className='card-title t-muted'>概率图</Text>
        <Text className='card-title t-muted'>质量图</Text>
      </View>
      {err ? (
        <Text className='t-red hm-err' onClick={() => { setErr('') }}>{err},下拉刷新重试</Text>
      ) : (
        <View className='hm-row'>
          {[prob, quality].map((src, i) => (
            <View key={i} className='hm-cell'>
              {src
                ? <Image src={src} mode='widthFix' className='hm-img'
                         onClick={() => preview(src)} />
                : <View className='hm-skeleton' />}
            </View>
          ))}
        </View>
      )}
      <Text className='traj-note t-muted'>网格规则分平滑渲染 · 点图看大图 · ⊙=北京</Text>
    </View>
  )
}
```

- [ ] **Step 2: Reading.tsx**(解读卡,标题就叫"解读"):

```tsx
import { Text, View } from '@tarojs/components'
import type { Latest } from '../api/types'

export default function Reading({ latest }: { latest: Latest | null }) {
  if (!latest) return null
  return (
    <View className='glass-card'>
      <Text className='card-title t-muted'>解读</Text>
      {latest.llm_status === 'done' && latest.reasoning ? (
        <>
          <Text className='reading-text t-secondary'>{latest.reasoning}</Text>
          {latest.risks && <Text className='reading-risk t-muted'>风险:{latest.risks}</Text>}
        </>
      ) : (
        <Text className='t-muted'>解读暂缺,以上为基础数据</Text>
      )}
    </View>
  )
}
```

- [ ] **Step 3: index.tsx 组件树补全**(ModelRows 之后):

```tsx
      <Heatmaps event={ev.event} date={dateData.date} />
      <Reading latest={ev.latest} />
```

index.scss 追加:

```scss
.hm-titles { display: flex; justify-content: space-between; }
.hm-row { display: flex; gap: 16rpx; }
.hm-cell { flex: 1; }
.hm-img { width: 100%; border-radius: 20rpx; }
.hm-skeleton {
  width: 100%; height: 220rpx; border-radius: 20rpx;
  background: rgba(255, 255, 255, 0.55);
}
.hm-err { font-size: 24rpx; }
.reading-text { display: block; font-size: 26rpx; line-height: 1.7; }
.reading-risk { display: block; margin-top: 10rpx; font-size: 24rpx; }
```

- [ ] **Step 4: 编译 + Commit**

```bash
cd /Users/feitong/photo-app/skyfire-miniapp && export PATH="$HOME/.local/node/bin:$PATH" && npm run build:weapp 2>&1 | tail -3
cd /Users/feitong/photo-app && git add skyfire-miniapp && git commit -m "feat(miniapp): 双热力图懒加载(arraybuffer+骨架屏+全屏预览)+解读卡"
```

---

### Task 5: 联调冒烟 + README + 合并

- [ ] **Step 1: 起 API 并出联调说明**

```bash
cd /Users/feitong/photo-app/skyfire && .venv/bin/skyfire serve > /tmp/skyfire_serve.log 2>&1 &
```

新建 `skyfire-miniapp/README.md`:

```markdown
# skyfire 小程序(自用 v1)

## 跑起来
1. Mac 上起 API:`cd ../skyfire && .venv/bin/skyfire serve`
2. 微信开发者工具 → 导入项目 → 选本目录(AppID 已在 project.config.json)
3. 工具内会自动用 dist/;改代码需 `npm run dev:weapp` 保持编译
4. 模拟器直接可用(urlCheck 已关);真机预览:把 src/api/client.ts 的
   API_BASE 改成 Mac 局域网 IP(系统设置→Wi-Fi),手机与 Mac 同一 WiFi

## 手测清单(每次改版过一遍)
- [ ] 登录页一键登录 → 进首页(首次);杀掉重开不再要求登录
- [ ] 首页显示今天/明天下拉;朝霞/晚霞 tab;已结束事件带角标且数字淡化
- [ ] hero 大数字/定性词与 `skyfire latest` 输出一致
- [ ] 轨迹曲线点数 = 该事件 predictions 行数;标签顺序 展望→C1→门控→C2→C3
- [ ] 各模式行4行,降水≥0.1mm 标红
- [ ] 热力图骨架屏→1-3秒浮现;点开全屏;第二次切回秒出(缓存)
- [ ] 解读卡文字与推送一致;pending 时显示"解读暂缺"
- [ ] 下拉刷新生效;关掉 serve 后重进显示"服务未启动"引导
```

- [ ] **Step 2: 开发者工具编译验证**(需要用户/图形环境的部分列给用户,agent 只验证 build 与 API 可达):

```bash
cd /Users/feitong/photo-app/skyfire-miniapp && export PATH="$HOME/.local/node/bin:$PATH" && npm run build:weapp 2>&1 | tail -3
ls dist/app.json dist/pages/index/index.js dist/pages/login/index.js && echo "dist 结构 OK"
curl -s -o /dev/null -w "%{http_code}" localhost:8000/v1/summary && echo " (401=API 活着且鉴权生效)"
kill %1
```

- [ ] **Step 3: Commit + 合并**

```bash
cd /Users/feitong/photo-app && git add skyfire-miniapp/README.md && git commit -m "docs(miniapp): 联调说明+手测清单"
```

按 superpowers:finishing-a-development-branch:merge 到 main → skyfire 全量 pytest(220)+ miniapp build 各一遍 → push → 删分支。真机/模拟器的人工手测清单交给用户执行,反馈问题迭代。

---

## 执行后偏差标注(2026-07-08,惯例同前两批)

- Task 0:babel-preset-taro 4.0.9 缺 peer 依赖,补装 @babel/preset-react、@babel/preset-typescript、@babel/plugin-proposal-class-properties、@babel/plugin-proposal-object-rest-spread(devDependencies)。首个实现 agent 因基础设施 403 挂掉,协调者接手收尾。
- **计划自带 bug ×3,审查抓出并已修**:
  1. Task 2 `load()` 每次刷新用今天(dates[0])的状态重算 eventIdx,"明天"tab 上刷新会被无关状态切 tab → 改为仅首载 pickDefault(241e96e)。
  2. Task 3 轨迹 Canvas 背衬用设计常量 `W*dpr/2` 而非 CSS 盒×dpr,真机纵向拉伸(圆点变椭圆)→ 改为 selectorQuery 实测 CSS 尺寸 ×dpr + ctx.scale(dpr,dpr)(9fb2888,微信官方模式,独立核查确认)。
  3. Task 4 热力图错误卡"重试"是死按钮(只清 err 不重拉),且 fetchPng 401 不静默重登 → retryTick 进 useEffect 依赖 + 401 login() 重试一次(391e7fe)。
- 携带备忘:summary 里 created_at(UTC 空格串)与 updated_at(北京 ISO 带+08:00)两种时间约定并存,Hero 的 +'Z' 解析正确但耦合脆弱,v2 建议 API 统一时间格式;previewImage 对 base64 data url 的真机行为在手测清单覆盖。

## Self-Review 记录

- Spec §3 覆盖:登录页→Task 1,顶部日期下拉+tab+已结束→Task 2,hero+轨迹→Task 2/3,模式明细→Task 3,热力图懒加载+全屏→Task 4,解读卡→Task 4,下拉刷新→Task 2,服务未启动引导→Task 2,反馈两键 v1 隐藏→不实现(占位都不留,спec 如此)。§4 前端侧错误处理→Task 2(err 页)/Task 4(热力图重试)。陈旧提醒用 latest.created_at(API 终审携带项)→Task 2 Hero.staleHint。
- 类型一致性:types.ts 与 API 实测响应逐字段对照;Heatmaps 不用 `<Image src=url>`(带不了 X-Session 头)而走 arraybuffer→base64,heatmapUrl 保留但 v1 未用于渲染。
- 已知取舍:Taro 版本钉 4.0.9、允许统一升 patch;Canvas 用 type='2d' 新接口;无前端单测(手测清单代替,逻辑最重的部分已收敛到 client.ts/纯函数);summary 30 秒防抖缓存(spec §3)简化为"下拉刷新+每次进入拉取"——自用频率下无意义,YAGNI(偏差,记录在此)。
