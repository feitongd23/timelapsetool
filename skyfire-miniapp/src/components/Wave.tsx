import { useEffect, useRef } from 'react'
import Taro from '@tarojs/taro'
import { Canvas, Text, View } from '@tarojs/components'
import type { TrajectoryPoint } from '../api/types'

// 今日质量走势:每报一点,横轴=生成时间,点上标质量%;点任意一点看当时报告
const PAD_X = 18
const PAD_TOP = 20
const PAD_BOT = 18

function bjTime(createdAt: string): string {
  const d = new Date(createdAt.replace(' ', 'T') + 'Z')
  const h = (d.getUTCHours() + 8) % 24
  return `${h}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}

export default function Wave({ points, accent, deep, onPick }: {
  points: TrajectoryPoint[]
  accent: string
  deep: string
  onPick: (id: number) => void
}) {
  const idRef = useRef(`wave-${Math.random().toString(36).slice(2, 8)}`)
  const pxRef = useRef<{ x: number; id: number }[]>([])

  useEffect(() => {
    if (points.length < 2) return
    const q = Taro.createSelectorQuery()
    q.select(`#${idRef.current}`).fields({ node: true, size: true }).exec(res => {
      const node = res?.[0]?.node
      if (!node) return
      const cssW = res[0].width || 320
      const cssH = res[0].height || 78
      const dpr = Taro.getSystemInfoSync().pixelRatio || 2
      node.width = cssW * dpr
      node.height = cssH * dpr
      const ctx = node.getContext('2d')
      ctx.scale(dpr, dpr)
      ctx.clearRect(0, 0, cssW, cssH)
      const xs = points.map((_, i) =>
        PAD_X + (cssW - 2 * PAD_X) * i / (points.length - 1))
      const ys = points.map(p =>
        cssH - PAD_BOT - (cssH - PAD_TOP - PAD_BOT) * p.quality_pct / 100)
      pxRef.current = xs.map((x, i) => ({ x, id: points[i].id }))
      ctx.strokeStyle = 'rgba(43,36,46,.22)'
      ctx.lineWidth = 2
      ctx.lineJoin = 'round'
      ctx.beginPath()
      xs.forEach((x, i) => i === 0 ? ctx.moveTo(x, ys[i]) : ctx.lineTo(x, ys[i]))
      ctx.stroke()
      xs.forEach((x, i) => {
        const last = i === xs.length - 1
        ctx.beginPath()
        ctx.fillStyle = last ? accent : 'rgba(43,36,46,.28)'
        ctx.arc(x, ys[i], last ? 4.5 : 3, 0, Math.PI * 2)
        ctx.fill()
        if (last) {
          ctx.beginPath()
          ctx.strokeStyle = accent
          ctx.globalAlpha = 0.4
          ctx.arc(x, ys[i], 8, 0, Math.PI * 2)
          ctx.stroke()
          ctx.globalAlpha = 1
        }
        // 点上质量值
        ctx.fillStyle = last ? deep : '#77707f'
        ctx.font = `${last ? 'bold 11px' : '9.5px'} sans-serif`
        ctx.textAlign = 'center'
        ctx.fillText(String(Math.round(points[i].quality_pct)), x, ys[i] - 8)
        // 点下时间
        ctx.fillStyle = '#a49cae'
        ctx.font = '8.5px sans-serif'
        ctx.fillText(bjTime(points[i].created_at), x, cssH - 4)
      })
    })
  }, [points, accent, deep])

  if (points.length < 2) return null

  const onTouch = (e: any) => {
    const t = e.changedTouches?.[0]
    if (!t || t.x === undefined) return
    let best: { x: number; id: number } | null = null
    for (const p of pxRef.current) {
      if (!best || Math.abs(p.x - t.x) < Math.abs(best.x - t.x)) best = p
    }
    if (best && Math.abs(best.x - t.x) < 24) onPick(best.id)
  }

  return (
    <View className='wave'>
      <Text className='wave-cap'>今日质量走势 · 点任意一报查看当时报告</Text>
      <Canvas type='2d' id={idRef.current} className='wave-canvas'
              onTouchEnd={onTouch} />
    </View>
  )
}
