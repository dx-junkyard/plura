'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { useAuthStore, useConversationStore } from '@/lib/store';

/**
 * アプリ起動時にトークンを検証し、無効ならログアウトするガード
 */
function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, logout } = useAuthStore();
  const clearConversation = useConversationStore((s) => s.clearConversation);

  useEffect(() => {
    // 401 レスポンス時に Zustand ストアからもログアウト
    api.onUnauthorized(() => {
      clearConversation();
      logout();
    });
  }, [logout, clearConversation]);

  useEffect(() => {
    // 起動時: localStorage に認証状態があるならトークンを検証
    if (!isAuthenticated) return;
    const token = api.getToken();
    if (!token) {
      // トークンが消えているのに isAuthenticated が true → クリア
      clearConversation();
      logout();
      return;
    }
    // バックエンドに問い合わせてトークンの有効性を確認
    api.getMe().catch(() => {
      // 401 等 → 無効なトークン → ログアウト
      clearConversation();
      logout();
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return <>{children}</>;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000, // 1分
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthGuard>{children}</AuthGuard>
    </QueryClientProvider>
  );
}
