'use client';

/**
 * PLURA - Project Lobby Page
 * Flash Team Formation: チーム結成後のプロジェクトロビー画面
 */
import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Users,
  Zap,
  Send,
  Sparkles,
  User,
  MessageSquare,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface MockMessage {
  id: string;
  sender: string;
  content: string;
  timestamp: string;
  isSystem?: boolean;
}

const MOCK_MESSAGES: MockMessage[] = [
  {
    id: '1',
    sender: 'PLURA AI',
    content:
      'Flash Team が結成されました。プロジェクトの目標と各メンバーの役割を確認してください。',
    timestamp: 'たった今',
    isSystem: true,
  },
  {
    id: '2',
    sender: 'PLURA AI',
    content:
      'AIの分析により、このチームは技術・デザイン・ドメイン知識の3領域をカバーしています。それぞれの強みを活かした協働が期待されます。',
    timestamp: 'たった今',
    isSystem: true,
  },
];

const MOCK_MEMBERS = [
  {
    name: 'Takeshi M.',
    role: 'エンジニア',
    specialty: 'バックエンド / インフラ',
    color: 'bg-blue-500',
    status: 'online',
  },
  {
    name: 'Yuki S.',
    role: 'デザイナー',
    specialty: 'UX / プロダクトデザイン',
    color: 'bg-emerald-500',
    status: 'online',
  },
  {
    name: 'Kenji A.',
    role: 'ドメインエキスパート',
    specialty: '業界知識 / 顧客理解',
    color: 'bg-amber-500',
    status: 'away',
  },
];

export default function ProjectLobbyPage() {
  const params = useParams();
  const router = useRouter();
  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState<MockMessage[]>(MOCK_MESSAGES);

  const projectId = params.id as string;

  const handleSendMessage = () => {
    if (!chatInput.trim()) return;

    const newMessage: MockMessage = {
      id: String(messages.length + 1),
      sender: 'あなた',
      content: chatInput,
      timestamp: 'たった今',
    };

    setMessages([...messages, newMessage]);
    setChatInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* ヘッダー */}
      <div className="bg-white border-b border-gray-200 sticky top-14 z-30">
        <div className="max-w-6xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={() => router.back()}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <ArrowLeft className="w-5 h-5 text-gray-600" />
              </button>
              <div>
                <div className="flex items-center gap-2">
                  <Zap className="w-5 h-5 text-primary-500" />
                  <h1 className="text-lg font-bold text-gray-900">
                    Flash Team Project
                  </h1>
                </div>
                <p className="text-xs text-gray-500 mt-0.5">
                  AI-powered team formation
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400">Project ID: {projectId.slice(0, 8)}...</span>
            </div>
          </div>
        </div>
      </div>

      {/* メインコンテンツ */}
      <div className="max-w-6xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 左カラム: プロジェクト情報 + メンバー */}
          <div className="space-y-6">
            {/* プロジェクト概要 */}
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="bg-gradient-to-r from-primary-600 to-primary-500 px-4 py-3">
                <div className="flex items-center gap-2 text-white">
                  <Sparkles className="w-4 h-4" />
                  <span className="text-sm font-semibold">AI生成プロジェクト概要</span>
                </div>
              </div>
              <div className="p-4 space-y-3">
                <p className="text-sm text-gray-700 leading-relaxed">
                  このプロジェクトは、AIが分析した各メンバーの専門性と経験を元に自動生成されました。
                  技術力、デザイン思考、ドメイン知識を組み合わせることで、従来の手動チーム編成では
                  見落とされがちなシナジーを最大化します。
                </p>
                <div className="flex flex-wrap gap-1.5">
                  <span className="text-xs px-2.5 py-1 bg-primary-100 text-primary-700 rounded-full font-medium">
                    技術
                  </span>
                  <span className="text-xs px-2.5 py-1 bg-primary-100 text-primary-700 rounded-full font-medium">
                    デザイン
                  </span>
                  <span className="text-xs px-2.5 py-1 bg-primary-100 text-primary-700 rounded-full font-medium">
                    ドメイン知識
                  </span>
                </div>
              </div>
            </div>

            {/* メンバーリスト */}
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100">
                <div className="flex items-center gap-2 text-gray-700">
                  <Users className="w-4 h-4" />
                  <span className="text-sm font-semibold">
                    チームメンバー ({MOCK_MEMBERS.length})
                  </span>
                </div>
              </div>
              <div className="divide-y divide-gray-100">
                {MOCK_MEMBERS.map((member) => (
                  <div key={member.name} className="p-4 flex items-center gap-3">
                    <div className="relative">
                      <div
                        className={cn(
                          'w-12 h-12 rounded-full flex items-center justify-center text-white font-bold',
                          member.color
                        )}
                      >
                        <User className="w-6 h-6" />
                      </div>
                      {/* オンラインステータス */}
                      <div
                        className={cn(
                          'absolute bottom-0 right-0 w-3.5 h-3.5 rounded-full border-2 border-white',
                          member.status === 'online'
                            ? 'bg-green-400'
                            : 'bg-yellow-400'
                        )}
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-gray-800">
                        {member.name}
                      </p>
                      <p className="text-xs text-primary-600 font-medium">
                        {member.role}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {member.specialty}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 右カラム: チャット */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden flex flex-col h-[600px]">
              {/* チャットヘッダー */}
              <div className="px-4 py-3 border-b border-gray-100">
                <div className="flex items-center gap-2 text-gray-700">
                  <MessageSquare className="w-4 h-4" />
                  <span className="text-sm font-semibold">プロジェクトチャット</span>
                  <span className="text-xs text-gray-400 ml-auto">
                    {MOCK_MEMBERS.length}名が参加中
                  </span>
                </div>
              </div>

              {/* メッセージ一覧 */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={cn(
                      'flex gap-3',
                      msg.sender === 'あなた' && 'flex-row-reverse'
                    )}
                  >
                    {/* アバター */}
                    <div
                      className={cn(
                        'w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-white text-xs font-bold',
                        msg.isSystem
                          ? 'bg-primary-500'
                          : msg.sender === 'あなた'
                          ? 'bg-gray-400'
                          : 'bg-emerald-500'
                      )}
                    >
                      {msg.isSystem ? (
                        <Sparkles className="w-4 h-4" />
                      ) : (
                        <User className="w-4 h-4" />
                      )}
                    </div>

                    {/* メッセージバブル */}
                    <div
                      className={cn(
                        'max-w-[70%] rounded-xl px-4 py-2.5',
                        msg.isSystem
                          ? 'bg-primary-50 border border-primary-100'
                          : msg.sender === 'あなた'
                          ? 'bg-gray-100'
                          : 'bg-gray-50 border border-gray-100'
                      )}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span
                          className={cn(
                            'text-xs font-semibold',
                            msg.isSystem
                              ? 'text-primary-600'
                              : 'text-gray-700'
                          )}
                        >
                          {msg.sender}
                        </span>
                        <span className="text-xs text-gray-400">
                          {msg.timestamp}
                        </span>
                      </div>
                      <p className="text-sm text-gray-700 leading-relaxed">
                        {msg.content}
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              {/* 入力エリア */}
              <div className="px-4 py-3 border-t border-gray-100 bg-gray-50">
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="メッセージを入力..."
                    className={cn(
                      'flex-1 px-4 py-2 rounded-lg border border-gray-200',
                      'text-sm text-gray-700 placeholder-gray-400',
                      'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                      'bg-white'
                    )}
                  />
                  <button
                    onClick={handleSendMessage}
                    disabled={!chatInput.trim()}
                    className={cn(
                      'p-2 rounded-lg transition-colors',
                      chatInput.trim()
                        ? 'bg-primary-600 text-white hover:bg-primary-700'
                        : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    )}
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
