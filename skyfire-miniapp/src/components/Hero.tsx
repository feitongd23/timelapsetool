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
