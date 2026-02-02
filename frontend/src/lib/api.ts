/**
 * MINDYARD - API Client
 */
import axios, { AxiosInstance } from 'axios';
import type {
  Token,
  User,
  RawLog,
  RawLogListResponse,
  AckResponse,
  InsightCard,
  InsightCardListResponse,
  SharingProposal,
  RecommendationResponse,
} from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || '/api/v1';

class ApiClient {
  private client: AxiosInstance;
  private token: string | null = null;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // リクエストインターセプター
    this.client.interceptors.request.use((config) => {
      if (this.token) {
        config.headers.Authorization = `Bearer ${this.token}`;
      }
      return config;
    });

    // トークンをローカルストレージから復元
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('mindyard_token');
    }
  }

  setToken(token: string | null) {
    this.token = token;
    if (typeof window !== 'undefined') {
      if (token) {
        localStorage.setItem('mindyard_token', token);
      } else {
        localStorage.removeItem('mindyard_token');
      }
    }
  }

  getToken(): string | null {
    return this.token;
  }

  // Auth
  async register(email: string, password: string, display_name?: string): Promise<Token> {
    const { data } = await this.client.post<Token>('/auth/register', {
      email,
      password,
      display_name,
    });
    this.setToken(data.access_token);
    return data;
  }

  async login(email: string, password: string): Promise<Token> {
    const { data } = await this.client.post<Token>('/auth/login', {
      email,
      password,
    });
    this.setToken(data.access_token);
    return data;
  }

  async getMe(): Promise<User> {
    const { data } = await this.client.get<User>('/auth/me');
    return data;
  }

  logout() {
    this.setToken(null);
  }

  // Logs (Layer 1)
  async createLog(content: string, content_type: string = 'text'): Promise<AckResponse> {
    const { data } = await this.client.post<AckResponse>('/logs/', {
      content,
      content_type,
    });
    return data;
  }

  async getLogs(page: number = 1, page_size: number = 20): Promise<RawLogListResponse> {
    const { data } = await this.client.get<RawLogListResponse>('/logs/', {
      params: { page, page_size },
    });
    return data;
  }

  async getLog(logId: string): Promise<RawLog> {
    const { data } = await this.client.get<RawLog>(`/logs/${logId}`);
    return data;
  }

  async deleteLog(logId: string): Promise<void> {
    await this.client.delete(`/logs/${logId}`);
  }

  async getLogsByMonth(year: number, month: number) {
    const { data } = await this.client.get(`/logs/calendar/${year}/${month}`);
    return data;
  }

  // Insights (Layer 3)
  async getInsights(
    page: number = 1,
    page_size: number = 20,
    topic?: string,
    tag?: string,
    search?: string
  ): Promise<InsightCardListResponse> {
    const { data } = await this.client.get<InsightCardListResponse>('/insights/', {
      params: { page, page_size, topic, tag, search },
    });
    return data;
  }

  async getMyInsights(
    page: number = 1,
    page_size: number = 20,
    status_filter?: string
  ): Promise<InsightCardListResponse> {
    const { data } = await this.client.get<InsightCardListResponse>('/insights/my', {
      params: { page, page_size, status_filter },
    });
    return data;
  }

  async getPendingProposals(): Promise<SharingProposal[]> {
    const { data } = await this.client.get<SharingProposal[]>('/insights/pending');
    return data;
  }

  async decideSharingProposal(insightId: string, approved: boolean): Promise<InsightCard> {
    const { data } = await this.client.post<InsightCard>('/insights/decide', {
      insight_id: insightId,
      approved,
    });
    return data;
  }

  async getInsight(insightId: string): Promise<InsightCard> {
    const { data } = await this.client.get<InsightCard>(`/insights/${insightId}`);
    return data;
  }

  async sendThanks(insightId: string): Promise<{ message: string; thanks_count: number }> {
    const { data } = await this.client.post(`/insights/${insightId}/thanks`);
    return data;
  }

  // Recommendations
  async getRecommendations(
    currentInput: string,
    excludeIds?: string[]
  ): Promise<RecommendationResponse> {
    const { data } = await this.client.post<RecommendationResponse>('/recommendations/', {
      current_input: currentInput,
      exclude_ids: excludeIds,
    });
    return data;
  }
}

export const api = new ApiClient();
