'use client';

/**
 * MINDYARD - Insight Card Component
 * Layer 3: 公開インサイトの表示カード
 */
import { useState } from 'react';
import { Eye, Heart, Calendar, Tag, MessageSquare } from 'lucide-react';
import { cn, formatRelativeTime, truncate } from '@/lib/utils';
import { api } from '@/lib/api';
import type { InsightCard as InsightCardType } from '@/types';

interface InsightCardProps {
  insight: InsightCardType;
  onClick?: () => void;
}

export function InsightCard({ insight, onClick }: InsightCardProps) {
  const [thanksCount, setThanksCount] = useState(insight.thanks_count);
  const [hasThanked, setHasThanked] = useState(false);

  const handleThanks = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (hasThanked) return;

    try {
      const result = await api.sendThanks(insight.id);
      setThanksCount(result.thanks_count);
      setHasThanked(true);
    } catch (error) {
      // エラーは無視
    }
  };

  return (
    <div
      className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow cursor-pointer"
      onClick={onClick}
    >
      {/* タイトル */}
      <h3 className="font-semibold text-gray-800 text-lg line-clamp-2 mb-2">
        {insight.title}
      </h3>

      {/* サマリー */}
      <p className="text-gray-600 text-sm line-clamp-3 mb-3">
        {insight.summary}
      </p>

      {/* 構造化コンテンツのプレビュー */}
      {insight.problem && (
        <div className="bg-red-50 rounded p-2 mb-2">
          <span className="text-xs font-medium text-red-700">課題:</span>
          <p className="text-xs text-red-600 mt-0.5 line-clamp-2">
            {truncate(insight.problem, 80)}
          </p>
        </div>
      )}

      {insight.solution && (
        <div className="bg-green-50 rounded p-2 mb-3">
          <span className="text-xs font-medium text-green-700">解決策:</span>
          <p className="text-xs text-green-600 mt-0.5 line-clamp-2">
            {truncate(insight.solution, 80)}
          </p>
        </div>
      )}

      {/* タグ */}
      {insight.topics && insight.topics.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {insight.topics.slice(0, 3).map((topic) => (
            <span
              key={topic}
              className="text-xs px-2 py-0.5 bg-public-100 text-public-700 rounded-full"
            >
              {topic}
            </span>
          ))}
          {insight.topics.length > 3 && (
            <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-500 rounded-full">
              +{insight.topics.length - 3}
            </span>
          )}
        </div>
      )}

      {/* メタ情報 */}
      <div className="flex items-center justify-between text-xs text-gray-400">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <Eye className="w-3 h-3" />
            {insight.view_count}
          </span>
          <button
            onClick={handleThanks}
            className={cn(
              'flex items-center gap-1 transition-colors',
              hasThanked ? 'text-red-500' : 'hover:text-red-400'
            )}
          >
            <Heart className={cn('w-3 h-3', hasThanked && 'fill-current')} />
            {thanksCount}
          </button>
        </div>
        <span className="flex items-center gap-1">
          <Calendar className="w-3 h-3" />
          {formatRelativeTime(insight.published_at || insight.created_at)}
        </span>
      </div>
    </div>
  );
}
