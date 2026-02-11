'use client';

/**
 * タイムラインは AIエージェントページ (/) に統合済み。
 * ブックマーク用に / へリダイレクトする。
 */
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function TimelineRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/');
  }, [router]);

  return (
    <div className="flex items-center justify-center min-h-[200px] text-gray-500 text-sm">
      リダイレクト中...
    </div>
  );
}
