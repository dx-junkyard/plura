/**
 * MINDYARD - Utility Functions
 */
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('ja-JP', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function formatDateTime(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('ja-JP', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'たった今';
  if (diffMins < 60) return `${diffMins}分前`;
  if (diffHours < 24) return `${diffHours}時間前`;
  if (diffDays < 7) return `${diffDays}日前`;
  return formatDate(dateString);
}

export function getEmotionLabel(emotion: string): string {
  const labels: Record<string, string> = {
    frustrated: '焦り',
    angry: '怒り',
    achieved: '達成感',
    anxious: '不安',
    confused: '困惑',
    relieved: '安堵',
    excited: '興奮',
    neutral: '平静',
  };
  return labels[emotion] || emotion;
}

export function getIntentLabel(intent: string): string {
  const labels: Record<string, string> = {
    log: '記録',
    vent: '吐き出し',
    structure: '整理',
  };
  return labels[intent] || intent;
}

export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + '...';
}
