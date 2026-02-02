'use client';

/**
 * MINDYARD - Home Page
 * Layer 1: Private Safehouse (思考の私有地)
 */
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ThoughtStream } from '@/components/ThoughtStream';
import { useAuthStore } from '@/lib/store';

export default function HomePage() {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();

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
    <div className="max-w-3xl mx-auto h-[calc(100vh-3.5rem)]">
      <ThoughtStream />
    </div>
  );
}
