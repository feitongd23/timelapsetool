import { Text, View } from '@tarojs/components'
import type { PerModel } from '../api/types'

// 排布顺序按用户拍板:EC GFS ICON CMA;概率/质量 bar 之后展示总/高/中/低云量小 bar
const ORDER = ['ecmwf_ifs', 'ecmwf_ifs025', 'gfs_seamless', 'icon_seamless', 'cma_grapes_global']
const ABBR: Record<string, string> = {
  ecmwf_ifs: 'EC', ecmwf_ifs025: 'EC', gfs_seamless: 'GFS',
  icon_seamless: 'ICON', cma_grapes_global: 'CMA'
}
const clamp = (v: number | null) =>
  v === null || v === undefined ? 0 : Math.max(0, Math.min(100, v))
const pct = (v: number | null) =>
  v === null || v === undefined ? '—' : `${Math.round(v)}%`

function CloudCell({ label, value, total }: {
  label: string; value: number | null; total?: boolean
}) {
  return (
    <View className='mr-cl'>
      <View className='mr-clt'>
        <Text className='mr-cll'>{label}</Text>
        <Text className='mr-clv'>{pct(value)}</Text>
      </View>
      <View className='mr-clb'>
        <View className={`mr-clbi ${total ? 'mr-clbi-tot' : ''}`}
              style={{ width: `${clamp(value)}%` }} />
      </View>
    </View>
  )
}

export default function ModelRows({ perModel, accent, deep }: {
  perModel: Record<string, PerModel>
  accent: string
  deep: string
}) {
  const entries = ORDER.filter(m => perModel[m]).map(m => [m, perModel[m]] as const)
  if (!entries.length) return null
  return (
    <View className='glass-card'>
      <Text className='card-title'>各模式 · 概率 质量 与云量</Text>
      {entries.map(([m, v]) => {
        const total = Math.min(100,
          (v.cloud_high || 0) + (v.cloud_mid || 0) + (v.cloud_low || 0))
        const wet = v.precipitation !== null && v.precipitation >= 0.1
        return (
          <View key={m} className='mrb'>
            <View className='mrb-head'>
              <Text className='mrb-nm'>{ABBR[m]}</Text>
              <Text className={wet ? 'mrb-rain wet' : 'mrb-rain'}>
                {wet ? `雨 ${v.precipitation!.toFixed(1)}mm` : '无雨'}
              </Text>
            </View>
            <View className='mrb-row'>
              <Text className='mrb-bl'>概率</Text>
              <View className='mrb-bar'>
                <View className='mrb-fill' style={{
                  width: `${clamp(v.prob)}%`, background: accent }} />
              </View>
              <Text className='mrb-bv'>{Math.round(v.prob)}%</Text>
            </View>
            <View className='mrb-row'>
              <Text className='mrb-bl'>质量</Text>
              <View className='mrb-bar'>
                <View className='mrb-fill' style={{
                  width: `${clamp(v.qual)}%`, background: deep }} />
              </View>
              <Text className='mrb-bv'>{Math.round(v.qual)}%</Text>
            </View>
            <View className='mr-clouds'>
              <CloudCell label='总' value={total} total />
              <CloudCell label='高' value={v.cloud_high} />
              <CloudCell label='中' value={v.cloud_mid} />
              <CloudCell label='低' value={v.cloud_low} />
            </View>
          </View>
        )
      })}
    </View>
  )
}
