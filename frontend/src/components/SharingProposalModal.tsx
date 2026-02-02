'use client';

/**
 * MINDYARD - Sharing Proposal Modal
 * Layer 2: 共有提案の承認/拒否UI
 */
import { useState } from 'react';
import { X, Share2, XCircle, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { SharingProposal } from '@/types';

interface SharingProposalModalProps {
  proposal: SharingProposal;
  onApprove: () => void;
  onReject: () => void;
  onClose: () => void;
}

export function SharingProposalModal({
  proposal,
  onApprove,
  onReject,
  onClose,
}: SharingProposalModalProps) {
  const [isProcessing, setIsProcessing] = useState(false);
  const { insight, message } = proposal;

  const handleApprove = async () => {
    setIsProcessing(true);
    await onApprove();
    setIsProcessing(false);
  };

  const handleReject = async () => {
    setIsProcessing(true);
    await onReject();
    setIsProcessing(false);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl max-w-lg w-full max-h-[90vh] overflow-hidden shadow-xl">
        {/* ヘッダー */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-public-50">
          <div className="flex items-center gap-2 text-public-700">
            <Sparkles className="w-5 h-5" />
            <span className="font-semibold">共有のご提案</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-public-100 rounded-full transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* コンテンツ */}
        <div className="p-4 overflow-y-auto max-h-[60vh]">
          {/* メッセージ */}
          <p className="text-gray-700 mb-4">{message}</p>

          {/* インサイトプレビュー */}
          <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
            <h3 className="font-semibold text-gray-800 text-lg mb-2">
              {insight.title}
            </h3>

            {insight.context && (
              <div className="mb-3">
                <span className="text-xs font-medium text-gray-500 uppercase">
                  背景
                </span>
                <p className="text-sm text-gray-600 mt-1">{insight.context}</p>
              </div>
            )}

            {insight.problem && (
              <div className="mb-3">
                <span className="text-xs font-medium text-red-600 uppercase">
                  課題
                </span>
                <p className="text-sm text-gray-600 mt-1">{insight.problem}</p>
              </div>
            )}

            {insight.solution && (
              <div className="mb-3">
                <span className="text-xs font-medium text-green-600 uppercase">
                  解決策・結果
                </span>
                <p className="text-sm text-gray-600 mt-1">{insight.solution}</p>
              </div>
            )}

            {insight.topics && insight.topics.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-3">
                {insight.topics.map((topic) => (
                  <span
                    key={topic}
                    className="text-xs px-2 py-0.5 bg-white text-gray-600 rounded-full border border-gray-200"
                  >
                    {topic}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* スコア表示 */}
          <div className="flex items-center justify-center mt-4 text-sm text-gray-500">
            <span>共有価値スコア: </span>
            <span className="ml-1 font-semibold text-public-600">
              {Math.round(insight.sharing_value_score)}点
            </span>
          </div>
        </div>

        {/* フッター */}
        <div className="flex gap-3 p-4 border-t border-gray-200 bg-gray-50">
          <button
            onClick={handleReject}
            disabled={isProcessing}
            className={cn(
              'flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg border border-gray-300 text-gray-700 transition-colors',
              isProcessing
                ? 'opacity-50 cursor-not-allowed'
                : 'hover:bg-gray-100'
            )}
          >
            <XCircle className="w-4 h-4" />
            今回はやめておく
          </button>
          <button
            onClick={handleApprove}
            disabled={isProcessing}
            className={cn(
              'flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-public-600 text-white transition-colors',
              isProcessing
                ? 'opacity-50 cursor-not-allowed'
                : 'hover:bg-public-700'
            )}
          >
            <Share2 className="w-4 h-4" />
            共有する
          </button>
        </div>
      </div>
    </div>
  );
}
