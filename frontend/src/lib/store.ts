/**
 * MINDYARD - Zustand Store
 * グローバル状態管理
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, RecommendationItem, RawLog } from '@/types';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  setUser: (user: User | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      logout: () => set({ user: null, isAuthenticated: false }),
    }),
    {
      name: 'mindyard-auth',
    }
  )
);

interface RecommendationState {
  recommendations: RecommendationItem[];
  isVisible: boolean;
  displayMessage: string | null;
  setRecommendations: (items: RecommendationItem[], message: string | null) => void;
  clearRecommendations: () => void;
  hideRecommendations: () => void;
}

export const useRecommendationStore = create<RecommendationState>()((set) => ({
  recommendations: [],
  isVisible: false,
  displayMessage: null,
  setRecommendations: (items, message) =>
    set({
      recommendations: items,
      isVisible: items.length > 0,
      displayMessage: message,
    }),
  clearRecommendations: () =>
    set({
      recommendations: [],
      isVisible: false,
      displayMessage: null,
    }),
  hideRecommendations: () => set({ isVisible: false }),
}));

interface NotificationState {
  pendingProposalCount: number;
  setPendingProposalCount: (count: number) => void;
}

export const useNotificationStore = create<NotificationState>()((set) => ({
  pendingProposalCount: 0,
  setPendingProposalCount: (count) => set({ pendingProposalCount: count }),
}));

// ────────────────────────────────────────
// 会話メッセージ（ThoughtStream 用）
// 画面遷移しても消えないように persist で localStorage に永続化
// ────────────────────────────────────────

/** チャット表示用のメッセージ（localStorage にシリアライズ可能な形） */
export interface ChatMessage {
  id: string;
  type: 'user' | 'system' | 'assistant' | 'ai-question';
  content: string;
  timestamp: string; // ISO 8601 string
  logId?: string;
  relationshipType?: string;
  structuralAnalysis?: {
    relationship_type: string;
    relationship_reason: string;
    updated_structural_issue: string;
    probing_question: string;
    model_info?: { tier: string; model: string; is_reasoning: boolean };
  };
  isVoiceInput?: boolean;
}

/** RawLog → ChatMessage[] 変換（バックエンドのログを会話メッセージに復元） */
export function rawLogToMessages(log: RawLog): ChatMessage[] {
  const msgs: ChatMessage[] = [];

  // 1. ユーザーの発言
  msgs.push({
    id: `user-${log.id}`,
    type: 'user',
    content: log.content,
    timestamp: log.created_at,
    logId: log.id,
    isVoiceInput: log.content_type === 'voice',
  });

  // 2. アシスタントの返答 or 相槌
  msgs.push({
    id: `ack-${log.id}`,
    type: log.assistant_reply ? 'assistant' : 'system',
    content: log.assistant_reply || '受け取りました。',
    timestamp: log.created_at,
    logId: log.id,
  });

  // 3. 構造分析の深掘り問い（あれば）
  if (log.structural_analysis?.probing_question) {
    msgs.push({
      id: `ai-${log.id}`,
      type: 'ai-question',
      content: log.structural_analysis.probing_question,
      timestamp: log.updated_at,
      logId: log.id,
      relationshipType: log.structural_analysis.relationship_type,
      structuralAnalysis: log.structural_analysis ?? undefined,
    });
  }

  return msgs;
}

interface ConversationState {
  /** 現在表示中のメッセージ一覧 */
  messages: ChatMessage[];
  /** 続きで送るときの thread_id */
  continuingThreadId: string | null;
  /** バックエンドから履歴をロード済みか */
  isHistoryLoaded: boolean;

  addMessage: (message: ChatMessage) => void;
  addMessages: (messages: ChatMessage[]) => void;
  setMessages: (messages: ChatMessage[]) => void;
  setContinuingThreadId: (id: string | null) => void;
  setHistoryLoaded: (loaded: boolean) => void;
  clearConversation: () => void;
}

export const useConversationStore = create<ConversationState>()(
  persist(
    (set) => ({
      messages: [],
      continuingThreadId: null,
      isHistoryLoaded: false,

      addMessage: (message) =>
        set((state) => ({ messages: [...state.messages, message] })),

      addMessages: (messages) =>
        set((state) => ({ messages: [...state.messages, ...messages] })),

      setMessages: (messages) => set({ messages }),

      setContinuingThreadId: (id) => set({ continuingThreadId: id }),

      setHistoryLoaded: (loaded) => set({ isHistoryLoaded: loaded }),

      clearConversation: () =>
        set({ messages: [], continuingThreadId: null, isHistoryLoaded: false }),
    }),
    {
      name: 'mindyard-conversation',
    }
  )
);
