'use client';

/**
 * PLURA - Navigation Component
 */
import { useEffect, useCallback } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Bot,
  Lightbulb,
  Bell,
  LogOut
} from 'lucide-react';
import { useAuthStore, useNotificationStore, useConversationStore } from '@/lib/store';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

const POLL_INTERVAL_MS = 30_000; // 30秒ごとに推奨インサイトをチェック

export function Navigation() {
  const pathname = usePathname();
  const { user, isAuthenticated, logout } = useAuthStore();
  const { pendingProposalCount, setPendingProposalCount } = useNotificationStore();

  // 推奨インサイトの件数をポーリング
  const fetchPendingCount = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const proposals = await api.getPendingProposals();
      setPendingProposalCount(proposals.length);
    } catch {
      // 認証切れなどは無視
    }
  }, [isAuthenticated, setPendingProposalCount]);

  useEffect(() => {
    fetchPendingCount(); // 初回チェック
    const id = setInterval(fetchPendingCount, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchPendingCount]);

  const clearConversation = useConversationStore((s) => s.clearConversation);

  const handleLogout = () => {
    api.logout();
    clearConversation();
    logout();
  };

  const navItems = [
    {
      href: '/',
      label: 'AIエージェント',
      icon: Bot,
      description: '思考を整理し、課題・解決策を「みんなの知恵」に共有',
    },
    {
      href: '/insights',
      label: 'みんなの知恵',
      icon: Lightbulb,
      description: 'Layer 3: 共創の広場',
    },
  ];

  // 未認証 or 認証ページにいる場合はシンプルなナビを表示
  const isAuthPage = pathname === '/login' || pathname === '/register';
  if (!isAuthenticated || isAuthPage) {
    return (
      <nav className="fixed top-0 left-0 right-0 h-14 bg-white border-b border-gray-200 z-40">
        <div className="max-w-7xl mx-auto px-4 h-full flex items-center justify-between">
          <Link href="/" className="text-xl font-bold text-primary-600">
            PLURA
          </Link>
          <div className="flex items-center gap-4">
            <Link
              href="/login"
              className="text-gray-600 hover:text-gray-800 text-sm"
            >
              ログイン
            </Link>
            <Link
              href="/register"
              className="px-4 py-2 bg-primary-600 text-white rounded-lg text-sm hover:bg-primary-700 transition-colors"
            >
              新規登録
            </Link>
          </div>
        </div>
      </nav>
    );
  }

  return (
    <nav className="fixed top-0 left-0 right-0 h-14 bg-white border-b border-gray-200 z-40">
      <div className="max-w-7xl mx-auto px-4 h-full flex items-center justify-between">
        {/* ロゴ */}
        <Link href="/" className="text-xl font-bold text-primary-600">
          PLURA
        </Link>

        {/* ナビゲーションリンク */}
        <div className="flex items-center gap-1">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;

            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors',
                  isActive
                    ? 'bg-primary-100 text-primary-700'
                    : 'text-gray-600 hover:bg-gray-100'
                )}
                title={item.description}
              >
                <Icon className="w-4 h-4" />
                <span className="hidden sm:inline">{item.label}</span>
              </Link>
            );
          })}
        </div>

        {/* 右側のアクション */}
        <div className="flex items-center gap-2">
          {/* 通知 */}
          <Link
            href="/proposals"
            className="relative p-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <Bell className="w-5 h-5" />
            {pendingProposalCount > 0 && (
              <span className="absolute top-1 right-1 w-4 h-4 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
                {pendingProposalCount}
              </span>
            )}
          </Link>

          {/* ユーザーメニュー */}
          <div className="flex items-center gap-2 pl-2 border-l border-gray-200">
            <span className="text-sm text-gray-600 hidden sm:inline">
              {user?.display_name || user?.email}
            </span>
            <button
              onClick={handleLogout}
              className="p-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              title="ログアウト"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
