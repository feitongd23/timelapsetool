import { useState } from 'react'
import Taro from '@tarojs/taro'
import { Text, View } from '@tarojs/components'
import { fetchLocal } from '../api/client'
import type { LocalResult } from '../api/types'

// 按用户 GPS 给位置专属火烧云质量/概率(用户 2026-07-08:地理位置影响好坏)。
// 位置值 = 中心精修预测 + 本地物理差(西/东侧透光通道+云),与首页口径一致。
export default function LocationCard({ event, date }: { event: string; date: string }) {
  const [loc, setLoc] = useState<LocalResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const locate = async () => {
    setBusy(true); setErr('')
    try {
      const pos = await Taro.getLocation({ type: 'gcj02' })
      const r = await fetchLocal(event, date, +pos.latitude.toFixed(3),
                                 +pos.longitude.toFixed(3))
      setLoc(r)
    } catch (e: any) {
      setErr(e?.errMsg?.includes('auth') || e?.errMsg?.includes('deny')
        ? '未授权定位,可在右上角···→设置里开启' : '定位失败,点我重试')
    } finally {
      setBusy(false)
    }
  }

  const deltaTxt = loc && loc.delta_quality !== 0
    ? `（较城区${loc.delta_quality > 0 ? '+' : ''}${loc.delta_quality}）` : ''

  return (
    <View className='glass-card loc-card' onClick={busy ? undefined : locate}>
      {loc ? (
        <View className='loc-row'>
          <Text className='loc-pin'>📍 你的位置</Text>
          <Text className='loc-val t-primary'>
            质量 {loc.quality_pct}%
            <Text className='loc-level t-amber'> {loc.level}</Text>
            <Text className='loc-delta t-muted'>{deltaTxt}</Text>
          </Text>
          <Text className='loc-prob t-secondary'>概率 {loc.probability_pct}%</Text>
        </View>
      ) : (
        <Text className='loc-cta t-amber'>
          {busy ? '定位中…' : err || '📍 用我的位置算更准的质量/概率'}
        </Text>
      )}
    </View>
  )
}
