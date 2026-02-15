'use client';

/**
 * PLURA - Sharing Proposals Page
 * Layer 2: 推奨インサイトの一覧と承認
 */
import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { Loader2, Inbox } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuthStore, useNotificationStore } from '@/lib/store';
import { SharingProposalModal } from '@/components/SharingProposalModal';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { SharingProposal } from '@/types';

export default function ProposalsPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const { setPendingProposalCount } = useNotificationStore();
  const queryClient = useQueryClient();

  const [selectedProposal, setSelectedProposal] = useState<SharingProposal | null>(null);

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login');
    }
  }, [isAuthenticated, router]);

  const { data: proposals, isLoading, error } = useQuery({
    queryKey: ['proposals'],
    queryFn: () => api.getPendingProposals(),
    enabled: isAuthenticated,
  });

  // 通知カウントを更新
  useEffect(() => {
    if (proposals) {
      setPendingProposalCount(proposals.length);
    }
  }, [proposals, setPendingProposalCount]);

  const decideMutation = useMutation({
    mutationFn: ({ insightId, approved }: { insightId: string; approved: boolean }) =>
      api.decideSharingProposal(insightId, approved),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proposals'] });
      setSelectedProposal(null);
    },
  });

  const handleApprove = () => {
    if (selectedProposal) {
      decideMutation.mutate({
        insightId: selectedProposal.insight.id,
        approved: true,
      });
    }
  };

  const handleReject = () => {
    if (selectedProposal) {
      decideMutation.mutate({
        insightId: selectedProposal.insight.id,
        approved: false,
      });
    }
  };

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* ヘッダー */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-800 mb-2">共有の推奨</h1>
        <p className="text-gray-500">
          AIがあなたの知見に共有価値を見出しました。チームに共有しませんか？
        </p>
      </div>

      {/* 提案リスト */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
        </div>
      ) : error ? (
        <div className="text-center py-12 text-red-500">
          データの取得に失敗しました
        </div>
      ) : proposals?.length === 0 ? (
        <div className="text-center py-12">
          <Inbox className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">現在、推奨はありません</p>
          <p className="text-sm text-gray-400 mt-2">
            記録を続けると、共有価値の高い知見がAIから推奨されます
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {proposals?.map((proposal) => (
            <div
              key={proposal.insight.id}
              onClick={() => setSelectedProposal(proposal)}
              className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow cursor-pointer"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-gray-800 mb-1">
                    {proposal.insight.title}
                  </h3>
                  <p className="text-sm text-gray-500 line-clamp-2">
                    {proposal.insight.summary}
                  </p>
                </div>
                <span className="text-xs text-public-600 font-medium whitespace-nowrap ml-4">
                  スコア: {Math.round(proposal.insight.sharing_value_score)}
                </span>
              </div>

              <div className="flex items-center justify-between mt-3">
                <div className="flex gap-1">
                  {proposal.insight.topics?.slice(0, 2).map((topic) => (
                    <span
                      key={topic}
                      className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full"
                    >
                      {topic}
                    </span>
                  ))}
                </div>
                <span className="text-xs text-gray-400">
                  {formatRelativeTime(proposal.insight.created_at)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* モーダル */}
      {selectedProposal && (
        <SharingProposalModal
          proposal={selectedProposal}
          onApprove={handleApprove}
          onReject={handleReject}
          onClose={() => setSelectedProposal(null)}
        />
      )}
    </div>
  );
}
