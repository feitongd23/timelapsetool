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
