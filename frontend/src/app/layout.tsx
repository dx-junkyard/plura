import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Providers } from './providers';
import { Navigation } from '@/components/Navigation';
import { RecommendationPanel } from '@/components/RecommendationPanel';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
});

export const metadata: Metadata = {
  title: 'PLURA - 自分だけのノートから、みんなの集合知へ',
  description:
    '個人が自分のために行う「記録」を、組織全体の「集合知」へと自然に変換するナレッジ共創プラットフォーム',
  keywords: ['ナレッジマネジメント', '集合知', 'メモ', '記録', 'チーム'],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body className={`${inter.variable} font-sans antialiased`}>
        <Providers>
          <Navigation />
          <main className="pt-14 min-h-screen bg-gray-50">{children}</main>
          <RecommendationPanel />
        </Providers>
      </body>
    </html>
  );
}
