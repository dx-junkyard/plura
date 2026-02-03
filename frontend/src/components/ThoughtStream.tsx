'use client';

/**
 * MINDYARD - ThoughtStream Component
 * Layer 1: チャット形式の入力UI（ノン・ジャッジメンタル応答）
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import TextareaAutosize from 'react-textarea-autosize';
import { Send, Mic, MicOff, Loader2 } from 'lucide-react';
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
}

export function ThoughtStream() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [pendingLogId, setPendingLogId] = useState<string | null>(null);
  const [isWaitingForAnalysis, setIsWaitingForAnalysis] = useState(false);
  const [recordingError, setRecordingError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const debounceRef = useRef<NodeJS.Timeout>();
  const pollingRef = useRef<NodeJS.Timeout>();
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const { setRecommendations, clearRecommendations } = useRecommendationStore();

  // メッセージ追加時にスクロール
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 構造分析結果のポーリング
  useEffect(() => {
    if (!pendingLogId) return;

    const pollForAnalysis = async () => {
      try {
        const log: RawLog = await api.getLog(pendingLogId);

        if (log.is_structure_analyzed && log.structural_analysis?.probing_question) {
          // 分析完了 - AIの問いかけを表示
          const aiMessage: Message = {
            id: `ai-${log.id}`,
            type: 'ai-question',
            content: log.structural_analysis.probing_question,
            timestamp: new Date(),
            logId: log.id,
            relationshipType: log.structural_analysis.relationship_type,
          };

          setMessages((prev) => [...prev, aiMessage]);
          setPendingLogId(null);
          setIsWaitingForAnalysis(false);

          // ポーリング停止
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = undefined;
          }
        }
      } catch (error: any) {
        console.error('Polling error:', error);
        // 404 Not Found の場合は、ログが存在しないためポーリングを停止する
        if (error.response && error.response.status === 404) {
          setPendingLogId(null);
          setIsWaitingForAnalysis(false);
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = undefined;
          }
        }
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
  }, [pendingLogId]);

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

      const systemMessage: Message = {
        id: response.log_id,
        type: 'system',
        content: response.message,
        timestamp: new Date(response.timestamp),
        logId: response.log_id,
      };

      setMessages((prev) => [...prev, systemMessage]);

      // 構造分析のポーリングを開始
      setPendingLogId(response.log_id);
      setIsWaitingForAnalysis(true);
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
          content: '🎤 (音声入力)',
          timestamp: new Date(response.timestamp),
          logId: response.log_id,
        };

        // システムからの相槌
        const systemMessage: Message = {
          id: response.log_id,
          type: 'system',
          content: response.message,
          timestamp: new Date(response.timestamp),
          logId: response.log_id,
        };

        return [...filtered, userMessage, systemMessage];
      });

      // 構造分析のポーリングを開始
      setPendingLogId(response.log_id);
      setIsWaitingForAnalysis(true);
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
            {message.type === 'ai-question' && (
              <span className="text-xs text-blue-500 font-medium mb-1 block">
                🤔 考えを深める問い
              </span>
            )}
            <p className="whitespace-pre-wrap">{message.content}</p>
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
          <div className="mr-auto bg-blue-50 border border-blue-100 rounded-lg p-3 flex items-center gap-2 text-blue-600">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>考えを整理しています...</span>
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
