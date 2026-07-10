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

// 以模式为基准并排:每个模式一行,概率/质量两张缩略图,点开全屏可左右翻
// (用户 2026-07-11 拍板)
const MODELS = [['EC', 'ec'], ['GFS', 'gfs']] as const

export default function Heatmaps({ event, date }: { event: string; date: string }) {
  const [srcs, setSrcs] = useState<Record<string, string>>({})
  const [err, setErr] = useState('')
  const [retryTick, setRetryTick] = useState(0)

  useEffect(() => {
    setSrcs({}); setErr('')
    let alive = true
    const jobs: Promise<void>[] = []
    for (const [, model] of MODELS) {
      for (const kind of ['prob', 'quality'] as const) {
        jobs.push(fetchPng(event, date, kind, model).then(src => {
          if (alive) setSrcs(prev => ({ ...prev, [`${model}-${kind}`]: src }))
        }))
      }
    }
    Promise.all(jobs).catch(e => { if (alive) setErr(e.message) })
    return () => { alive = false }
  }, [event, date, retryTick])

  const preview = (model: string, kind: string) => {
    const urls = ['prob', 'quality']
      .map(k => srcs[`${model}-${k}`])
      .filter(s => s && s !== PENDING)
    const current = srcs[`${model}-${kind}`]
    if (current && current !== PENDING) {
      Taro.previewImage({ current, urls })
    }
  }

  const thumb = (model: string, kind: string, label: string) => {
    const src = srcs[`${model}-${kind}`] || ''
    return (
      <View className='hm-thumb' onClick={() => preview(model, kind)}>
        <Text className='hm-tlabel'>{label}</Text>
        {src === PENDING
          ? <View className='hm-tskeleton hm-pending'>
              <Text className='t-muted'>生成中</Text>
            </View>
          : src
          ? <Image src={src} mode='widthFix' className='hm-timg' />
          : <View className='hm-tskeleton' />}
      </View>
    )
  }

  return (
    <View className='glass-card'>
      {err ? (
        <Text className='t-red hm-err' onClick={() => setRetryTick(t => t + 1)}>{err},点我重试</Text>
      ) : (
        <View>
          {MODELS.map(([name, model]) => (
            <View key={model} className='hm-modelrow'>
              <Text className='card-title t-muted'>{name} 全国图</Text>
              <View className='hm-pair'>
                {thumb(model, 'prob', '概率')}
                {thumb(model, 'quality', '质量')}
              </View>
            </View>
          ))}
        </View>
      )}
      <Text className='traj-note t-muted'>点缩略图全屏预览 · 左右滑切换概率/质量 · 各随自家轮次更新</Text>
    </View>
  )
}
