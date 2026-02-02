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
import type { AckResponse } from '@/types';

interface Message {
  id: string;
  type: 'user' | 'system';
  content: string;
  timestamp: Date;
  logId?: string;
}

export function ThoughtStream() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const debounceRef = useRef<NodeJS.Timeout>();

  const { setRecommendations, clearRecommendations } = useRecommendationStore();

  // メッセージ追加時にスクロール
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

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
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // 音声入力（プレースホルダー）
  const toggleRecording = () => {
    setIsRecording(!isRecording);
    // TODO: Web Speech API または Whisper API を使用した音声入力の実装
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
                : 'mr-auto bg-gray-100 text-gray-600'
            )}
          >
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

        <div ref={messagesEndRef} />
      </div>

      {/* 入力エリア */}
      <div className="border-t border-gray-200 p-4 bg-white">
        <div className="flex items-end gap-2">
          <button
            onClick={toggleRecording}
            className={cn(
              'p-2 rounded-full transition-colors',
              isRecording
                ? 'bg-red-500 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            )}
            title={isRecording ? '録音停止' : '音声入力'}
          >
            {isRecording ? (
              <MicOff className="w-5 h-5" />
            ) : (
              <Mic className="w-5 h-5" />
            )}
          </button>

          <div className="flex-1 relative">
            <TextareaAutosize
              ref={inputRef}
              value={input}
              onChange={(e) => handleInputChange(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="今、何を考えていますか？"
              className="w-full resize-none rounded-lg border border-gray-200 px-4 py-3 pr-12 focus:border-private-400 focus:ring-1 focus:ring-private-400 outline-none"
              minRows={1}
              maxRows={6}
            />
            <button
              onClick={handleSubmit}
              disabled={!input.trim() || isSubmitting}
              className={cn(
                'absolute right-2 bottom-2 p-2 rounded-full transition-colors',
                input.trim() && !isSubmitting
                  ? 'bg-private-500 text-white hover:bg-private-600'
                  : 'bg-gray-100 text-gray-400 cursor-not-allowed'
              )}
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>

        <p className="text-xs text-gray-400 mt-2 text-center">
          Shift + Enter で改行 / Enter で送信
        </p>
      </div>
    </div>
  );
}
