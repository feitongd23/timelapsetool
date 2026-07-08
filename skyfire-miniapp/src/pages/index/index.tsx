import { useCallback, useEffect, useMemo, useState } from 'react'
import Taro, { usePullDownRefresh } from '@tarojs/taro'
import { ScrollView, Swiper, SwiperItem, Text, View } from '@tarojs/components'
import { fetchAqi, fetchHourly, fetchLocal, fetchSummary } from '../../api/client'
import type { Aqi, EventData, HourItem, LocalResult, Summary } from '../../api/types'
import { themeFor } from '../../theme'
import Wave from '../../components/Wave'
import ModelRows from '../../components/ModelRows'
import Heatmaps from '../../components/Heatmaps'
import SatLive from '../../components/SatLive'
import './index.scss'

const CITY_CENTER = { lat: 39.9042, lon: 116.4074 }
const EVENT_ORDER = ['sunrise_glow', 'sunset_glow'] as const   // 朝霞在前
const EVENT_ZH = { sunrise_glow: '朝霞', sunset_glow: '晚霞' } as const

function cpLabel(cp: string, sunset: boolean): string {
  const when = sunset ? '日落' : '日出'
  return ({ c1: '早间首报', c2: `${when}前2小时终判`, c3: `${when}前1小时终判`,
            gated: '波动补报', outlook: '明日展望', manual: '手动' } as any)[cp] || cp
}

function bjTime(createdAt: string): string {
  const d = new Date(createdAt.replace(' ', 'T') + 'Z')
  const h = (d.getUTCHours() + 8) % 24
  return `${h}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}

function minutesToPeak(dateS: string, peakHM: string): number {
  const [h, m] = peakHM.split(':').map(Number)
  const peak = new Date(`${dateS}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00+08:00`)
  return Math.round((peak.getTime() - Date.now()) / 60000)
}

// 简洁天气图标(单色线条,无 emoji)
function WeatherIcon({ text }: { text: string }) {
  if (text === '晴') return (
    <View className='wicon'><View className='wsun' /></View>)
  if (text.includes('雨') || text.includes('雪')) return (
    <View className='wicon'><View className='wcloud' /><View className='wdrop' /></View>)
  return <View className='wicon'><View className='wcloud' /></View>
}

export default function Index() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [err, setErr] = useState('')
  const [dateIdx, setDateIdx] = useState(0)
  const [eventKey, setEventKey] = useState<'sunrise_glow' | 'sunset_glow'>('sunset_glow')
  const [loc, setLoc] = useState<LocalResult | null>(null)
  const [coords, setCoords] = useState(CITY_CENTER)
  const [aqi, setAqi] = useState<Aqi | null>(null)
  const [hours, setHours] = useState<HourItem[]>([])

  const load = useCallback(async (pickDefault = false) => {
    setErr('')
    try {
      const s = await fetchSummary()
      setSummary(s)
      if (pickDefault) {
        const evs = s.dates[0].events
        const firstUp = evs.find(e => e.status === 'upcoming')
        setEventKey((firstUp?.event as any) || 'sunset_glow')
      }
    } catch (e: any) {
      setErr(e.message || '服务未启动')
    }
  }, [])

  const locate = useCallback(async (dateS: string, ev: string) => {
    try {
      const pos = await Taro.getLocation({ type: 'gcj02' })
      const c = { lat: +pos.latitude.toFixed(3), lon: +pos.longitude.toFixed(3) }
      setCoords(c)
      const r = await fetchLocal(ev, dateS, c.lat, c.lon)
      setLoc(r)
    } catch { /* 未授权/失败:保持城区口径 */ }
  }, [])

  useEffect(() => { load(true) }, [load])
  usePullDownRefresh(async () => { await load(); Taro.stopPullDownRefresh() })

  const dateData = summary?.dates[dateIdx]
  const ev: EventData | undefined =
    dateData?.events.find(e => e.event === eventKey)

  // 定位与随动数据:日期/天象/坐标变化时刷新
  useEffect(() => {
    if (!dateData || !ev) return
    locate(dateData.date, ev.event)
  }, [summary, dateIdx, eventKey])  // eslint-disable-line
  useEffect(() => {
    fetchAqi(coords.lat, coords.lon).then(setAqi).catch(() => setAqi(null))
    fetchHourly(coords.lat, coords.lon).then(r => setHours(r.hours))
      .catch(() => setHours([]))
  }, [coords])

  const displayQ = loc ? loc.quality_pct : ev?.latest?.quality_pct ?? 0
  const displayP = loc ? loc.probability_pct : ev?.latest?.probability_pct ?? 0
  const theme = useMemo(() => themeFor(displayQ), [displayQ])
  const qBig = displayQ >= displayP   // 谁高谁大

  const openReport = (id: number) => {
    Taro.navigateTo({ url: `/pages/report/index?id=${id}` })
  }

  if (err) {
    return (
      <View className='center-page'>
        <Text className='t-secondary'>{err}</Text>
        <Text className='retry' onClick={() => load(!summary)}>点我重试</Text>
      </View>
    )
  }
  if (!summary || !dateData || !ev) {
    return <View className='center-page'><Text className='t-muted'>加载中…</Text></View>
  }

  const l = ev.latest
  const traj = ev.trajectory
  const seq = traj.length
  const prev = traj.length > 1 ? traj[traj.length - 2] : null
  const dq = l && prev ? Math.round(l.quality_pct - prev.quality_pct) : 0
  const sunset = ev.event === 'sunset_glow'
  const when = sunset ? '日落' : '日出'
  const toPeak = minutesToPeak(dateData.date, ev.peak)
  const genT = l ? bjTime(l.created_at) : ''
  const isFinal = l && ['c2', 'c3', 'gated'].includes(l.checkpoint)

  const numBlock = (label: string, v: number, big: boolean) => (
    <View className={big ? 'qcol' : 'pcol'}>
      {big && <Text className='lbltop'>你的位置 火烧云</Text>}
      <Text className='lbl'>{label}</Text>
      <Text className={big ? 'num-big' : 'num-small'}
            style={big ? { backgroundImage: theme.numGrad } : { color: '#96796b' }}>
        {Math.round(v)}<Text className={big ? 'unit-big' : 'unit-small'}>%</Text>
      </Text>
    </View>
  )

  return (
    <View className='page' style={{ background: theme.bg }}>
      {/* 顶行:定位(左),右侧留给系统胶囊 */}
      <View className='topline'>
        <View className='loc' onClick={() => locate(dateData.date, ev.event)}>
          <View className='pin-row'>
            <View className='pin-icon' />
            <Text className='pin-name'>{loc?.name || summary.city_name}</Text>
            <Text className='pin-arrow'>▾</Text>
          </View>
          <Text className='pin-sub'>
            {summary.city_name}{loc?.district ? ` · ${loc.district}` : ''} · 点此重新定位
          </Text>
        </View>
      </View>

      {/* 日期 + 朝晚 双组 tab */}
      <View className='segrow'>
        <View className='seg'>
          {summary.dates.map((d, i) => (
            <Text key={d.date} className={`seg-i ${i === dateIdx ? 'on' : ''}`}
                  onClick={() => setDateIdx(i)}>{d.label.split(' ')[0]}</Text>
          ))}
        </View>
        <View className='seg'>
          {EVENT_ORDER.map(k => (
            <Text key={k} className={`seg-i ${k === eventKey ? 'on' : ''}`}
                  onClick={() => setEventKey(k)}>{EVENT_ZH[k]}</Text>
          ))}
        </View>
      </View>

      <Swiper className='pages' indicatorDots indicatorColor='rgba(43,36,46,.2)'
              indicatorActiveColor='rgba(43,36,46,.55)'>
        {/* 第一屏:主页 */}
        <SwiperItem>
          <ScrollView scrollY className='pagescroll'>
            <Wave points={traj} accent={theme.accent} deep={theme.deep}
                  onPick={openReport} />

            {l ? (
              <View className='hero'>
                <View className='heronums'>
                  {qBig ? (<>
                    {numBlock('质量', displayQ, true)}
                    {numBlock('概率', displayP, false)}
                  </>) : (<>
                    {numBlock('概率', displayP, true)}
                    {numBlock('质量', displayQ, false)}
                  </>)}
                </View>
                <Text className='level' style={{ color: theme.deep }}>
                  {loc ? loc.level : themeFor(displayQ).level}
                </Text>

                <View className='striprow'>
                  {prev && (
                    <View className='sstrip'>
                      <Text className='stag' style={{
                        background: Math.abs(dq) >= 15
                          ? `linear-gradient(135deg, ${theme.accent}, ${theme.deep})`
                          : '#8d8398' }}>
                        {Math.abs(dq) >= 15 ? '突变' : '变化'}
                      </Text>
                      <Text className='stxt'>较上次 {dq >= 0 ? '+' : ''}{dq}</Text>
                    </View>
                  )}
                  {loc && (
                    <View className='sstrip'>
                      <Text className='stag' style={{ background: '#8d8398' }}>位置</Text>
                      <Text className='stxt'>
                        较城区 {loc.delta_quality >= 0 ? '+' : ''}{loc.delta_quality}
                      </Text>
                    </View>
                  )}
                </View>

                <Text className='genline'>
                  第 {seq} 报 · {cpLabel(l.checkpoint, sunset)}
                </Text>
                <Text className='genline2'>
                  {genT} 生成{toPeak > 0 ? ` · 距${when}约 ${toPeak > 90
                    ? (toPeak / 60).toFixed(1) + ' 小时' : toPeak + ' 分钟'}` : ` · ${when}已过`}
                </Text>

                {l.risks && (
                  <View className='tagblock tb-risk'>
                    <Text className='tag'>风险</Text>
                    <Text className='tbody'>{l.risks}</Text>
                  </View>
                )}

                {aqi && aqi.aqi !== null && (
                  <View className='tagblock tb-air'>
                    <Text className='tag'>空气</Text>
                    <Text className='tbody'>
                      AQI {aqi.aqi} {aqi.level} · PM2.5 {aqi.pm25 ?? '—'} · {aqi.source} {aqi.time}
                    </Text>
                  </View>
                )}

                <View className='tagblock tb-ai'>
                  <Text className='tag'>解读</Text>
                  <View className='tbd'>
                    <Text className='tbody'>
                      {l.llm_status === 'done' && l.reasoning
                        ? l.reasoning : '解读暂缺,以上为基础数据'}
                    </Text>
                    <Text className='tsrc'>
                      第 {seq} 报 · {genT} 生成{isFinal ? ' · 结合实时云图' : ''}
                    </Text>
                  </View>
                </View>

                <View className='glass-card'>
                  <Text className='card-title'>本报信息</Text>
                  <View className='kv'><Text className='k'>报次</Text>
                    <Text className='v'>第 {seq} 报 · {cpLabel(l.checkpoint, sunset)}</Text></View>
                  <View className='kv'><Text className='k'>生成</Text>
                    <Text className='v'>{genT}{toPeak > 0 ? ` · 距${when} ${toPeak} 分钟` : ''}</Text></View>
                  <View className='kv'><Text className='k'>{when}</Text>
                    <Text className='v'>{ev.peak} · 最佳 {ev.best_window}</Text></View>
                  {loc && (
                    <View className='kv'><Text className='k'>位置</Text>
                      <Text className='v'>{loc.name}{loc.district ? ` · ${loc.district}` : ''} · 较城区 {loc.delta_quality >= 0 ? '+' : ''}{loc.delta_quality}</Text></View>
                  )}
                  <View className='kv'><Text className='k'>可信度</Text>
                    <Text className='v'>{{ high: '高', medium: '中', low: '低',
                      degraded: '弱' }[l.confidence] || l.confidence} · 四模型置信加权</Text></View>
                </View>

                {hours.length > 0 && (
                  <View className='glass-card'>
                    <Text className='card-title'>小时天气{loc ? ` · ${loc.name}` : ''}</Text>
                    <View className='hours'>
                      {hours.slice(0, 6).map(h => (
                        <View key={h.hour} className='hr'>
                          <Text className='hr-t'>{h.hour}时</Text>
                          <WeatherIcon text={h.text} />
                          <Text className='hr-tp'>{h.temp}°</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                )}

                <Heatmaps event={ev.event} date={dateData.date} />
                <View className='swipehint'><Text>右滑 专业数据</Text></View>
              </View>
            ) : (
              <View className='glass-card'>
                <Text className='t-muted'>待检查点生成预测,每晚21点起陆续更新</Text>
              </View>
            )}
          </ScrollView>
        </SwiperItem>

        {/* 第二屏:专业数据 */}
        <SwiperItem>
          <ScrollView scrollY className='pagescroll'>
            <View className='p2head'>
              <Text className='p2t'>专业数据</Text>
              <Text className='p2b'>{dateData.label.split(' ')[0]} {EVENT_ZH[eventKey]} · 随主页联动</Text>
            </View>
            <SatLive />
            <ModelRows perModel={ev.per_model} accent={theme.accent}
                       deep={theme.deep} />
          </ScrollView>
        </SwiperItem>
      </Swiper>
    </View>
  )
}
