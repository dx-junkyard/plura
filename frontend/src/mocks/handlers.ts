/**
 * MSW (Mock Service Worker) ハンドラー
 *
 * schema.d.ts の型を直接インポートし、型安全なモックレスポンスを返します。
 * これにより、バックエンドAPIとの「契約」が壊れたとき即座にコンパイルエラーで検出できます。
 */
import { http, HttpResponse } from 'msw'
import type { components } from '../types/schema.d'

// ==================== スキーマから型を抽出 ====================
type AckResponse = components['schemas']['AckResponse']
type RawLogResponse = components['schemas']['RawLogResponse']
type RawLogListResponse = components['schemas']['RawLogListResponse']
type ConversationResponse = components['schemas']['ConversationResponse']
type InsightCardResponse = components['schemas']['InsightCardResponse']
type InsightCardListResponse = components['schemas']['InsightCardListResponse']
type RecommendationResponse = components['schemas']['RecommendationResponse']
type Token = components['schemas']['Token']
type UserResponse = components['schemas']['UserResponse']
type SharingProposal = components['schemas']['SharingProposal']

const API_BASE = '/api/v1'

// ==================== モックデータ (固定値) ====================

const MOCK_USER: UserResponse = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'test@example.com',
  display_name: 'テストユーザー',
  avatar_url: null,
  is_active: true,
  is_verified: true,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

const MOCK_LOG: RawLogResponse = {
  id: '00000000-0000-0000-0000-000000000101',
  user_id: MOCK_USER.id,
  content: '今日は疲れた。でも良いプロジェクトが進んでいる。',
  content_type: 'text',
  thread_id: null,
  intent: 'log',
  emotions: ['疲労', '達成感'],
  emotion_scores: { 疲労: 0.6, 達成感: 0.4 },
  topics: ['仕事', 'プロジェクト'],
  tags: ['仕事', '振り返り'],
  metadata_analysis: null,
  structural_analysis: null,
  assistant_reply: 'そうなんですね。お疲れ様でした。',
  is_analyzed: true,
  is_processed_for_insight: false,
  is_structure_analyzed: false,
  created_at: '2024-01-15T10:00:00Z',
  updated_at: '2024-01-15T10:00:00Z',
}

const MOCK_INSIGHT: InsightCardResponse = {
  id: '00000000-0000-0000-0000-000000000201',
  author_id: MOCK_USER.id,
  title: 'リモートワーク移行時のチームコミュニケーション改善策',
  context: 'チームがフルリモートに移行した際、情報の非同期化が進みすぎた。',
  problem: '週次ミーティングだけでは、日々の判断の根拠が共有されない。',
  solution:
    'Slackのチャンネル設計を「議論」と「決定事項」で分離し、決定事項チャンネルは必ずサマリーをPinする。',
  summary: 'リモートワークでのチームコミュニケーション改善に関するインサイト',
  topics: ['チームワーク', 'リモートワーク', 'コミュニケーション'],
  tags: ['Slack', '非同期', '情報共有'],
  sharing_value_score: 85,
  status: 'approved',
  view_count: 42,
  thanks_count: 7,
  created_at: '2024-01-10T09:00:00Z',
  updated_at: '2024-01-12T11:00:00Z',
  published_at: '2024-01-12T11:00:00Z',
}

// ==================== ハンドラー定義 ====================

export const handlers = [
  // ==================== 認証 ====================

  /**
   * POST /api/v1/auth/register
   * ユーザー登録
   */
  http.post(`${API_BASE}/auth/register`, () => {
    const token: Token = {
      access_token: 'mock-jwt-token-for-testing',
      token_type: 'bearer',
      user: MOCK_USER,
    }
    return HttpResponse.json(token, { status: 201 })
  }),

  /**
   * POST /api/v1/auth/login
   * ユーザーログイン
   */
  http.post(`${API_BASE}/auth/login`, () => {
    const token: Token = {
      access_token: 'mock-jwt-token-for-testing',
      token_type: 'bearer',
      user: MOCK_USER,
    }
    return HttpResponse.json(token)
  }),

  /**
   * GET /api/v1/auth/me
   * 現在のユーザー情報取得
   */
  http.get(`${API_BASE}/auth/me`, () => {
    return HttpResponse.json<UserResponse>(MOCK_USER)
  }),

  // ==================== ログ ====================

  /**
   * GET /api/v1/logs/
   * ログ一覧の取得（タイムラインビュー用）
   */
  http.get(`${API_BASE}/logs/`, () => {
    const response: RawLogListResponse = {
      items: [MOCK_LOG],
      total: 1,
      page: 1,
      page_size: 20,
    }
    return HttpResponse.json(response)
  }),

  /**
   * POST /api/v1/logs/
   * 新しいログを作成（ノン・ジャッジメンタル応答）
   */
  http.post(`${API_BASE}/logs/`, () => {
    const response: AckResponse = {
      message: 'そうなんですね。記録しました。',
      log_id: '00000000-0000-0000-0000-000000000102',
      thread_id: '00000000-0000-0000-0000-000000000501',
      timestamp: new Date().toISOString(),
      conversation_reply: null,
      requires_research_consent: false,
      research_log_id: null,
    }
    return HttpResponse.json(response, { status: 201 })
  }),

  /**
   * GET /api/v1/logs/:log_id
   * 特定のログを取得
   */
  http.get(`${API_BASE}/logs/:log_id`, ({ params }) => {
    return HttpResponse.json<RawLogResponse>({
      ...MOCK_LOG,
      id: params.log_id as string,
    })
  }),

  /**
   * DELETE /api/v1/logs/:log_id
   * ログを削除
   */
  http.delete(`${API_BASE}/logs/:log_id`, () => {
    return new HttpResponse(null, { status: 204 })
  }),

  // ==================== 会話 ====================

  /**
   * POST /api/v1/conversation/
   * LangGraph による会話エンドポイント
   * 意図に応じて異なるノードでレスポンスを生成する
   */
  http.post(`${API_BASE}/conversation/`, () => {
    const response: ConversationResponse = {
      response: '今日も頑張りましたね。疲れた時は無理せず休んでください。',
      intent_badge: {
        intent: 'empathy',
        confidence: 0.9,
        label: '共感モード',
        icon: 'heart',
      },
      background_task_info: null,
      background_task: null,
      user_id: MOCK_USER.id,
      timestamp: new Date().toISOString(),
      requires_research_consent: false,
      is_researching: false,
      research_plan: null,
    }
    return HttpResponse.json(response)
  }),

  // ==================== インサイト ====================

  /**
   * GET /api/v1/insights/
   * 公開インサイト一覧（誰でも閲覧可能）
   */
  http.get(`${API_BASE}/insights/`, () => {
    const response: InsightCardListResponse = {
      items: [MOCK_INSIGHT],
      total: 1,
      page: 1,
      page_size: 20,
    }
    return HttpResponse.json(response)
  }),

  /**
   * GET /api/v1/insights/my
   * 自分のインサイト一覧
   */
  http.get(`${API_BASE}/insights/my`, () => {
    const response: InsightCardListResponse = {
      items: [MOCK_INSIGHT],
      total: 1,
      page: 1,
      page_size: 20,
    }
    return HttpResponse.json(response)
  }),

  /**
   * GET /api/v1/insights/pending
   * 承認待ちの共有提案
   */
  http.get(`${API_BASE}/insights/pending`, () => {
    const proposals: SharingProposal[] = [
      {
        insight: MOCK_INSIGHT,
        message:
          'あなたのこの経験は、チームの役に立つ可能性があります。この形式で共有しますか？',
        original_content_preview: '今日、チームのSlack運用について話し合った...',
      },
    ]
    return HttpResponse.json(proposals)
  }),

  /**
   * GET /api/v1/insights/:insight_id
   * インサイト詳細取得
   */
  http.get(`${API_BASE}/insights/:insight_id`, ({ params }) => {
    return HttpResponse.json<InsightCardResponse>({
      ...MOCK_INSIGHT,
      id: params.insight_id as string,
    })
  }),

  /**
   * POST /api/v1/insights/:insight_id/thanks
   * 「ありがとう」を送る
   */
  http.post(`${API_BASE}/insights/:insight_id/thanks`, () => {
    return HttpResponse.json({ thanks_count: MOCK_INSIGHT.thanks_count + 1 })
  }),

  // ==================== レコメンデーション ====================

  /**
   * POST /api/v1/recommendations/
   * Serendipity Matcher によるリアルタイムレコメンデーション
   */
  http.post(`${API_BASE}/recommendations/`, () => {
    const response: RecommendationResponse = {
      has_recommendations: true,
      recommendations: [
        {
          id: MOCK_INSIGHT.id,
          title: MOCK_INSIGHT.title,
          summary: MOCK_INSIGHT.summary,
          topics: MOCK_INSIGHT.topics ?? [],
          relevance_score: 0.85,
          preview: MOCK_INSIGHT.summary,
          category: null,
          reason: '入力内容と類似した経験が見つかりました。',
          team_members: null,
          project_name: null,
        },
      ],
      trigger_reason: 'similar_experiences_found',
      display_message: '似た経験を持つ人がいます',
    }
    return HttpResponse.json(response)
  }),

  /**
   * GET /api/v1/recommendations/similar/:insight_id
   * 類似インサイトの取得
   */
  http.get(`${API_BASE}/recommendations/similar/:insight_id`, () => {
    return HttpResponse.json([MOCK_INSIGHT])
  }),
]
