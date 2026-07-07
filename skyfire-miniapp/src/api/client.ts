import Taro from '@tarojs/taro'
import type { Summary } from './types'

// 开发者工具用 127.0.0.1;真机改成 Mac 局域网 IP(设置→Wi-Fi 查看)
export const API_BASE = 'http://127.0.0.1:8000'

const TOKEN_KEY = 'skyfire_token'

export function getToken(): string { return Taro.getStorageSync(TOKEN_KEY) || '' }

export async function login(): Promise<void> {
  const { code } = await Taro.login()
  const res = await Taro.request({
    url: `${API_BASE}/v1/login`,
    method: 'POST',
    data: { code },
    header: { 'content-type': 'application/json' }
  })
  if (res.statusCode !== 200) {
    throw new Error((res.data && res.data.detail) || `登录失败(${res.statusCode})`)
  }
  Taro.setStorageSync(TOKEN_KEY, res.data.token)
}

async function authedGet<T>(path: string, retried = false): Promise<T> {
  const res = await Taro.request({
    url: `${API_BASE}${path}`,
    method: 'GET',
    header: { 'X-Session': getToken() }
  })
  if (res.statusCode === 401 && !retried) {
    await login()                     // 静默重登一次再试
    return authedGet<T>(path, true)
  }
  if (res.statusCode !== 200) {
    throw new Error((res.data && res.data.detail) || `请求失败(${res.statusCode})`)
  }
  return res.data as T
}

export function fetchSummary(city = 'beijing'): Promise<Summary> {
  return authedGet<Summary>(`/v1/summary?city=${city}`)
}

export function heatmapUrl(event: string, date: string,
                           kind: 'prob' | 'quality', city = 'beijing'): string {
  return `${API_BASE}/v1/heatmap?city=${city}&event=${event}&date=${date}&kind=${kind}`
}
