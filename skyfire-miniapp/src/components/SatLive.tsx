import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { Image, Text, View } from '@tarojs/components'
import { API_BASE, getToken, login } from '../api/client'

// 实时卫星判读图(专业页):带鉴权拉取,读 X-Sat-Time 显示北京时刻
export default function SatLive() {
  const [src, setSrc] = useState('')
  const [time, setTime] = useState('')
  const [state, setState] = useState<'loading' | 'ok' | 'none' | 'err'>('loading')

  const fetchImg = async (retried = false) => {
    try {
      const res = await Taro.request({
        url: `${API_BASE}/v1/satimg`, method: 'GET',
        responseType: 'arraybuffer', header: { 'X-Session': getToken() }
      })
      if (res.statusCode === 401 && !retried) {
        await login()
        return fetchImg(true)
      }
      if (res.statusCode === 404) { setState('none'); return }
      if (res.statusCode !== 200) { setState('err'); return }
      const hdr = res.header || {}
      setTime(hdr['X-Sat-Time'] || hdr['x-sat-time'] || '')
      setSrc('data:image/png;base64,' + Taro.arrayBufferToBase64(res.data as ArrayBuffer))
      setState('ok')
    } catch { setState('err') }
  }

  useEffect(() => { fetchImg() }, [])   // eslint-disable-line

  return (
    <View className='glass-card'>
      <Text className='card-title'>实时卫星云图 · 葵花9{time ? ` · ${time}` : ''}</Text>
      {state === 'ok' && (
        <>
          <Image src={src} mode='widthFix' className='satimg'
                 onClick={() => Taro.previewImage({ urls: [src] })} />
          <Text className='hnote'>点图看大图 · 10 分钟一帧</Text>
        </>
      )}
      {state === 'loading' && <View className='sat-skeleton' />}
      {state === 'none' && <Text className='t-muted'>实况云图暂缺,随下次检查点更新</Text>}
      {state === 'err' && (
        <Text className='t-muted' onClick={() => { setState('loading'); fetchImg() }}>
          加载失败,点我重试
        </Text>
      )}
    </View>
  )
}
