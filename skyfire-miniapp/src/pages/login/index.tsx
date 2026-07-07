import { useState } from 'react'
import Taro from '@tarojs/taro'
import { Button, Text, View } from '@tarojs/components'
import { getToken, login } from '../../api/client'
import './index.scss'

export default function Login() {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function onLogin() {
    setBusy(true); setErr('')
    try {
      await login()
      Taro.redirectTo({ url: '/pages/index/index' })
    } catch (e: any) {
      setErr(e.message || '登录失败,检查 API 服务是否已启动')
    } finally {
      setBusy(false)
    }
  }

  // 已有 token 直接进首页(401 时首页会静默重登)
  if (getToken()) {
    Taro.redirectTo({ url: '/pages/index/index' })
    return null
  }

  return (
    <View className='login-page'>
      <View className='login-hero'>
        <Text className='login-title'>火烧云</Text>
        <Text className='login-sub t-secondary'>烧不烧,提前知道</Text>
      </View>
      <Button className='login-btn' loading={busy} onClick={onLogin}>
        微信一键登录
      </Button>
      {err && <Text className='login-err t-red'>{err}</Text>}
    </View>
  )
}
