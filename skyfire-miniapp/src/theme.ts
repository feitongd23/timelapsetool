// 莫兰迪主题引擎:背景与主色随火烧云质量等级变化(用户 2026-07-09 定稿)
// 不烧 浅蓝灰 → 微烧 灰米 → 小烧 灰橘 → 中烧 灰玫瑰 → 大烧 莫兰迪红 → 爆烧 深酒红

export interface Theme {
  level: string
  deep: string        // 主深色(等级字/强调)
  accent: string      // 主色(bar/点)
  numGrad: string     // 大数字渐变 CSS
  bg: string          // 整屏大气层背景 CSS
}

interface Stop { max: number; level: string; deep: string; accent: string
  a: string; b: string }

// a/b = 大气层顶部光晕的两档 rgb(逗号串)
const STOPS: Stop[] = [
  { max: 20, level: '不烧', deep: '#5d7286', accent: '#8ba3b8',
    a: '160,175,200', b: '139,163,184' },
  { max: 40, level: '微烧', deep: '#8a7a63', accent: '#b3a48e',
    a: '211,196,181', b: '179,164,142' },
  { max: 60, level: '小烧', deep: '#9c6b52', accent: '#c9a08a',
    a: '201,160,138', b: '156,107,82' },
  { max: 80, level: '中烧', deep: '#8a5f7d', accent: '#c08e96',
    a: '192,142,150', b: '169,122,151' },
  { max: 90, level: '大烧', deep: '#8f4a4f', accent: '#b5655e',
    a: '181,101,94', b: '143,74,79' },
  { max: 101, level: '爆烧', deep: '#6e3a3f', accent: '#8f4a4f',
    a: '143,74,79', b: '110,58,63' },
]

export function levelFor(q: number): string {
  return STOPS.find(s => q < s.max)!.level
}

export function themeFor(q: number): Theme {
  const s = STOPS.find(x => q < x.max)!
  return {
    level: s.level, deep: s.deep, accent: s.accent,
    numGrad: `linear-gradient(180deg, ${s.accent}, ${s.deep})`,
    bg: [
      `radial-gradient(120% 55% at 70% -6%, rgba(${s.a},.8), rgba(${s.b},.5) 40%, rgba(${s.b},0) 68%)`,
      `radial-gradient(90% 40% at 15% 14%, rgba(${s.b},.32), rgba(${s.b},0) 60%)`,
      `radial-gradient(120% 70% at 50% 112%, rgba(160,175,200,.34), rgba(160,175,200,0) 55%)`,
      `linear-gradient(180deg, #f2ecec 0%, #ece9f0 55%, #e7e6ee 100%)`,
    ].join(', '),
  }
}
