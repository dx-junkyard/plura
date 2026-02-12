'use client';

/**
 * MINDYARD - ThoughtStream Component
 * Layer 1: チャット形式の入力UI（ノン・ジャッジメンタル応答）
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import TextareaAutosize from 'react-textarea-autosize';
import Link from 'next/link';
import { Send, Mic, MicOff, Loader2, ChevronDown, ChevronUp, Copy, Check, Lightbulb, MessageSquarePlus, Search } from 'lucide-react';
import { api } from '@/lib/api';
import { useRecommendationStore, useConversationStore, rawLogToMessages } from '@/lib/store';
import type { ChatMessage } from '@/lib/store';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { AckResponse, RawLog, ResearchPlan } from '@/types';

// 整理プロセスのステップ定義
interface AnalysisStep {
  id: string;
  label: string;
  status: 'pending' | 'in_progress' | 'completed';
}

interface ThoughtStreamProps {
  selectedLogId?: string | null;
  onClearSelection?: () => void;
}

export function ThoughtStream({ selectedLogId, onClearSelection }: ThoughtStreamProps) {
  const [input, setInput] = useState('');

  // ── 会話メッセージ & スレッド管理は Zustand ストア（localStorage 永続化） ──
  const {
    messages,
    continuingThreadId,
    isHistoryLoaded,
    addMessage,
    addMessages,
    setMessages,
    setContinuingThreadId,
    setHistoryLoaded,
    clearConversation,
  } = useConversationStore();

  const [isLoadingLog, setIsLoadingLog] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [pendingLogIds, setPendingLogIds] = useState<string[]>([]);
  const [recordingError, setRecordingError] = useState<string | null>(null);
  const [analysisSteps, setAnalysisSteps] = useState<AnalysisStep[]>([]);
  const [isAnalysisExpanded, setIsAnalysisExpanded] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [isResearching, setIsResearching] = useState(false);
  const [researchLogId, setResearchLogId] = useState<string | null>(null);
  const researchPollingRef = useRef<NodeJS.Timeout>();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const debounceRef = useRef<NodeJS.Timeout>();
  const pollingRef = useRef<NodeJS.Timeout>();
  const isPollingRef = useRef(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const { setRecommendations, clearRecommendations } = useRecommendationStore();

  // 分析待ちのログがあるかどうか（UIの表示制御用）
  const isWaitingForAnalysis = pendingLogIds.length > 0;

  // ── 初回マウント: バックエンドから会話履歴をロード（ストアが空のとき） ──
  useEffect(() => {
    if (isHistoryLoaded || messages.length > 0) return;

    let cancelled = false;
    const loadHistory = async () => {
      try {
        const data = await api.getLogs(1, 50);
        if (cancelled || data.items.length === 0) {
          setHistoryLoaded(true);
          return;
        }

        // 古い順にソート → メッセージに変換
        const sorted = [...data.items].sort(
          (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        );
        const restored: ChatMessage[] = [];
        for (const log of sorted) {
          restored.push(...rawLogToMessages(log));
        }
        if (!cancelled) {
          setMessages(restored);
          // 最新ログのスレッドを continuingThreadId にセット
          const latest = data.items[0]; // getLogs は created_at desc
          setContinuingThreadId(latest.thread_id ?? latest.id);
          setHistoryLoaded(true);
        }
      } catch (e) {
        console.error('Failed to load conversation history:', e);
        if (!cancelled) setHistoryLoaded(true);
      }
    };
    loadHistory();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // タイムラインで選択されたログを読み込み、そのスレッド全体をチャットに展開する
  useEffect(() => {
    if (!selectedLogId) return;

    const loadThreadLogs = async () => {
      setIsLoadingLog(true);
      try {
        const log: RawLog = await api.getLog(selectedLogId);
        const threadId = log.thread_id ?? log.id;

        // スレッドに属する全ログを取得（getLogs から thread_id でフィルタ）
        const allData = await api.getLogs(1, 100);
        const threadLogs = allData.items
          .filter((l) => (l.thread_id ?? l.id) === threadId)
          .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());

        const thread: ChatMessage[] = [];
        for (const tl of threadLogs) {
          thread.push(...rawLogToMessages(tl));
        }

        setMessages(thread);
        setContinuingThreadId(threadId);
      } catch (e) {
        console.error('Failed to load log for continue:', e);
        setContinuingThreadId(null);
      } finally {
        setIsLoadingLog(false);
      }
    };

    loadThreadLogs();
  }, [selectedLogId]); // eslint-disable-line react-hooks/exhaustive-deps

  // 選択が外れたらスレッド id をクリア（メッセージはそのまま残す）
  useEffect(() => {
    if (!selectedLogId) setContinuingThreadId(null);
  }, [selectedLogId]); // eslint-disable-line react-hooks/exhaustive-deps

  // メッセージ追加時にスクロール
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 整理プロセス開始時にステップを初期化
  const initializeAnalysisSteps = useCallback(() => {
    setAnalysisSteps([
      { id: 'receive', label: '入力を受け取りました', status: 'completed' },
      { id: 'context', label: '文脈を分析中... (Fast)', status: 'in_progress' },
      { id: 'structure', label: '深い思考で構造を分析中... (Deep)', status: 'pending' },
      { id: 'question', label: '深掘りの問いを生成中...', status: 'pending' },
    ]);
    setIsAnalysisExpanded(true);
  }, []);

  // 構造分析結果のポーリング（複数ログ対応）
  useEffect(() => {
    if (pendingLogIds.length === 0) return;

    const pollForAnalysis = async () => {
      // 同時実行を防止
      if (isPollingRef.current) return;
      isPollingRef.current = true;

      try {
        const completedIds: string[] = [];
        const newMessages: ChatMessage[] = [];
        const latestPendingId = pendingLogIds[pendingLogIds.length - 1];

        for (const logId of pendingLogIds) {
          try {
            const log: RawLog = await api.getLog(logId);

            // 最新のログに対してはステップ表示を更新
            if (logId === latestPendingId) {
              if (log.is_analyzed && !log.is_structure_analyzed) {
                setAnalysisSteps((prev) =>
                  prev.map((step) => {
                    if (step.id === 'context') return { ...step, label: '文脈を分析しました (Fast)', status: 'completed' };
                    if (step.id === 'structure') return { ...step, label: '深い思考で構造を分析中... (Deep)', status: 'in_progress' };
                    return step;
                  })
                );
              }
            }

            if (log.is_structure_analyzed && log.structural_analysis?.probing_question) {
              completedIds.push(logId);

              // 最新のログのステップ表示を完了に
              if (logId === latestPendingId) {
                const modelInfo = log.structural_analysis.model_info;
                const isReasoning = modelInfo?.is_reasoning;

                setAnalysisSteps((prev) =>
                  prev.map((step) => ({
                    ...step,
                    status: 'completed',
                    label: step.id === 'context' ? '文脈を分析しました (Fast)' :
                           step.id === 'structure' ? `構造を深く分析しました${isReasoning ? ' (Reasoning)' : ' (Deep)'}` :
                           step.id === 'question' ? '深掘りの問いを生成しました' : step.label,
                  }))
                );
              }

              // 分析完了 - AIの問いかけをメッセージに追加
              const aiMessage: ChatMessage = {
                id: `ai-${log.id}`,
                type: 'ai-question',
                content: log.structural_analysis.probing_question,
                timestamp: new Date().toISOString(),
                logId: log.id,
                relationshipType: log.structural_analysis.relationship_type,
                structuralAnalysis: log.structural_analysis,
              };
              newMessages.push(aiMessage);
            }
          } catch (error: any) {
            console.error('Polling error:', error);
            // 404 Not Found の場合はポーリング対象から除外
            if (error.response && error.response.status === 404) {
              completedIds.push(logId);
            }
          }
        }

        if (newMessages.length > 0) {
          addMessages(newMessages);
        }

        if (completedIds.length > 0) {
          setPendingLogIds((prev) => {
            const filtered = prev.filter((id) => !completedIds.includes(id));
            return filtered.length === prev.length ? prev : filtered;
          });
        }
      } finally {
        isPollingRef.current = false;
      }
    };

    // 初回実行
    pollForAnalysis();

    // 3秒おきにポーリング
    pollingRef.current = setInterval(pollForAnalysis, 3000);

    // クリーンアップ
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, [pendingLogIds]);

  // 入力変更時にレコメンデーションを取得
  const fetchRecommendations = useCallback(async (text: string) => {
    if (text.length < 20) {
      clearRecommendations();
      return;
    }

    try {
      const result = await api.getRecommendations(text);
      if (result.has_recommendations) {
        setRecommendations(result.recommendations, result.display_message);
      } else {
        clearRecommendations();
      }
    } catch (error) {
      // エラーは無視（レコメンデーションは副次的機能）
    }
  }, [setRecommendations, clearRecommendations]);

  // デバウンス付き入力変更ハンドラ
  const handleInputChange = useCallback((value: string) => {
    setInput(value);

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    debounceRef.current = setTimeout(() => {
      fetchRecommendations(value);
    }, 500);
  }, [fetchRecommendations]);

  // 送信ハンドラ
  const handleSubmit = async () => {
    if (!input.trim() || isSubmitting) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: input.trim(),
      timestamp: new Date().toISOString(),
    };

    addMessage(userMessage);
    setInput('');
    setIsSubmitting(true);
    clearRecommendations();

    try {
      const response: AckResponse = await api.createLog(
        input.trim(),
        'text',
        continuingThreadId ?? undefined
      );

      const replyContent = response.conversation_reply || response.message;
      const replyType: ChatMessage['type'] = response.conversation_reply ? 'assistant' : 'system';
      const replyMessage: ChatMessage = {
        id: response.log_id,
        type: replyType,
        content: replyContent,
        timestamp: new Date().toISOString(),
        logId: response.log_id,
        requiresResearchConsent: response.requires_research_consent,
      };

      addMessage(replyMessage);

      if (!response.skip_structural_analysis) {
        // 構造分析のポーリングを開始
        setPendingLogIds(prev => [...prev, response.log_id]);
        initializeAnalysisSteps();
      }
    } catch (error) {
      const errorMessage: ChatMessage = {
        id: Date.now().toString(),
        type: 'system',
        content: '保存に失敗しました。もう一度お試しください。',
        timestamp: new Date().toISOString(),
      };
      addMessage(errorMessage);
    } finally {
      setIsSubmitting(false);
      inputRef.current?.focus();
    }
  };

  // 整理結果を共有用テキストとしてコピー
  const copyAnalysisResult = useCallback(async (message: ChatMessage) => {
    if (!message.structuralAnalysis) return;

    const { relationship_type, updated_structural_issue, probing_question } = message.structuralAnalysis;

    const relationshipLabel = {
      ADDITIVE: '深化',
      PARALLEL: '並列',
      CORRECTION: '訂正',
      NEW: '新規',
    }[relationship_type] || relationship_type;

    const shareText = `【思考の整理結果】

📌 構造的な課題:
${updated_structural_issue}

💭 深掘りの問い:
${probing_question}

🔗 関係性: ${relationshipLabel}

---
MINDYARD で思考を整理しました`;

    try {
      await navigator.clipboard.writeText(shareText);
      setCopiedMessageId(message.id);
      setTimeout(() => setCopiedMessageId(null), 2000);
    } catch (error) {
      console.error('コピーに失敗しました:', error);
    }
  }, []);

  // Deep Research ポーリング: result_log_id の assistant_reply を監視
  useEffect(() => {
    if (!researchLogId) return;

    const pollForResearchResult = async () => {
      try {
        const log = await api.getLog(researchLogId);
        if (log.assistant_reply) {
          // 結果が到着 — 「調査中...」を除去して結果を表示
          const resultMessage: ChatMessage = {
            id: `research-result-${researchLogId}`,
            type: 'assistant',
            content: log.assistant_reply,
            timestamp: new Date().toISOString(),
          };
          const currentMsgs = useConversationStore.getState().messages;
          setMessages([
            ...currentMsgs.filter((m) => !m.id.startsWith('researching-')),
            resultMessage,
          ]);
          setIsResearching(false);
          setResearchLogId(null);
        }
      } catch {
        // 404 等は無視（ログがまだ作成されていない）
      }
    };

    // 初回実行
    pollForResearchResult();
    // 3秒間隔でポーリング
    researchPollingRef.current = setInterval(pollForResearchResult, 3000);

    return () => {
      if (researchPollingRef.current) {
        clearInterval(researchPollingRef.current);
      }
    };
  }, [researchLogId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Deep Research Step 1: 「提案」— 調査計画書を生成させる
  const handleDeepResearch = useCallback(async (message: ChatMessage) => {
    if (isResearching) return;

    // 「計画を作成中...」メッセージを表示
    const preparingMessage: ChatMessage = {
      id: `researching-${Date.now()}`,
      type: 'system',
      content: '調査計画を作成しています...',
      timestamp: new Date().toISOString(),
    };
    addMessage(preparingMessage);

    try {
      const userMsg = messages.find(
        (m) => m.logId === message.logId && m.type === 'user'
      );
      const queryText = userMsg?.content || message.content;

      const result = await api.converse(queryText, {
        researchApproved: true,
        threadId: continuingThreadId ?? undefined,
      });

      // 調査計画書が返ってきた場合 → 確認カードとして表示
      const planMessage: ChatMessage = {
        id: `research-plan-${Date.now()}`,
        type: 'assistant',
        content: result.response,
        timestamp: new Date().toISOString(),
        researchPlan: result.research_plan ?? undefined,
      };
      const currentMsgs = useConversationStore.getState().messages;
      setMessages([
        ...currentMsgs.filter((m) => !m.id.startsWith('researching-')),
        planMessage,
      ]);
    } catch (error) {
      console.error('調査計画の作成に失敗:', error);
      const errorMsg: ChatMessage = {
        id: `research-error-${Date.now()}`,
        type: 'system',
        content: '調査計画の作成に失敗しました。もう一度お試しください。',
        timestamp: new Date().toISOString(),
      };
      const currentMsgs = useConversationStore.getState().messages;
      setMessages([
        ...currentMsgs.filter((m) => !m.id.startsWith('researching-')),
        errorMsg,
      ]);
    }
  }, [isResearching, messages, addMessage, setMessages, continuingThreadId]);

  // Deep Research Step 2: 「確認」— 調査計画を確定して実行を開始
  const handleConfirmResearchPlan = useCallback(async (plan: ResearchPlan, planMessageId: string) => {
    if (isResearching) return;

    setIsResearching(true);

    // 計画カードのボタンを消して「実行中...」メッセージに差し替え
    const executingMessage: ChatMessage = {
      id: `researching-${Date.now()}`,
      type: 'system',
      content: `「${plan.title}」の調査を開始しました...`,
      timestamp: new Date().toISOString(),
    };

    // 元の計画メッセージから researchPlan を消す（ボタンを非表示に）
    const currentMsgs = useConversationStore.getState().messages;
    const updatedMsgs = currentMsgs.map((m) =>
      m.id === planMessageId ? { ...m, researchPlan: undefined } : m
    );
    setMessages([...updatedMsgs, executingMessage]);

    try {
      const result = await api.converse(plan.sanitized_query, {
        researchPlanConfirmed: true,
        researchPlan: plan,
        threadId: continuingThreadId ?? undefined,
      });

      // バックグラウンドタスクの result_log_id でポーリング開始
      if (result.background_task?.result_log_id) {
        setResearchLogId(result.background_task.result_log_id);
      }

      // 即時レスポンスを表示
      const ackMessage: ChatMessage = {
        id: `research-ack-${Date.now()}`,
        type: 'system',
        content: result.response,
        timestamp: new Date().toISOString(),
      };
      const msgs = useConversationStore.getState().messages;
      setMessages([
        ...msgs.filter((m) => !m.id.startsWith('researching-')),
        ackMessage,
      ]);
    } catch (error) {
      console.error('Deep Research 実行エラー:', error);
      const errorMsg: ChatMessage = {
        id: `research-error-${Date.now()}`,
        type: 'system',
        content: 'Deep Research の実行に失敗しました。もう一度お試しください。',
        timestamp: new Date().toISOString(),
      };
      const msgs = useConversationStore.getState().messages;
      setMessages([
        ...msgs.filter((m) => !m.id.startsWith('researching-')),
        errorMsg,
      ]);
      setIsResearching(false);
    }
  }, [isResearching, setMessages, continuingThreadId]);

  // キーボードショートカット
  const handleKeyDown = (e: React.KeyboardEvent) => {
    // IME変換中（日本語入力中）は送信しない
    if (e.nativeEvent.isComposing) {
      return;
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // 音声入力（Whisper API使用）
  const toggleRecording = async () => {
    setRecordingError(null);

    if (isRecording) {
      // 録音停止
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      setIsRecording(false);
    } else {
      // 録音開始
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        // WebM形式を優先、非対応ならMP4
        const mimeType = MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : MediaRecorder.isTypeSupported('audio/mp4')
          ? 'audio/mp4'
          : 'audio/ogg';

        const mediaRecorder = new MediaRecorder(stream, { mimeType });
        mediaRecorderRef.current = mediaRecorder;
        audioChunksRef.current = [];

        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            audioChunksRef.current.push(event.data);
          }
        };

        mediaRecorder.onstop = async () => {
          // ストリームを停止
          stream.getTracks().forEach((track) => track.stop());

          if (audioChunksRef.current.length === 0) {
            setRecordingError('録音データがありません');
            return;
          }

          // 音声Blobを作成
          const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });

          // 送信処理
          await sendAudioToServer(audioBlob);
        };

        mediaRecorder.start();
        setIsRecording(true);
      } catch (error) {
        console.error('録音開始エラー:', error);
        if (error instanceof DOMException && error.name === 'NotAllowedError') {
          setRecordingError('マイクへのアクセスが許可されていません。ブラウザの設定を確認してください。');
        } else {
          setRecordingError('録音の開始に失敗しました。');
        }
      }
    }
  };

  // 音声をサーバーに送信
  const sendAudioToServer = async (audioBlob: Blob) => {
    setIsTranscribing(true);

    // 「音声を送信中」のシステムメッセージを表示
    const transcribingMessage: ChatMessage = {
      id: `transcribing-${Date.now()}`,
      type: 'system',
      content: '🎤 音声を解析中...',
      timestamp: new Date().toISOString(),
    };
    addMessage(transcribingMessage);

    try {
      const response: AckResponse = await api.transcribeAudio(audioBlob);

      // 「解析中」メッセージを削除し、結果を表示
      const userMsg: ChatMessage = {
        id: `voice-${response.log_id}`,
        type: 'user',
        content: response.transcribed_text || '(音声入力)',
        timestamp: response.timestamp,
        logId: response.log_id,
        isVoiceInput: true,
      };

      const replyContent = response.conversation_reply || response.message;
      const replyType: ChatMessage['type'] = response.conversation_reply ? 'assistant' : 'system';
      const replyMsg: ChatMessage = {
        id: response.log_id,
        type: replyType,
        content: replyContent,
        timestamp: response.timestamp,
        logId: response.log_id,
      };

      // transcribing メッセージを除いてから結果を追加
      setMessages([
        ...messages.filter((m) => !m.id.startsWith('transcribing-')),
        userMsg,
        replyMsg,
      ]);

      if (!response.skip_structural_analysis) {
        // 構造分析のポーリングを開始
        setPendingLogIds(prev => [...prev, response.log_id]);
        initializeAnalysisSteps();
      }
    } catch (error) {
      console.error('音声送信エラー:', error);

      // エラーメッセージを表示
      const errorMsg: ChatMessage = {
        id: Date.now().toString(),
        type: 'system',
        content: '音声の処理に失敗しました。もう一度お試しください。',
        timestamp: new Date().toISOString(),
      };
      setMessages([
        ...messages.filter((m) => !m.id.startsWith('transcribing-')),
        errorMsg,
      ]);
    } finally {
      setIsTranscribing(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* メッセージエリア */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {selectedLogId && (
          <div className="flex items-center justify-between gap-2 py-2 px-3 rounded-lg bg-primary-50 border border-primary-100 text-sm text-primary-800">
            <span>この会話の続きを話せます</span>
            <button
              type="button"
              onClick={() => {
                clearConversation();
                onClearSelection?.();
              }}
              className="flex items-center gap-1.5 px-2 py-1 rounded-md hover:bg-primary-100 text-primary-700 font-medium transition-colors"
            >
              <MessageSquarePlus className="w-4 h-4" />
              新しい会話を始める
            </button>
          </div>
        )}

        {isLoadingLog && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
          </div>
        )}

        {!isLoadingLog && messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 px-4">
            <p className="text-lg font-medium mb-2">何でも話しかけてみてください</p>
            <p className="text-sm text-center mb-4">聞き上手なAIが相手です。思いついたことを自由に。</p>
            <p className="text-xs text-center text-gray-400 max-w-sm">
              浮かび上がった課題と解決の方向性は、一般化されて
              <Link href="/insights" className="text-primary-500 hover:text-primary-600 inline-flex items-center gap-0.5 mx-0.5">
                <Lightbulb className="w-3.5 h-3.5" /> みんなの知恵
              </Link>
              に共有できる形で整理されます。
            </p>
          </div>
        )}

        {!isLoadingLog && messages.map((message) => (
          <div
            key={message.id}
            className={cn(
              'rounded-lg p-3',
              message.type === 'user'
                ? 'ml-auto max-w-[80%] bg-private-100 text-gray-800'
                : message.type === 'assistant'
                ? 'mr-auto max-w-[80%] bg-emerald-50 border border-emerald-100 text-gray-800'
                : message.type === 'ai-question'
                ? 'mr-auto max-w-[85%] bg-gray-50 border border-gray-200 text-gray-500 text-sm'
                : 'mr-auto max-w-[80%] bg-gray-100 text-gray-600'
            )}
          >
            {message.type === 'user' && message.isVoiceInput && (
              <span className="text-xs text-private-500 font-medium mb-1 flex items-center gap-1">
                <Mic className="w-3 h-3" /> 音声入力
              </span>
            )}
            {message.type === 'ai-question' && (
              <div className="flex items-start justify-between mb-1">
                <span className="text-xs text-gray-400 font-medium">
                  思考の整理
                </span>
                {message.structuralAnalysis && (
                  <button
                    onClick={() => copyAnalysisResult(message)}
                    className="text-gray-400 hover:text-gray-600 transition-colors p-1 -m-1"
                    title="整理結果をコピー"
                  >
                    {copiedMessageId === message.id ? (
                      <Check className="w-3.5 h-3.5 text-green-500" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                )}
              </div>
            )}
            <p className="whitespace-pre-wrap">{message.content}</p>
            {message.type === 'assistant' && message.requiresResearchConsent && !isResearching && !message.researchPlan && (
              <button
                onClick={() => handleDeepResearch(message)}
                className="mt-3 flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-500 text-white text-sm font-medium hover:bg-indigo-600 transition-colors shadow-sm"
              >
                <Search className="w-4 h-4" />
                Deep Research を実行する
              </button>
            )}
            {message.type === 'assistant' && message.researchPlan && !isResearching && (
              <div className="mt-3 p-4 rounded-lg bg-indigo-50 border border-indigo-200">
                <div className="flex items-center gap-2 mb-3">
                  <Search className="w-4 h-4 text-indigo-600" />
                  <span className="text-sm font-semibold text-indigo-800">調査計画書</span>
                </div>
                <h4 className="text-sm font-bold text-gray-800 mb-2">{message.researchPlan.title}</h4>
                <dl className="space-y-1.5 text-sm text-gray-700 mb-3">
                  <div>
                    <dt className="text-xs font-medium text-gray-500">トピック</dt>
                    <dd>{message.researchPlan.topic}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-gray-500">調査範囲</dt>
                    <dd>{message.researchPlan.scope}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-gray-500">視点</dt>
                    <dd>
                      <ul className="list-disc list-inside">
                        {message.researchPlan.perspectives.map((p, i) => (
                          <li key={i}>{p}</li>
                        ))}
                      </ul>
                    </dd>
                  </div>
                </dl>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => handleConfirmResearchPlan(message.researchPlan!, message.id)}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-500 text-white text-sm font-medium hover:bg-indigo-600 transition-colors shadow-sm"
                  >
                    <Search className="w-4 h-4" />
                    この内容で調査開始
                  </button>
                  <span className="text-xs text-gray-500">
                    条件を変更したい場合はチャットで指示してください
                  </span>
                </div>
              </div>
            )}
            {message.type === 'ai-question' && message.structuralAnalysis && (
              <details className="mt-2 pt-2 border-t border-gray-200">
                <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-500">
                  詳細を見る
                </summary>
                <div className="mt-2 space-y-1">
                  <p className="text-xs text-gray-500">
                    <span className="font-medium">課題:</span> {message.structuralAnalysis.updated_structural_issue}
                  </p>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    <span className="inline-block text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
                      {message.structuralAnalysis.relationship_type === 'ADDITIVE' && '深化'}
                      {message.structuralAnalysis.relationship_type === 'PARALLEL' && '並列'}
                      {message.structuralAnalysis.relationship_type === 'CORRECTION' && '訂正'}
                      {message.structuralAnalysis.relationship_type === 'NEW' && '新規'}
                    </span>
                  </div>
                </div>
              </details>
            )}
            <span className="text-xs text-gray-400 mt-1 block">
              {formatRelativeTime(message.timestamp)}
            </span>
          </div>
        ))}

        {isSubmitting && (
          <div className="mr-auto bg-gray-100 rounded-lg p-3 flex items-center gap-2 text-gray-500">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>受け取っています...</span>
          </div>
        )}

        {isResearching && (
          <div className="mr-auto bg-indigo-50 border border-indigo-100 rounded-lg p-3 flex items-center gap-2 text-indigo-600">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>Deep Research を実行中...</span>
          </div>
        )}

        {isWaitingForAnalysis && !isSubmitting && (
          <div className="mr-auto bg-blue-50 border border-blue-100 rounded-lg p-3 max-w-[80%]">
            <button
              onClick={() => setIsAnalysisExpanded(!isAnalysisExpanded)}
              className="flex items-center gap-2 text-blue-600 w-full"
            >
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="flex-1 text-left">考えを整理しています...</span>
              {isAnalysisExpanded ? (
                <ChevronUp className="w-4 h-4" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
            </button>
            {isAnalysisExpanded && analysisSteps.length > 0 && (
              <div className="mt-3 pt-3 border-t border-blue-100 space-y-2">
                {analysisSteps.map((step) => (
                  <div key={step.id} className="flex items-center gap-2 text-sm">
                    {step.status === 'completed' ? (
                      <Check className="w-4 h-4 text-green-500" />
                    ) : step.status === 'in_progress' ? (
                      <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
                    ) : (
                      <div className="w-4 h-4 rounded-full border-2 border-gray-300" />
                    )}
                    <span
                      className={cn(
                        step.status === 'completed' ? 'text-green-600' :
                        step.status === 'in_progress' ? 'text-blue-600' :
                        'text-gray-400'
                      )}
                    >
                      {step.label}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 入力エリア */}
      <div className="border-t border-gray-200 p-4 bg-white">
        {/* タイムラインから続けているとき: 新しいチャットに切り替えるボタン（常に見える位置） */}
        {selectedLogId && (
          <div className="mb-3 flex items-center justify-between gap-2 py-2 px-3 rounded-lg bg-primary-50 border border-primary-100">
            <span className="text-sm text-primary-800">この会話の続き</span>
            <button
              type="button"
              onClick={() => {
                clearConversation();
                onClearSelection?.();
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary-300 bg-white text-primary-700 text-sm font-medium hover:bg-primary-50 transition-colors shadow-sm"
            >
              <MessageSquarePlus className="w-4 h-4" />
              新しいチャットを始める
            </button>
          </div>
        )}

        {/* 録音エラー表示 */}
        {recordingError && (
          <div className="mb-3 p-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
            {recordingError}
          </div>
        )}

        <div className="flex items-end gap-2">
          <button
            onClick={toggleRecording}
            disabled={isTranscribing || isSubmitting}
            className={cn(
              'p-2 rounded-full transition-all relative',
              isRecording
                ? 'bg-red-500 text-white animate-pulse'
                : isTranscribing
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            )}
            title={isRecording ? '録音停止' : isTranscribing ? '解析中...' : '音声入力'}
          >
            {isTranscribing ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : isRecording ? (
              <MicOff className="w-5 h-5" />
            ) : (
              <Mic className="w-5 h-5" />
            )}
            {/* 録音中インジケーター */}
            {isRecording && (
              <span className="absolute -top-1 -right-1 w-3 h-3 bg-red-600 rounded-full animate-ping" />
            )}
          </button>

          <div className="flex-1 relative">
            <TextareaAutosize
              ref={inputRef}
              value={input}
              onChange={(e) => handleInputChange(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isRecording ? '🎤 録音中... ボタンを押して停止' : '今、何を考えていますか？'}
              disabled={isRecording || isTranscribing}
              className={cn(
                'w-full resize-none rounded-lg border px-4 py-3 pr-12 outline-none',
                isRecording || isTranscribing
                  ? 'border-gray-300 bg-gray-50 text-gray-400 cursor-not-allowed'
                  : 'border-gray-200 focus:border-private-400 focus:ring-1 focus:ring-private-400'
              )}
              minRows={1}
              maxRows={6}
            />
            <button
              onClick={handleSubmit}
              disabled={!input.trim() || isSubmitting || isRecording || isTranscribing}
              className={cn(
                'absolute right-2 bottom-2 p-2 rounded-full transition-colors',
                input.trim() && !isSubmitting && !isRecording && !isTranscribing
                  ? 'bg-private-500 text-white hover:bg-private-600'
                  : 'bg-gray-100 text-gray-400 cursor-not-allowed'
              )}
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>

        <p className="text-xs text-gray-400 mt-2 text-center">
          {isRecording
            ? '🔴 録音中 - マイクボタンを押して停止'
            : 'Shift + Enter で改行 / Enter で送信 / マイクで音声入力'}
        </p>
      </div>
    </div>
  );
}
