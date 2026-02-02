'use client';

/**
 * MINDYARD - Timeline Page
 * 過去のログを振り返る
 */
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import {
  ChevronLeft,
  ChevronRight,
  Loader2,
  Calendar as CalendarIcon,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useAuthStore } from '@/lib/store';
import {
  cn,
  formatDateTime,
  getEmotionLabel,
  getIntentLabel,
} from '@/lib/utils';

export default function TimelinePage() {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login');
    }
  }, [isAuthenticated, router]);

  const { data, isLoading, error } = useQuery({
    queryKey: ['logs', page],
    queryFn: () => api.getLogs(page, 20),
    enabled: isAuthenticated,
  });

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* ヘッダー */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-800 mb-2">
          タイムライン
        </h1>
        <p className="text-gray-500">あなたの記録を振り返りましょう</p>
      </div>

      {/* ログリスト */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
        </div>
      ) : error ? (
        <div className="text-center py-12 text-red-500">
          データの取得に失敗しました
        </div>
      ) : data?.items.length === 0 ? (
        <div className="text-center py-12">
          <CalendarIcon className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">まだ記録がありません</p>
          <button
            onClick={() => router.push('/')}
            className="mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            最初の記録を始める
          </button>
        </div>
      ) : (
        <>
          <div className="space-y-4">
            {data?.items.map((log) => (
              <div
                key={log.id}
                className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow"
              >
                {/* コンテンツ */}
                <p className="text-gray-800 whitespace-pre-wrap mb-3">
                  {log.content}
                </p>

                {/* メタデータ */}
                <div className="flex flex-wrap gap-2 mb-3">
                  {log.intent && (
                    <span className="text-xs px-2 py-0.5 bg-private-100 text-private-700 rounded-full">
                      {getIntentLabel(log.intent)}
                    </span>
                  )}
                  {log.emotions?.map((emotion) => (
                    <span
                      key={emotion}
                      className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full"
                    >
                      {getEmotionLabel(emotion)}
                    </span>
                  ))}
                  {log.topics?.map((topic) => (
                    <span
                      key={topic}
                      className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full"
                    >
                      {topic}
                    </span>
                  ))}
                </div>

                {/* 日時 */}
                <div className="text-xs text-gray-400">
                  {formatDateTime(log.created_at)}
                </div>
              </div>
            ))}
          </div>

          {/* ページネーション */}
          {data && data.total > data.page_size && (
            <div className="flex justify-center gap-2 mt-8">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-2 rounded-lg border border-gray-300 text-gray-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <span className="px-4 py-2 text-gray-600">
                {page} / {Math.ceil(data.total / data.page_size)}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= Math.ceil(data.total / data.page_size)}
                className="p-2 rounded-lg border border-gray-300 text-gray-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
