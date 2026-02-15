'use client';

/**
 * PLURA - Login Page
 */
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useAuthStore, useConversationStore } from '@/lib/store';

export default function LoginPage() {
  const router = useRouter();
  const { isAuthenticated, setUser } = useAuthStore();
  const clearConversation = useConversationStore((s) => s.clearConversation);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // 認証済みならトップページへリダイレクト
  useEffect(() => {
    if (isAuthenticated) {
      router.replace('/');
    }
  }, [isAuthenticated, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const result = await api.login(email, password);
      clearConversation();
      setUser(result.user);
      router.push('/');
    } catch (err: any) {
      setError(
        err.response?.data?.detail || 'ログインに失敗しました。'
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-xl shadow-lg p-8">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-gray-800">PLURA</h1>
            <p className="text-gray-500 mt-2">
              自分だけのノートから、みんなの集合知へ
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="p-3 bg-red-50 text-red-600 rounded-lg text-sm">
                {error}
              </div>
            )}

            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                メールアドレス
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label
                  htmlFor="password"
                  className="block text-sm font-medium text-gray-700"
                >
                  パスワード
                </label>
                <Link
                  href="/forgot-password"
                  className="text-xs text-primary-600 hover:underline"
                >
                  パスワードを忘れた方（再設定）
                </Link>
              </div>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? 'ログイン中...' : 'ログイン'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-gray-500">
            アカウントをお持ちでない方は{' '}
            <Link
              href="/register"
              className="text-primary-600 hover:underline"
            >
              新規登録
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
