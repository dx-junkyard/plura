// frontend/src/app/reports/[logId]/page.tsx
'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Loader2, Calendar, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '@/lib/api';
import type { RawLog } from '@/types';

export default function ReportPage() {
  const { logId } = useParams();
  const router = useRouter();
  const [log, setLog] = useState<RawLog | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!logId) return;
    const fetchLog = async () => {
      try {
        const data = await api.getLog(Array.isArray(logId) ? logId[0] : logId);
        setLog(data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchLog();
  }, [logId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  if (!log) return <div className="flex items-center justify-center min-h-screen text-gray-500">Report not found.</div>;

  const researchData = log.metadata_analysis?.deep_research || {};
  const content = researchData.details || log.assistant_reply || log.content;
  const summary = researchData.summary || 'サマリーはありません';

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10 px-4 py-3 flex items-center gap-3">
        <button
          onClick={() => router.back()}
          className="p-2 hover:bg-gray-100 rounded-full transition-colors"
        >
          <ArrowLeft className="w-5 h-5 text-gray-600" />
        </button>
        <h1 className="text-lg font-bold text-gray-800 truncate">
          Deep Research Report
        </h1>
      </header>

      {/* Content */}
      <main className="max-w-3xl mx-auto mt-6 px-4 sm:px-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="bg-indigo-50 px-6 py-4 border-b border-indigo-100">
            <div className="flex items-center gap-2 text-indigo-700 font-semibold mb-2">
              <FileText className="w-5 h-5" />
              調査レポート
            </div>
            <p className="text-indigo-900 text-lg font-bold">
              {researchData.topic || '無題の調査'}
            </p>
            <div className="flex items-center gap-2 text-xs text-indigo-600 mt-2">
              <Calendar className="w-3.5 h-3.5" />
              {new Date(log.created_at).toLocaleString()}
            </div>
          </div>

          <div className="p-6 md:p-8 space-y-8">
            {/* Summary Section */}
            <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
              <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-2">
                Executive Summary
              </h2>
              <div className="text-gray-800 leading-relaxed prose prose-sm max-w-none prose-headings:text-gray-700 prose-p:my-1">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {summary}
                </ReactMarkdown>
              </div>
            </div>

            {/* Main Content (Markdown) */}
            <div className="prose prose-indigo max-w-none">
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
