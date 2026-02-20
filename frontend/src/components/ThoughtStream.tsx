'use client';

/**
 * PLURA - ThoughtStream Component
 * Layer 1: チャット形式の入力UI（ノン・ジャッジメンタル応答）
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import TextareaAutosize from 'react-textarea-autosize';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import { useRouter } from 'next/navigation';
import { Send, Mic, MicOff, Loader2, ChevronDown, ChevronUp, Copy, Check, Lightbulb, MessageSquarePlus, Search, ThumbsUp, ThumbsDown, FileText, ExternalLink } from 'lucide-react';
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
  const router = useRouter();
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
  const [expandedAnalysisIds, setExpandedAnalysisIds] = useState<Set<string>>(new Set());
  // トーンフィードバック: メッセージIDごとに "gentler" | "sharper" | null
  const [toneFeedback, setToneFeedback] = useState<Record<string, 'gentler' | 'sharper'>>({});
  // Deep Research state
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
  const prevSelectedLogIdRef = useRef<string | null | undefined>(undefined);

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

  // タイムラインでログ選択 → 選択解除 の遷移時のみスレッド id をクリア
  // （初回マウントや通常会話中の null→null 遷移ではクリアしない）
  useEffect(() => {
    const prev = prevSelectedLogIdRef.current;
    prevSelectedLogIdRef.current = selectedLogId;

    // 前回が truthy → 今回が falsy のときだけクリア（タイムラインで選択→解除）
    if (prev && !selectedLogId) {
      setContinuingThreadId(null);
    }
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

            // STATE インテントは構造分析がスキップされるため、
            // is_analyzed が完了した時点でポーリング終了
            const isStateLog = log.intent === 'state';
            const structureComplete = log.is_structure_analyzed || isStateLog;

            if (structureComplete) {
              completedIds.push(logId);

              if (log.structural_analysis?.probing_question) {
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
              } else if (isStateLog && logId === latestPendingId) {
                // STATE ログは構造分析不要 → ステップ表示を即完了
                setAnalysisSteps((prev) =>
                  prev.map((step) => ({
                    ...step,
                    status: 'completed',
                    label: step.id === 'context' ? '文脈を分析しました (Fast)' :
                           step.id === 'structure' ? '状態記録（構造分析スキップ）' :
                           step.id === 'question' ? '完了' : step.label,
                  }))
                );
              }
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

    // 2分後にタイムアウト: まだ pendingLogIds が残っていたら強制クリア
    const timeout = setTimeout(() => {
      setPendingLogIds((prev) => {
        if (prev.length > 0) {
          console.warn('Analysis polling timeout: clearing pending log IDs', prev);
          setAnalysisSteps((steps) =>
            steps.map((step) => ({
              ...step,
              status: step.status === 'in_progress' ? 'completed' : step.status,
            }))
          );
          return [];
        }
        return prev;
      });
    }, 120_000);

    // クリーンアップ
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
      clearTimeout(timeout);
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
        setRecommendations(result.recommendations, result.display_message ?? null);
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
    const submittedText = input.trim();

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: submittedText,
      timestamp: new Date().toISOString(),
    };

    addMessage(userMessage);
    setInput('');
    setIsSubmitting(true);

    try {
      const response: AckResponse = await api.createLog(
        submittedText,
        'text',
        continuingThreadId ?? undefined
      );
      await fetchRecommendations(submittedText);

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

      // スレッドを継続するために thread_id を保存
      setContinuingThreadId(response.thread_id);

      if (response.research_log_id) {
        // Deep Research が開始された — ポーリングを開始
        setResearchLogId(response.research_log_id);
        setIsResearching(true);
      } else if (!response.skip_structural_analysis) {
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

    const shareText = `【課題の深掘り】

📌 構造的な課題:
${updated_structural_issue}

💭 深掘りの問い:
${probing_question}

🔗 関係性: ${relationshipLabel}

---
PLURA で思考を整理しました`;

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

        // Deep Research の完了判定:
        // 1. metadata_analysis.deep_research が存在する
        // 2. assistant_reply が空でなく、受付プレースホルダーでもない
        const hasDeepResearchMeta = log.metadata_analysis?.deep_research != null;
        const hasRealReply =
          log.assistant_reply != null &&
          log.assistant_reply.trim() !== '' &&
          !log.assistant_reply.startsWith('Deep Researchのリクエストを受け付けました');

        if (hasDeepResearchMeta || hasRealReply) {
          // 結果が到着 — 「調査中...」を除去して結果を表示
          const completionNotice: ChatMessage = {
            id: `research-complete-${researchLogId}`,
            type: 'system',
            content: '調査が完了しました。',
            timestamp: new Date().toISOString(),
          };
          const resultMessage: ChatMessage = {
            id: `research-result-${researchLogId}`,
            type: 'assistant',
            content: log.assistant_reply || log.metadata_analysis?.deep_research?.summary || '',
            timestamp: new Date().toISOString(),
            logId: researchLogId,
            researchSummary: log.metadata_analysis?.deep_research?.summary,
            researchDetails: log.metadata_analysis?.deep_research?.details,
            isResearchCacheHit: log.metadata_analysis?.deep_research?.is_cache_hit,
          };
          const currentMsgs = useConversationStore.getState().messages;
          setMessages([
            ...currentMsgs.filter((m) => !m.id.startsWith('researching-')),
            completionNotice,
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

    // 元メッセージの実行ボタンを消して再実行を防止
    const beforeMsgs = useConversationStore.getState().messages;
    setMessages(
      beforeMsgs.map((m) =>
        m.id === message.id
          ? { ...m, requiresResearchConsent: false, researchConsentConsumed: true }
          : m
      )
    );

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
      // API応答は background_task に統一されているが、
      // ノード直返しの background_task_info も安全にフォールバックする
      const bgTask = result.background_task ?? (result as any).background_task_info;
      if (bgTask?.result_log_id) {
        setResearchLogId(bgTask.result_log_id);
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
      const response: AckResponse = await api.transcribeAudio(audioBlob, continuingThreadId);

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

      // スレッドを継続するために thread_id を保存
      setContinuingThreadId(response.thread_id);

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
    <div className="flex flex-col h-full relative">
      {/* フローティング: 新しい会話ボタン（会話が始まっている場合のみ表示） */}
      {(messages.length >= 2 || selectedLogId) && (
        <div className="sticky top-0 z-10 flex items-center justify-end px-4 py-2 bg-white/80 backdrop-blur-sm border-b border-gray-100">
          {selectedLogId && (
            <span className="text-sm text-primary-800 mr-auto">この会話の続きを話せます</span>
          )}
          <button
            type="button"
            onClick={() => {
              clearConversation();
              onClearSelection?.();
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-primary-50 text-primary-700 text-sm font-medium transition-colors"
          >
            <MessageSquarePlus className="w-4 h-4" />
            新しい会話を始める
          </button>
        </div>
      )}

      {/* メッセージエリア */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">

        {isLoadingLog && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
          </div>
        )}

        {!isLoadingLog && messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 px-8">
            <p className="text-lg font-medium mb-2 text-gray-600">
              うまく言えなくても大丈夫。
            </p>
            <p className="text-sm text-center mb-4 text-gray-500 max-w-sm leading-relaxed">
              断片的な言葉でも、AIが一緒に整理します。<br />
              まずは頭の中にあることを、そのまま書いてみてください。
            </p>
            <div className="text-xs text-center text-gray-400 max-w-sm space-y-1.5 mt-2">
              <p className="italic text-gray-400/80">
                例: 「今日の会議でなんか引っかかったことがあって...」
              </p>
              <p className="italic text-gray-400/80">
                例: 「Aにすべきか Bにすべきか迷ってる」
              </p>
            </div>
            <p className="text-xs text-center text-gray-400 max-w-sm mt-6">
              浮かび上がった課題と解決の方向性は、一般化されて
              <Link href="/insights" className="text-primary-500 hover:text-primary-600 inline-flex items-center gap-0.5 mx-0.5">
                <Lightbulb className="w-3.5 h-3.5" /> みんなの知恵
              </Link>
              に共有できる形で整理されます。
            </p>
          </div>
        )}

        {!isLoadingLog && messages.map((message) => {
          const isAiQuestion = message.type === 'ai-question';
          const hasStructuralData = isAiQuestion && message.structuralAnalysis?.updated_structural_issue;
          const isExpanded = expandedAnalysisIds.has(message.id);

          return (
            <div key={message.id} className="space-y-2">
              {/* AI問いかけ: 白い吹き出しとして表示 */}
              {isAiQuestion && (
                <div className="mr-auto max-w-[80%] rounded-lg p-3 bg-white border border-gray-200 text-gray-800">
                  <span className="text-xs text-gray-400 font-medium mb-1 block">
                    💡 深掘りのヒント
                  </span>
                  <div className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1">
                    <ReactMarkdown>{message.content}</ReactMarkdown>
                  </div>
                  <span className="text-xs text-gray-400 mt-1 block">
                    {formatRelativeTime(message.timestamp)}
                  </span>
                </div>
              )}
              {/* 課題記録: 折りたたみグレーボックス */}
              {isAiQuestion && hasStructuralData && (
                <div className="mr-auto max-w-[85%]">
                  <button
                    type="button"
                    onClick={() => {
                      setExpandedAnalysisIds((prev) => {
                        const next = new Set(prev);
                        if (next.has(message.id)) next.delete(message.id);
                        else next.add(message.id);
                        return next;
                      });
                    }}
                    className="w-full flex items-center justify-between gap-2 py-2 px-3 rounded-lg bg-gray-100 border border-gray-200 text-gray-600 text-sm hover:bg-gray-50 transition-colors text-left"
                  >
                    <span>📝 課題を記録しました</span>
                    {isExpanded ? (
                      <ChevronUp className="w-4 h-4 flex-shrink-0" />
                    ) : (
                      <ChevronDown className="w-4 h-4 flex-shrink-0" />
                    )}
                  </button>
                  {isExpanded && message.structuralAnalysis && (
                    <div className="mt-1 p-3 rounded-lg bg-gray-50 border border-gray-200 space-y-2">
                      <p className="text-xs text-gray-600">
                        <span className="font-medium">🔍 課題の深掘り:</span>{' '}
                        {message.structuralAnalysis.updated_structural_issue}
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        <span className="inline-block text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded-full">
                          {message.structuralAnalysis.relationship_type === 'ADDITIVE' && '深化'}
                          {message.structuralAnalysis.relationship_type === 'PARALLEL' && '並列'}
                          {message.structuralAnalysis.relationship_type === 'CORRECTION' && '訂正'}
                          {message.structuralAnalysis.relationship_type === 'NEW' && '新規'}
                        </span>
                      </div>
                      <button
                        onClick={() => copyAnalysisResult(message)}
                        className="text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1"
                      >
                        {copiedMessageId === message.id ? (
                          <Check className="w-3.5 h-3.5 text-green-500" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                        結果をコピー
                      </button>
                    </div>
                  )}
                </div>
              )}
              {/* その他のメッセージ (user, assistant, system) */}
              {!isAiQuestion && (
                <div className={message.type === 'user' ? 'ml-auto max-w-[80%]' : 'mr-auto max-w-[80%]'}>
                  <div
                    className={cn(
                      'rounded-lg p-3',
                      message.type === 'user'
                        ? 'bg-[#F3F4F6] text-gray-800'
                        : message.type === 'assistant'
                        ? 'bg-white border border-[#E5E7EB] text-gray-800'
                        : 'bg-gray-100 text-gray-600'
                    )}
                  >
                    {message.type === 'user' && message.isVoiceInput && (
                      <span className="text-xs text-gray-500 font-medium mb-1 flex items-center gap-1">
                        <Mic className="w-3 h-3" /> 音声入力
                      </span>
                    )}
                    {message.type === 'assistant' && (message.researchDetails || message.researchSummary) ? (
                      /* 調査結果がある場合は「カード」を表示する */
                      <div className="p-4 rounded-lg bg-white border border-indigo-200 shadow-sm">
                        <div className="flex items-start gap-3">
                          <div className="p-2 bg-indigo-100 text-indigo-600 rounded-lg shrink-0">
                            <FileText className="w-6 h-6" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <h3 className="font-bold text-gray-800 text-sm mb-1">Deep Research 完了</h3>
                            <p className="text-xs text-gray-500 line-clamp-2 mb-3">
                              {message.researchSummary || '調査結果のレポートが生成されました。'}
                            </p>
                            <button
                              onClick={() => router.push(`/reports/${message.logId}`)}
                              className="flex items-center justify-center gap-2 w-full px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700 transition-colors"
                            >
                              <ExternalLink className="w-4 h-4" />
                              レポートを読む
                            </button>
                          </div>
                        </div>
                        {message.isResearchCacheHit && (
                          <p className="mt-2 text-[10px] text-center text-gray-400">
                            ※既存のナレッジを活用して生成されました
                          </p>
                        )}
                      </div>
                    ) : (message.type === 'assistant' || message.type === 'system') ? (
                      <div className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-pre:my-1 prose-pre:text-xs">
                        <ReactMarkdown>{message.content}</ReactMarkdown>
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap">{message.content}</p>
                    )}
                    {/* Deep Research 提案 */}
                    {message.type === 'assistant' && message.requiresResearchConsent && !message.researchConsentConsumed && !isResearching && !message.researchPlan && (
                      <div className="mt-3 bg-indigo-50 p-3 rounded-lg border border-indigo-100 inline-block">
                        <p className="text-sm text-indigo-800 font-medium mb-2">
                          この件について詳細な調査（Deep Research）を行いますか？
                        </p>
                        <button
                          onClick={() => handleDeepResearch(message)}
                          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm"
                        >
                          <Search className="w-4 h-4" />
                          Deep Research を開始
                        </button>
                      </div>
                    )}
                    {/* 調査計画書 */}
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
                    <span className="text-xs text-gray-400 mt-1 block">
                      {formatRelativeTime(message.timestamp)}
                    </span>
                    {/* トーン調整フィードバック（アシスタント返答のみ） */}
                    {message.type === 'assistant' && (
                      <div className="flex items-center gap-1 mt-1 ml-1">
                        {toneFeedback[message.id] ? (
                          <span className="text-xs text-gray-400">
                            {toneFeedback[message.id] === 'gentler'
                              ? '次はもう少し柔らかく返答します'
                              : '次はもう少し踏み込んで返答します'}
                          </span>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => setToneFeedback((prev) => ({ ...prev, [message.id]: 'gentler' }))}
                              className="flex items-center gap-1 px-2 py-1 rounded text-xs text-gray-400 hover:text-blue-500 hover:bg-blue-50 transition-colors"
                              title="もう少し柔らかく"
                            >
                              <ThumbsDown className="w-3 h-3" />
                              <span className="hidden sm:inline">もう少し柔らかく</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => setToneFeedback((prev) => ({ ...prev, [message.id]: 'sharper' }))}
                              className="flex items-center gap-1 px-2 py-1 rounded text-xs text-gray-400 hover:text-orange-500 hover:bg-orange-50 transition-colors"
                              title="もっと踏み込んで"
                            >
                              <ThumbsUp className="w-3 h-3" />
                              <span className="hidden sm:inline">もっと踏み込んで</span>
                            </button>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}

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
              placeholder={isRecording ? '🎤 録音中... ボタンを押して停止' : 'モヤモヤしていることを書き出してみよう'}
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
