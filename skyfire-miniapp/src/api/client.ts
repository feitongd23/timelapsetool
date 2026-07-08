import Taro from '@tarojs/taro'
import type { LocalResult, Summary } from './types'

// 真机与开发者工具都走 Mac 局域网 IP(2026-07-07,192.168.50.80);
// 换了 WiFi 网段要同步改(ipconfig getifaddr en0 查)
export const API_BASE = 'http://192.168.50.80:8000'

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

export function fetchLocal(event: string, date: string, lat: number,
                          lon: number): Promise<LocalResult> {
  return authedGet<LocalResult>(
    `/v1/local?event=${event}&date=${date}&lat=${lat}&lon=${lon}`)
}

export function heatmapUrl(event: string, date: string,
                           kind: 'prob' | 'quality', city = 'beijing'): string {
  return `${API_BASE}/v1/heatmap?city=${city}&event=${event}&date=${date}&kind=${kind}`
}
