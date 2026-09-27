import React, { useState, useEffect, useRef } from 'react';
import {
  Card,
  Typography,
  Box,
  Button,
  Paper,
  Grid,
  Checkbox,
  Chip,
  CircularProgress,
  LinearProgress,
  Pagination,
  Tooltip,
  Divider,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
} from '@mui/material';
import FacebookIcon from '@mui/icons-material/Facebook';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import HistoryIcon from '@mui/icons-material/History';
import CloseIcon from '@mui/icons-material/Close';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import TerminalIcon from '@mui/icons-material/Terminal';
import SyncIcon from '@mui/icons-material/Sync';
import PushPinIcon from '@mui/icons-material/PushPin';
import TableChartIcon from '@mui/icons-material/TableChart';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import DesktopWindowsIcon from '@mui/icons-material/DesktopWindows';
import FilterListIcon from '@mui/icons-material/FilterList';
import LaunchIcon from '@mui/icons-material/Launch';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import PhotoCameraIcon from '@mui/icons-material/PhotoCamera';
import { api } from '../services/api.ts';
import { sseClient } from '../services/sse.ts';

interface SocialMediaHubProps {
  onSync?: () => Promise<void>;
}

export const SocialMediaHub: React.FC<SocialMediaHubProps> = () => {
  // Dhanvi Collection Pinterest Pins State
  const [dhanviPins, setDhanviPins] = useState<Array<{
    pinId: string;
    title: string;
    price: string;
    pinUrl: string;
    imageUrl: string;
    status: 'posted' | 'pending';
    statusLabel: string;
  }>>([]);
  const [pinPage, setPinPage] = useState<number>(1);
  const [pinPageSize] = useState<number>(12);
  const [pinTotalPages, setPinTotalPages] = useState<number>(1);
  const [pinTotalCount, setPinTotalCount] = useState<number>(0);
  const [pinFilter, setPinFilter] = useState<'pending' | 'all'>('pending');
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [postedCount, setPostedCount] = useState<number>(0);
  const [isLoadingPins, setIsLoadingPins] = useState<boolean>(false);
  const [isCleaning, setIsCleaning] = useState<boolean>(false);
  const [selectedPinIds, setSelectedPinIds] = useState<Set<string>>(new Set());

  // Automation Execution State
  const [fbSharePinCount, setFbSharePinCount] = useState<number>(10);
  const [fbShareDelay, setFbShareDelay] = useState<number>(60);
  const [fbDestination, setFbDestination] = useState<'both' | 'page' | 'group'>('both');
  const [isFbShareRunning, setIsFbShareRunning] = useState<boolean>(false);
  const [fbShareStep, setFbShareStep] = useState<{ step: number; message: string } | null>(null);
  const [statusMessage, setStatusMessage] = useState<{ text: string; severity: 'info' | 'success' | 'warning' | 'error' } | null>(null);
  const [socialLogs, setSocialLogs] = useState<Array<{ level: string; message: string; timestamp: string }>>([]);

  // Modals
  const [liveBrowserFrame, setLiveBrowserFrame] = useState<string | null>(null);
  const [liveBrowserModalOpen, setLiveBrowserModalOpen] = useState<boolean>(false);
  const [completedModalOpen, setCompletedModalOpen] = useState<boolean>(false);
  const [lastBatchResult, setLastBatchResult] = useState<any>(null);
  const [activeProofUrl, setActiveProofUrl] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState<boolean>(false);
  const [historyStats, setHistoryStats] = useState<any>(null);

  const terminalEndRef = useRef<HTMLDivElement>(null);
  const wasRunningRef = useRef<boolean>(false);

  const fetchDhanviPins = async (page = pinPage, filter = pinFilter, forceRefresh = false) => {
    setIsLoadingPins(true);
    try {
      const data = await api.getFacebookPins(page, pinPageSize, filter, forceRefresh);
      if (data && data.pins) {
        setDhanviPins(data.pins);
        setPinTotalPages(data.totalPages || 1);
        setPinTotalCount(data.totalCount || 0);
        setPendingCount(data.pendingCount || 0);
        setPostedCount(data.postedCount || 0);
      }
    } catch (e) {
      console.error('Error fetching Dhanvi pins:', e);
    } finally {
      setIsLoadingPins(false);
    }
  };

  const fetchHistory = async () => {
    try {
      const data = await api.getSocialHistory();
      setHistoryStats(data);
    } catch (_) {}
  };

  const handleBatchComplete = (batchData: any) => {
    if (batchData) {
      setLastBatchResult(batchData);
      if (batchData.runId) {
        try {
          sessionStorage.setItem('fb_share_ack_run_id', String(batchData.runId));
        } catch (_) {}
      }
    }
    wasRunningRef.current = false;
    setIsFbShareRunning(false);
    setFbShareStep(null);
    setCompletedModalOpen(true);
    setSelectedPinIds(new Set());
    setStatusMessage({
      text: `🎉 Pinterest → Facebook Share completed! Published ${batchData?.successCount ?? batchData?.totalShared ?? 'all'} pin(s) to WorldNewzs Page & Amazon Affiliate Group.`,
      severity: 'success',
    });
    api.cleanPostedPins().catch(() => {});
    fetchDhanviPins(1, undefined, true);
    fetchHistory();
  };

  const checkFbShareStatus = async () => {
    try {
      const status = await api.getPinterestFacebookStatus();
      if (!status) return;

      if (Array.isArray(status.recentLogs) && status.recentLogs.length > 0) {
        setSocialLogs((prev) => {
          if (prev.length === 0) return status.recentLogs;
          const existingMessages = new Set(prev.map((l) => `${l.timestamp || ''}|${l.message}`));
          const newLogs = status.recentLogs.filter(
            (l: any) => !existingMessages.has(`${l.timestamp || ''}|${l.message}`)
          );
          if (newLogs.length === 0) return prev;
          return [...prev, ...newLogs].slice(-200);
        });
      }

      if (status.isRunning) {
        wasRunningRef.current = true;
        setIsFbShareRunning(true);
        if (status.currentStep) {
          setFbShareStep({
            step: status.currentStep,
            message: status.lastStepMessage || `Processing Pin #${status.currentPin || 1}/${status.totalPins || 1}...`,
          });
        }
      } else {
        const ackRunId = (() => {
          try {
            return sessionStorage.getItem('fb_share_ack_run_id');
          } catch {
            return null;
          }
        })();
        const latestRunId = status.lastBatchResult?.runId ? String(status.lastBatchResult.runId) : null;

        if (wasRunningRef.current) {
          handleBatchComplete(status.lastBatchResult || {
            totalShared: status.results?.filter((r: any) => r.status === 'success').length || fbSharePinCount,
            successCount: status.results?.filter((r: any) => r.status === 'success').length || fbSharePinCount,
            skippedCount: status.results?.filter((r: any) => r.status === 'skipped').length || 0,
            failedCount: status.results?.filter((r: any) => r.status === 'failed').length || 0,
            excelReport: status.lastExcelReport,
            pdfReport: status.lastPdfReport,
          });
        } else if (latestRunId && latestRunId !== ackRunId && status.lastBatchResult) {
          handleBatchComplete(status.lastBatchResult);
        } else {
          setIsFbShareRunning(false);
          setFbShareStep(null);
          if (status.lastBatchResult && !lastBatchResult) {
            setLastBatchResult(status.lastBatchResult);
          }
        }
      }
    } catch (_) {}
  };

  useEffect(() => {
    fetchDhanviPins(pinPage, pinFilter);
  }, [pinPage, pinFilter]);

  useEffect(() => {
    fetchHistory();
    checkFbShareStatus();
    const statusPoll = setInterval(checkFbShareStatus, 3000);

    // Subscribe to SSE via shared singleton client
    const unsubs = [
      sseClient.subscribe('social_log', (data: any) => {
        setSocialLogs((prev) => [...prev.slice(-200), data]);
      }),
      sseClient.subscribe('fb_share_step', (data: any) => {
        setFbShareStep({ step: data.step, message: data.message });
      }),
      sseClient.subscribe('fb_live_frame', (data: any) => {
        if (data.url) {
          setLiveBrowserFrame(data.url);
        }
      }),
      sseClient.subscribe('fb_share_complete', (data: any) => {
        handleBatchComplete(data);
      }),
      sseClient.subscribe('state_change', (data: any) => {
        if (data && data.fbShareRunning === false && wasRunningRef.current) {
          checkFbShareStatus();
        }
      }),
    ];

    return () => {
      clearInterval(statusPoll);
      unsubs.forEach((unsub) => unsub());
    };
  }, []);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [socialLogs.length]);

  const toggleSelectPin = (pinId: string) => {
    const next = new Set(selectedPinIds);
    if (next.has(pinId)) {
      next.delete(pinId);
    } else {
      next.add(pinId);
    }
    setSelectedPinIds(next);
  };

  const handleSelect10Unposted = () => {
    const pendingPins = dhanviPins.filter((p) => p.status === 'pending');
    const first10 = pendingPins.slice(0, 10).map((p) => p.pinId);
    setSelectedPinIds(new Set(first10));
    setFbSharePinCount(first10.length > 0 ? first10.length : 10);
    setStatusMessage({
      text: `✅ Selected ${first10.length} pending pin(s) from Dhanvi Collections. Click "Share to Facebook" to begin!`,
      severity: 'info',
    });
  };

  const handlePinterestFacebookShare = async () => {
    if (isFbShareRunning) return;
    wasRunningRef.current = true;
    setIsFbShareRunning(true);
    setFbShareStep({ step: 1, message: 'Verifying Facebook session & WorldNewzs Page identity...' });
    const countToShare =
      selectedPinIds.size > 0
        ? selectedPinIds.size
        : fbSharePinCount === 0
        ? Math.max(1, pendingCount)
        : fbSharePinCount;
    const destLabel = fbDestination === 'both' ? 'WorldNewzs Page & Group' : fbDestination === 'page' ? 'WorldNewzs Page Feed' : 'Amazon Affiliate Group';
    setStatusMessage({
      text: `🚀 Starting Pinterest → Facebook Share (${countToShare} unposted pin(s) to ${destLabel}, ${fbShareDelay}s delay)...`,
      severity: 'info',
    });
    try {
      const specificIds = selectedPinIds.size > 0 ? Array.from(selectedPinIds) : undefined;
      const res = await api.pinterestFacebookShare({
        pinCount: countToShare,
        delaySeconds: fbShareDelay,
        specificPinIds: specificIds,
        destination: fbDestination,
      });
      setStatusMessage({
        text: res.message || 'Pinterest → Facebook share started!',
        severity: 'success',
      });
    } catch (err: any) {
      setStatusMessage({
        text: `Pinterest → Facebook share failed: ${err.message || err}`,
        severity: 'error',
      });
      wasRunningRef.current = false;
      setIsFbShareRunning(false);
      setFbShareStep(null);
    }
  };

  const handleStopFacebookShare = async () => {
    try {
      await api.stopPinterestFacebookShare();
      setStatusMessage({
        text: '⏹️ Stopping Facebook Share after current action and generating Excel & PDF reports...',
        severity: 'warning',
      });
    } catch (err: any) {
      setStatusMessage({
        text: `Stop request error: ${err.message || err}`,
        severity: 'error',
      });
    }
  };

  const handleLaunchEdgeFacebook = async () => {
    setStatusMessage({
      text: '🌐 Launching Microsoft Edge directly on your screen with the AutomatePinterest profile...',
      severity: 'info',
    });
    try {
      const res = await api.launchEdgeFacebook();
      setStatusMessage({
        text: res.message || 'Microsoft Edge opened on your screen!',
        severity: 'success',
      });
    } catch (err: any) {
      setStatusMessage({
        text: `Error opening Edge: ${err.message || err}`,
        severity: 'error',
      });
    }
  };

  const handleExportExcel = () => {
    window.open(api.getExportExcelUrl(), '_blank');
  };

  const handleExportPdf = () => {
    window.open(api.getExportPdfUrl(), '_blank');
  };

  const handleOpenHistory = async () => {
    await fetchHistory();
    setHistoryOpen(true);
  };

  const handleCleanPostedPins = async () => {
    if (isCleaning || isFbShareRunning) return;
    setIsCleaning(true);
    try {
      const res = await api.cleanPostedPins();
      setStatusMessage({
        text: `🧹 Clean Complete: Purged ${res.cleanedCount} already-posted pin(s) from Facebook Automation Hub (${res.remainingCount} unposted pins ready to share).`,
        severity: 'success',
      });
      await fetchDhanviPins(1, undefined, true);
      await fetchHistory();
    } catch (err: any) {
      setStatusMessage({
        text: `Failed to clean posted pins: ${err.message || err}`,
        severity: 'error',
      });
    } finally {
      setIsCleaning(false);
    }
  };

  return (
    <Card
      elevation={3}
      sx={{
        borderRadius: 3,
        border: '1px solid #E2E8F0',
        mt: 3,
        overflow: 'hidden',
        p: { xs: 2, sm: 3 },
        bgcolor: '#FFFFFF',
      }}
    >
      {/* ── Main Header ── */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2, flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
            <Box
              sx={{
                width: 38,
                height: 38,
                borderRadius: 2,
                bgcolor: '#1877F2',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#FFF',
                boxShadow: '0 4px 10px rgba(24, 119, 242, 0.3)',
              }}
            >
              <FacebookIcon />
            </Box>
            <Typography variant="h5" fontWeight={800} color="#0F172A">
              Facebook Automation Hub
            </Typography>
            <Chip
              label="Dhanvi Collection → WorldNewzs Page & Amazon Affiliate Group"
              size="small"
              sx={{ bgcolor: '#EFF6FF', color: '#1D4ED8', fontWeight: 800, fontSize: '0.75rem' }}
            />
          </Box>
          <Typography variant="body2" color="text.secondary">
            Automated publishing of unposted pins from Dhanvi Collections (<a href="https://in.pinterest.com/ganeshkumardevarasetty/" target="_blank" rel="noreferrer" style={{ color: '#E60023', fontWeight: 700, textDecoration: 'none' }}>@ganeshkumardevarasetty</a>) directly to <a href="https://www.facebook.com/profile.php?id=61589266599006" target="_blank" rel="noreferrer" style={{ color: '#1877F2', fontWeight: 700, textDecoration: 'none' }}>WorldNewzs Facebook Page</a> & <a href="https://www.facebook.com/groups/1761596288324903/" target="_blank" rel="noreferrer" style={{ color: '#1877F2', fontWeight: 700, textDecoration: 'none' }}>Amazon Affiliate Group</a>.
          </Typography>
        </Box>

        {/* Status KPI Chips */}
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          <Chip
            icon={<PushPinIcon fontSize="small" />}
            label={`Ready to Post: ${pendingCount}`}
            size="small"
            sx={{ bgcolor: '#FEF3C7', color: '#92400E', fontWeight: 800 }}
          />
          <Chip
            icon={<CheckCircleIcon fontSize="small" />}
            label={`Posted to Facebook: ${postedCount}`}
            size="small"
            clickable
            onClick={handleOpenHistory}
            title="Click to view complete Facebook share history"
            sx={{ bgcolor: '#DCFCE7', color: '#15803D', fontWeight: 800 }}
          />
          <Chip
            icon={<DeleteSweepIcon fontSize="small" />}
            label="🧹 Posted Pins Filtered & Cleaned"
            size="small"
            sx={{ bgcolor: '#EFF6FF', color: '#1D4ED8', fontWeight: 700 }}
          />
        </Box>
      </Box>

      {/* ── Unified Action Toolbar ── */}
      <Paper
        variant="outlined"
        sx={{
          p: 2,
          mb: 2.5,
          borderRadius: 2.5,
          bgcolor: '#F8FAFC',
          borderColor: '#E2E8F0',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 1.5,
        }}
      >
        {/* Left Controls: Pin count, Delay, Destination, Primary Share Button, Quick Select */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
          {/* Target Destination selector */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
            <Typography variant="caption" fontWeight={700} color="#475569">
              Target:
            </Typography>
            <Box
              component="select"
              value={fbDestination}
              onChange={(e: any) => setFbDestination(e.target.value)}
              disabled={isFbShareRunning}
              sx={{
                px: 1.2,
                py: 0.6,
                borderRadius: 1.5,
                border: '1px solid #CBD5E1',
                bgcolor: '#FFFFFF',
                fontWeight: 800,
                fontSize: '0.85rem',
                color: '#1E293B',
                cursor: 'pointer',
              }}
            >
              <option value="both">🌐 Both (Page + Group)</option>
              <option value="page">📄 WorldNewzs Page Feed</option>
              <option value="group">👥 Amazon Affiliate Group</option>
            </Box>
          </Box>

          {/* Pins to share selector */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
            <Typography variant="caption" fontWeight={700} color="#475569">
              Pins:
            </Typography>
            <Box
              component="select"
              value={fbSharePinCount}
              onChange={(e: any) => setFbSharePinCount(Number(e.target.value))}
              disabled={isFbShareRunning}
              sx={{
                px: 1.2,
                py: 0.6,
                borderRadius: 1.5,
                border: '1px solid #CBD5E1',
                bgcolor: '#FFFFFF',
                fontWeight: 800,
                fontSize: '0.85rem',
                color: '#0F172A',
                cursor: 'pointer',
              }}
            >
              <option value={0}>All Unposted ({pendingCount})</option>
              <option value={5}>5 Pins</option>
              <option value={10}>10 Pins (Recommended)</option>
              <option value={15}>15 Pins</option>
              <option value={20}>20 Pins</option>
              <option value={25}>25 Pins</option>
              <option value={50}>50 Pins</option>
            </Box>
          </Box>

          {/* Delay selector */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
            <Typography variant="caption" fontWeight={700} color="#475569">
              Interval:
            </Typography>
            <Box
              component="select"
              value={fbShareDelay}
              onChange={(e: any) => setFbShareDelay(Number(e.target.value))}
              disabled={isFbShareRunning}
              sx={{
                px: 1.2,
                py: 0.6,
                borderRadius: 1.5,
                border: '1px solid #CBD5E1',
                bgcolor: '#FFFFFF',
                fontWeight: 800,
                fontSize: '0.85rem',
                color: '#0F172A',
                cursor: 'pointer',
              }}
            >
              <option value={30}>30 secs</option>
              <option value={60}>60 secs (Safe)</option>
              <option value={90}>90 secs</option>
              <option value={120}>2 mins</option>
            </Box>
          </Box>

          {/* Primary Action Button */}
          <Button
            variant="contained"
            size="medium"
            startIcon={isFbShareRunning ? <CircularProgress size={16} color="inherit" /> : <FacebookIcon />}
            onClick={() => handlePinterestFacebookShare()}
            disabled={isFbShareRunning || (pendingCount === 0 && selectedPinIds.size === 0)}
            sx={{
              bgcolor: '#1877F2',
              color: '#FFFFFF',
              fontWeight: 800,
              textTransform: 'none',
              borderRadius: 2,
              px: 2.5,
              py: 0.9,
              fontSize: '0.88rem',
              boxShadow: '0 2px 6px rgba(24, 119, 242, 0.3)',
              '&:hover': { bgcolor: '#0C63D4' },
              '&:disabled': { bgcolor: '#93C5FD', color: '#FFFFFF' },
            }}
          >
            {isFbShareRunning
              ? 'Sharing to Facebook...'
              : `🚀 Share ${
                  selectedPinIds.size > 0
                    ? selectedPinIds.size
                    : fbSharePinCount === 0
                    ? pendingCount
                    : fbSharePinCount
                } Unposted Pins`}
          </Button>

          {isFbShareRunning && (
            <Button
              variant="contained"
              size="medium"
              color="error"
              onClick={handleStopFacebookShare}
              sx={{
                fontWeight: 800,
                textTransform: 'none',
                borderRadius: 2,
                px: 2,
                py: 0.9,
                fontSize: '0.84rem',
              }}
            >
              ⏹️ Stop & Finish
            </Button>
          )}

          {/* Select 10 Unposted Helper Button */}
          <Button
            variant="outlined"
            size="medium"
            onClick={handleSelect10Unposted}
            disabled={isFbShareRunning}
            sx={{
              borderColor: '#CBD5E1',
              color: '#334155',
              fontWeight: 700,
              textTransform: 'none',
              borderRadius: 2,
              px: 1.8,
              py: 0.8,
              fontSize: '0.82rem',
              bgcolor: '#FFFFFF',
              '&:hover': { bgcolor: '#F1F5F9', borderColor: '#94A3B8' },
            }}
          >
            ⚡ Select 10 Unposted
          </Button>

          {/* Clean Posted Pins Button */}
          <Tooltip title="Remove any pins already posted to Facebook from the active hub">
            <Button
              variant="outlined"
              size="medium"
              startIcon={isCleaning ? <CircularProgress size={16} color="inherit" /> : <DeleteSweepIcon />}
              onClick={handleCleanPostedPins}
              disabled={isCleaning || isFbShareRunning}
              sx={{
                borderColor: '#FDBA74',
                color: '#C2410C',
                fontWeight: 700,
                textTransform: 'none',
                borderRadius: 2,
                px: 1.8,
                py: 0.8,
                fontSize: '0.82rem',
                bgcolor: '#FFF7ED',
                '&:hover': { bgcolor: '#FFEDD5', borderColor: '#EA580C' },
              }}
            >
              {isCleaning ? 'Cleaning...' : '🧹 Clean Posted Pins'}
            </Button>
          </Tooltip>

          {selectedPinIds.size > 0 && (
            <Button
              variant="text"
              size="small"
              onClick={() => setSelectedPinIds(new Set())}
              sx={{ textTransform: 'none', color: '#64748B', fontWeight: 600, fontSize: '0.75rem' }}
            >
              Clear Selection ({selectedPinIds.size})
            </Button>
          )}
        </Box>

        {/* Right Tools: Live View, Reports, Audit History, Edge Helper */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          {/* Live Browser Screen View */}
          <Button
            variant="outlined"
            size="medium"
            startIcon={<DesktopWindowsIcon />}
            onClick={() => setLiveBrowserModalOpen(true)}
            sx={{
              borderColor: '#2563EB',
              color: '#1D4ED8',
              fontWeight: 700,
              textTransform: 'none',
              borderRadius: 2,
              px: 2,
              py: 0.8,
              fontSize: '0.82rem',
              bgcolor: isFbShareRunning ? '#EFF6FF' : '#FFFFFF',
              '&:hover': { bgcolor: '#DBEAFE', borderColor: '#1D4ED8' },
            }}
          >
            👁️ Live Browser Screen {isFbShareRunning && '● LIVE'}
          </Button>

          {/* Export to Excel (.xlsx) */}
          <Tooltip title="Download live proof Excel spreadsheet with direct pin links">
            <Button
              variant="contained"
              size="medium"
              startIcon={<TableChartIcon />}
              onClick={handleExportExcel}
              sx={{
                bgcolor: '#059669',
                color: '#FFFFFF',
                fontWeight: 700,
                textTransform: 'none',
                borderRadius: 2,
                px: 1.8,
                py: 0.8,
                fontSize: '0.82rem',
                '&:hover': { bgcolor: '#047857' },
              }}
            >
              📊 Export Excel
            </Button>
          </Tooltip>

          {/* Download PDF Report */}
          <Tooltip title="Download dated PDF activity report with embedded Facebook proof screenshots">
            <Button
              variant="contained"
              size="medium"
              startIcon={<PictureAsPdfIcon />}
              onClick={handleExportPdf}
              sx={{
                bgcolor: '#DC2626',
                color: '#FFFFFF',
                fontWeight: 700,
                textTransform: 'none',
                borderRadius: 2,
                px: 1.8,
                py: 0.8,
                fontSize: '0.82rem',
                '&:hover': { bgcolor: '#B91C1C' },
              }}
            >
              📄 PDF Report
            </Button>
          </Tooltip>

          {/* History Ledger */}
          <Button
            variant="outlined"
            size="medium"
            startIcon={<HistoryIcon />}
            onClick={handleOpenHistory}
            sx={{
              textTransform: 'none',
              fontWeight: 700,
              borderRadius: 2,
              borderColor: '#CBD5E1',
              color: '#334155',
              bgcolor: '#FFFFFF',
              px: 1.5,
              py: 0.8,
              fontSize: '0.82rem',
              '&:hover': { bgcolor: '#F1F5F9' },
            }}
          >
            📜 History ({historyStats?.facebookCount || postedCount || 0})
          </Button>

          {/* Refresh Pins */}
          <Tooltip title="Refresh Dhanvi Collection pins from Pinterest">
            <IconButton
              size="small"
              onClick={() => fetchDhanviPins(pinPage, pinFilter, true)}
              disabled={isLoadingPins}
              sx={{ color: '#475569', border: '1px solid #CBD5E1', borderRadius: 2, p: 0.8 }}
            >
              {isLoadingPins ? <CircularProgress size={16} color="inherit" /> : <SyncIcon fontSize="small" />}
            </IconButton>
          </Tooltip>

          {/* Launch Facebook in Edge */}
          <Button
            variant="text"
            size="small"
            startIcon={<LaunchIcon />}
            onClick={handleLaunchEdgeFacebook}
            disabled={isFbShareRunning}
            sx={{
              color: '#475569',
              fontWeight: 700,
              textTransform: 'none',
              fontSize: '0.78rem',
            }}
          >
            Login Helper
          </Button>
        </Box>
      </Paper>

      {/* ── Status Alert Message ── */}
      {statusMessage && (
        <Alert
          severity={statusMessage.severity}
          onClose={() => setStatusMessage(null)}
          sx={{ mb: 2.5, borderRadius: 2 }}
        >
          {statusMessage.text}
        </Alert>
      )}

      {/* ── 7-Step Progress Tracker (Active Run) ── */}
      {isFbShareRunning && fbShareStep && (
        <Paper
          elevation={0}
          sx={{
            p: 2,
            mb: 2.5,
            borderRadius: 2,
            bgcolor: '#EFF6FF',
            border: '1px solid #BFDBFE',
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
            <Typography variant="body2" fontWeight={800} color="#1D4ED8">
              ⚡ Step {fbShareStep.step}/7: {fbShareStep.message}
            </Typography>
            <LinearProgress
              variant="determinate"
              value={Math.round((fbShareStep.step / 7) * 100)}
              sx={{
                flex: 1,
                height: 8,
                borderRadius: 4,
                bgcolor: '#DBEAFE',
                '& .MuiLinearProgress-bar': {
                  bgcolor: '#2563EB',
                  borderRadius: 4,
                },
              }}
            />
            <Typography variant="caption" fontWeight={800} color="#1D4ED8">
              {Math.round((fbShareStep.step / 7) * 100)}%
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {[
              { n: 1, label: 'FB Session' },
              { n: 2, label: 'Pinterest Pins' },
              { n: 3, label: 'Image Check' },
              { n: 4, label: 'FB Page' },
              { n: 5, label: 'FB Group' },
              { n: 6, label: 'Record Proof' },
              { n: 7, label: 'Complete' },
            ].map((s) => (
              <Chip
                key={s.n}
                label={`${s.n}. ${s.label}`}
                size="small"
                sx={{
                  fontWeight: 700,
                  fontSize: '0.65rem',
                  height: 22,
                  bgcolor:
                    fbShareStep.step > s.n
                      ? '#D1FAE5'
                      : fbShareStep.step === s.n
                      ? '#FEF3C7'
                      : '#F1F5F9',
                  color:
                    fbShareStep.step > s.n
                      ? '#065F46'
                      : fbShareStep.step === s.n
                      ? '#92400E'
                      : '#94A3B8',
                  border: fbShareStep.step === s.n ? '1px solid #D97706' : 'none',
                }}
              />
            ))}
          </Box>
        </Paper>
      )}

      {/* ── Live Activity Stream Terminal ── */}
      {socialLogs.length > 0 && (
        <Box sx={{ mb: 2.5 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.8 }}>
            <Typography variant="caption" fontWeight={800} color="#475569" sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
              <TerminalIcon fontSize="small" sx={{ color: '#2563EB', fontSize: 16 }} />
              Live Playwright & Facebook Automation Feed ({socialLogs.length} events)
            </Typography>
            <Button
              size="small"
              onClick={() => setSocialLogs([])}
              sx={{ textTransform: 'none', fontSize: '0.7rem', p: 0, color: '#64748B' }}
            >
              Clear Feed
            </Button>
          </Box>
          <Paper
            variant="outlined"
            sx={{
              p: 1.5,
              bgcolor: '#0F172A',
              color: '#F8FAFC',
              borderRadius: 2,
              maxHeight: 180,
              overflowY: 'auto',
              fontFamily: 'monospace',
              fontSize: '0.74rem',
              border: '1px solid #1E293B',
            }}
          >
            {socialLogs.map((log, idx) => (
              <Box key={idx} sx={{ py: 0.2, display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                <Typography variant="caption" sx={{ color: '#64748B', whiteSpace: 'nowrap', fontSize: '0.7rem' }}>
                  [{log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString()}]
                </Typography>
                <Typography
                  variant="caption"
                  sx={{
                    fontFamily: 'monospace',
                    fontSize: '0.72rem',
                    color:
                      log.level === 'error'
                        ? '#F87171'
                        : log.level === 'warning'
                        ? '#FBBF24'
                        : log.level === 'success'
                        ? '#4ADE80'
                        : '#E2E8F0',
                    fontWeight: log.level === 'success' || log.level === 'error' ? 700 : 400,
                  }}
                >
                  {log.message}
                </Typography>
              </Box>
            ))}
            <div ref={terminalEndRef} />
          </Paper>
        </Box>
      )}

      {/* ── Filter Tabs Bar ── */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1.5 }}>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
          <FilterListIcon fontSize="small" sx={{ color: '#64748B' }} />
          <Typography variant="body2" fontWeight={800} color="#334155">
            Active Pins:
          </Typography>
          <Chip
            label={`🟡 Unposted Ready Pins (${pinTotalCount})`}
            size="small"
            sx={{
              fontWeight: 800,
              fontSize: '0.75rem',
              bgcolor: '#1877F2',
              color: '#FFFFFF',
            }}
          />
          <Button
            size="small"
            startIcon={isCleaning ? <CircularProgress size={12} color="inherit" /> : <DeleteSweepIcon fontSize="small" />}
            onClick={handleCleanPostedPins}
            disabled={isCleaning || isFbShareRunning}
            sx={{
              textTransform: 'none',
              fontWeight: 700,
              fontSize: '0.75rem',
              color: '#C2410C',
              bgcolor: '#FFF7ED',
              border: '1px solid #FDBA74',
              borderRadius: 4,
              px: 1.5,
              py: 0.3,
              minHeight: 26,
              '&:hover': { bgcolor: '#FFEDD5' },
            }}
          >
            {isCleaning ? 'Cleaning...' : '🧹 Clean Posted Pins'}
          </Button>
          <Button
            size="small"
            startIcon={<HistoryIcon fontSize="small" />}
            onClick={handleOpenHistory}
            sx={{
              textTransform: 'none',
              fontWeight: 700,
              fontSize: '0.75rem',
              color: '#15803D',
              bgcolor: '#F0FDF4',
              border: '1px solid #BBF7D0',
              borderRadius: 4,
              px: 1.5,
              py: 0.3,
              minHeight: 26,
              '&:hover': { bgcolor: '#DCFCE7' },
            }}
          >
            📜 View Posted History ({postedCount})
          </Button>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600}>
            Showing {pinTotalCount > 0 ? (pinPage - 1) * pinPageSize + 1 : 0} to {Math.min(pinPage * pinPageSize, pinTotalCount)} of {pinTotalCount}
          </Typography>
          {pinTotalPages > 1 && (
            <Pagination
              count={pinTotalPages}
              page={pinPage}
              onChange={(_, p) => setPinPage(p)}
              size="small"
              shape="rounded"
              color="primary"
            />
          )}
        </Box>
      </Box>

      {/* ── Dhanvi Collection Pins Grid ── */}
      {isLoadingPins ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 8, gap: 1.5 }}>
          <CircularProgress size={28} sx={{ color: '#1877F2' }} />
          <Typography variant="body2" color="text.secondary" fontWeight={700}>
            Loading Dhanvi Collection pins...
          </Typography>
        </Box>
      ) : dhanviPins.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center', bgcolor: '#F8FAFC', borderColor: '#E2E8F0', borderRadius: 2 }}>
          <Typography variant="body1" color="#0F172A" fontWeight={800} sx={{ mb: 0.5 }}>
            🎉 All Dhanvi Collection pins have been published to Facebook or cleaned!
          </Typography>
          <Typography variant="body2" color="text.secondary" fontWeight={500} sx={{ mb: 2 }}>
            Click "Refresh Pins" to discover newly published pins from Pinterest, or download your completion reports below:
          </Typography>
          <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1.5, flexWrap: 'wrap' }}>
            <Button
              variant="contained"
              size="medium"
              startIcon={<TableChartIcon />}
              onClick={handleExportExcel}
              sx={{
                bgcolor: '#059669',
                color: '#FFFFFF',
                fontWeight: 800,
                textTransform: 'none',
                borderRadius: 2,
                px: 2.5,
                '&:hover': { bgcolor: '#047857' },
              }}
            >
              📊 Export Excel
            </Button>
            <Button
              variant="contained"
              size="medium"
              startIcon={<PictureAsPdfIcon />}
              onClick={handleExportPdf}
              sx={{
                bgcolor: '#DC2626',
                color: '#FFFFFF',
                fontWeight: 800,
                textTransform: 'none',
                borderRadius: 2,
                px: 2.5,
                '&:hover': { bgcolor: '#B91C1C' },
              }}
            >
              📄 Download PDF
            </Button>
            <Button
              variant="outlined"
              size="medium"
              startIcon={<CheckCircleIcon />}
              onClick={() => setCompletedModalOpen(true)}
              sx={{
                borderColor: '#2563EB',
                color: '#1D4ED8',
                fontWeight: 800,
                textTransform: 'none',
                borderRadius: 2,
                px: 2.5,
              }}
            >
              🏆 View Completion Summary
            </Button>
          </Box>
        </Paper>
      ) : (
        <Grid container spacing={2}>
          {dhanviPins.map((pin) => {
            const isSelected = selectedPinIds.has(pin.pinId);
            const isPosted = pin.status === 'posted';

            return (
              <Grid item xs={6} sm={4} md={3} lg={2} key={pin.pinId}>
                <Card
                  variant="outlined"
                  sx={{
                    borderRadius: 2.5,
                    borderColor: isSelected ? '#1877F2' : isPosted ? '#BBF7D0' : '#E2E8F0',
                    borderWidth: isSelected ? 2 : 1,
                    bgcolor: isSelected ? '#EFF6FF' : isPosted ? '#F0FDF4' : '#FFFFFF',
                    transition: 'all 0.2s ease',
                    position: 'relative',
                    display: 'flex',
                    flexDirection: 'column',
                    height: '100%',
                    '&:hover': {
                      borderColor: '#1877F2',
                      boxShadow: '0 6px 16px rgba(24, 119, 242, 0.12)',
                    },
                  }}
                >
                  {/* Selection Checkbox */}
                  <Box sx={{ position: 'absolute', top: 6, left: 6, zIndex: 2, bgcolor: 'rgba(255,255,255,0.92)', borderRadius: 1.5, p: 0.2 }}>
                    <Checkbox
                      size="small"
                      checked={isSelected}
                      onChange={() => toggleSelectPin(pin.pinId)}
                      sx={{ p: 0.2, color: '#1877F2', '&.Mui-checked': { color: '#1877F2' } }}
                    />
                  </Box>

                  {/* Status Overlay Badges */}
                  <Box sx={{ position: 'absolute', top: 6, right: 6, zIndex: 2, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.4 }}>
                    {isPosted ? (
                      <Chip
                        icon={<CheckCircleIcon sx={{ fontSize: '13px !important' }} />}
                        label="ON FB"
                        size="small"
                        sx={{
                          height: 20,
                          fontSize: '0.62rem',
                          fontWeight: 800,
                          bgcolor: '#16A34A',
                          color: '#FFFFFF',
                          '& .MuiChip-icon': { color: '#FFFFFF' },
                        }}
                      />
                    ) : (
                      <Chip
                        label="READY"
                        size="small"
                        sx={{
                          height: 20,
                          fontSize: '0.62rem',
                          fontWeight: 800,
                          bgcolor: '#FEF3C7',
                          color: '#92400E',
                          border: '1px solid #FDE68A',
                        }}
                      />
                    )}
                    {pin.imageUrl ? (
                      <Tooltip title="High-res image verified & ready for Facebook photo upload" arrow>
                        <Chip
                          icon={<PhotoCameraIcon sx={{ fontSize: '11px !important', color: '#047857 !important' }} />}
                          label="PHOTO"
                          size="small"
                          sx={{
                            height: 18,
                            fontSize: '0.58rem',
                            fontWeight: 800,
                            bgcolor: '#D1FAE5',
                            color: '#065F46',
                            border: '1px solid #A7F3D0',
                            px: 0.2,
                          }}
                        />
                      </Tooltip>
                    ) : (
                      <Tooltip title="Image URL missing; will auto-resolve before post" arrow>
                        <Chip
                          label="NO IMG"
                          size="small"
                          sx={{
                            height: 18,
                            fontSize: '0.58rem',
                            fontWeight: 700,
                            bgcolor: '#FEE2E2',
                            color: '#991B1B',
                            border: '1px solid #FECACA',
                            px: 0.2,
                          }}
                        />
                      </Tooltip>
                    )}
                  </Box>

                  {/* Image with Eager/Off-thread Decoding */}
                  <Box
                    sx={{
                      width: '100%',
                      height: 140,
                      bgcolor: '#F8FAFC',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      overflow: 'hidden',
                      p: 0.5,
                    }}
                  >
                    {pin.imageUrl ? (
                      <img
                        src={pin.imageUrl}
                        alt={pin.title}
                        loading="eager"
                        decoding="async"
                        width={140}
                        height={140}
                        onError={(e: any) => {
                          e.currentTarget.style.display = 'none';
                        }}
                        style={{
                          width: '100%',
                          height: '100%',
                          objectFit: 'contain',
                        }}
                      />
                    ) : (
                      <PushPinIcon sx={{ fontSize: 36, color: '#CBD5E1' }} />
                    )}
                  </Box>

                  {/* Pin Details */}
                  <Box sx={{ p: 1.2, flexGrow: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                    <Box>
                      <Tooltip title={pin.title} arrow>
                        <Typography
                          variant="caption"
                          fontWeight={700}
                          color="#0F172A"
                          sx={{
                            display: '-webkit-box',
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                            lineHeight: 1.3,
                            fontSize: '0.74rem',
                          }}
                        >
                          {pin.title}
                        </Typography>
                      </Tooltip>
                      {pin.price && (
                        <Typography variant="caption" fontWeight={800} color="#D97706" sx={{ display: 'block', mt: 0.4 }}>
                          {pin.price}
                        </Typography>
                      )}
                    </Box>

                    {/* Footer with Pin ID & Link */}
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1, pt: 0.6, borderTop: '1px solid #F1F5F9' }}>
                      <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.62rem', fontFamily: 'monospace' }}>
                        ID: {pin.pinId.slice(-6)}
                      </Typography>
                      {pin.pinUrl && (
                        <IconButton
                          size="small"
                          onClick={() => window.open(pin.pinUrl, '_blank')}
                          title="Open Pin on Pinterest"
                          sx={{ p: 0.3 }}
                        >
                          <OpenInNewIcon sx={{ fontSize: 13, color: '#64748B' }} />
                        </IconButton>
                      )}
                    </Box>
                  </Box>
                </Card>
              </Grid>
            );
          })}
        </Grid>
      )}

      {/* ── Bottom Pagination ── */}
      {pinTotalPages > 1 && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
          <Pagination
            count={pinTotalPages}
            page={pinPage}
            onChange={(_, p) => setPinPage(p)}
            size="medium"
            shape="rounded"
            color="primary"
          />
        </Box>
      )}

      {/* ══════════════════════════════════════════════════════
          MODALS & DIALOGS
      ══════════════════════════════════════════════════════ */}

      {/* 1. Live Playwright Browser Screen Modal */}
      <Dialog
        open={liveBrowserModalOpen}
        onClose={() => setLiveBrowserModalOpen(false)}
        maxWidth="lg"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3, p: 0.5, bgcolor: '#0F172A', color: '#F8FAFC' } }}
      >
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', pb: 1, borderBottom: '1px solid #334155' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <DesktopWindowsIcon sx={{ color: '#38BDF8' }} />
            <Typography variant="h6" fontWeight={800} color="#F8FAFC">
              Playwright Live Browser Screen Tracking
            </Typography>
            {isFbShareRunning ? (
              <Chip
                label="LIVE STREAMING"
                size="small"
                sx={{ bgcolor: '#EF4444', color: '#FFF', fontWeight: 800 }}
              />
            ) : (
              <Chip
                label="STANDBY / IDLE"
                size="small"
                sx={{ bgcolor: '#334155', color: '#94A3B8', fontWeight: 700 }}
              />
            )}
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <IconButton
              size="small"
              onClick={() => {
                setLiveBrowserFrame(api.getLiveFrameUrl());
              }}
              title="Refresh Screen"
              sx={{ color: '#94A3B8', '&:hover': { color: '#FFF' } }}
            >
              <SyncIcon fontSize="small" />
            </IconButton>
            <IconButton
              size="small"
              onClick={() => window.open(api.getLiveFrameUrl(), '_blank')}
              title="Open full view in new tab"
              sx={{ color: '#94A3B8', '&:hover': { color: '#FFF' } }}
            >
              <OpenInNewIcon fontSize="small" />
            </IconButton>
            <IconButton onClick={() => setLiveBrowserModalOpen(false)} size="small" sx={{ color: '#94A3B8' }}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
        </DialogTitle>

        <DialogContent sx={{ p: 2, display: 'flex', flexDirection: 'column', alignItems: 'center', minHeight: 460 }}>
          <Box sx={{ width: '100%', mb: 1.5, display: 'flex', justifyContent: 'space-between', alignItems: 'center', bgcolor: '#1E293B', p: 1, borderRadius: 2 }}>
            <Typography variant="caption" sx={{ color: '#38BDF8', fontWeight: 700 }}>
              {fbShareStep ? `Step ${fbShareStep.step}/7: ${fbShareStep.message}` : 'Target: Facebook Group "Amazon Affiliate Group" (Worldnewzs Page)'}
            </Typography>
            <Typography variant="caption" sx={{ color: '#94A3B8' }}>
              Engine: Playwright 1.62.0 CDP
            </Typography>
          </Box>

          <Box
            sx={{
              width: '100%',
              maxHeight: '68vh',
              overflow: 'auto',
              borderRadius: 2,
              border: '2px solid #334155',
              bgcolor: '#000',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <img
              src={liveBrowserFrame ? api.resolveUrl(liveBrowserFrame) : api.getLiveFrameUrl()}
              alt="Playwright Live Screen"
              onError={(e: any) => {
                e.target.style.display = 'none';
              }}
              onLoad={(e: any) => {
                e.target.style.display = 'block';
              }}
              style={{
                width: '100%',
                height: 'auto',
                display: 'block',
                objectFit: 'contain',
              }}
            />
          </Box>
        </DialogContent>

        <DialogActions sx={{ p: 2, borderTop: '1px solid #334155', justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              variant="outlined"
              size="small"
              startIcon={<TableChartIcon />}
              onClick={handleExportExcel}
              sx={{ color: '#34D399', borderColor: '#34D399', textTransform: 'none', fontWeight: 700 }}
            >
              Export Excel (.xlsx)
            </Button>
            <Button
              variant="outlined"
              size="small"
              startIcon={<PictureAsPdfIcon />}
              onClick={handleExportPdf}
              sx={{ color: '#F87171', borderColor: '#F87171', textTransform: 'none', fontWeight: 700 }}
            >
              Export PDF Report
            </Button>
          </Box>
          <Button
            onClick={() => setLiveBrowserModalOpen(false)}
            variant="contained"
            sx={{ bgcolor: '#2563EB', textTransform: 'none', fontWeight: 700 }}
          >
            Close Live View
          </Button>
        </DialogActions>
      </Dialog>

      {/* 2. Facebook Automation Batch Completed Modal */}
      <Dialog
        open={completedModalOpen}
        onClose={() => setCompletedModalOpen(false)}
        maxWidth="sm"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3, p: 1 } }}
      >
        <DialogTitle sx={{ textAlign: 'center', pt: 2, pb: 1 }}>
          <CheckCircleIcon sx={{ fontSize: 52, color: '#16A34A', mb: 1 }} />
          <Typography variant="h5" fontWeight={800} color="#0F172A">
            Pinterest → Facebook Share Complete!
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Automated sharing of unposted Dhanvi Collection pins to WorldNewzs Page & Amazon Affiliate Group has finished.
          </Typography>
        </DialogTitle>

        <DialogContent sx={{ py: 1.5 }}>
          <Paper
            variant="outlined"
            sx={{
              p: 2,
              borderRadius: 2,
              bgcolor: '#F8FAFC',
              borderColor: '#E2E8F0',
              display: 'flex',
              justifyContent: 'space-around',
              textAlign: 'center',
              mb: 2,
            }}
          >
            <Box>
              <Typography variant="h4" fontWeight={900} color="#16A34A">
                {lastBatchResult?.successCount ?? lastBatchResult?.totalShared ?? lastBatchResult?.sharedCount ?? postedCount}
              </Typography>
              <Typography variant="caption" fontWeight={700} color="text.secondary">
                PINS POSTED
              </Typography>
            </Box>
            <Divider orientation="vertical" flexItem />
            <Box>
              <Typography variant="h4" fontWeight={900} color="#D97706">
                {lastBatchResult?.skippedCount ?? 0}
              </Typography>
              <Typography variant="caption" fontWeight={700} color="text.secondary">
                SKIPPED (ON FB)
              </Typography>
            </Box>
            <Divider orientation="vertical" flexItem />
            <Box>
              <Typography variant="h4" fontWeight={900} color={lastBatchResult?.failedCount ? '#DC2626' : '#2563EB'}>
                {lastBatchResult?.failedCount ? `${lastBatchResult.failedCount} Failed` : '100%'}
              </Typography>
              <Typography variant="caption" fontWeight={700} color="text.secondary">
                {lastBatchResult?.failedCount ? 'FAILED' : 'SUCCESS RATE'}
              </Typography>
            </Box>
          </Paper>

          <Alert severity="success" sx={{ mb: 2, borderRadius: 2 }}>
            Live proofs and deduplication audit records are saved. Click below to export your Excel spreadsheet or download the dated PDF report:
          </Alert>

          <Box sx={{ display: 'flex', gap: 1.5, flexDirection: { xs: 'column', sm: 'row' } }}>
            <Button
              variant="contained"
              fullWidth
              size="large"
              startIcon={<TableChartIcon />}
              onClick={handleExportExcel}
              sx={{
                bgcolor: '#059669',
                color: '#FFF',
                fontWeight: 800,
                textTransform: 'none',
                borderRadius: 2,
                py: 1.4,
                fontSize: '0.95rem',
                boxShadow: '0 4px 12px rgba(5, 150, 105, 0.25)',
                '&:hover': { bgcolor: '#047857' },
              }}
            >
              📊 Export Excel
            </Button>
            <Button
              variant="contained"
              fullWidth
              size="large"
              startIcon={<PictureAsPdfIcon />}
              onClick={handleExportPdf}
              sx={{
                bgcolor: '#DC2626',
                color: '#FFF',
                fontWeight: 800,
                textTransform: 'none',
                borderRadius: 2,
                py: 1.4,
                fontSize: '0.95rem',
                boxShadow: '0 4px 12px rgba(220, 38, 38, 0.25)',
                '&:hover': { bgcolor: '#B91C1C' },
              }}
            >
              📄 Download PDF
            </Button>
          </Box>
        </DialogContent>

        <DialogActions sx={{ p: 2, justifyContent: 'center' }}>
          <Button
            onClick={() => setCompletedModalOpen(false)}
            variant="outlined"
            sx={{ textTransform: 'none', fontWeight: 700, borderRadius: 2, px: 4 }}
          >
            Done & Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* 3. Facebook Post Proof Screenshot Modal */}
      <Dialog
        open={Boolean(activeProofUrl)}
        onClose={() => setActiveProofUrl(null)}
        maxWidth="md"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3, p: 1 } }}
      >
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="h6" fontWeight={800}>
            Facebook Post Verification Proof
          </Typography>
          <IconButton onClick={() => setActiveProofUrl(null)} size="small">
            <CloseIcon fontSize="small" />
          </IconButton>
        </DialogTitle>
        <DialogContent sx={{ p: 1, display: 'flex', justifyContent: 'center' }}>
          {activeProofUrl && (
            <img
              src={activeProofUrl}
              alt="Facebook Proof Screenshot"
              style={{ maxWidth: '100%', maxHeight: '70vh', borderRadius: 8, objectFit: 'contain' }}
            />
          )}
        </DialogContent>
        <DialogActions sx={{ p: 1.5 }}>
          <Button
            onClick={() => setActiveProofUrl(null)}
            variant="contained"
            sx={{ textTransform: 'none', fontWeight: 700 }}
          >
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* 4. Share History & Audit Ledger Dialog */}
      <Dialog
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        maxWidth="md"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3, p: 1 } }}
      >
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', pb: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <HistoryIcon sx={{ color: '#1877F2' }} />
            <Typography variant="h6" fontWeight={800}>
              Facebook Share History & Audit Ledger
            </Typography>
          </Box>
          <IconButton onClick={() => setHistoryOpen(false)} size="small">
            <CloseIcon fontSize="small" />
          </IconButton>
        </DialogTitle>

        <DialogContent dividers>
          <Box sx={{ display: 'flex', gap: 1.5, mb: 2.5, flexWrap: 'wrap' }}>
            <Chip
              label={`Total Shared on FB: ${historyStats?.facebookCount || postedCount || 0}`}
              color="primary"
              variant="outlined"
              sx={{ fontWeight: 800 }}
            />
            <Chip
              icon={<FacebookIcon fontSize="small" />}
              label="Worldnewzs → Amazon Affiliate Group"
              sx={{ bgcolor: '#1877F2', color: '#fff', fontWeight: 800 }}
            />
            <Chip
              label={`Pending Unposted: ${pendingCount}`}
              sx={{ bgcolor: '#FEF3C7', color: '#92400E', fontWeight: 800 }}
            />
          </Box>

          {(!historyStats?.recentLogs || historyStats.recentLogs.length === 0) ? (
            <Alert severity="info" sx={{ borderRadius: 2 }}>
              No pins have been logged yet. Click "Share to Facebook" to begin sharing your Dhanvi Collection pins!
            </Alert>
          ) : (
            <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #E2E8F0', borderRadius: 2, maxHeight: 400 }}>
              <Table size="small" stickyHeader>
                <TableHead sx={{ bgcolor: '#F8FAFC' }}>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 800, fontSize: '0.78rem' }}>Date & Time</TableCell>
                    <TableCell sx={{ fontWeight: 800, fontSize: '0.78rem' }}>Destination</TableCell>
                    <TableCell sx={{ fontWeight: 800, fontSize: '0.78rem' }}>Product Title</TableCell>
                    <TableCell sx={{ fontWeight: 800, fontSize: '0.78rem' }}>Status</TableCell>
                    <TableCell sx={{ fontWeight: 800, fontSize: '0.78rem' }}>Action</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {historyStats.recentLogs
                    .filter((l: any) => l.platform === 'facebook' || !l.platform)
                    .map((log: any) => (
                      <TableRow key={log.id} hover>
                        <TableCell sx={{ fontSize: '0.75rem', color: '#64748B', whiteSpace: 'nowrap' }}>
                          {log.timestamp ? new Date(log.timestamp).toLocaleString() : 'N/A'}
                        </TableCell>
                        <TableCell>
                          <Chip
                            icon={<FacebookIcon fontSize="small" />}
                            label="Amazon Affiliate Group"
                            size="small"
                            sx={{
                              fontSize: '0.7rem',
                              fontWeight: 700,
                              bgcolor: '#EFF6FF',
                              color: '#1D4ED8',
                            }}
                          />
                        </TableCell>
                        <TableCell sx={{ fontSize: '0.78rem', fontWeight: 600, maxWidth: 240 }}>
                          <Typography
                            variant="caption"
                            fontWeight={700}
                            sx={{
                              display: '-webkit-box',
                              WebkitLineClamp: 1,
                              WebkitBoxOrient: 'vertical',
                              overflow: 'hidden',
                            }}
                          >
                            {log.title || 'Pinterest Deal'}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          {log.status === 'success' ? (
                            <Chip
                              icon={<CheckCircleIcon fontSize="small" />}
                              label="Posted"
                              size="small"
                              color="success"
                              sx={{ height: 20, fontSize: '0.65rem', fontWeight: 800 }}
                            />
                          ) : log.status === 'skipped' ? (
                            <Tooltip title={log.error || 'Deduplication skip'} arrow>
                              <Chip
                                icon={<WarningAmberIcon fontSize="small" />}
                                label="Skipped"
                                size="small"
                                color="warning"
                                sx={{ height: 20, fontSize: '0.65rem', fontWeight: 800 }}
                              />
                            </Tooltip>
                          ) : (
                            <Tooltip title={log.error || 'Encountered error'} arrow>
                              <Chip
                                icon={<CloseIcon fontSize="small" />}
                                label="Failed"
                                size="small"
                                color="error"
                                sx={{ height: 20, fontSize: '0.65rem', fontWeight: 800 }}
                              />
                            </Tooltip>
                          )}
                        </TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', gap: 0.5 }}>
                            {log.pinUrl && (
                              <IconButton
                                size="small"
                                onClick={() => window.open(log.pinUrl, '_blank')}
                                title="Open Pin on Pinterest"
                              >
                                <OpenInNewIcon fontSize="small" />
                              </IconButton>
                            )}
                            {(log.screenshot || log.screenshotPath) && (
                              <IconButton
                                size="small"
                                onClick={() => {
                                  const sc = log.screenshot || log.screenshotPath;
                                  const filename = sc.split(/[\/\\]/).pop();
                                  setActiveProofUrl(api.getProofUrl(filename));
                                }}
                                title="View Proof Screenshot"
                                sx={{ color: '#1877F2' }}
                              >
                                <DesktopWindowsIcon fontSize="small" />
                              </IconButton>
                            )}
                          </Box>
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DialogContent>

        <DialogActions sx={{ p: 2 }}>
          <Button
            onClick={() => setHistoryOpen(false)}
            variant="contained"
            sx={{ textTransform: 'none', fontWeight: 700, borderRadius: 2 }}
          >
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
};

export default SocialMediaHub;
