/**
 * MINDYARD - Zustand Store
 * グローバル状態管理
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, RecommendationItem } from '@/types';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  setUser: (user: User | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      logout: () => set({ user: null, isAuthenticated: false }),
    }),
    {
      name: 'mindyard-auth',
    }
  )
);

interface RecommendationState {
  recommendations: RecommendationItem[];
  isVisible: boolean;
  displayMessage: string | null;
  setRecommendations: (items: RecommendationItem[], message: string | null) => void;
  clearRecommendations: () => void;
  hideRecommendations: () => void;
}

export const useRecommendationStore = create<RecommendationState>()((set) => ({
  recommendations: [],
  isVisible: false,
  displayMessage: null,
  setRecommendations: (items, message) =>
    set({
      recommendations: items,
      isVisible: items.length > 0,
      displayMessage: message,
    }),
  clearRecommendations: () =>
    set({
      recommendations: [],
      isVisible: false,
      displayMessage: null,
    }),
  hideRecommendations: () => set({ isVisible: false }),
}));

interface NotificationState {
  pendingProposalCount: number;
  setPendingProposalCount: (count: number) => void;
}

export const useNotificationStore = create<NotificationState>()((set) => ({
  pendingProposalCount: 0,
  setPendingProposalCount: (count) => set({ pendingProposalCount: count }),
}));
