import { Text, View } from '@tarojs/components'
import type { PerModel } from '../api/types'

const ABBR: Record<string, string> = {
  ecmwf_ifs025: 'EC', gfs_seamless: 'GFS', icon_seamless: 'ICON',
  cma_grapes_global: 'CMA'
}
const pct = (v: number | null) =>
  v === null || v === undefined ? '—' : `${Math.round(v)}%`
const clamp = (v: number) => Math.max(0, Math.min(100, v))

function Bar({ value, tone }: { value: number; tone: 'prob' | 'qual' }) {
  return (
    <View className='bar-track'>
      <View className={`bar-fill bar-${tone}`} style={{ width: `${clamp(value)}%` }} />
    </View>
  )
}

export default function ModelRows({ perModel }: { perModel: Record<string, PerModel> }) {
  const entries = Object.entries(perModel)
  if (!entries.length) return null
  return (
    <View className='glass-card'>
      <Text className='card-title t-muted'>各模式</Text>
      {entries.map(([m, v]) => (
        <View key={m} className='mr'>
          <View className='mr-head'>
            <Text className='mr-name t-primary'>
              {ABBR[m] || m.split('_')[0].toUpperCase()}
            </Text>
            <Text className={v.precipitation && v.precipitation >= 0.1
              ? 'mr-rain t-red' : 'mr-rain t-muted'}>
              {v.precipitation && v.precipitation >= 0.1
                ? `雨 ${v.precipitation.toFixed(1)}mm` : '无雨'}
            </Text>
          </View>
          <View className='mr-metric'>
            <Text className='mr-label t-muted'>概率</Text>
            <Bar value={v.prob} tone='prob' />
            <Text className='mr-val t-secondary'>{Math.round(v.prob)}%</Text>
          </View>
          <View className='mr-metric'>
            <Text className='mr-label t-muted'>质量</Text>
            <Bar value={v.qual} tone='qual' />
            <Text className='mr-val t-amber'>{Math.round(v.qual)}%</Text>
          </View>
          <View className='mr-clouds'>
            <Text className='mr-cloud t-secondary'>高 {pct(v.cloud_high)}</Text>
            <Text className='mr-cloud t-secondary'>中 {pct(v.cloud_mid)}</Text>
            <Text className='mr-cloud t-secondary'>低 {pct(v.cloud_low)}</Text>
          </View>
        </View>
      ))}
    </View>
  )
}
