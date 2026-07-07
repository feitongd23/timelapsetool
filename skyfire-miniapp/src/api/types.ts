export interface Latest {
  checkpoint: string
  probability_pct: number
  quality_pct: number
  prob_word: string
  qual_word: string
  confidence: string
  llm_status: string
  reasoning: string | null
  risks: string | null
  created_at: string
}

export interface TrajectoryPoint {
  checkpoint: string
  probability_pct: number
  quality_pct: number
  created_at: string
}

export interface PerModel {
  prob: number
  qual: number
  cloud_high: number | null
  cloud_mid: number | null
  cloud_low: number | null
  precipitation: number | null
}

export interface EventData {
  event: 'sunrise_glow' | 'sunset_glow'
  status: 'ended' | 'upcoming'
  peak: string
  best_window: string
  latest: Latest | null
  trajectory: TrajectoryPoint[]
  per_model: Record<string, PerModel>
}

export interface DateData {
  date: string
  label: string
  events: EventData[]
}

export interface Summary {
  city: string
  city_name: string
  updated_at: string
  dates: DateData[]
}
