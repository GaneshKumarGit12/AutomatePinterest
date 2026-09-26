import axios from 'axios';
import { RunConfig, RunState, ProductDeal } from '../types/index.ts';

const API_BASE = ''; // Talks to current host (or proxy port 8000 / 3001)

const client = axios.create({
  baseURL: API_BASE,
  timeout: 120000, // 2 minutes to prevent premature 30000ms timeouts on browser automation
});

export const api = {
  // Get engine status
  getStatus: async () => {
    const res = await client.get('/api/status');
    return res.data;
  },

  // Get paginated deals (6 products per page)
  getDeals: async (page: number = 1, pageSize: number = 6): Promise<{
    page: number;
    pageSize: number;
    totalPages: number;
    totalProducts: number;
    deals: ProductDeal[];
  }> => {
    const res = await client.get(`/api/deals?page=${page}&page_size=${pageSize}`);
    return res.data;
  },

  // Sync deals from WorldNewzs live API
  syncDeals: async () => {
    const res = await client.post('/api/deals/sync');
    return res.data;
  },

  // Start 11-step automation run across page range
  startRun: async (config: {
    startPage: number;
    endPage?: number;
    pages?: number;
    collaborators?: string[];
    startCardIndex?: number;
    startDealNumber?: number;
  }) => {
    const res = await client.post('/api/automation/start', config);
    return res.data;
  },

  // Stop active automation run
  stopRun: async () => {
    const res = await client.post('/api/automation/stop');
    return res.data;
  },

  // Trigger login window
  triggerLogin: async () => {
    const res = await client.post('/api/auth/login');
    return res.data;
  },

  // Sync Edge session
  syncEdgeSession: async () => {
    const res = await client.post('/api/auth/sync-edge');
    return res.data;
  },

  // Get generated PDF reports
  getReports: async () => {
    const res = await client.get('/api/reports');
    return res.data;
  },

  getDownloadUrl: (filename: string) => `/api/reports/download/${encodeURIComponent(filename)}`,

  // Social Media Hub (Twitter @ganeshkumard1 & Facebook Worldnewzs)
  shareToSocial: async (payload: {
    deals: any[];
    platform: 'twitter' | 'facebook' | 'both';
    enablePacing?: boolean;
    pacingMinutes?: number;
    dryRun?: boolean;
  }) => {
    const res = await client.post('/api/social/share', payload);
    return res.data;
  },

  getSocialPreview: async (deals: any[]) => {
    const res = await client.post('/api/social/preview', { deals });
    return res.data;
  },

  getSocialHistory: async () => {
    const res = await client.get('/api/social/history');
    return res.data;
  },

  checkSocialSession: async () => {
    const res = await client.post('/api/social/check-session');
    return res.data;
  },

  loginSocial: async () => {
    const res = await client.post('/api/social/login');
    return res.data;
  },

  getSocialSessionStatus: async () => {
    const res = await client.get('/api/social/session-status');
    return res.data;
  },

  // Pinterest → Facebook Page & Group Share
  pinterestFacebookShare: async (payload: {
    pinCount: number;
    delaySeconds: number;
    targetBoardUrl?: string;
    specificPinIds?: string[];
    destination?: 'both' | 'page' | 'group';
  }) => {
    const res = await client.post('/api/social/pinterest-facebook-share', payload);
    return res.data;
  },

  getPinterestFacebookStatus: async () => {
    const res = await client.get('/api/social/pinterest-facebook-status');
    return res.data;
  },

  launchEdgeFacebook: async () => {
    const res = await client.post('/api/social/launch-edge-facebook');
    return res.data;
  },

  // Get lazy-loadable Pinterest pins from Dhanvi Collection
  getFacebookPins: async (page: number = 1, pageSize: number = 12, filter: string = 'pending', forceRefresh: boolean = false) => {
    const res = await client.get(`/api/social/facebook-pins?page=${page}&pageSize=${pageSize}&filter=${filter}&forceRefresh=${forceRefresh}`);
    return res.data;
  },

  // Purge already-posted Facebook pins from cache and UI
  cleanPostedPins: async () => {
    const res = await client.post('/api/social/clean-posted-pins');
    return res.data;
  },

  getExportExcelUrl: () => '/api/social/export-excel',
  getExportPdfUrl: () => '/api/social/export-pdf',
  getLiveFrameUrl: () => `/api/social/live-frame?t=${Date.now()}`,
};

