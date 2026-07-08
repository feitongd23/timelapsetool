import { useCallback, useEffect, useState } from 'react'
import Taro, { usePullDownRefresh } from '@tarojs/taro'
import { Picker, Text, View } from '@tarojs/components'
import { fetchSummary } from '../../api/client'
import type { EventData, Summary } from '../../api/types'
import Hero from '../../components/Hero'
import LocationCard from '../../components/LocationCard'
import ModelRows from '../../components/ModelRows'
import Heatmaps from '../../components/Heatmaps'
import Reading from '../../components/Reading'
import './index.scss'

const EVENT_ZH = { sunrise_glow: '朝霞', sunset_glow: '晚霞' } as const

export default function Index() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [err, setErr] = useState('')
  const [dateIdx, setDateIdx] = useState(0)
  const [eventIdx, setEventIdx] = useState(0)

  const load = useCallback(async (pickDefault = false) => {
    setErr('')
    try {
      const s = await fetchSummary()
      setSummary(s)
      if (pickDefault) {
        // 仅首载:默认选中今天第一个未结束的事件
        const evs = s.dates[0].events
        const firstUpcoming = evs.findIndex(e => e.status === 'upcoming')
        setEventIdx(firstUpcoming === -1 ? evs.length - 1 : firstUpcoming)
      }
    } catch (e: any) {
      setErr(e.message || '服务未启动?在 Mac 上运行 skyfire serve')
    }
  }, [])

  useEffect(() => { load(true) }, [load])
  usePullDownRefresh(async () => { await load(); Taro.stopPullDownRefresh() })

  if (err) {
    return (
      <View className='center-page'>
        <Text className='t-secondary'>{err}</Text>
        <Text className='retry t-amber' onClick={() => load(!summary)}>点我重试</Text>
      </View>
    )
  }
  if (!summary) return <View className='center-page'><Text className='t-muted'>加载中…</Text></View>

  const dateData = summary.dates[dateIdx]
  const ev: EventData = dateData.events[eventIdx]

  return (
    <View className='index-page'>
      <View className='topbar'>
        <Text className='city t-primary'>{summary.city_name}</Text>
        <Picker mode='selector' range={summary.dates.map(d => d.label)}
                value={dateIdx}
                onChange={e => setDateIdx(Number(e.detail.value))}>
          <Text className='date-picker t-secondary'>{dateData.label} ▾</Text>
        </Picker>
      </View>

      <View className='tabs glass-card'>
        {dateData.events.map((e, i) => (
          <View key={e.event}
                className={`tab ${i === eventIdx ? 'tab-active' : ''}`}
                onClick={() => setEventIdx(i)}>
            <Text>{EVENT_ZH[e.event]}</Text>
            {e.status === 'ended' && <Text className='ended-badge'>已结束</Text>}
          </View>
        ))}
      </View>

      <Hero ev={ev} />
      <LocationCard event={ev.event} date={dateData.date} />
      <Heatmaps event={ev.event} date={dateData.date} />
      <ModelRows perModel={ev.per_model} />
      <Reading latest={ev.latest} />
    </View>
  )
}
