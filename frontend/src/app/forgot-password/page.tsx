'use client';

/**
 * PLURA - パスワード再設定
 * 現在はプレースホルダー。メール送信などの実装は今後対応。
 */
import Link from 'next/link';

export default function ForgotPasswordPage() {
  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-xl shadow-lg p-8">
          <div className="text-center mb-6">
            <h1 className="text-xl font-bold text-gray-800">パスワードを忘れた方</h1>
            <p className="text-gray-500 mt-2 text-sm">
              パスワード再設定機能は準備中です。
              <br />
              お手数ですが、管理者にお問い合わせください。
            </p>
          </div>
          <Link
            href="/login"
            className="block w-full py-3 text-center bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 transition-colors"
          >
            ログイン画面に戻る
          </Link>
        </div>
      </div>
    </div>
  );
}
