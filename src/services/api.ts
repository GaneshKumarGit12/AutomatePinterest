import axios from 'axios';
import { ProductDeal } from '../types/index.ts';

const LOCAL_ENGINE_URL = 'http://localhost:3001';

const isRemoteHost =
  typeof window !== 'undefined' &&
  window.location.hostname !== 'localhost' &&
  window.location.hostname !== '127.0.0.1';

let activeApiBase = '';
let localEngineConfirmed = !isRemoteHost;
let probePromise: Promise<string> | null = null;

function setActiveApiBase(nextBase: string) {
  if (activeApiBase !== nextBase) {
    activeApiBase = nextBase;
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('api-base-changed', { detail: activeApiBase }));
    }
  }
}

export async function ensureApiBase(): Promise<string> {
  if (!isRemoteHost) {
    return '';
  }
  if (localEngineConfirmed && activeApiBase === LOCAL_ENGINE_URL) {
    return activeApiBase;
  }
  if (probePromise) {
    return probePromise;
  }

  probePromise = axios
    .get(`${LOCAL_ENGINE_URL}/api/status`, { timeout: 2500 })
    .then((res) => {
      if (res.status === 200 && res.data?.status === 'online') {
        localEngineConfirmed = true;
        setActiveApiBase(LOCAL_ENGINE_URL);
        return LOCAL_ENGINE_URL;
      }
      return activeApiBase;
    })
    .catch(() => {
      localEngineConfirmed = false;
      setActiveApiBase('');
      return '';
    })
    .finally(() => {
      probePromise = null;
    });

  return probePromise;
}

// Kick off initial local engine discovery immediately on load
if (isRemoteHost) {
  ensureApiBase();
}

const client = axios.create({
  timeout: 120000, // 2 minutes to prevent premature timeouts on browser automation
});

client.interceptors.request.use(async (config) => {
  const base = await ensureApiBase();
  config.baseURL = base;
  return config;
});

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    // If local engine stopped mid-session, fall back to cloud relative origin and retry once
    if (
      isRemoteHost &&
      activeApiBase === LOCAL_ENGINE_URL &&
      !error.response &&
      error.config &&
      !error.config.__retriedCloud
    ) {
      localEngineConfirmed = false;
      setActiveApiBase('');
      error.config.__retriedCloud = true;
      error.config.baseURL = '';
      return client.request(error.config);
    }
    return Promise.reject(error);
  }
);

export const api = {
  getApiBase: () => activeApiBase,

  resolveUrl: (path: string) => {
    if (!path) return '';
    if (path.startsWith('http://') || path.startsWith('https://')) return path;
    const normalized = path.startsWith('/') ? path : `/${path}`;
    return `${activeApiBase}${normalized}`;
  },

  // Get engine status
  getStatus: async () => {
    if (isRemoteHost && !localEngineConfirmed) {
      await ensureApiBase();
    }
    const res = await client.get('/api/status');
    return res.data;
  },

  // Get paginated deals (6 products per page)
  getDeals: async (
    page: number = 1,
    pageSize: number = 6
  ): Promise<{
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
    await ensureApiBase();
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

  getDownloadUrl: (filename: string) =>
    `${activeApiBase}/api/reports/download/${encodeURIComponent(filename)}`,

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
    await ensureApiBase();
    const res = await client.post('/api/social/pinterest-facebook-share', payload);
    return res.data;
  },

  getPinterestFacebookStatus: async () => {
    await ensureApiBase();
    const res = await client.get('/api/social/pinterest-facebook-status');
    return res.data;
  },

  stopPinterestFacebookShare: async () => {
    await ensureApiBase();
    const res = await client.post('/api/social/pinterest-facebook-stop');
    return res.data;
  },

  launchEdgeFacebook: async () => {
    const res = await client.post('/api/social/launch-edge-facebook');
    return res.data;
  },

  // Get lazy-loadable Pinterest pins from Dhanvi Collection
  getFacebookPins: async (
    page: number = 1,
    pageSize: number = 12,
    filter: string = 'pending',
    forceRefresh: boolean = false
  ) => {
    const res = await client.get(
      `/api/social/facebook-pins?page=${page}&pageSize=${pageSize}&filter=${filter}&forceRefresh=${forceRefresh}`
    );
    return res.data;
  },

  // Purge already-posted Facebook pins from cache and UI
  cleanPostedPins: async () => {
    const res = await client.post('/api/social/clean-posted-pins');
    return res.data;
  },

  getExportExcelUrl: () => `${activeApiBase}/api/social/export-excel`,
  getExportPdfUrl: () => `${activeApiBase}/api/social/export-pdf`,
  getLiveFrameUrl: () => `${activeApiBase}/api/social/live-frame?t=${Date.now()}`,
  getProofUrl: (filename: string) =>
    `${activeApiBase}/api/social/proof/${encodeURIComponent(filename)}`,
};
