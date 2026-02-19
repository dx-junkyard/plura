'use client';

/**
 * PLURA - Project Lobby Page
 * Flash Team Formation: チーム結成後のプロジェクトロビー画面
 * APIからプロジェクトデータを取得して表示する
 */
import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Users,
  Zap,
  Send,
  Sparkles,
  User,
  MessageSquare,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import type { ProjectResponse, TeamMember } from '@/types';

interface ChatMessage {
  id: string;
  sender: string;
  content: string;
  timestamp: string;
  isSystem?: boolean;
}

export default function ProjectLobbyPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;

  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  useEffect(() => {
    const fetchProject = async () => {
      try {
        setLoading(true);
        const data = await api.getProject(projectId);
        setProject(data);

        // 初期システムメッセージを生成
        const initMessages: ChatMessage[] = [
          {
            id: 'sys-1',
            sender: 'PLURA AI',
            content: `Flash Team「${data.name}」が結成されました。プロジェクトの目標と各メンバーの役割を確認してください。`,
            timestamp: new Date(data.created_at).toLocaleString('ja-JP'),
            isSystem: true,
          },
        ];
        if (data.reason) {
          initMessages.push({
            id: 'sys-2',
            sender: 'PLURA AI',
            content: data.reason,
            timestamp: new Date(data.created_at).toLocaleString('ja-JP'),
            isSystem: true,
          });
        }
        setMessages(initMessages);
      } catch (err) {
        console.error('Failed to fetch project:', err);
        setError('プロジェクトが見つかりませんでした');
      } finally {
        setLoading(false);
      }
    };

    fetchProject();
  }, [projectId]);

  const handleSendMessage = () => {
    if (!chatInput.trim()) return;

    const newMessage: ChatMessage = {
      id: String(Date.now()),
      sender: 'あなた',
      content: chatInput,
      timestamp: new Date().toLocaleString('ja-JP'),
    };

    setMessages((prev) => [...prev, newMessage]);
    setChatInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="flex items-center gap-3 text-gray-500">
          <Loader2 className="w-6 h-6 animate-spin" />
          <span>プロジェクトを読み込み中...</span>
        </div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center space-y-4">
          <AlertCircle className="w-12 h-12 text-red-400 mx-auto" />
          <p className="text-gray-600">{error || 'プロジェクトが見つかりません'}</p>
          <button
            onClick={() => router.back()}
            className="text-primary-600 hover:underline text-sm"
          >
            戻る
          </button>
        </div>
      </div>
    );
  }

  const members: TeamMember[] = project.team_members ?? [];
  const memberColors = ['bg-blue-500', 'bg-emerald-500', 'bg-amber-500', 'bg-purple-500', 'bg-rose-500'];

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
                    {project.name}
                  </h1>
                </div>
                <p className="text-xs text-gray-500 mt-0.5">
                  Flash Team • {members.length}名
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className={cn(
                'text-xs px-2 py-1 rounded-full font-medium',
                project.status === 'proposed' && 'bg-yellow-100 text-yellow-700',
                project.status === 'active' && 'bg-green-100 text-green-700',
                project.status === 'completed' && 'bg-blue-100 text-blue-700',
                project.status === 'archived' && 'bg-gray-100 text-gray-500',
              )}>
                {project.status === 'proposed' && '提案中'}
                {project.status === 'active' && 'アクティブ'}
                {project.status === 'completed' && '完了'}
                {project.status === 'archived' && 'アーカイブ'}
              </span>
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
                  {project.description || project.reason || 'AIが分析した各メンバーの専門性と経験を元に、最適なチームを自動編成しました。'}
                </p>
                {project.topics.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {project.topics.map((topic) => (
                      <span
                        key={topic}
                        className="text-xs px-2.5 py-1 bg-primary-100 text-primary-700 rounded-full font-medium"
                      >
                        {topic}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* メンバーリスト */}
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100">
                <div className="flex items-center gap-2 text-gray-700">
                  <Users className="w-4 h-4" />
                  <span className="text-sm font-semibold">
                    チームメンバー ({members.length})
                  </span>
                </div>
              </div>
              <div className="divide-y divide-gray-100">
                {members.map((member, index) => (
                  <div key={member.user_id} className="p-4 flex items-center gap-3">
                    <div className="relative">
                      <div
                        className={cn(
                          'w-12 h-12 rounded-full flex items-center justify-center text-white font-bold',
                          memberColors[index % memberColors.length]
                        )}
                      >
                        {member.avatar_url ? (
                          <img
                            src={member.avatar_url}
                            alt={member.display_name}
                            className="w-full h-full rounded-full object-cover"
                          />
                        ) : (
                          <User className="w-6 h-6" />
                        )}
                      </div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-gray-800">
                        {member.display_name}
                      </p>
                      <p className="text-xs text-primary-600 font-medium">
                        {member.role}
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
                    {members.length}名が参加中
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
