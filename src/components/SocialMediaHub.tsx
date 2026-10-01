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
  // WorldNewzs Amazon Products (6 per page, unposted only)
  const [dhanviPins, setDhanviPins] = useState<Array<{
    pinId: string;
    asin?: string;
    title: string;
    price: string;
    originalPrice?: string;
    discount?: string;
    category?: string;
    tag?: string;
    pinUrl: string;
    dealUrl?: string;
    destinationLink?: string;
    imageUrl: string;
    pageNumber?: number;
    cardIndex?: number;
    cardIndexOnPage?: number;
    serialNumber?: number;
    status: 'posted' | 'pending';
    statusLabel: string;
  }>>([]);
  const [pinPage, setPinPage] = useState<number>(1);
  const [endPage, setEndPage] = useState<number>(1);
  const [pinPageSize] = useState<number>(6);
  const [pinTotalPages, setPinTotalPages] = useState<number>(1);
  const [pinTotalCount, setPinTotalCount] = useState<number>(0);
  const [pinFilter, setPinFilter] = useState<'pending' | 'all'>('pending');
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [postedCount, setPostedCount] = useState<number>(0);
  const [isLoadingPins, setIsLoadingPins] = useState<boolean>(false);
  const [isCleaning, setIsCleaning] = useState<boolean>(false);
  const [isSyncingWorldNewzs, setIsSyncingWorldNewzs] = useState<boolean>(false);
  const [selectedPinIds, setSelectedPinIds] = useState<Set<string>>(new Set());

  // Automation Execution State
  const [fbSharePinCount, setFbSharePinCount] = useState<number>(6);
  const [fbShareDelay, setFbShareDelay] = useState<number>(60);
  const [fbDestination, setFbDestination] = useState<'both' | 'page' | 'group'>('both');
  const [isFbShareRunning, setIsFbShareRunning] = useState<boolean>(false);
  const [fbShareStep, setFbShareStep] = useState<{ step: number; message: string } | null>(null);
  const [statusMessage, setStatusMessage] = useState<{ text: string; severity: 'info' | 'success' | 'warning' | 'error' } | null>(null);
  const [socialLogs, setSocialLogs] = useState<Array<{ level: string; message: string; timestamp: string }>>([]);

  // Modals & Live Monitor
  const [liveBrowserFrame, setLiveBrowserFrame] = useState<string | null>(null);
  const [showInlineLiveMonitor, setShowInlineLiveMonitor] = useState<boolean>(true);
  const [liveBrowserModalOpen, setLiveBrowserModalOpen] = useState<boolean>(false);
  const [completedModalOpen, setCompletedModalOpen] = useState<boolean>(false);
  const [lastBatchResult, setLastBatchResult] = useState<any>(null);
  const [activeProofUrl, setActiveProofUrl] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState<boolean>(false);
  const [historyStats, setHistoryStats] = useState<any>(null);

  const terminalEndRef = useRef<HTMLDivElement>(null);
  const wasRunningRef = useRef<boolean>(false);
  const pinPageRef = useRef<number>(pinPage);
  const pinFilterRef = useRef<'pending' | 'all'>(pinFilter);

  useEffect(() => {
    pinPageRef.current = pinPage;
  }, [pinPage]);

  useEffect(() => {
    pinFilterRef.current = pinFilter;
  }, [pinFilter]);

  const fetchDhanviPins = async (page = pinPageRef.current, filter = pinFilterRef.current, forceRefresh = false) => {
    setIsLoadingPins(true);
    try {
      const data = await api.getFacebookPins(page, pinPageSize, filter, forceRefresh);
      if (data && (data.pins || data.deals)) {
        const list = data.pins || data.deals || [];
        setDhanviPins(list);
        const totPages = data.totalPages || 1;
        setPinTotalPages(totPages);
        setPinTotalCount(data.totalCount || 0);
        setPendingCount(data.pendingCount || 0);
        setPostedCount(data.postedCount || 0);
        if (data.page && data.page !== page) {
          setPinPage(data.page);
          pinPageRef.current = data.page;
          setEndPage((prev) => Math.max(data.page, Math.min(prev, totPages)));
        }
      }
    } catch (e) {
      console.error('Error fetching WorldNewzs Amazon products for Facebook Hub:', e);
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

  const handleBatchComplete = async (batchData: any) => {
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
      text: `🎉 WorldNewzs Amazon Products → Facebook Share completed! Published ${batchData?.successCount ?? batchData?.totalShared ?? 'all'} product(s) to WorldNewzs Page & Amazon Affiliate Group. All posted items have been automatically cleared from the active queue.`,
      severity: 'success',
    });
    try {
      await api.cleanPostedPins();
    } catch (_) {}
    await fetchDhanviPins(pinPageRef.current, pinFilterRef.current, false);
    await fetchHistory();
  };

  const checkFbShareStatus = async () => {
    try {
      const status = await api.getPinterestFacebookStatus();
      if (!status) return;

      if (status.lastLiveFrameUrl) {
        setLiveBrowserFrame(status.lastLiveFrameUrl);
      }

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

      // Also auto-clear any completed/skipped ASINs reported in status poll
      const pollClearedSet = new Set<string>();
      if (Array.isArray(status.clearedAsins)) {
        status.clearedAsins.forEach((a: any) => {
          if (a) pollClearedSet.add(String(a).trim().toUpperCase());
        });
      }
      if (Array.isArray(status.results)) {
        status.results.forEach((r: any) => {
          if (r && (r.status === 'success' || r.status === 'skipped')) {
            const key = String(r.asin || r.pinId || '').trim().toUpperCase();
            if (key) pollClearedSet.add(key);
          }
        });
      }
      if (pollClearedSet.size > 0) {
        setDhanviPins((prev) => {
          const next = prev.filter(
            (p) => !pollClearedSet.has(String(p.asin || p.pinId || '').trim().toUpperCase())
          );
          if (prev.length > 0 && next.length === 0) {
            setTimeout(() => fetchDhanviPins(pinPageRef.current, pinFilterRef.current, false), 150);
          }
          return next;
        });
      }

      if (status.isRunning) {
        wasRunningRef.current = true;
        setIsFbShareRunning(true);
        if (status.currentStep) {
          setFbShareStep({
            step: status.currentStep,
            message: status.lastStepMessage || `Processing Deal #${status.currentPin || 1}/${status.totalPins || 6}...`,
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
          await handleBatchComplete(status.lastBatchResult || {
            totalShared: status.results?.filter((r: any) => r.status === 'success').length || fbSharePinCount,
            successCount: status.results?.filter((r: any) => r.status === 'success').length || fbSharePinCount,
            skippedCount: status.results?.filter((r: any) => r.status === 'skipped').length || 0,
            failedCount: status.results?.filter((r: any) => r.status === 'failed').length || 0,
            excelReport: status.lastExcelReport,
            pdfReport: status.lastPdfReport,
          });
        } else if (latestRunId && latestRunId !== ackRunId && status.lastBatchResult) {
          await handleBatchComplete(status.lastBatchResult);
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
    setEndPage((prev) => (prev < pinPage ? pinPage : prev));
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
      sseClient.subscribe('fb_item_cleared', (data: any) => {
        const clearedAsin = String(data?.asin || data?.pinId || '').trim().toUpperCase();
        if (clearedAsin) {
          setDhanviPins((prev) => {
            const next = prev.filter(
              (p) => String(p.asin || p.pinId || '').trim().toUpperCase() !== clearedAsin
            );
            if (prev.length > 0 && next.length === 0) {
              setTimeout(() => fetchDhanviPins(pinPageRef.current, pinFilterRef.current, false), 150);
            }
            return next;
          });
          setPendingCount((c) => Math.max(0, c - 1));
          setPinTotalCount((c) => Math.max(0, c - 1));
          setPostedCount((c) => c + 1);
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

  const handleSelectCurrentPage6 = () => {
    const pageIds = dhanviPins.map((p) => p.asin || p.pinId);
    setSelectedPinIds(new Set(pageIds));
    setFbSharePinCount(pageIds.length > 0 ? pageIds.length : 6);
    setStatusMessage({
      text: `✅ Selected all ${pageIds.length} newly added Amazon product(s) on Page ${pinPage}. Click "Share to Facebook" to begin!`,
      severity: 'info',
    });
  };

  const handleSyncWorldNewzsDeals = async () => {
    if (isSyncingWorldNewzs || isFbShareRunning) return;
    setIsSyncingWorldNewzs(true);
    setStatusMessage({
      text: '🔄 Syncing newly added Amazon.in products from worldnewzs.in/amazon-products...',
      severity: 'info',
    });
    try {
      await api.syncDeals();
      await fetchDhanviPins(1, pinFilter, true);
      setPinPage(1);
      setEndPage(1);
      setStatusMessage({
        text: '✅ Synced latest Amazon.in products from worldnewzs.in/amazon-products! Showing 6 unposted deals per page.',
        severity: 'success',
      });
    } catch (err: any) {
      setStatusMessage({
        text: `Sync note: ${err.message || err}`,
        severity: 'warning',
      });
    } finally {
      setIsSyncingWorldNewzs(false);
    }
  };

  const handlePinterestFacebookShare = async (singleProductId?: string) => {
    if (isFbShareRunning) return;
    wasRunningRef.current = true;
    setIsFbShareRunning(true);
    setShowInlineLiveMonitor(true);
    setFbShareStep({ step: 1, message: 'Verifying Facebook session & WorldNewzs Page identity...' });

    const specificIds = singleProductId
      ? [singleProductId]
      : selectedPinIds.size > 0
      ? Array.from(selectedPinIds)
      : undefined;

    const effectiveEndPage = Math.max(pinPage, endPage);
    const pagesSpan = effectiveEndPage - pinPage + 1;
    const countToShare = specificIds
      ? specificIds.length
      : pagesSpan > 1
      ? pagesSpan * 6
      : fbSharePinCount === 0
      ? Math.max(1, pendingCount)
      : fbSharePinCount;

    const destLabel = fbDestination === 'both' ? 'WorldNewzs Page & Group' : fbDestination === 'page' ? 'WorldNewzs Page Feed' : 'Amazon Affiliate Group';
    setStatusMessage({
      text: `🚀 Starting WorldNewzs Amazon Products → Facebook Automation (${
        specificIds
          ? `${specificIds.length} selected product(s)`
          : pagesSpan > 1
          ? `Page ${pinPage} to ${effectiveEndPage} (${countToShare} products, 6/page)`
          : `Page ${pinPage} (${countToShare} products)`
      } to ${destLabel}, ${fbShareDelay}s interval)...`,
      severity: 'info',
    });
    try {
      const res = await api.pinterestFacebookShare({
        pinCount: countToShare,
        delaySeconds: fbShareDelay,
        specificPinIds: specificIds,
        destination: fbDestination,
        startPage: pinPage,
        endPage: specificIds ? undefined : effectiveEndPage,
      });
      setStatusMessage({
        text: res.message || 'WorldNewzs → Facebook automation started!',
        severity: 'success',
      });
    } catch (err: any) {
      setStatusMessage({
        text: `WorldNewzs → Facebook share failed: ${err.message || err}`,
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
        text: `🧹 Auto-Clear Verified: ${res.cleanedCount} already-posted Amazon product(s) cleared from queue (${res.remainingCount} newly added / unposted products ready across ${Math.ceil((res.remainingCount || 1) / 6)} pages).`,
        severity: 'success',
      });
      await fetchDhanviPins(1, undefined, false);
      await fetchHistory();
    } catch (err: any) {
      setStatusMessage({
        text: `Failed to clean posted products: ${err.message || err}`,
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
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5, flexWrap: 'wrap' }}>
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
              label="worldnewzs.in/amazon-products (6/Page) → WorldNewzs Page & Affiliate Group"
              size="small"
              sx={{ bgcolor: '#EFF6FF', color: '#1D4ED8', fontWeight: 800, fontSize: '0.75rem' }}
            />
          </Box>
          <Typography variant="body2" color="text.secondary">
            Automated publishing of newly added Amazon.in products from{' '}
            <a href="https://worldnewzs.in/amazon-products" target="_blank" rel="noreferrer" style={{ color: '#D97706', fontWeight: 800, textDecoration: 'none' }}>
              worldnewzs.in/amazon-products
            </a>{' '}
            (<strong>6 products per page</strong>, matching Amazon Deal Cards) directly to{' '}
            <a href="https://www.facebook.com/profile.php?id=61589266599006" target="_blank" rel="noreferrer" style={{ color: '#1877F2', fontWeight: 700, textDecoration: 'none' }}>
              WorldNewzs Facebook Page
            </a>{' '}
            &{' '}
            <a href="https://www.facebook.com/groups/1761596288324903/" target="_blank" rel="noreferrer" style={{ color: '#1877F2', fontWeight: 700, textDecoration: 'none' }}>
              Amazon Affiliate Group
            </a>
            . Completed items auto-clear immediately after posting.
          </Typography>
        </Box>

        {/* Status KPI Chips */}
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          <Chip
            icon={<PushPinIcon fontSize="small" />}
            label={`New Unposted Deals: ${pendingCount} (${pinTotalPages} Pages × 6)`}
            size="small"
            sx={{ bgcolor: '#FEF3C7', color: '#92400E', fontWeight: 800 }}
          />
          <Chip
            icon={<CheckCircleIcon fontSize="small" />}
            label={`Posted & Auto-Cleared: ${postedCount}`}
            size="small"
            clickable
            onClick={handleOpenHistory}
            title="Click to view complete Facebook share history"
            sx={{ bgcolor: '#DCFCE7', color: '#15803D', fontWeight: 800 }}
          />
          <Chip
            icon={<DeleteSweepIcon fontSize="small" />}
            label="🧹 Auto-Clear Active"
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
        {/* Left Controls: Target, Page Range (6/page), Batch Size, Delay, Primary Share Button */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.2, flexWrap: 'wrap' }}>
          {/* Target Destination selector */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6 }}>
            <Typography variant="caption" fontWeight={700} color="#475569">
              Target:
            </Typography>
            <Box
              component="select"
              value={fbDestination}
              onChange={(e: any) => setFbDestination(e.target.value)}
              disabled={isFbShareRunning}
              sx={{
                px: 1.1,
                py: 0.6,
                borderRadius: 1.5,
                border: '1px solid #CBD5E1',
                bgcolor: '#FFFFFF',
                fontWeight: 800,
                fontSize: '0.82rem',
                color: '#1E293B',
                cursor: 'pointer',
              }}
            >
              <option value="both">🌐 Both (Page + Group)</option>
              <option value="page">📄 WorldNewzs Page Feed</option>
              <option value="group">👥 Amazon Affiliate Group</option>
            </Box>
          </Box>

          {/* From Page / To Page Range (6 products per page, matching Amazon Deal Cards) */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6 }}>
            <Typography variant="caption" fontWeight={700} color="#475569">
              From Page:
            </Typography>
            <Box
              component="select"
              value={pinPage}
              onChange={(e: any) => {
                const p = Number(e.target.value);
                setPinPage(p);
                if (endPage < p) setEndPage(p);
              }}
              disabled={isFbShareRunning}
              sx={{
                px: 1,
                py: 0.6,
                borderRadius: 1.5,
                border: '1px solid #CBD5E1',
                bgcolor: '#FFFFFF',
                fontWeight: 800,
                fontSize: '0.82rem',
                color: '#0F172A',
                cursor: 'pointer',
              }}
            >
              {Array.from({ length: Math.min(pinTotalPages, 500) }, (_, i) => i + 1).map((p) => (
                <option key={p} value={p}>
                  Page {p} (#{(p - 1) * 6 + 1}–#{Math.min(p * 6, pinTotalCount)})
                </option>
              ))}
            </Box>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6 }}>
            <Typography variant="caption" fontWeight={700} color="#475569">
              To Page:
            </Typography>
            <Box
              component="select"
              value={Math.max(pinPage, endPage)}
              onChange={(e: any) => {
                const ep = Number(e.target.value);
                setEndPage(ep);
                setFbSharePinCount(Math.max(1, ep - pinPage + 1) * 6);
              }}
              disabled={isFbShareRunning}
              sx={{
                px: 1,
                py: 0.6,
                borderRadius: 1.5,
                border: '1px solid #CBD5E1',
                bgcolor: '#FFFFFF',
                fontWeight: 800,
                fontSize: '0.82rem',
                color: '#0F172A',
                cursor: 'pointer',
              }}
            >
              {Array.from({ length: Math.min(pinTotalPages, 500) }, (_, i) => i + 1)
                .filter((p) => p >= pinPage)
                .slice(0, 50)
                .map((p) => (
                  <option key={p} value={p}>
                    Page {p} ({(p - pinPage + 1) * 6} Deals)
                  </option>
                ))}
            </Box>
          </Box>

          {/* Deals count selector */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6 }}>
            <Typography variant="caption" fontWeight={700} color="#475569">
              Batch:
            </Typography>
            <Box
              component="select"
              value={fbSharePinCount}
              onChange={(e: any) => {
                const val = Number(e.target.value);
                setFbSharePinCount(val);
                if (val >= 6) {
                  setEndPage(pinPage + Math.floor(val / 6) - 1);
                } else {
                  setEndPage(pinPage);
                }
              }}
              disabled={isFbShareRunning}
              sx={{
                px: 1,
                py: 0.6,
                borderRadius: 1.5,
                border: '1px solid #CBD5E1',
                bgcolor: '#FFFFFF',
                fontWeight: 800,
                fontSize: '0.82rem',
                color: '#0F172A',
                cursor: 'pointer',
              }}
            >
              <option value={6}>6 Deals (1 Page — Recommended)</option>
              <option value={12}>12 Deals (2 Pages)</option>
              <option value={18}>18 Deals (3 Pages)</option>
              <option value={24}>24 Deals (4 Pages)</option>
              <option value={30}>30 Deals (5 Pages)</option>
              <option value={0}>All Unposted ({pendingCount})</option>
            </Box>
          </Box>

          {/* Delay selector */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6 }}>
            <Typography variant="caption" fontWeight={700} color="#475569">
              Interval:
            </Typography>
            <Box
              component="select"
              value={fbShareDelay}
              onChange={(e: any) => setFbShareDelay(Number(e.target.value))}
              disabled={isFbShareRunning}
              sx={{
                px: 1,
                py: 0.6,
                borderRadius: 1.5,
                border: '1px solid #CBD5E1',
                bgcolor: '#FFFFFF',
                fontWeight: 800,
                fontSize: '0.82rem',
                color: '#0F172A',
                cursor: 'pointer',
              }}
            >
              <option value={15}>15 secs (Fast)</option>
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
              px: 2.2,
              py: 0.85,
              fontSize: '0.86rem',
              boxShadow: '0 2px 6px rgba(24, 119, 242, 0.3)',
              '&:hover': { bgcolor: '#0C63D4' },
              '&:disabled': { bgcolor: '#93C5FD', color: '#FFFFFF' },
            }}
          >
            {isFbShareRunning
              ? 'Sharing to Facebook...'
              : selectedPinIds.size > 0
              ? `🚀 Share ${selectedPinIds.size} Selected Product(s)`
              : endPage > pinPage
              ? `🚀 Share Pages ${pinPage}–${endPage} (${(endPage - pinPage + 1) * 6} Deals)`
              : `🚀 Share Page ${pinPage} (${fbSharePinCount === 0 ? pendingCount : fbSharePinCount} Deals)`}
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
                py: 0.85,
                fontSize: '0.84rem',
              }}
            >
              ⏹️ Stop & Finish
            </Button>
          )}

          {/* Select Current Page (6 Deals) Helper Button */}
          <Button
            variant="outlined"
            size="medium"
            onClick={handleSelectCurrentPage6}
            disabled={isFbShareRunning}
            sx={{
              borderColor: '#CBD5E1',
              color: '#334155',
              fontWeight: 700,
              textTransform: 'none',
              borderRadius: 2,
              px: 1.5,
              py: 0.75,
              fontSize: '0.8rem',
              bgcolor: '#FFFFFF',
              '&:hover': { bgcolor: '#F1F5F9', borderColor: '#94A3B8' },
            }}
          >
            ⚡ Select Page {pinPage} (6 Deals)
          </Button>

          {/* Sync New WorldNewzs Products Button */}
          <Tooltip title="Fetch newly added Amazon.in products from worldnewzs.in/amazon-products">
            <Button
              variant="outlined"
              size="medium"
              startIcon={isSyncingWorldNewzs ? <CircularProgress size={15} color="inherit" /> : <SyncIcon />}
              onClick={handleSyncWorldNewzsDeals}
              disabled={isSyncingWorldNewzs || isFbShareRunning}
              sx={{
                borderColor: '#93C5FD',
                color: '#1D4ED8',
                fontWeight: 700,
                textTransform: 'none',
                borderRadius: 2,
                px: 1.5,
                py: 0.75,
                fontSize: '0.8rem',
                bgcolor: '#EFF6FF',
                '&:hover': { bgcolor: '#DBEAFE', borderColor: '#2563EB' },
              }}
            >
              {isSyncingWorldNewzs ? 'Syncing...' : '🔄 Sync WorldNewzs Deals'}
            </Button>
          </Tooltip>

          {/* Clean Posted Products Button */}
          <Tooltip title="Verify and purge any already-posted Amazon products from the active queue">
            <Button
              variant="outlined"
              size="medium"
              startIcon={isCleaning ? <CircularProgress size={15} color="inherit" /> : <DeleteSweepIcon />}
              onClick={handleCleanPostedPins}
              disabled={isCleaning || isFbShareRunning}
              sx={{
                borderColor: '#FDBA74',
                color: '#C2410C',
                fontWeight: 700,
                textTransform: 'none',
                borderRadius: 2,
                px: 1.5,
                py: 0.75,
                fontSize: '0.8rem',
                bgcolor: '#FFF7ED',
                '&:hover': { bgcolor: '#FFEDD5', borderColor: '#EA580C' },
              }}
            >
              {isCleaning ? 'Cleaning...' : '🧹 Clear Posted'}
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

          {/* Refresh Unposted Deals */}
          <Tooltip title="Refresh unposted Amazon deals from worldnewzs.in/amazon-products">
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
              { n: 2, label: 'WorldNewzs 6/Page' },
              { n: 3, label: '1500px Image' },
              { n: 4, label: 'FB Page' },
              { n: 5, label: 'FB Group' },
              { n: 6, label: 'Clear & Record' },
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

      {/* ── Live Activity Stream Terminal + Inline Live Playwright Browser Monitor ── */}
      {(socialLogs.length > 0 || isFbShareRunning || liveBrowserFrame) && (
        <Box sx={{ mb: 2.5 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.8, flexWrap: 'wrap', gap: 1 }}>
            <Typography variant="caption" fontWeight={800} color="#475569" sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
              <TerminalIcon fontSize="small" sx={{ color: '#2563EB', fontSize: 16 }} />
              Live Playwright & WorldNewzs → Facebook Automation Stream ({socialLogs.length} events)
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <Button
                size="small"
                onClick={() => setShowInlineLiveMonitor((prev) => !prev)}
                sx={{ textTransform: 'none', fontSize: '0.72rem', p: 0, color: '#2563EB', fontWeight: 700 }}
              >
                {showInlineLiveMonitor ? '🔽 Hide Inline Browser View' : '🖥️ Show Inline Browser View'}
              </Button>
              <Button
                size="small"
                onClick={() => setLiveBrowserModalOpen(true)}
                sx={{ textTransform: 'none', fontSize: '0.72rem', p: 0, color: '#059669', fontWeight: 700 }}
              >
                🔍 Full Screen Browser
              </Button>
              {socialLogs.length > 0 && (
                <Button
                  size="small"
                  onClick={() => setSocialLogs([])}
                  sx={{ textTransform: 'none', fontSize: '0.7rem', p: 0, color: '#64748B' }}
                >
                  Clear Feed
                </Button>
              )}
            </Box>
          </Box>

          <Grid container spacing={1.5}>
            {/* Left: Terminal Log Stream */}
            <Grid item xs={12} md={showInlineLiveMonitor ? 7 : 12}>
              <Paper
                variant="outlined"
                sx={{
                  p: 1.5,
                  bgcolor: '#0F172A',
                  color: '#F8FAFC',
                  borderRadius: 2,
                  height: showInlineLiveMonitor ? 220 : 180,
                  overflowY: 'auto',
                  fontFamily: 'monospace',
                  fontSize: '0.74rem',
                  border: '1px solid #1E293B',
                }}
              >
                {socialLogs.length === 0 ? (
                  <Typography variant="caption" sx={{ color: '#64748B', fontFamily: 'monospace' }}>
                    Waiting for Playwright automation stream... Click "Post Page {pinPage} (6 Deals)" to watch live execution.
                  </Typography>
                ) : (
                  socialLogs.map((log, idx) => (
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
                  ))
                )}
                <div ref={terminalEndRef} />
              </Paper>
            </Grid>

            {/* Right: Inline Live Playwright Browser Split-Monitor */}
            {showInlineLiveMonitor && (
              <Grid item xs={12} md={5}>
                <Paper
                  variant="outlined"
                  sx={{
                    height: 220,
                    bgcolor: '#0F172A',
                    borderRadius: 2,
                    border: isFbShareRunning ? '2px solid #38BDF8' : '1px solid #1E293B',
                    overflow: 'hidden',
                    display: 'flex',
                    flexDirection: 'column',
                    position: 'relative',
                  }}
                >
                  <Box
                    sx={{
                      px: 1.2,
                      py: 0.5,
                      bgcolor: '#1E293B',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      borderBottom: '1px solid #334155',
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
                      <DesktopWindowsIcon sx={{ fontSize: 14, color: '#38BDF8' }} />
                      <Typography variant="caption" fontWeight={800} sx={{ color: '#F8FAFC', fontSize: '0.68rem' }}>
                        Playwright Live Viewport (worldnewzs.in → Facebook)
                      </Typography>
                    </Box>
                    <Chip
                      label={isFbShareRunning ? '● LIVE' : 'IDLE'}
                      size="small"
                      sx={{
                        height: 16,
                        fontSize: '0.58rem',
                        fontWeight: 800,
                        bgcolor: isFbShareRunning ? '#EF4444' : '#334155',
                        color: '#FFFFFF',
                      }}
                    />
                  </Box>
                  <Box
                    onClick={() => setLiveBrowserModalOpen(true)}
                    sx={{
                      flex: 1,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      bgcolor: '#020617',
                      cursor: 'pointer',
                      overflow: 'hidden',
                      position: 'relative',
                    }}
                  >
                    <img
                      src={liveBrowserFrame ? api.resolveUrl(liveBrowserFrame) : api.getLiveFrameUrl()}
                      alt="Playwright Live Preview"
                      onError={(e: any) => {
                        e.currentTarget.style.display = 'none';
                      }}
                      onLoad={(e: any) => {
                        e.currentTarget.style.display = 'block';
                      }}
                      style={{
                        width: '100%',
                        height: '100%',
                        objectFit: 'contain',
                        display: 'block',
                      }}
                    />
                    <Typography
                      variant="caption"
                      sx={{
                        position: 'absolute',
                        bottom: 6,
                        right: 8,
                        bgcolor: 'rgba(15,23,42,0.85)',
                        color: '#38BDF8',
                        px: 0.8,
                        py: 0.2,
                        borderRadius: 1,
                        fontSize: '0.62rem',
                        fontWeight: 700,
                        border: '1px solid #334155',
                      }}
                    >
                      Click to Expand
                    </Typography>
                  </Box>
                </Paper>
              </Grid>
            )}
          </Grid>
        </Box>
      )}

      {/* ── Filter & Pagination Bar (Strictly 6 Products / Page) ── */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1.5 }}>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
          <FilterListIcon fontSize="small" sx={{ color: '#64748B' }} />
          <Typography variant="body2" fontWeight={800} color="#334155">
            Active Queue (worldnewzs.in/amazon-products):
          </Typography>
          <Chip
            label={`🟡 Unposted Amazon Deals (${pinTotalCount}) • 6 Per Page`}
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
            {isCleaning ? 'Cleaning...' : '🧹 Auto-Clear Posted'}
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
          <Typography variant="caption" color="text.secondary" fontWeight={700}>
            Page {pinPage} of {pinTotalPages} • Showing {pinTotalCount > 0 ? (pinPage - 1) * pinPageSize + 1 : 0}–{Math.min(pinPage * pinPageSize, pinTotalCount)} of {pinTotalCount} Unposted Deals
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

      {/* ── WorldNewzs Amazon Deals Grid (6 Cards Per Page = 3 Columns x 2 Rows) ── */}
      {isLoadingPins ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 8, gap: 1.5 }}>
          <CircularProgress size={28} sx={{ color: '#1877F2' }} />
          <Typography variant="body2" color="text.secondary" fontWeight={700}>
            Loading unposted Amazon deals (6 per page) from worldnewzs.in/amazon-products...
          </Typography>
        </Box>
      ) : dhanviPins.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center', bgcolor: '#F8FAFC', borderColor: '#E2E8F0', borderRadius: 2 }}>
          <Typography variant="body1" color="#0F172A" fontWeight={800} sx={{ mb: 0.5 }}>
            🎉 All newly added Amazon products on worldnewzs.in/amazon-products have been posted to Facebook & auto-cleared!
          </Typography>
          <Typography variant="body2" color="text.secondary" fontWeight={500} sx={{ mb: 2 }}>
            Click "🔄 Sync WorldNewzs Deals" when new Amazon.in products are added, or download your completion reports below:
          </Typography>
          <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1.5, flexWrap: 'wrap' }}>
            <Button
              variant="outlined"
              size="medium"
              startIcon={isSyncingWorldNewzs ? <CircularProgress size={16} color="inherit" /> : <SyncIcon />}
              onClick={handleSyncWorldNewzsDeals}
              disabled={isSyncingWorldNewzs}
              sx={{
                borderColor: '#1877F2',
                color: '#1877F2',
                fontWeight: 800,
                textTransform: 'none',
                borderRadius: 2,
                px: 2.5,
              }}
            >
              🔄 Sync WorldNewzs Deals
            </Button>
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
          {dhanviPins.map((pin, idx) => {
            const isSelected = selectedPinIds.has(pin.pinId);
            const isPosted = pin.status === 'posted';
            const cardNumOnPage = pin.cardIndexOnPage || idx + 1;
            const asinCode = pin.asin || pin.pinId;
            const directAmazonUrl = pin.dealUrl || pin.destinationLink || pin.pinUrl;

            return (
              <Grid item xs={12} sm={6} md={4} key={pin.pinId}>
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
                  {/* Top-Left: Selection Checkbox + Page & Card Slot Badge */}
                  <Box
                    sx={{
                      position: 'absolute',
                      top: 8,
                      left: 8,
                      zIndex: 2,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.6,
                      bgcolor: 'rgba(255,255,255,0.94)',
                      borderRadius: 1.5,
                      px: 0.6,
                      py: 0.2,
                      border: '1px solid #E2E8F0',
                    }}
                  >
                    <Checkbox
                      size="small"
                      checked={isSelected}
                      onChange={() => toggleSelectPin(pin.pinId)}
                      sx={{ p: 0.2, color: '#1877F2', '&.Mui-checked': { color: '#1877F2' } }}
                    />
                    <Typography variant="caption" fontWeight={800} sx={{ fontSize: '0.66rem', color: '#1E293B' }}>
                      Page {pin.pageNumber || pinPage} • #{cardNumOnPage}/6
                    </Typography>
                  </Box>

                  {/* Top-Right: Discount + Status + High-Res Photo Badges */}
                  <Box sx={{ position: 'absolute', top: 8, right: 8, zIndex: 2, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.4 }}>
                    {pin.discount && (
                      <Chip
                        label={String(pin.discount).toUpperCase().includes('OFF') ? pin.discount : `${pin.discount} OFF`}
                        size="small"
                        sx={{
                          height: 20,
                          fontSize: '0.62rem',
                          fontWeight: 900,
                          bgcolor: '#DC2626',
                          color: '#FFFFFF',
                        }}
                      />
                    )}
                    {isPosted ? (
                      <Chip
                        icon={<CheckCircleIcon sx={{ fontSize: '13px !important' }} />}
                        label="POSTED"
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
                        label="NEW DEAL"
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
                    {pin.imageUrl && (
                      <Tooltip title="1500px High-Res Amazon Product Image verified for Facebook upload" arrow>
                        <Chip
                          icon={<PhotoCameraIcon sx={{ fontSize: '11px !important', color: '#047857 !important' }} />}
                          label="1500px HD"
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
                    )}
                  </Box>

                  {/* Product Image */}
                  <Box
                    sx={{
                      width: '100%',
                      height: 165,
                      bgcolor: '#F8FAFC',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      overflow: 'hidden',
                      pt: 3.5,
                      pb: 1,
                      px: 1.5,
                    }}
                  >
                    {pin.imageUrl ? (
                      <img
                        src={pin.imageUrl}
                        alt={pin.title}
                        loading="eager"
                        decoding="async"
                        width={160}
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

                  {/* Product Details (Matching Amazon Deal Cards) */}
                  <Box sx={{ p: 1.5, flexGrow: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                    <Box>
                      <Tooltip title={pin.title} arrow>
                        <Typography
                          variant="body2"
                          fontWeight={700}
                          color="#0F172A"
                          sx={{
                            display: '-webkit-box',
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                            lineHeight: 1.35,
                            fontSize: '0.82rem',
                            minHeight: '2.2rem',
                          }}
                        >
                          {pin.title}
                        </Typography>
                      </Tooltip>

                      {/* Price, MRP & Category Row */}
                      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, mt: 0.8, flexWrap: 'wrap' }}>
                        {pin.price && (
                          <Typography variant="subtitle2" fontWeight={900} color="#B45309" sx={{ fontSize: '0.95rem' }}>
                            {String(pin.price).startsWith('₹') ? pin.price : `₹${pin.price}`}
                          </Typography>
                        )}
                        {pin.originalPrice && (
                          <Typography
                            variant="caption"
                             sx={{ textDecoration: 'line-through', color: '#94A3B8', fontWeight: 600, fontSize: '0.75rem' }}
                          >
                            {String(pin.originalPrice).startsWith('₹') ? pin.originalPrice : `₹${pin.originalPrice}`}
                          </Typography>
                        )}
                        {pin.category && (
                          <Chip
                            label={pin.category}
                            size="small"
                            sx={{
                              height: 18,
                              fontSize: '0.6rem',
                              fontWeight: 700,
                              bgcolor: '#F1F5F9',
                              color: '#475569',
                              ml: 'auto',
                            }}
                          />
                        )}
                      </Box>
                    </Box>

                    {/* Footer: ASIN, Amazon.in Link, and 1-Click Share to FB */}
                    <Box
                      sx={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        mt: 1.2,
                        pt: 0.8,
                        borderTop: '1px solid #F1F5F9',
                        gap: 0.8,
                      }}
                    >
                      <Chip
                        label={`ASIN: ${asinCode.slice(-10)}`}
                        size="small"
                        sx={{
                          height: 20,
                          fontSize: '0.62rem',
                          fontFamily: 'monospace',
                          fontWeight: 700,
                          bgcolor: '#F8FAFC',
                          color: '#475569',
                          border: '1px solid #E2E8F0',
                        }}
                      />

                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        {directAmazonUrl && (
                          <Tooltip title={`Open Amazon.in Product (${directAmazonUrl})`} arrow>
                            <IconButton
                              size="small"
                              onClick={() => window.open(directAmazonUrl, '_blank')}
                              sx={{ p: 0.4, color: '#D97706', border: '1px solid #FDE68A', bgcolor: '#FFFBEB', borderRadius: 1.5 }}
                            >
                              <OpenInNewIcon sx={{ fontSize: 13 }} />
                            </IconButton>
                          </Tooltip>
                        )}
                        <Button
                          size="small"
                          variant="contained"
                          disabled={isFbShareRunning}
                          onClick={async () => {
                            setIsFbShareRunning(true);
                            setFbShareStep({ step: 1, message: `Posting ${pin.title.slice(0, 32)}...` });
                            try {
                              await api.pinterestFacebookShare({
                                pinCount: 1,
                                delaySeconds: fbShareDelay || 15,
                                destination: fbDestination,
                                startPage: pinPage,
                                endPage: pinPage,
                                specificPinIds: [pin.pinId],
                              });
                            } catch (e: any) {
                              setIsFbShareRunning(false);
                              setStatusMessage({ text: e.message || 'Failed to start Facebook share', severity: 'error' });
                            }
                          }}
                          sx={{
                            textTransform: 'none',
                            fontWeight: 800,
                            fontSize: '0.68rem',
                            py: 0.25,
                            px: 1,
                            minWidth: 0,
                            borderRadius: 1.5,
                            bgcolor: '#1877F2',
                            '&:hover': { bgcolor: '#155DB2' },
                          }}
                        >
                          Share to FB
                        </Button>
                      </Box>
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
              Playwright Live Browser Screen (worldnewzs.in/amazon-products → Facebook)
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
              {fbShareStep ? `Step ${fbShareStep.step}/7: ${fbShareStep.message}` : 'Source: worldnewzs.in/amazon-products (6/page) → Facebook Group "Amazon Affiliate Group"'}
            </Typography>
            <Typography variant="caption" sx={{ color: '#94A3B8' }}>
              Engine: Playwright CDP + Visual Spotlight HUD
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
            WorldNewzs → Facebook Share Complete!
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Automated sharing of unposted Amazon.in deals from worldnewzs.in/amazon-products (6 per page) to WorldNewzs Page & Amazon Affiliate Group has finished. Posted items have been automatically cleared from the active queue.
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
                DEALS POSTED & CLEARED
              </Typography>
            </Box>
            <Divider orientation="vertical" flexItem />
            <Box>
              <Typography variant="h4" fontWeight={900} color="#D97706">
                {lastBatchResult?.skippedCount ?? 0}
              </Typography>
              <Typography variant="caption" fontWeight={700} color="text.secondary">
                SKIPPED (ALREADY ON FB)
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
            Live proofs and ASIN deduplication records are saved. Click below to export your Excel spreadsheet or download the dated PDF report:
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
              Facebook Share History & ASIN Audit Ledger
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
              label="worldnewzs.in/amazon-products → Amazon Affiliate Group"
              sx={{ bgcolor: '#1877F2', color: '#fff', fontWeight: 800 }}
            />
            <Chip
              label={`Pending Unposted: ${pendingCount}`}
              sx={{ bgcolor: '#FEF3C7', color: '#92400E', fontWeight: 800 }}
            />
          </Box>

          {(!historyStats?.recentLogs || historyStats.recentLogs.length === 0) ? (
            <Alert severity="info" sx={{ borderRadius: 2 }}>
              No Amazon products have been logged yet. Click "Post Page 1 (6 Deals)" to begin sharing unposted deals from worldnewzs.in/amazon-products!
            </Alert>
          ) : (
            <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #E2E8F0', borderRadius: 2, maxHeight: 400 }}>
              <Table size="small" stickyHeader>
                <TableHead sx={{ bgcolor: '#F8FAFC' }}>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 800, fontSize: '0.78rem' }}>Date & Time</TableCell>
                    <TableCell sx={{ fontWeight: 800, fontSize: '0.78rem' }}>Destination</TableCell>
                    <TableCell sx={{ fontWeight: 800, fontSize: '0.78rem' }}>Amazon Product Title</TableCell>
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
                            {log.title || 'Amazon Deal'}
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
                            {(log.dealUrl || log.pinUrl) && (
                              <IconButton
                                size="small"
                                onClick={() => window.open(log.dealUrl || log.pinUrl, '_blank')}
                                title="Open Amazon.in Product Link"
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
