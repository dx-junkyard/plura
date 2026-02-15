'use client';

/**
 * PLURA - Timeline Section
 * AIエージェントページ内に配置する過去ログのタイムライン
 */
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ChevronLeft,
  ChevronRight,
  Loader2,
  Calendar as CalendarIcon,
  Trash2,
} from 'lucide-react';
import { api } from '@/lib/api';
import {
  cn,
  formatDateTime,
  getEmotionLabel,
  getIntentLabel,
} from '@/lib/utils';
import type { RawLog } from '@/types';

const PAGE_SIZE = 20;

/** 分析タイムアウト: 作成から2分以上経過したらスピナーを止める */
const ANALYSIS_TIMEOUT_MS = 2 * 60 * 1000;

/**
 * ログがまだ分析中かどうかを判定する。
 * - STATE インテントのログは構造分析がスキップされるため、
 *   is_structure_analyzed=false でも「分析中」とは扱わない。
 * - 作成から2分以上経過している場合もスピナーを止める（タスク失敗時の無限スピン防止）。
 */
function isStillAnalyzing(log: RawLog): boolean {
  // 両方完了していれば問題なし
  if (log.is_analyzed && log.is_structure_analyzed) return false;

  // タイムアウト: 古すぎるログは分析完了扱いにする
  const age = Date.now() - new Date(log.created_at).getTime();
  if (age > ANALYSIS_TIMEOUT_MS) return false;

  // 文脈分析（context_analyzer）がまだなら分析中
  if (!log.is_analyzed) return true;

  // 構造分析について: STATE インテントはスキップされるので分析中ではない
  if (log.intent === 'state') return false;

  // それ以外で構造分析が未完了なら分析中
  return !log.is_structure_analyzed;
}

/** ログ一覧を thread_id でグループ化し、スレッドごとにまとめる（先頭ログ基準でソート） */
function groupLogsByThread(items: RawLog[]): { threadKey: string; logs: RawLog[] }[] {
  const byThread = new Map<string, RawLog[]>();
  for (const log of items) {
    const key = log.thread_id ?? log.id;
    if (!byThread.has(key)) byThread.set(key, []);
    byThread.get(key)!.push(log);
  }
  const threads = Array.from(byThread.entries()).map(([threadKey, logs]) => {
    const sorted = [...logs].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    );
    return { threadKey, logs: sorted };
  });
  threads.sort((a, b) => {
    const aLast = new Date(a.logs[a.logs.length - 1].created_at).getTime();
    const bLast = new Date(b.logs[b.logs.length - 1].created_at).getTime();
    return bLast - aLast;
  });
  return threads;
}

interface TimelineSectionProps {
  selectedLogId?: string | null;
  onSelectLog?: (logId: string) => void;
}

export function TimelineSection({ selectedLogId, onSelectLog }: TimelineSectionProps) {
  const [page, setPage] = useState(1);
  const [deletingThread, setDeletingThread] = useState<string | null>(null);
  const queryClient = useQueryClient();

  /** スレッド内の全ログを削除 */
  const handleDeleteThread = async (
    e: React.MouseEvent,
    threadKey: string,
    logs: RawLog[]
  ) => {
    e.stopPropagation(); // 親の onClick（ログ選択）を発火させない
    if (!confirm(`このスレッド（${logs.length}件）を削除しますか？`)) return;

    setDeletingThread(threadKey);
    try {
      await Promise.all(logs.map((log) => api.deleteLog(log.id)));
      queryClient.invalidateQueries({ queryKey: ['logs'] });
    } catch (err) {
      console.error('Failed to delete thread:', err);
    } finally {
      setDeletingThread(null);
    }
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ['logs', page],
    queryFn: () => api.getLogs(page, PAGE_SIZE),
    refetchInterval: (query) => {
      const items = query.state.data?.items;
      if (items?.some((log) => isStillAnalyzing(log))) {
        return 3000;
      }
      return false;
    },
  });

  const threads = data?.items ? groupLogsByThread(data.items) : [];

  return (
    <section className="flex flex-col h-full">
      <div className="shrink-0 px-4 py-3 border-b border-gray-200 bg-gray-50/80">
        <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <CalendarIcon className="w-4 h-4 text-gray-500" />
          タイムライン
        </h2>
        <p className="text-xs text-gray-500 mt-0.5">
          過去の記録を振り返れます
        </p>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-3">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
          </div>
        ) : error ? (
          <p className="text-center py-6 text-sm text-red-500">
            データの取得に失敗しました
          </p>
        ) : threads.length === 0 ? (
          <div className="text-center py-6">
            <CalendarIcon className="w-10 h-10 text-gray-300 mx-auto mb-2" />
            <p className="text-sm text-gray-500">まだ記録がありません</p>
          </div>
        ) : (
          <>
            <ul className="space-y-3">
              {threads.map(({ threadKey, logs }) => {
                const root = logs[0];
                const isSelected = selectedLogId === root.id;
                const count = logs.length;
                // スレッド内の最新の構造的課題を取得（振り返りの要約表示用）
                const latestStructuralIssue = [...logs]
                  .reverse()
                  .find((l) => l.structural_analysis?.updated_structural_issue)
                  ?.structural_analysis?.updated_structural_issue;
                return (
                  <li key={threadKey} className="group relative">
                    <button
                      type="button"
                      onClick={() => onSelectLog?.(root.id)}
                      className={cn(
                        'w-full text-left rounded-lg border p-3 pr-9 transition-colors',
                        isSelected
                          ? 'border-primary-300 bg-primary-50/80 ring-1 ring-primary-200'
                          : 'border-gray-100 hover:border-gray-200 hover:bg-gray-50/50'
                      )}
                    >
                      {latestStructuralIssue ? (
                        <p className="text-sm text-gray-800 line-clamp-2 font-medium">
                          {latestStructuralIssue}
                        </p>
                      ) : (
                        <p className="text-sm text-gray-800 whitespace-pre-wrap line-clamp-3">
                          {root.content}
                        </p>
                      )}
                      {count > 1 && (
                        <p className="text-xs text-gray-500 mt-1">
                          {count}件のやりとり
                        </p>
                      )}
                      {isStillAnalyzing(root) && (
                        <div className="flex items-center gap-1.5 text-xs text-blue-600 mt-2">
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>
                            {!root.is_analyzed
                              ? '文脈を分析中...'
                              : '構造を分析中...'}
                          </span>
                        </div>
                      )}
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {root.intent && (
                          <span className="text-xs px-1.5 py-0.5 bg-private-100 text-private-700 rounded-full">
                            {getIntentLabel(root.intent)}
                          </span>
                        )}
                        {root.emotions?.slice(0, 2).map((emotion) => (
                          <span
                            key={emotion}
                            className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded-full"
                          >
                            {getEmotionLabel(emotion)}
                          </span>
                        ))}
                        {root.topics?.slice(0, 2).map((topic) => (
                          <span
                            key={topic}
                            className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded-full"
                          >
                            {topic}
                          </span>
                        ))}
                      </div>
                      <div className="text-xs text-gray-400 mt-1.5">
                        {formatDateTime(logs[logs.length - 1].created_at)}
                      </div>
                    </button>
                    {/* 削除ボタン（ホバーで表示） */}
                    <button
                      type="button"
                      onClick={(e) => handleDeleteThread(e, threadKey, logs)}
                      disabled={deletingThread === threadKey}
                      className="absolute top-2 right-2 p-1.5 rounded-md text-gray-400 opacity-0 group-hover:opacity-100 hover:bg-red-50 hover:text-red-500 transition-all disabled:opacity-50"
                      title="このスレッドを削除"
                    >
                      {deletingThread === threadKey ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>

            {data && data.total > PAGE_SIZE && (
              <div className="flex justify-center items-center gap-2 mt-4 pt-3 border-t border-gray-100">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="p-1.5 rounded-md border border-gray-200 text-gray-600 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="text-xs text-gray-500">
                  {page} / {Math.ceil(data.total / PAGE_SIZE)}
                </span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page >= Math.ceil(data.total / PAGE_SIZE)}
                  className="p-1.5 rounded-md border border-gray-200 text-gray-600 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
