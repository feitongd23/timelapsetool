import { useEffect, useRef } from 'react'
import Taro from '@tarojs/taro'
import { Canvas, Text, View } from '@tarojs/components'
import type { TrajectoryPoint } from '../api/types'

const CP_ZH: Record<string, string> = {
  outlook: '展望', c1: 'C1', gated: '门控', c2: 'C2', c3: 'C3', manual: '手动'
}
const PAD = 26

export default function Trajectory({ points }: { points: TrajectoryPoint[] }) {
  const idRef = useRef(`traj-${Math.random().toString(36).slice(2, 8)}`)
  useEffect(() => {
    if (points.length < 2) return
    const q = Taro.createSelectorQuery()
    q.select(`#${idRef.current}`).fields({ node: true, size: true }).exec(res => {
      const node = res?.[0]?.node
      if (!node) return
      const cssW = res[0].width || 320
      const cssH = res[0].height || 150
      const dpr = Taro.getSystemInfoSync().pixelRatio || 2
      node.width = cssW * dpr
      node.height = cssH * dpr
      const ctx = node.getContext('2d')
      ctx.scale(dpr, dpr)
      ctx.clearRect(0, 0, cssW, cssH)
      const xs = points.map((_, i) => PAD + (cssW - 2 * PAD) * i / (points.length - 1))
      const ys = points.map(p => cssH - PAD - (cssH - 2 * PAD) * p.probability_pct / 100)
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
      xs.forEach((x, i) => ctx.fillText(CP_ZH[points[i].checkpoint] || points[i].checkpoint, x, cssH - 8))
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
