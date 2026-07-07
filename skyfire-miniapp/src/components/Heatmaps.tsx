import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { Image, Text, View } from '@tarojs/components'
import { API_BASE, getToken, login } from '../api/client'

async function fetchPng(event: string, date: string, kind: string,
                        retried = false): Promise<string> {
  const res = await Taro.request({
    url: `${API_BASE}/v1/heatmap?city=beijing&event=${event}&date=${date}&kind=${kind}`,
    method: 'GET',
    responseType: 'arraybuffer',
    header: { 'X-Session': getToken() }
  })
  if (res.statusCode === 401 && !retried) {
    await login()                     // 静默重登一次,与 authedGet 同语义
    return fetchPng(event, date, kind, true)
  }
  if (res.statusCode !== 200) throw new Error(`热力图加载失败(${res.statusCode})`)
  return 'data:image/png;base64,' + Taro.arrayBufferToBase64(res.data as ArrayBuffer)
}

export default function Heatmaps({ event, date }: { event: string; date: string }) {
  const [prob, setProb] = useState('')
  const [quality, setQuality] = useState('')
  const [err, setErr] = useState('')
  const [retryTick, setRetryTick] = useState(0)

  useEffect(() => {
    setProb(''); setQuality(''); setErr('')
    let alive = true
    Promise.all([fetchPng(event, date, 'prob'), fetchPng(event, date, 'quality')])
      .then(([p, q]) => { if (alive) { setProb(p); setQuality(q) } })
      .catch(e => { if (alive) setErr(e.message) })
    return () => { alive = false }
  }, [event, date, retryTick])

  const preview = (src: string) => src && Taro.previewImage({ urls: [src] })

  return (
    <View className='glass-card'>
      <View className='hm-titles'>
        <Text className='card-title t-muted'>概率图</Text>
        <Text className='card-title t-muted'>质量图</Text>
      </View>
      {err ? (
        <Text className='t-red hm-err' onClick={() => setRetryTick(t => t + 1)}>{err},点我重试</Text>
      ) : (
        <View className='hm-row'>
          {[prob, quality].map((src, i) => (
            <View key={i} className='hm-cell'>
              {src
                ? <Image src={src} mode='widthFix' className='hm-img'
                         onClick={() => preview(src)} />
                : <View className='hm-skeleton' />}
            </View>
          ))}
        </View>
      )}
      <Text className='traj-note t-muted'>网格规则分平滑渲染 · 点图看大图 · ⊙=北京</Text>
    </View>
  )
}
