import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { Image, Text, View } from '@tarojs/components'
import { API_BASE, getToken, login } from '../api/client'

async function fetchPng(event: string, date: string, kind: string,
                        model: string, retried = false): Promise<string> {
  const res = await Taro.request({
    url: `${API_BASE}/v1/heatmap?city=beijing&event=${event}&date=${date}` +
         `&kind=${kind}&model=${model}`,
    method: 'GET',
    responseType: 'arraybuffer',
    header: { 'X-Session': getToken() }
  })
  if (res.statusCode === 401 && !retried) {
    await login()                     // 静默重登一次,与 authedGet 同语义
    return fetchPng(event, date, kind, model, true)
  }
  if (res.statusCode === 404) return PENDING   // 后台还没生成(跟随模式更新)
  if (res.statusCode !== 200) throw new Error(`热力图加载失败(${res.statusCode})`)
  return 'data:image/png;base64,' + Taro.arrayBufferToBase64(res.data as ArrayBuffer)
}

const PENDING = 'pending'   // 哨兵:地图跟随模式更新,尚未生成

// EC 与 GFS 双模式全国图(2026-07-09 拍板),各自跟随该模式发布轮次更新
const SLOTS = [
  ['EC 概率图', 'prob', 'ec'],
  ['EC 质量图', 'quality', 'ec'],
  ['GFS 概率图', 'prob', 'gfs'],
  ['GFS 质量图', 'quality', 'gfs'],
] as const

export default function Heatmaps({ event, date }: { event: string; date: string }) {
  const [srcs, setSrcs] = useState<string[]>([])
  const [err, setErr] = useState('')
  const [retryTick, setRetryTick] = useState(0)

  useEffect(() => {
    setSrcs([]); setErr('')
    let alive = true
    Promise.all(SLOTS.map(([, kind, model]) => fetchPng(event, date, kind, model)))
      .then(list => { if (alive) setSrcs(list) })
      .catch(e => { if (alive) setErr(e.message) })
    return () => { alive = false }
  }, [event, date, retryTick])

  const preview = (src: string) =>
    src && src !== PENDING && Taro.previewImage({ urls: [src] })

  return (
    <View className='glass-card'>
      {err ? (
        <Text className='t-red hm-err' onClick={() => setRetryTick(t => t + 1)}>{err},点我重试</Text>
      ) : (
        <View>
          {SLOTS.map(([title], i) => {
            const src = srcs[i] || ''
            return (
              <View key={title} className='hm-block'>
                <Text className='card-title t-muted'>{title}</Text>
                {src === PENDING
                  ? <View className='hm-skeleton hm-pending'>
                      <Text className='t-muted'>地图生成中 · 跟随模式更新</Text>
                    </View>
                  : src
                  ? <Image src={src} mode='widthFix' className='hm-map'
                           onClick={() => preview(src)} />
                  : <View className='hm-skeleton' />}
              </View>
            )
          })}
        </View>
      )}
      <Text className='traj-note t-muted'>全国 · 双模式各随自家更新 · 点图看大图</Text>
    </View>
  )
}
