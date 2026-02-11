'use client';

/**
 * MINDYARD - AIエージェントページ
 * 思考の記録 → 課題・解決策の整理 → 「みんなの知恵」へ共有
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { ThoughtStream } from '@/components/ThoughtStream';
import { TimelineSection } from '@/components/TimelineSection';
import { useAuthStore } from '@/lib/store';
import { Lightbulb } from 'lucide-react';

export default function AgentPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const [selectedLogId, setSelectedLogId] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login');
    }
  }, [isAuthenticated, router]);

  if (!isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-3.5rem)]">
        <div className="animate-pulse text-gray-400">読み込み中...</div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-3.5rem)] flex">
      {/* 左: タイムライン（サイドメニュー） */}
      <aside className="w-72 shrink-0 border-r border-gray-200 bg-white flex flex-col h-full">
        <TimelineSection
          selectedLogId={selectedLogId}
          onSelectLog={setSelectedLogId}
        />
      </aside>

      {/* 右: メイン（AIエージェント） */}
      <div className="flex-1 min-w-0 flex flex-col max-w-3xl mx-auto w-full">
        <header className="shrink-0 px-4 py-3 border-b border-gray-200 bg-white">
          <h1 className="text-lg font-bold text-gray-800">AIエージェント</h1>
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
