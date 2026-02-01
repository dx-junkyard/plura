'use client';

/**
 * MINDYARD - Recommendation Panel
 * Serendipity Matcher による「副作用的」レコメンデーション表示
 */
import { X, Sparkles, ThumbsUp } from 'lucide-react';
import { useRecommendationStore } from '@/lib/store';
import { cn } from '@/lib/utils';

export function RecommendationPanel() {
  const { recommendations, isVisible, displayMessage, hideRecommendations } =
    useRecommendationStore();

  if (!isVisible || recommendations.length === 0) {
    return null;
  }

  return (
    <div className="fixed bottom-24 right-4 w-80 bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden animate-slide-up">
      {/* ヘッダー */}
      <div className="flex items-center justify-between p-3 bg-public-50 border-b border-public-100">
        <div className="flex items-center gap-2 text-public-700">
          <Sparkles className="w-4 h-4" />
          <span className="text-sm font-medium">
            {displayMessage || '関連するみんなの知恵'}
          </span>
        </div>
        <button
          onClick={hideRecommendations}
          className="p-1 hover:bg-public-100 rounded-full transition-colors"
        >
          <X className="w-4 h-4 text-gray-500" />
        </button>
      </div>

      {/* レコメンデーションリスト */}
      <div className="max-h-64 overflow-y-auto">
        {recommendations.map((item, index) => (
          <div
            key={item.id}
            className={cn(
              'p-3 hover:bg-gray-50 cursor-pointer transition-colors',
              index !== recommendations.length - 1 && 'border-b border-gray-100'
            )}
          >
            <h4 className="font-medium text-gray-800 text-sm line-clamp-2">
              {item.title}
            </h4>
            <p className="text-xs text-gray-500 mt-1 line-clamp-2">
              {item.preview}
            </p>
            <div className="flex items-center justify-between mt-2">
              <div className="flex gap-1">
                {item.topics.slice(0, 2).map((topic) => (
                  <span
                    key={topic}
                    className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full"
                  >
                    {topic}
                  </span>
                ))}
              </div>
              <span className="text-xs text-public-600 font-medium">
                {item.relevance_score}% 関連
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* フッター */}
      <div className="p-2 bg-gray-50 border-t border-gray-100 text-center">
        <button className="text-xs text-gray-500 hover:text-gray-700">
          すべて見る
        </button>
      </div>
    </div>
  );
}
