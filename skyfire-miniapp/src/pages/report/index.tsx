import { useEffect, useState } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { ScrollView, Text, View } from '@tarojs/components'
import { fetchReport } from '../../api/client'
import type { Report } from '../../api/types'
import { themeFor } from '../../theme'
import ModelRows from '../../components/ModelRows'
import './index.scss'

// 历史报告回溯页:走势曲线点进来,展示当时那一报的完整内容
const EVENT_ZH = { sunrise_glow: '朝霞', sunset_glow: '晚霞' } as const
const CP_ZH: Record<string, string> = {
  c1: '早间首报', c2: '前2小时终判', c3: '前1小时终判',
  gated: '波动补报', outlook: '明日展望', manual: '手动'
}

function bjTime(createdAt: string): string {
  const d = new Date(createdAt.replace(' ', 'T') + 'Z')
  const h = (d.getUTCHours() + 8) % 24
  return `${h}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}

export default function ReportPage() {
  const router = useRouter()
  const [r, setR] = useState<Report | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    const id = Number(router.params.id)
    if (!id) { setErr('缺少报告编号'); return }
    fetchReport(id).then(setR).catch(e => setErr(e.message || '加载失败'))
  }, [router.params.id])

  if (err) return <View className='center-page'><Text>{err}</Text></View>
  if (!r) return <View className='center-page'><Text className='t-muted'>加载中…</Text></View>

  const theme = themeFor(r.quality_pct)
  const evZh = EVENT_ZH[r.event as keyof typeof EVENT_ZH] || r.event

  return (
    <View className='page' style={{ background: theme.bg }}>
      <ScrollView scrollY className='pagescroll rpt'>
        <Text className='rpt-title'>{r.date} {evZh} · 历史报告</Text>
        <Text className='rpt-sub'>{CP_ZH[r.checkpoint] || r.checkpoint} · {bjTime(r.created_at)} 生成</Text>

        <View className='heronums'>
          <View className='qcol'>
            <Text className='lbl'>质量</Text>
            <Text className='num-big' style={{ backgroundImage: theme.numGrad }}>
              {Math.round(r.quality_pct)}<Text className='unit-big'>%</Text>
            </Text>
          </View>
          <View className='pcol'>
            <Text className='lbl'>概率</Text>
            <Text className='num-small' style={{ color: '#96796b' }}>
              {Math.round(r.probability_pct)}<Text className='unit-small'>%</Text>
            </Text>
          </View>
        </View>
        <Text className='level' style={{ color: theme.deep }}>{r.level}</Text>

        {r.risks && (
          <View className='tagblock tb-risk'>
            <Text className='tag'>风险</Text>
            <Text className='tbody'>{r.risks}</Text>
          </View>
        )}
        <View className='tagblock tb-ai'>
          <Text className='tag'>解读</Text>
          <View className='tbd'>
            <Text className='tbody'>
              {r.llm_status === 'done' && r.reasoning ? r.reasoning : '此报无解读,为基础数据'}
            </Text>
            <Text className='tsrc'>{bjTime(r.created_at)} 生成</Text>
          </View>
        </View>

        <ModelRows perModel={r.per_model} accent={theme.accent} deep={theme.deep} />
        <View className='rpt-back' onClick={() => Taro.navigateBack()}>
          <Text>返回</Text>
        </View>
      </ScrollView>
    </View>
  )
}
