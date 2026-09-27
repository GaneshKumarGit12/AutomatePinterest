/**
 * Shared Singleton EventSource manager for AutomatePinterest.
 * Automatically bridges https://automate-pinterest-eight.vercel.app to the local
 * Playwright/Edge CDP engine (http://localhost:3001) when available.
 */

import { api, ensureApiBase } from './api.ts';

type EventHandler = (data: any) => void;

class SSEClient {
  private eventSource: EventSource | null = null;
  private currentStreamUrl: string = '';
  private listeners: Map<string, Set<EventHandler>> = new Map();
  private reconnectTimer: any = null;
  private reconnectAttempts = 0;

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => {
        this.reconnectAttempts = 0;
        this.connect(true);
      });

      window.addEventListener('api-base-changed', () => {
        this.reconnectAttempts = 0;
        this.connect(true);
      });

      // Handle tab visibility change (reconnect seamlessly if browser suspended background socket)
      document.addEventListener('visibilitychange', () => {
        if (
          document.visibilityState === 'visible' &&
          (!this.eventSource || this.eventSource.readyState === EventSource.CLOSED)
        ) {
          this.connect();
        }
      });
    }
  }

  public async connect(forceReconnect: boolean = false) {
    if (typeof window === 'undefined') return;

    await ensureApiBase();
    const targetUrl = `${api.getApiBase()}/api/automation/stream`;

    if (
      !forceReconnect &&
      this.eventSource &&
      this.currentStreamUrl === targetUrl &&
      (this.eventSource.readyState === EventSource.OPEN ||
        this.eventSource.readyState === EventSource.CONNECTING)
    ) {
      return;
    }

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.eventSource) {
      try {
        this.eventSource.close();
      } catch (_) {}
      this.eventSource = null;
    }

    try {
      this.currentStreamUrl = targetUrl;
      this.eventSource = new EventSource(targetUrl);

      this.eventSource.onopen = () => {
        this.reconnectAttempts = 0;
      };

      this.eventSource.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          this.emit('message', payload);
        } catch (_) {}
      };

      this.eventSource.onerror = () => {
        if (this.eventSource) {
          this.eventSource.close();
          this.eventSource = null;
        }

        const delay = Math.min(30000, 2000 * Math.pow(1.5, this.reconnectAttempts));
        this.reconnectAttempts++;

        this.reconnectTimer = setTimeout(() => {
          this.connect();
        }, delay);
      };

      // Register all known custom SSE event channels
      const knownEvents = [
        'log',
        'step_log',
        'step_update',
        'state_change',
        'run_complete',
        'social_log',
        'social_card_status',
        'fb_share_step',
        'fb_share_update',
        'fb_live_frame',
        'fb_share_complete',
      ];

      knownEvents.forEach((eventType) => {
        this.eventSource!.addEventListener(eventType, (e: any) => {
          try {
            const parsed = JSON.parse(e.data);
            this.emit(eventType, parsed);
          } catch (_) {}
        });
      });
    } catch (err) {
      console.warn('[SSEClient] Connection init error:', err);
    }
  }

  public subscribe(eventType: string, handler: EventHandler): () => void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(handler);

    // Ensure connection is established
    this.connect();

    // Return cleanup unsubscribe function
    return () => {
      const handlers = this.listeners.get(eventType);
      if (handlers) {
        handlers.delete(handler);
        if (handlers.size === 0) {
          this.listeners.delete(eventType);
        }
      }
    };
  }

  private emit(eventType: string, data: any) {
    const handlers = this.listeners.get(eventType);
    if (handlers) {
      handlers.forEach((fn) => {
        try {
          fn(data);
        } catch (err) {
          console.error(`[SSEClient] Error in listener for "${eventType}":`, err);
        }
      });
    }
  }

  public close() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}

export const sseClient = new SSEClient();
