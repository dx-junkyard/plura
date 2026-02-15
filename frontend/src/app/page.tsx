'use client';

/**
 * PLURA - AIエージェントページ
 * 思考の記録 → 課題・解決策の整理 → 「みんなの知恵」へ共有
 */
import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { ThoughtStream } from '@/components/ThoughtStream';
import { TimelineSection } from '@/components/TimelineSection';
import { useAuthStore } from '@/lib/store';
import { Lightbulb, PanelLeftOpen, X } from 'lucide-react';

export default function AgentPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const [selectedLogId, setSelectedLogId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login');
    }
  }, [isAuthenticated, router]);

  // モバイルでログ選択時にサイドバーを閉じる
  const handleSelectLog = useCallback((logId: string) => {
    setSelectedLogId(logId);
    setIsSidebarOpen(false);
  }, []);

  if (!isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-3.5rem)]">
        <div className="animate-pulse text-gray-400">読み込み中...</div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-3.5rem)] flex relative">
      {/* モバイル: オーバーレイ背景 */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-30 lg:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* 左: タイムライン（デスクトップ: 常時表示 / モバイル: オーバーレイ） */}
      <aside
        className={`
          fixed inset-y-0 left-0 top-14 z-40 w-72 border-r border-gray-200 bg-white flex flex-col
          transform transition-transform duration-200 ease-in-out
          lg:static lg:translate-x-0 lg:shrink-0
          ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        {/* モバイル: サイドバー閉じるボタン */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-gray-100 lg:hidden">
          <span className="text-sm font-medium text-gray-600">タイムライン</span>
          <button
            type="button"
            onClick={() => setIsSidebarOpen(false)}
            className="p-1.5 rounded-md hover:bg-gray-100 text-gray-500"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <TimelineSection
          selectedLogId={selectedLogId}
          onSelectLog={handleSelectLog}
        />
      </aside>

      {/* 右: メイン（AIエージェント） */}
      <div className="flex-1 min-w-0 flex flex-col max-w-3xl mx-auto w-full">
        <header className="shrink-0 px-4 py-3 border-b border-gray-200 bg-white">
          <div className="flex items-center gap-2">
            {/* モバイル: サイドバー開くボタン */}
            <button
              type="button"
              onClick={() => setIsSidebarOpen(true)}
              className="p-1.5 -ml-1.5 rounded-md hover:bg-gray-100 text-gray-500 lg:hidden"
              title="タイムラインを開く"
            >
              <PanelLeftOpen className="w-5 h-5" />
            </button>
            <h1 className="text-lg font-bold text-gray-800">AIエージェント</h1>
          </div>
          <p className="text-sm text-gray-500 mt-0.5">
            思いついたことを書くと、課題と解決の方向性を整理します。共有価値が高い気づきは
            <Link
              href="/insights"
              className="inline-flex items-center gap-1 text-primary-600 hover:text-primary-700 font-medium mx-1"
            >
              <Lightbulb className="w-4 h-4" />
              みんなの知恵
            </Link>
            に共有できる形で提案されます。
          </p>
        </header>

        <div className="flex-1 min-h-0 flex flex-col">
          <ThoughtStream
            selectedLogId={selectedLogId}
            onClearSelection={() => setSelectedLogId(null)}
          />
        </div>
      </div>
    </div>
  );
}
