'use client';

/**
 * MINDYARD - ThoughtStream Component
 * Layer 1: チャット形式の入力UI（ノン・ジャッジメンタル応答）
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import TextareaAutosize from 'react-textarea-autosize';
import { Send, Mic, MicOff, Loader2, ChevronDown, ChevronUp, Share2, Copy, Check } from 'lucide-react';
import { api } from '@/lib/api';
import { useRecommendationStore } from '@/lib/store';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { AckResponse, RawLog } from '@/types';

interface Message {
  id: string;
  type: 'user' | 'system' | 'ai-question';
  content: string;
  timestamp: Date;
  logId?: string;
  relationshipType?: string;
  structuralAnalysis?: {
    relationship_type: string;
    relationship_reason: string;
    updated_structural_issue: string;
    probing_question: string;
  };
  isVoiceInput?: boolean;
}

// 整理プロセスのステップ定義
interface AnalysisStep {
  id: string;
  label: string;
  status: 'pending' | 'in_progress' | 'completed';
}

export function ThoughtStream() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [pendingLogIds, setPendingLogIds] = useState<string[]>([]);
  const [recordingError, setRecordingError] = useState<string | null>(null);
  const [analysisSteps, setAnalysisSteps] = useState<AnalysisStep[]>([]);
  const [isAnalysisExpanded, setIsAnalysisExpanded] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
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
        const newMessages: Message[] = [];
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
              const aiMessage: Message = {
                id: `ai-${log.id}`,
                type: 'ai-question',
                content: log.structural_analysis.probing_question,
                timestamp: new Date(),
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
          setMessages((prev) => [...prev, ...newMessages]);
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

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsSubmitting(true);
    clearRecommendations();

    try {
      const response: AckResponse = await api.createLog(input.trim());

      if (response.message?.trim()) {
        const systemMessage: Message = {
          id: response.log_id,
          type: 'system',
          content: response.message,
          timestamp: new Date(response.timestamp),
          logId: response.log_id,
        };
        setMessages((prev) => [...prev, systemMessage]);
      }

      if (!response.skip_structural_analysis) {
        // 構造分析のポーリングを開始
        setPendingLogIds(prev => [...prev, response.log_id]);
        initializeAnalysisSteps();
      }
    } catch (error) {
      const errorMessage: Message = {
        id: Date.now().toString(),
        type: 'system',
        content: '保存に失敗しました。もう一度お試しください。',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsSubmitting(false);
      inputRef.current?.focus();
    }
  };

  // 整理結果を共有用テキストとしてコピー
  const copyAnalysisResult = useCallback(async (message: Message) => {
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
    const transcribingMessage: Message = {
      id: `transcribing-${Date.now()}`,
      type: 'system',
      content: '🎤 音声を解析中...',
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, transcribingMessage]);

    try {
      const response: AckResponse = await api.transcribeAudio(audioBlob);

      // 「解析中」メッセージを削除し、結果を表示
      setMessages((prev) => {
        const filtered = prev.filter((m) => !m.id.startsWith('transcribing-'));

        // ユーザーメッセージ（音声から変換されたテキスト）
        const userMessage: Message = {
          id: `voice-${response.log_id}`,
          type: 'user',
          content: response.transcribed_text || '(音声入力)',
          timestamp: new Date(response.timestamp),
          logId: response.log_id,
          isVoiceInput: true,
        };

        // システムからの相槌
        const systemMessage: Message = {
          id: response.log_id,
          type: 'system',
          content: response.message,
          timestamp: new Date(response.timestamp),
          logId: response.log_id,
        };

        return response.message?.trim()
          ? [...filtered, userMessage, systemMessage]
          : [...filtered, userMessage];
      });

      if (!response.skip_structural_analysis) {
        // 構造分析のポーリングを開始
        setPendingLogIds(prev => [...prev, response.log_id]);
        initializeAnalysisSteps();
      }
    } catch (error) {
      console.error('音声送信エラー:', error);

      // エラーメッセージを表示
      setMessages((prev) => {
        const filtered = prev.filter((m) => !m.id.startsWith('transcribing-'));
        const errorMessage: Message = {
          id: Date.now().toString(),
          type: 'system',
          content: '音声の処理に失敗しました。もう一度お試しください。',
          timestamp: new Date(),
        };
        return [...filtered, errorMessage];
      });
    } finally {
      setIsTranscribing(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* メッセージエリア */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <p className="text-lg font-medium mb-2">思いついたことを書いてみましょう</p>
            <p className="text-sm">ここは安全な場所です。何でも記録できます。</p>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={cn(
              'max-w-[80%] rounded-lg p-3',
              message.type === 'user'
                ? 'ml-auto bg-private-100 text-gray-800'
                : message.type === 'ai-question'
                ? 'mr-auto bg-blue-50 border border-blue-200 text-gray-700'
                : 'mr-auto bg-gray-100 text-gray-600'
            )}
          >
            {message.type === 'user' && message.isVoiceInput && (
              <span className="text-xs text-private-500 font-medium mb-1 flex items-center gap-1">
                <Mic className="w-3 h-3" /> 音声入力
              </span>
            )}
            {message.type === 'ai-question' && (
              <div className="flex items-start justify-between mb-2">
                <span className="text-xs text-blue-500 font-medium">
                  🤔 考えを深める問い
                </span>
                {message.structuralAnalysis && (
                  <button
                    onClick={() => copyAnalysisResult(message)}
                    className="text-blue-400 hover:text-blue-600 transition-colors p-1 -m-1"
                    title="整理結果をコピー"
                  >
                    {copiedMessageId === message.id ? (
                      <Check className="w-4 h-4 text-green-500" />
                    ) : (
                      <Copy className="w-4 h-4" />
                    )}
                  </button>
                )}
              </div>
            )}
            <p className="whitespace-pre-wrap">{message.content}</p>
            {message.type === 'ai-question' && message.structuralAnalysis && (
              <div className="mt-3 pt-3 border-t border-blue-100">
                <p className="text-xs text-blue-600 font-medium mb-1">構造的な課題:</p>
                <p className="text-sm text-gray-600 mb-2">{message.structuralAnalysis.updated_structural_issue}</p>
                <div className="flex flex-wrap gap-2">
                  <span className="inline-block text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded-full">
                    {message.structuralAnalysis.relationship_type === 'ADDITIVE' && '深化'}
                    {message.structuralAnalysis.relationship_type === 'PARALLEL' && '並列'}
                    {message.structuralAnalysis.relationship_type === 'CORRECTION' && '訂正'}
                    {message.structuralAnalysis.relationship_type === 'NEW' && '新規'}
                  </span>
                  {message.structuralAnalysis.model_info && (
                    <span className={cn(
                      "inline-block text-xs px-2 py-0.5 rounded-full",
                      message.structuralAnalysis.model_info.is_reasoning
                        ? "bg-purple-100 text-purple-600"
                        : "bg-gray-100 text-gray-500"
                    )}>
                      {message.structuralAnalysis.model_info.is_reasoning ? 'Reasoning' : message.structuralAnalysis.model_info.tier}
                    </span>
                  )}
                </div>
              </div>
            )}
            <span className="text-xs text-gray-400 mt-1 block">
              {formatRelativeTime(message.timestamp.toISOString())}
            </span>
          </div>
        ))}

        {isSubmitting && (
          <div className="mr-auto bg-gray-100 rounded-lg p-3 flex items-center gap-2 text-gray-500">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>受け取っています...</span>
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
