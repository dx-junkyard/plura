'use client';

/**
 * PLURA - Team Proposal Card
 * Flash Team Formation: AIによるチーム提案カード
 */
import { useRouter } from 'next/navigation';
import { Users, Zap, ArrowRight, User } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { RecommendationItem } from '@/types';

interface TeamProposalCardProps {
  proposal: RecommendationItem;
  onDismiss?: () => void;
}

export function TeamProposalCard({ proposal, onDismiss }: TeamProposalCardProps) {
  const router = useRouter();
  const members = proposal.team_members ?? [];

  const handleJoin = () => {
    router.push(`/projects/${proposal.id}`);
  };

  return (
    <div className="bg-gradient-to-br from-primary-50 via-white to-public-50 rounded-xl border-2 border-primary-200 shadow-lg overflow-hidden animate-slide-up">
      {/* ヘッダー */}
      <div className="bg-gradient-to-r from-primary-600 to-primary-500 px-4 py-3">
        <div className="flex items-center gap-2 text-white">
          <Zap className="w-5 h-5" />
          <span className="font-bold text-sm tracking-wide">FLASH TEAM PROPOSAL</span>
        </div>
      </div>

      {/* コンテンツ */}
      <div className="p-4 space-y-4">
        {/* プロジェクト名 */}
        <div>
          <h3 className="text-lg font-bold text-gray-900">
            {proposal.project_name || proposal.title}
          </h3>
          <p className="text-sm text-gray-600 mt-1">
            {proposal.reason || proposal.preview}
          </p>
        </div>

        {/* メンバーリスト */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            提案メンバー
          </h4>
          <div className="space-y-2">
            {members.map((member, index) => (
              <div
                key={member.user_id}
                className={cn(
                  'flex items-center gap-3 p-2 rounded-lg',
                  'bg-white border border-gray-100'
                )}
              >
                {/* アバター */}
                <div className={cn(
                  'w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm',
                  index === 0 && 'bg-blue-500',
                  index === 1 && 'bg-emerald-500',
                  index === 2 && 'bg-amber-500',
                  index > 2 && 'bg-gray-400',
                )}>
                  {member.avatar_url ? (
                    <img
                      src={member.avatar_url}
                      alt={member.display_name}
                      className="w-full h-full rounded-full object-cover"
                    />
                  ) : (
                    <User className="w-5 h-5" />
                  )}
                </div>

                {/* 名前と役割 */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">
                    {member.display_name}
                  </p>
                  <p className="text-xs text-gray-500">{member.role}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* トピックス */}
        {proposal.topics.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {proposal.topics.map((topic) => (
              <span
                key={topic}
                className="text-xs px-2.5 py-1 bg-primary-100 text-primary-700 rounded-full font-medium"
              >
                {topic}
              </span>
            ))}
          </div>
        )}

        {/* アクションボタン */}
        <div className="flex gap-2 pt-1">
          <button
            onClick={handleJoin}
            className={cn(
              'flex-1 flex items-center justify-center gap-2',
              'px-4 py-2.5 rounded-lg font-semibold text-sm',
              'bg-primary-600 text-white',
              'hover:bg-primary-700 active:bg-primary-800',
              'transition-colors shadow-sm'
            )}
          >
            <Users className="w-4 h-4" />
            Join Project
            <ArrowRight className="w-4 h-4" />
          </button>
          {onDismiss && (
            <button
              onClick={onDismiss}
              className={cn(
                'px-4 py-2.5 rounded-lg text-sm',
                'text-gray-500 hover:bg-gray-100',
                'transition-colors'
              )}
            >
              後で
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
