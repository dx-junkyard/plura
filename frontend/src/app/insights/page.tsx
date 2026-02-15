'use client';

/**
 * PLURA - Insights Page
 * Layer 3: Public Plaza (共創の広場)
 */
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search, Filter, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { InsightCard } from '@/components/InsightCard';
import { cn } from '@/lib/utils';

export default function InsightsPage() {
  const [search, setSearch] = useState('');
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useQuery({
    queryKey: ['insights', page, search, selectedTopic],
    queryFn: () =>
      api.getInsights(
        page,
        20,
        selectedTopic || undefined,
        undefined,
        search || undefined
      ),
  });

  // トピック一覧（実際はAPIから取得するべき）
  const topics = [
    'プロジェクト管理',
    'コミュニケーション',
    'チームビルディング',
    '技術選定',
    '顧客対応',
  ];

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* ヘッダー */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-800 mb-2">
          みんなの知恵
        </h1>
        <p className="text-gray-500">
          チームの経験から生まれた知見を探索しましょう
        </p>
      </div>

      {/* 検索・フィルター */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="キーワードで検索..."
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
          />
        </div>

        <div className="flex gap-2 overflow-x-auto pb-2 sm:pb-0">
          <button
            onClick={() => setSelectedTopic(null)}
            className={cn(
              'px-3 py-2 rounded-lg text-sm whitespace-nowrap transition-colors',
              !selectedTopic
                ? 'bg-public-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            )}
          >
            すべて
          </button>
          {topics.map((topic) => (
            <button
              key={topic}
              onClick={() => setSelectedTopic(topic)}
              className={cn(
                'px-3 py-2 rounded-lg text-sm whitespace-nowrap transition-colors',
                selectedTopic === topic
                  ? 'bg-public-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              )}
            >
              {topic}
            </button>
          ))}
        </div>
      </div>

      {/* インサイトリスト */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
        </div>
      ) : error ? (
        <div className="text-center py-12 text-red-500">
          データの取得に失敗しました
        </div>
      ) : data?.items.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          インサイトが見つかりませんでした
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {data?.items.map((insight) => (
              <InsightCard key={insight.id} insight={insight} />
            ))}
          </div>

          {/* ページネーション */}
          {data && data.total > data.page_size && (
            <div className="flex justify-center gap-2 mt-8">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              >
                前へ
              </button>
              <span className="px-4 py-2 text-gray-600">
                {page} / {Math.ceil(data.total / data.page_size)}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= Math.ceil(data.total / data.page_size)}
                className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              >
                次へ
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
