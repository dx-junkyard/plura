/**
 * MSW ハンドラーの動作確認テスト
 *
 * handlers.ts で定義されたモックレスポンスが
 * 型安全な契約を満たしているかを確認します。
 *
 * このテストは「APIの型契約が守られているか」を保証するものです。
 * schema.d.ts が更新された際に型エラーで即座に検出できます。
 */
import { describe, expect, it } from 'vitest'
import type { components } from '../types/schema.d'

// MSW の fetch インターセプトをテスト内で使用
// (setup.ts で server.listen() 済み)
const BASE_URL = 'http://localhost'

type RawLogListResponse = components['schemas']['RawLogListResponse']
type AckResponse = components['schemas']['AckResponse']
type ConversationResponse = components['schemas']['ConversationResponse']
type InsightCardListResponse = components['schemas']['InsightCardListResponse']

describe('MSW ハンドラー - ログ API', () => {
  it('GET /api/v1/logs/ が RawLogListResponse を返す', async () => {
    const res = await fetch(`${BASE_URL}/api/v1/logs/`)
    const data: RawLogListResponse = await res.json()

    expect(res.status).toBe(200)
    expect(data).toHaveProperty('items')
    expect(data).toHaveProperty('total')
    expect(data).toHaveProperty('page')
    expect(data).toHaveProperty('page_size')
    expect(Array.isArray(data.items)).toBe(true)
  })

  it('POST /api/v1/logs/ が AckResponse (201) を返す', async () => {
    const res = await fetch(`${BASE_URL}/api/v1/logs/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: 'テストログ' }),
    })
    const data: AckResponse = await res.json()

    expect(res.status).toBe(201)
    expect(data).toHaveProperty('message')
    expect(data).toHaveProperty('log_id')
    expect(data).toHaveProperty('thread_id')
    expect(data).toHaveProperty('timestamp')
    expect(typeof data.message).toBe('string')
  })

  it('GET /api/v1/logs/:id が RawLogResponse を返す', async () => {
    const logId = '00000000-0000-0000-0000-000000000999'
    const res = await fetch(`${BASE_URL}/api/v1/logs/${logId}`)
    const data = await res.json()

    expect(res.status).toBe(200)
    expect(data.id).toBe(logId)
    expect(data).toHaveProperty('content')
    expect(data).toHaveProperty('is_analyzed')
  })

  it('DELETE /api/v1/logs/:id が 204 を返す', async () => {
    const res = await fetch(`${BASE_URL}/api/v1/logs/some-id`, {
      method: 'DELETE',
    })
    expect(res.status).toBe(204)
  })
})

describe('MSW ハンドラー - 会話 API', () => {
  it('POST /api/v1/conversation/ が ConversationResponse を返す', async () => {
    const res = await fetch(`${BASE_URL}/api/v1/conversation/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'こんにちは' }),
    })
    const data: ConversationResponse = await res.json()

    expect(res.status).toBe(200)
    expect(data).toHaveProperty('response')
    expect(data).toHaveProperty('intent_badge')
    expect(data).toHaveProperty('user_id')
    expect(data.intent_badge).toHaveProperty('intent')
    expect(data.intent_badge).toHaveProperty('confidence')
    expect(data.intent_badge).toHaveProperty('label')
    expect(typeof data.intent_badge.confidence).toBe('number')
  })

  it('intent_badge.intent が有効な ConversationIntent 値を持つ', async () => {
    const validIntents: components['schemas']['ConversationIntent'][] = [
      'chat', 'empathy', 'knowledge', 'deep_dive', 'brainstorm', 'probe', 'state_share',
    ]
    const res = await fetch(`${BASE_URL}/api/v1/conversation/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'テスト' }),
    })
    const data: ConversationResponse = await res.json()

    expect(validIntents).toContain(data.intent_badge.intent)
  })
})

describe('MSW ハンドラー - インサイト API', () => {
  it('GET /api/v1/insights/ が InsightCardListResponse を返す', async () => {
    const res = await fetch(`${BASE_URL}/api/v1/insights/`)
    const data: InsightCardListResponse = await res.json()

    expect(res.status).toBe(200)
    expect(data).toHaveProperty('items')
    expect(data).toHaveProperty('total')
    expect(Array.isArray(data.items)).toBe(true)
    if (data.items.length > 0) {
      const item = data.items[0]
      expect(item).toHaveProperty('id')
      expect(item).toHaveProperty('title')
      expect(item).toHaveProperty('summary')
      expect(item).toHaveProperty('status')
    }
  })

  it('GET /api/v1/insights/my が InsightCardListResponse を返す', async () => {
    const res = await fetch(`${BASE_URL}/api/v1/insights/my`)
    const data: InsightCardListResponse = await res.json()

    expect(res.status).toBe(200)
    expect(data).toHaveProperty('items')
  })

  it('InsightStatus が有効な値を持つ', async () => {
    const validStatuses: components['schemas']['InsightStatus'][] = [
      'draft', 'pending_approval', 'approved', 'rejected',
    ]
    const res = await fetch(`${BASE_URL}/api/v1/insights/`)
    const data: InsightCardListResponse = await res.json()

    data.items.forEach((item) => {
      expect(validStatuses).toContain(item.status)
    })
  })
})

describe('MSW ハンドラー - レコメンデーション API', () => {
  it('POST /api/v1/recommendations/ が RecommendationResponse を返す', async () => {
    const res = await fetch(`${BASE_URL}/api/v1/recommendations/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_input: 'チームのコミュニケーション改善について' }),
    })
    const data = await res.json()

    expect(res.status).toBe(200)
    expect(data).toHaveProperty('has_recommendations')
    expect(data).toHaveProperty('recommendations')
    expect(data).toHaveProperty('trigger_reason')
    expect(Array.isArray(data.recommendations)).toBe(true)
  })
})

describe('MSW ハンドラー - 認証 API', () => {
  it('POST /api/v1/auth/login が Token を返す', async () => {
    const res = await fetch(`${BASE_URL}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'test@example.com', password: 'password' }),
    })
    const data = await res.json()

    expect(res.status).toBe(200)
    expect(data).toHaveProperty('access_token')
    expect(data).toHaveProperty('token_type')
    expect(data).toHaveProperty('user')
    expect(data.user).toHaveProperty('id')
    expect(data.user).toHaveProperty('email')
  })

  it('GET /api/v1/auth/me が UserResponse を返す', async () => {
    const res = await fetch(`${BASE_URL}/api/v1/auth/me`)
    const data = await res.json()

    expect(res.status).toBe(200)
    expect(data).toHaveProperty('id')
    expect(data).toHaveProperty('email')
    expect(data).toHaveProperty('is_active')
    expect(data).toHaveProperty('is_verified')
  })
})
