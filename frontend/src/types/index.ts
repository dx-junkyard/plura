/**
 * PLURA - Type Definitions (Auto-sync Adapter)
 *
 * このファイルは Backend の Pydantic モデルから自動生成された schema.d.ts のアダプターです。
 * 直接手書きで型を定義せず、必ず schema.d.ts 経由で型を参照してください。
 *
 * 型の更新手順:
 *   1. Backend の schemas/*.py を修正
 *   2. `python backend/scripts/extract_openapi.py --output backend/openapi.json` を実行
 *   3. frontend で `npm run gen:types` を実行
 *   4. 以下のマッピングに変更が必要な場合のみ、このファイルを修正する
 */

import type { components } from './schema';

// =============================================================================
// User
// =============================================================================

/** ユーザープロフィール (Backend: UserResponse) */
export type User = components['schemas']['UserResponse'];

/** 認証トークン (Backend: Token) */
export type Token = components['schemas']['Token'];

// =============================================================================
// Log Intent
// =============================================================================

/** ログの意図分類 (Backend: LogIntent) */
export type LogIntent = components['schemas']['LogIntent'];

// =============================================================================
// Structural Analysis
// Frontend が独自に詳細型付けしている（BackendはJSON型で返す）
// =============================================================================

/** LLM使用モデル情報（Backend のレスポンスには含まれず Frontend のみで利用） */
export interface ModelInfo {
  tier: 'deep' | 'balanced' | 'fast';
  model: string;
  is_reasoning: boolean;
}

/** 構造的分析結果（structural_analysis フィールドの具体型） */
export interface StructuralAnalysis {
  relationship_type: 'ADDITIVE' | 'PARALLEL' | 'CORRECTION' | 'NEW';
  relationship_reason: string;
  updated_structural_issue: string;
  probing_question: string;
  model_info?: ModelInfo;
}

// =============================================================================
// Raw Log (Layer 1)
// structural_analysis / metadata_analysis は Backend では dict 型のため、
// Omit + 上書きで Frontend の詳細型付けを維持する。
// =============================================================================

/** Raw ログ (Backend: RawLogResponse, structural_analysis/metadata_analysis を詳細型付け) */
export type RawLog = Omit<
  components['schemas']['RawLogResponse'],
  'structural_analysis' | 'metadata_analysis'
> & {
  structural_analysis: StructuralAnalysis | null;
  metadata_analysis: {
    deep_research?: {
      title?: string;
      topic?: string;
      scope?: string;
      perspectives?: string[];
      summary?: string;
      details?: string;
      requested_by_user_id?: string;
      is_cache_hit?: boolean;
      cached_insight_id?: string | null;
    };
    [key: string]: unknown;
  } | null;
};

/** Raw ログ一覧レスポンス */
export type RawLogListResponse = Omit<
  components['schemas']['RawLogListResponse'],
  'items'
> & {
  items: RawLog[];
};

/** ログ作成後の応答 (Backend: AckResponse) */
export type AckResponse = components['schemas']['AckResponse'];

// =============================================================================
// Insight Card (Layer 3)
// =============================================================================

/** インサイトの状態 (Backend: InsightStatus) */
export type InsightStatus = components['schemas']['InsightStatus'];

/** インサイトカード (Backend: InsightCardResponse) */
export type InsightCard = components['schemas']['InsightCardResponse'];

/** インサイト一覧レスポンス */
export type InsightCardListResponse = Omit<
  components['schemas']['InsightCardListResponse'],
  'items'
> & {
  items: InsightCard[];
};

/** 共有提案 (Backend: SharingProposal) */
export type SharingProposal = Omit<
  components['schemas']['SharingProposal'],
  'insight'
> & {
  insight: InsightCard;
};

// =============================================================================
// Conversation (LangGraph Hypothesis-Driven Routing)
// =============================================================================

/** 会話の意図分類 (Backend: ConversationIntent) */
export type ConversationIntent = components['schemas']['ConversationIntent'];

/**
 * 前回の評価分類（Backend のスキーマには含まれず Frontend のみで利用）
 * IntentHypothesis の内部フィールド用
 */
export type PreviousEvaluation = 'positive' | 'negative' | 'pivot' | 'none';

/**
 * 仮説駆動ルーティング結果（Backend のスキーマには含まれず Frontend のみで利用）
 * LangGraph 内部状態の可視化用
 */
export interface IntentHypothesis {
  previous_evaluation: PreviousEvaluation;
  primary_intent: ConversationIntent;
  primary_confidence: number;
  secondary_intent: ConversationIntent;
  secondary_confidence: number;
  needs_probing: boolean;
  reasoning: string;
}

/** インテントバッジ（UI 表示用） (Backend: IntentBadge) */
export type IntentBadge = components['schemas']['IntentBadge'];

/** バックグラウンドタスクの状態 */
export type BackgroundTaskStatus = NonNullable<
  components['schemas']['BackgroundTask']['status']
>;

/** バックグラウンドタスク (Backend: BackgroundTask) */
export type BackgroundTask = components['schemas']['BackgroundTask'];

/** 調査計画書 (Backend: ResearchPlan) */
export type ResearchPlan = components['schemas']['ResearchPlan'];

/** 会話リクエスト (Backend: ConversationRequest) */
export type ConversationRequest = components['schemas']['ConversationRequest'];

/** 会話レスポンス (Backend: ConversationResponse) */
export type ConversationResponse = components['schemas']['ConversationResponse'];

// =============================================================================
// Recommendations
// =============================================================================

/** チームメンバー (Backend: TeamMember) */
export type TeamMember = components['schemas']['TeamMember'];

/** レコメンデーションアイテム (Backend: RecommendationItem) */
export type RecommendationItem = components['schemas']['RecommendationItem'];

/** レコメンデーションレスポンス (Backend: RecommendationResponse) */
export type RecommendationResponse = components['schemas']['RecommendationResponse'];

// =============================================================================
// Projects (Flash Team)
// Backend の Pydantic モデルが schema.d.ts に未反映のため暫定的に手動定義
// =============================================================================

export interface ProjectResponse {
  id: string;
  name: string;
  description: string | null;
  status: string;
  created_by: string;
  recommendation_id: string | null;
  team_members: TeamMember[];
  topics: string[];
  reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectListItem {
  id: string;
  name: string;
  status: string;
  topics: string[];
  member_count: number;
  created_at: string;
}

export interface ProjectCreateRequest {
  name: string;
  description?: string;
  recommendation_id?: string;
  team_members: TeamMember[];
  topics: string[];
  reason?: string;
}
