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
