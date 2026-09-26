export type StepStatus = 'pending' | 'in_progress' | 'success' | 'failed' | 'skipped';

export interface ProductDeal {
  id: string;
  asin?: string;
  title: string;
  truncatedTitle: string;
  isTruncated: boolean;
  price?: string;
  originalPrice?: string;
  discount?: string;
  tag?: string;
  dealUrl?: string;
  shareUrl?: string;
  imageUrl?: string;
  pageNumber: number;
  cardIndex: number;
  processedAt?: string;
  success?: boolean;
  status?: 'success' | 'failed';
  collaborators?: string[];
  error?: string;
}

export interface RunConfig {
  startPage?: number;
  pages?: number;
  collaborators?: string[];
}

export interface StepLogEntry {
  id: string;
  productId?: string;
  productTitle?: string;
  stepNumber: number;
  stepName: string;
  status: StepStatus;
  startedAt?: string;
  finishedAt?: string;
  durationMs?: number;
  message?: string;
  details?: Record<string, any>;
  timestamp?: string;
}

export interface RunState {
  isRunning: boolean;
  isStopping?: boolean;
  selectedPages: number;
  currentPage: number;
  startPage?: number;
  endPage?: number;
  totalPagesProcessed?: number;
  currentCardIndex: number;
  totalCardsOnCurrentPage?: number;
  totalCardsProcessed: number;
  totalSuccessful?: number;
  totalFailed?: number;
  processedCards?: ProductDeal[];
  currentProductId?: string;
  currentProductTitle?: string;
  currentStepIndex?: number;
  currentStepName?: string;
  startedAt?: string;
  finishedAt?: string;
  completionReason?: 'PAGES_COMPLETED' | 'NO_MORE_PAGES' | 'STOPPED_BY_USER' | 'ERROR';
  latestReportFile?: string;
}

export interface CompletionData {
  startPage: number;
  endPage: number;
  message: string;
  summary: {
    total_cards: number;
    success_count: number;
    failed_count: number;
    pages_count: number;
    start_page: number;
    end_page: number;
    duration_seconds: number;
  };
  report: GeneratedReport;
}

export interface GeneratedReport {
  fileName: string;
  filePath?: string;
  fullPath?: string;
  generatedAt?: string;
  createdAt?: string;
  sizeBytes: number;
}

export interface AutomationConfig {
  worldNewzsUrl: string;
  pinterestBaseUrl: string;
  pinterestEmail?: string;
  reportOutputDir: string;
  collaborators: string[];
}
