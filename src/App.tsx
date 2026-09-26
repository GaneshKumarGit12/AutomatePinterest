import React, { useState, useEffect, lazy, Suspense } from 'react';
import {
  ThemeProvider,
  createTheme,
  CssBaseline,
  Container,
  Box,
  AppBar,
  Toolbar,
  Typography,
  Chip,
  CircularProgress,
  IconButton,
  Tooltip,
  Snackbar,
  Alert,
  Paper,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
} from '@mui/material';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import WifiIcon from '@mui/icons-material/Wifi';
import WifiOffIcon from '@mui/icons-material/WifiOff';
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';
import SyncIcon from '@mui/icons-material/Sync';
import LaunchIcon from '@mui/icons-material/Launch';
import StopIcon from '@mui/icons-material/Stop';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import DownloadIcon from '@mui/icons-material/Download';
import { RunState, StepLogEntry, ProductDeal, CompletionData } from './types/index.ts';
import { api } from './services/api.ts';
import { sseClient } from './services/sse.ts';

// Lazy-loaded components for optimal performance
const PageDeckView = lazy(() => import('./components/PageDeckView.tsx'));
const ExecutionPipeline = lazy(() => import('./components/ExecutionPipeline.tsx'));
const SocialMediaHub = lazy(() => import('./components/SocialMediaHub.tsx'));
const ActivityLog = lazy(() => import('./components/ActivityLog.tsx'));
const ReportManager = lazy(() => import('./components/ReportManager.tsx'));

export const App: React.FC = () => {
  const [darkMode, setDarkMode] = useState<boolean>(false);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [selectedPage, setSelectedPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(265);
  const [isCompletionModalOpen, setIsCompletionModalOpen] = useState<boolean>(false);
  const [completionData, setCompletionData] = useState<CompletionData | null>(null);
  const [runState, setRunState] = useState<RunState>({
    isRunning: false,
    isStopping: false,
    selectedPages: 1,
    currentPage: 1,
    totalPagesProcessed: 0,
    currentCardIndex: 0,
    totalCardsOnCurrentPage: 6,
    totalCardsProcessed: 0,
    totalSuccessful: 0,
    totalFailed: 0,
  });
  const [stepLogs, setStepLogs] = useState<StepLogEntry[]>([]);
  const [liveLogs, setLiveLogs] = useState<Array<{ message: string; level: string; timestamp: string }>>([]);
  const [toast, setToast] = useState<{ message: string; severity: 'success' | 'info' | 'error' } | null>(null);
  const [currentDeals, setCurrentDeals] = useState<ProductDeal[]>([]);

  const theme = createTheme({
    palette: {
      mode: darkMode ? 'dark' : 'light',
      primary: {
        main: '#E60023', // Pinterest signature red
      },
      secondary: {
        main: '#2563EB',
      },
      background: {
        default: darkMode ? '#0B0F17' : '#F8FAFC',
        paper: darkMode ? '#161F30' : '#FFFFFF',
      },
    },
    typography: {
      fontFamily: '"Inter", "Roboto", "Segoe UI", sans-serif',
    },
    shape: {
      borderRadius: 12,
    },
  });

  const checkStatus = async () => {
    try {
      const data = await api.getStatus();
      if (data && data.runState) {
        setRunState((prev) => ({ ...prev, ...data.runState }));
      }
      setIsConnected(true);
    } catch {
      setIsConnected(false);
    }
  };

  useEffect(() => {
    checkStatus();
    const interval = setInterval(checkStatus, 4000);

    // Connect to Server-Sent Events (SSE) stream via shared singleton client
    const unsubs = [
      sseClient.subscribe('message', (payload: any) => {
        if (payload.level && payload.message) {
          setLiveLogs((prev) => [...prev.slice(-400), payload]);
        }
      }),
      sseClient.subscribe('log', (log: any) => {
        setLiveLogs((prev) => [...prev.slice(-400), log]);
      }),
      sseClient.subscribe('step_log', (step: any) => {
        setStepLogs((prev) => {
          const idx = prev.findIndex((s) => s.id === step.id);
          if (idx !== -1) {
            const copy = [...prev];
            copy[idx] = step;
            return copy;
          }
          return [...prev, step];
        });
      }),
      sseClient.subscribe('step_update', (data: any) => {
        setRunState((prev) => ({
          ...prev,
          currentPage: data.page,
          currentCardIndex: data.cardIndex,
          currentProductTitle: data.card?.truncatedTitle,
        }));
      }),
      sseClient.subscribe('state_change', (data: any) => {
        setRunState((prev) => ({ ...prev, isRunning: data.isRunning }));
      }),
      sseClient.subscribe('run_complete', (data: any) => {
        setCompletionData(data);
        setIsCompletionModalOpen(true);
        setRunState((prev) => ({ ...prev, isRunning: false }));
        setToast({
          message: data.message || `Automate process between page ${data.startPage || 1} to ${data.endPage || 1} completed`,
          severity: 'success',
        });
      }),
    ];

    return () => {
      clearInterval(interval);
      unsubs.forEach((unsub) => unsub());
    };
  }, []);

  useEffect(() => {
    api
      .getDeals(selectedPage, 6)
      .then((res) => {
        if (res && res.deals) {
          setCurrentDeals(res.deals);
          if (res.totalPages) {
            setTotalPages(res.totalPages);
          }
        }
      })
      .catch(() => {});
  }, [selectedPage]);

  const handleStartForPage = async (page: number) => {
    try {
      setToast({
        message: `Starting 11-step automation for Page ${page} (6 Deal Cards)...`,
        severity: 'info',
      });
      await api.startRun({ startPage: page, pages: 1 });
      setRunState((prev) => ({ ...prev, isRunning: true, currentPage: page, startPage: page, endPage: page }));
    } catch (err: any) {
      setToast({ message: `Failed to start: ${err.message}`, severity: 'error' });
    }
  };

  const handleStartForRange = async (startPage: number, endPage: number, startDealNumber?: number) => {
    try {
      const pageCount = endPage - startPage + 1;
      const dealMsg = startDealNumber ? ` (resuming from Deal #${startDealNumber})` : '';
      setToast({
        message: `Starting 11-step automation for Page ${startPage} to ${endPage} (${pageCount * 6} Deals across ${pageCount} pages)${dealMsg}...`,
        severity: 'info',
      });
      await api.startRun({ startPage, endPage, startDealNumber });
      setRunState((prev) => ({
        ...prev,
        isRunning: true,
        currentPage: startPage,
        startPage,
        endPage,
        selectedPages: pageCount,
      }));
    } catch (err: any) {
      setToast({ message: `Failed to start: ${err.message}`, severity: 'error' });
    }
  };

  const handleStop = async () => {
    try {
      await api.stopRun();
      setToast({ message: 'Stopping automation loop...', severity: 'info' });
      setRunState((prev) => ({ ...prev, isRunning: false }));
    } catch (err: any) {
      setToast({ message: `Failed to stop: ${err.message}`, severity: 'error' });
    }
  };

  const handleLoginOpen = async () => {
    window.open('https://www.pinterest.com/login', '_blank');
    try {
      await api.triggerLogin();
      setToast({ message: 'Opened Pinterest Login. Please sign in with Google.', severity: 'info' });
    } catch (_) {}
  };

  const handleSyncEdge = async () => {
    try {
      const res = await api.syncEdgeSession();
      setToast({ message: res.message, severity: res.success ? 'success' : 'info' });
    } catch (err: any) {
      setToast({ message: `Sync note: ${err.message}`, severity: 'error' });
    }
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', bgcolor: 'background.default' }}>
        {/* Navigation Bar */}
        <AppBar
          position="static"
          elevation={1}
          sx={{
            bgcolor: darkMode ? '#1E293B' : '#FFFFFF',
            color: darkMode ? '#F8FAFC' : '#0F172A',
            borderBottom: '1px solid #E2E8F0',
          }}
        >
          <Toolbar sx={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 1.5, py: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <Box sx={{ bgcolor: '#E60023', p: 0.9, borderRadius: 2, display: 'flex', color: '#fff' }}>
                <AutoFixHighIcon fontSize="medium" />
              </Box>
              <Box>
                <Typography variant="h6" fontWeight={800} sx={{ letterSpacing: -0.5, lineHeight: 1.2 }}>
                  AutomatePinterest (Python FastAPI + Browser-Use CDP)
                </Typography>
                <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 500 }}>
                  Target Account: Dhanvi Collections (in.pinterest.com/ganeshkumardevarasetty)
                </Typography>
              </Box>
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
              <Chip
                icon={isConnected ? <WifiIcon fontSize="small" /> : <WifiOffIcon fontSize="small" />}
                label={isConnected ? 'FastAPI Backend Online' : 'Connecting Backend...'}
                color={isConnected ? 'success' : 'warning'}
                size="small"
                variant="outlined"
                sx={{ fontWeight: 700 }}
              />

              <Button
                variant="outlined"
                size="small"
                startIcon={<SyncIcon />}
                onClick={handleSyncEdge}
                sx={{ textTransform: 'none', fontWeight: 700, borderRadius: 2 }}
              >
                Sync Edge Session
              </Button>

              <Button
                variant="contained"
                size="small"
                startIcon={<LaunchIcon />}
                onClick={handleLoginOpen}
                sx={{
                  bgcolor: '#E60023',
                  textTransform: 'none',
                  fontWeight: 700,
                  borderRadius: 2,
                  '&:hover': { bgcolor: '#be123c' },
                }}
              >
                Open Login Window
              </Button>

              <Tooltip title={darkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}>
                <IconButton onClick={() => setDarkMode(!darkMode)} color="inherit" size="small">
                  {darkMode ? <Brightness7Icon /> : <Brightness4Icon />}
                </IconButton>
              </Tooltip>
            </Box>
          </Toolbar>
        </AppBar>

        {/* Main Content */}
        <Container maxWidth="xl" sx={{ py: 3.5, flexGrow: 1 }}>
          <Suspense
            fallback={
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 10 }}>
                <CircularProgress color="primary" />
              </Box>
            }
          >
            {/* Section 1: Pagewise Deals Selector & Card Grid */}
            <PageDeckView
              selectedPage={selectedPage}
              onPageChange={(p) => setSelectedPage(p)}
              runState={runState}
              onStartForPage={handleStartForPage}
              onStartForRange={handleStartForRange}
              onSync={async () => {
                const res = await api.getDeals(selectedPage, 6);
                if (res && res.deals) setCurrentDeals(res.deals);
              }}
            />

            {/* Section 1: 11-Step Interactive Execution Pipeline */}
            <ExecutionPipeline runState={runState} stepLogs={stepLogs} />

            {/* Facebook Automation Hub (Dhanvi Collection → Amazon Affiliate Group) */}
            <SocialMediaHub />

            {/* Daily PDF Reports Manager */}
            <ReportManager />

            {/* Real-time Streaming Activity Console */}
            <ActivityLog processedDeals={runState.processedCards || []} stepLogs={stepLogs} liveLogs={liveLogs} />
          </Suspense>
        </Container>

        {/* Completion Modal Popup: 'Automate process between page X to Y completed' */}
        <Dialog
          open={isCompletionModalOpen}
          onClose={() => setIsCompletionModalOpen(false)}
          maxWidth="sm"
          fullWidth
          PaperProps={{
            sx: {
              borderRadius: 3.5,
              p: 1.5,
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
            },
          }}
        >
          <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1.5, pb: 1 }}>
            <Box sx={{ bgcolor: '#dcfce7', p: 1.2, borderRadius: '50%', display: 'flex', color: '#16a34a' }}>
              <CheckCircleIcon sx={{ fontSize: 32 }} />
            </Box>
            <Box>
              <Typography variant="h6" fontWeight={800} color="#0f172a" sx={{ lineHeight: 1.25 }}>
                {completionData?.message ||
                  `Automate process between page ${completionData?.startPage || 1} to ${completionData?.endPage || 1} completed`}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                All selected deal cards and boards processed through the 11-step pipeline.
              </Typography>
            </Box>
          </DialogTitle>

          <DialogContent dividers sx={{ my: 1 }}>
            <Grid container spacing={1.5}>
              <Grid item xs={6} sm={4}>
                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, textAlign: 'center', bgcolor: '#f8fafc' }}>
                  <Typography variant="caption" color="text.secondary" fontWeight={600}>
                    Pages Processed
                  </Typography>
                  <Typography variant="h6" fontWeight={800} color="#0f172a">
                    {completionData?.startPage || 1} → {completionData?.endPage || 1}
                  </Typography>
                  <Typography variant="caption" color="primary" fontWeight={700}>
                    ({(completionData?.endPage || 1) - (completionData?.startPage || 1) + 1} pages)
                  </Typography>
                </Paper>
              </Grid>

              <Grid item xs={6} sm={4}>
                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, textAlign: 'center', bgcolor: '#f8fafc' }}>
                  <Typography variant="caption" color="text.secondary" fontWeight={600}>
                    Total Deals
                  </Typography>
                  <Typography variant="h6" fontWeight={800} color="#0f172a">
                    {completionData?.summary?.total_cards || 0}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    processed
                  </Typography>
                </Paper>
              </Grid>

              <Grid item xs={12} sm={4}>
                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, textAlign: 'center', bgcolor: '#f8fafc' }}>
                  <Typography variant="caption" color="text.secondary" fontWeight={600}>
                    Success / Fail
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'center', gap: 0.8, mt: 0.5 }}>
                    <Chip
                      label={`${completionData?.summary?.success_count || 0} Success`}
                      size="small"
                      color="success"
                      sx={{ fontWeight: 700 }}
                    />
                    {(completionData?.summary?.failed_count || 0) > 0 && (
                      <Chip
                        label={`${completionData?.summary?.failed_count || 0} Failed`}
                        size="small"
                        color="error"
                        sx={{ fontWeight: 700 }}
                      />
                    )}
                  </Box>
                </Paper>
              </Grid>
            </Grid>

            {completionData?.report && (
              <Paper
                elevation={0}
                sx={{
                  mt: 2,
                  p: 1.8,
                  borderRadius: 2.5,
                  bgcolor: '#f1f5f9',
                  border: '1px solid #e2e8f0',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: 1.5,
                }}
              >
                <Box>
                  <Typography variant="subtitle2" fontWeight={800} color="#0f172a">
                    📄 {completionData.report.fileName}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', wordBreak: 'break-all' }}>
                    {completionData.report.fullPath || completionData.report.filePath}
                  </Typography>
                </Box>
                <Button
                  variant="contained"
                  color="primary"
                  size="small"
                  startIcon={<DownloadIcon />}
                  component="a"
                  href={`/api/reports/download/${encodeURIComponent(completionData.report.fileName)}`}
                  download={completionData.report.fileName}
                  target="_blank"
                  sx={{
                    bgcolor: '#E60023',
                    fontWeight: 700,
                    textTransform: 'none',
                    borderRadius: 2,
                    px: 2,
                    '&:hover': { bgcolor: '#be123c' },
                  }}
                >
                  Download PDF
                </Button>
              </Paper>
            )}
          </DialogContent>

          <DialogActions sx={{ px: 3, py: 1.5 }}>
            <Button
              variant="contained"
              onClick={() => setIsCompletionModalOpen(false)}
              sx={{
                bgcolor: '#0f172a',
                color: '#ffffff',
                fontWeight: 700,
                textTransform: 'none',
                borderRadius: 2,
                px: 3.5,
                '&:hover': { bgcolor: '#1e293b' },
              }}
            >
              Done
            </Button>
          </DialogActions>
        </Dialog>

        {toast && (
          <Snackbar
            open={!!toast}
            autoHideDuration={5000}
            onClose={() => setToast(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
          >
            <Alert severity={toast.severity} onClose={() => setToast(null)}>
              {toast.message}
            </Alert>
          </Snackbar>
        )}
      </Box>
    </ThemeProvider>
  );
};

export default App;
