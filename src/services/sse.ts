/**
 * Shared Singleton EventSource manager for AutomatePinterest.
 * Maintains exactly 1 persistent SSE connection across all components,
 * preventing HTTP/1.1 connection starvation (6-connection browser limit)
 * and resolving net::ERR_NETWORK_IO_SUSPENDED errors.
 */

type EventHandler = (data: any) => void;

class SSEClient {
  private eventSource: EventSource | null = null;
  private listeners: Map<string, Set<EventHandler>> = new Map();
  private reconnectTimer: any = null;
  private reconnectAttempts = 0;

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => {
        this.reconnectAttempts = 0;
        this.connect();
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

  public connect() {
    if (typeof window === 'undefined') return;

    if (
      this.eventSource &&
      (this.eventSource.readyState === EventSource.OPEN ||
        this.eventSource.readyState === EventSource.CONNECTING)
    ) {
      return;
    }

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    try {
      this.eventSource = new EventSource('/api/automation/stream');

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
        // When network suspends, closes, or tab sleeps, cleanly close and backoff
        if (this.eventSource) {
          this.eventSource.close();
          this.eventSource = null;
        }

        // Exponential backoff between 2s and 30s
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
