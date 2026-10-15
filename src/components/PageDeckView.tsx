import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  IconButton,
  Chip,
  Tooltip,
  Button,
  Paper,
  Grid,
  Pagination,
  CircularProgress,
  Skeleton,
  TextField,
  Checkbox,
} from '@mui/material';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import ShareIcon from '@mui/icons-material/Share';
import ContentCutIcon from '@mui/icons-material/ContentCut';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import SyncIcon from '@mui/icons-material/Sync';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import PushPinIcon from '@mui/icons-material/PushPin';
import { ProductDeal, RunState } from '../types/index.ts';
import { api } from '../services/api.ts';
import { sseClient } from '../services/sse.ts';

interface PageDeckViewProps {
  selectedPage: number;
  onPageChange: (page: number) => void;
  runState: RunState;
  onStartForPage: (page: number) => void;
  onStartForRange?: (startPage: number, endPage: number, startDealNumber?: number) => void;
  onStartForSelectedDeals?: (selectedDeals: ProductDeal[]) => void;
  onSync?: () => Promise<void>;
}

export const PageDeckView: React.FC<PageDeckViewProps> = ({
  selectedPage,
  onPageChange,
  runState,
  onStartForPage,
  onStartForRange,
  onStartForSelectedDeals,
  onSync,
}) => {
  const [deals, setDeals] = useState<ProductDeal[]>([]);
  const [totalPages, setTotalPages] = useState<number>(265);
  const [totalProducts, setTotalProducts] = useState<number>(1588);
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [pinnedCount, setPinnedCount] = useState<number>(508);
  const [totalCatalog, setTotalCatalog] = useState<number>(3048);
  const [pinFilter, setPinFilter] = useState<'pending' | 'pinned' | 'all'>('pending');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [isCleaning, setIsCleaning] = useState<boolean>(false);

  // Page range automation controller states
  const [rangeStart, setRangeStart] = useState<number>(1);
  const [rangeEnd, setRangeEnd] = useState<number>(1);
  const [startDealNumber, setStartDealNumber] = useState<number | ''>('');

  // Checkbox selection state (keyed by deal.id or asin or `${page}-${cardIndex}`)
  const [selectedDealsMap, setSelectedDealsMap] = useState<Map<string, ProductDeal>>(new Map());

  const getDealKey = (deal: ProductDeal, idx?: number) =>
    deal.id || deal.asin || `${deal.pageNumber || selectedPage}-${deal.cardIndex ?? idx ?? 0}`;

  const handleToggleCard = (deal: ProductDeal, idx: number) => {
    if (deal.isPinned) return; // Prevent selecting already-pinned deals
    const key = getDealKey(deal, idx);
    setSelectedDealsMap((prev) => {
      const next = new Map(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.set(key, { ...deal, cardIndex: deal.cardIndex ?? idx, pageNumber: deal.pageNumber || selectedPage });
      }
      return next;
    });
  };

  const selectableDeals = deals.filter((d) => !d.isPinned);
  const isCurrentPageFullySelected =
    selectableDeals.length > 0 && selectableDeals.every((d, i) => selectedDealsMap.has(getDealKey(d, i)));

  const handleToggleSelectCurrentPage = () => {
    setSelectedDealsMap((prev) => {
      const next = new Map(prev);
      if (isCurrentPageFullySelected) {
        selectableDeals.forEach((d, i) => next.delete(getDealKey(d, i)));
      } else {
        selectableDeals.forEach((d, i) => {
          next.set(getDealKey(d, i), { ...d, cardIndex: d.cardIndex ?? i, pageNumber: d.pageNumber || selectedPage });
        });
      }
      return next;
    });
  };

  const handleClearSelection = () => {
    setSelectedDealsMap(new Map());
  };

  const handleRunSelected = () => {
    const selectedList = Array.from(selectedDealsMap.values());
    if (selectedList.length === 0 || runState.isRunning) return;
    if (onStartForSelectedDeals) {
      onStartForSelectedDeals(selectedList);
    }
  };

  const numStart = Number(rangeStart);
  const numEnd = Number(rangeEnd);

  let validationError = '';
  if (!numStart || numStart < 1) {
    validationError = 'Start page must be at least 1.';
  } else if (numStart > totalPages) {
    validationError = `Start page cannot exceed total pages (${totalPages}).`;
  } else if (!numEnd || numEnd < 1) {
    validationError = 'End page must be at least 1.';
  } else if (numEnd > totalPages) {
    validationError = `End page cannot exceed total pages (${totalPages}).`;
  } else if (numEnd < numStart) {
    validationError = `End page (${numEnd}) must be >= Start page (${numStart}).`;
  }

  const isRangeValid = !validationError;
  const rangePageCount = isRangeValid ? numEnd - numStart + 1 : 0;
  const rangeExpectedCards = rangePageCount * 6;

  const handleRunRange = () => {
    if (!isRangeValid || runState.isRunning) return;
    const dealNum = typeof startDealNumber === 'number' && startDealNumber > 0 ? startDealNumber : undefined;
    if (onStartForRange) {
      onStartForRange(numStart, numEnd, dealNum);
    } else {
      onStartForPage(numStart);
    }
  };

  const fetchPageDeals = async (
    pageToFetch: number = selectedPage,
    filterToFetch: 'pending' | 'pinned' | 'all' = pinFilter
  ) => {
    setIsLoading(true);
    try {
      const res = await api.getDeals(pageToFetch, 6, filterToFetch);
      setDeals(res.deals || []);
      setTotalPages(res.totalPages || 1);
      setTotalProducts(res.totalProducts || 0);
      if (typeof res.pendingCount === 'number') setPendingCount(res.pendingCount);
      if (typeof res.pinnedCount === 'number') setPinnedCount(res.pinnedCount);
      if (typeof res.totalCatalog === 'number') setTotalCatalog(res.totalCatalog);
    } catch (err) {
      console.error('Failed to load page deals:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchPageDeals(selectedPage, pinFilter);
  }, [selectedPage, pinFilter]);

  // Real-time synchronization when automation pins deals
  useEffect(() => {
    const unsub = sseClient.subscribe('deal_pinned', () => {
      setPinnedCount((prev) => prev + 1);
      setPendingCount((prev) => Math.max(0, prev - 1));
      if (pinFilter === 'pending') {
        fetchPageDeals(selectedPage, 'pending');
      }
    });
    return () => unsub();
  }, [selectedPage, pinFilter]);

  const handleFilterChange = (newFilter: 'pending' | 'pinned' | 'all') => {
    setPinFilter(newFilter);
    onPageChange(1);
    fetchPageDeals(1, newFilter);
  };

  const handleCleanPinnedDeals = async () => {
    setIsCleaning(true);
    try {
      const res = await api.cleanPinnedDeals();
      if (res && typeof res.cleanedCount === 'number') {
        setPinnedCount(res.cleanedCount);
        setPendingCount(res.remainingCount || 0);
      }
      onPageChange(1);
      await fetchPageDeals(1, pinFilter);
    } catch (err) {
      console.error('Failed to clean pinned deals:', err);
    } finally {
      setIsCleaning(false);
    }
  };

  const handleSyncDeals = async () => {
    setIsSyncing(true);
    try {
      const res = await api.syncDeals();
      if (res && res.success) {
        setTotalProducts(res.totalProducts);
        setTotalPages(res.totalPages);
        await fetchPageDeals(selectedPage, pinFilter);
        if (onSync) {
          await onSync();
        }
      }
    } catch (err) {
      console.error('Failed to sync live deals:', err);
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <Card elevation={2} sx={{ borderRadius: 3, border: '1px solid #e2e8f0', p: { xs: 2, sm: 3 } }}>
      {/* Header Bar with Filter Tabs & Quick Actions */}
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', md: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'flex-start', md: 'center' },
          flexWrap: 'wrap',
          gap: 2,
          pb: 2,
          borderBottom: '1px solid #f1f5f9',
        }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
            <Typography variant="h6" fontWeight={800} color="#0f172a" sx={{ lineHeight: 1.2 }}>
              Amazon Deal Cards
            </Typography>
            <Chip
              label={`Page ${selectedPage} of ${totalPages} • ${totalProducts} deals in view`}
              size="small"
              sx={{ bgcolor: '#f1f5f9', fontWeight: 700, color: '#475569' }}
            />
          </Box>

          {/* Pinterest Automation Filter Chips */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <Chip
              icon={<AutoAwesomeIcon sx={{ fontSize: 14 }} />}
              label={`Ready to Pin (${pendingCount > 0 ? pendingCount : (pinFilter === 'pending' ? totalProducts : totalCatalog - pinnedCount)})`}
              size="small"
              onClick={() => handleFilterChange('pending')}
              color={pinFilter === 'pending' ? 'primary' : 'default'}
              variant={pinFilter === 'pending' ? 'filled' : 'outlined'}
              sx={{
                fontWeight: 700,
                cursor: 'pointer',
                bgcolor: pinFilter === 'pending' ? '#E60023' : undefined,
                color: pinFilter === 'pending' ? '#ffffff' : '#334155',
                '&:hover': { bgcolor: pinFilter === 'pending' ? '#be123c' : '#f1f5f9' },
              }}
            />

            <Chip
              icon={<CheckCircleIcon sx={{ fontSize: 14 }} />}
              label={`Moved to Pinterest (${pinnedCount})`}
              size="small"
              onClick={() => handleFilterChange('pinned')}
              color={pinFilter === 'pinned' ? 'success' : 'default'}
              variant={pinFilter === 'pinned' ? 'filled' : 'outlined'}
              sx={{
                fontWeight: 700,
                cursor: 'pointer',
                bgcolor: pinFilter === 'pinned' ? '#059669' : undefined,
                color: pinFilter === 'pinned' ? '#ffffff' : '#334155',
                '&:hover': { bgcolor: pinFilter === 'pinned' ? '#047857' : '#f1f5f9' },
              }}
            />

            <Chip
              label={`All Deals (${totalCatalog || 3048})`}
              size="small"
              onClick={() => handleFilterChange('all')}
              color={pinFilter === 'all' ? 'default' : 'default'}
              variant={pinFilter === 'all' ? 'filled' : 'outlined'}
              sx={{
                fontWeight: 700,
                cursor: 'pointer',
                bgcolor: pinFilter === 'all' ? '#334155' : undefined,
                color: pinFilter === 'all' ? '#ffffff' : '#64748b',
                '&:hover': { bgcolor: pinFilter === 'all' ? '#1e293b' : '#f1f5f9' },
              }}
            />
          </Box>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
          <Pagination
            count={totalPages}
            page={selectedPage}
            onChange={(_, val) => onPageChange(val)}
            color="primary"
            shape="rounded"
            size="medium"
            disabled={runState.isRunning}
          />

          <Tooltip title="Verify and purge all 508+ already-pinned products from the active queue">
            <Button
              variant="outlined"
              size="small"
              startIcon={isCleaning ? <CircularProgress size={15} color="inherit" /> : <DeleteSweepIcon />}
              onClick={handleCleanPinnedDeals}
              disabled={isCleaning || runState.isRunning}
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
              {isCleaning ? 'Cleaning...' : '🧹 Clean Pinned'}
            </Button>
          </Tooltip>

          <Tooltip title="Fetch latest live Amazon deals directly from WorldNewzs.in">
            <Button
              variant="outlined"
              color="primary"
              size="small"
              startIcon={isSyncing ? <CircularProgress size={15} color="inherit" /> : <SyncIcon />}
              disabled={isSyncing || runState.isRunning}
              onClick={handleSyncDeals}
              sx={{
                fontWeight: 700,
                textTransform: 'none',
                borderRadius: 2,
                px: 1.75,
                py: 0.75,
                fontSize: '0.8rem',
              }}
            >
              {isSyncing ? 'Syncing...' : 'Sync Deals'}
            </Button>
          </Tooltip>

          <Button
            variant="contained"
            color="primary"
            size="small"
            startIcon={<AutoAwesomeIcon />}
            disabled={runState.isRunning || (pinFilter === 'pinned' && deals.every((d) => d.isPinned))}
            onClick={() => onStartForPage(selectedPage)}
            sx={{
              bgcolor: '#E60023',
              fontWeight: 700,
              textTransform: 'none',
              borderRadius: 2,
              px: 2,
              py: 0.75,
              fontSize: '0.8rem',
              '&:hover': { bgcolor: '#be123c' },
            }}
          >
            Run Page {selectedPage}
          </Button>
        </Box>
      </Box>

      {/* Page Range Automation Controller */}
      <Paper
        elevation={0}
        sx={{
          mt: 2,
          p: 2,
          borderRadius: 2.5,
          bgcolor: '#f8fafc',
          border: '1px solid #e2e8f0',
          display: 'flex',
          flexDirection: 'column',
          gap: 1.5,
        }}
      >
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AutoAwesomeIcon color="primary" fontSize="small" />
            <Typography variant="subtitle2" fontWeight={800} color="#0f172a">
              Automate Pagination Range (Between Pages)
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <Typography variant="caption" color="text.secondary" fontWeight={600}>
              Presets:
            </Typography>
            <Chip
              label="Page 1 (Start)"
              size="small"
              onClick={() => {
                setRangeStart(1);
                setRangeEnd(1);
                onPageChange(1);
              }}
              color={numStart === 1 && numEnd === 1 ? 'primary' : 'default'}
              variant={numStart === 1 && numEnd === 1 ? 'filled' : 'outlined'}
              sx={{ fontWeight: 700, cursor: 'pointer' }}
            />
            <Chip
              label="Pages 1 - 5"
              size="small"
              onClick={() => {
                setRangeStart(1);
                setRangeEnd(5);
              }}
              color={numStart === 1 && numEnd === 5 ? 'primary' : 'default'}
              variant={numStart === 1 && numEnd === 5 ? 'filled' : 'outlined'}
              sx={{ fontWeight: 700, cursor: 'pointer' }}
            />
            <Chip
              label="Pages 1 - 10"
              size="small"
              onClick={() => {
                setRangeStart(1);
                setRangeEnd(10);
                setStartDealNumber('');
              }}
              color={numStart === 1 && numEnd === 10 && !startDealNumber ? 'primary' : 'default'}
              variant={numStart === 1 && numEnd === 10 && !startDealNumber ? 'filled' : 'outlined'}
              sx={{ fontWeight: 700, cursor: 'pointer' }}
            />
            <Chip
              label={`Active (Page ${selectedPage})`}
              size="small"
              onClick={() => {
                setRangeStart(selectedPage);
                setRangeEnd(selectedPage);
                setStartDealNumber('');
              }}
              variant="outlined"
              sx={{ fontWeight: 600, cursor: 'pointer' }}
            />
          </Box>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
          {/* Start Page Input Controller */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" fontWeight={700} color="#334155">
              From Page:
            </Typography>
            <TextField
              type="number"
              size="small"
              value={rangeStart}
              onChange={(e) => setRangeStart(parseInt(e.target.value) || 1)}
              inputProps={{ min: 1, max: totalPages, style: { width: 70, fontWeight: 700 } }}
              disabled={runState.isRunning}
              error={!numStart || numStart < 1 || numStart > totalPages}
            />
          </Box>

          <Typography variant="body2" fontWeight={700} color="#64748b">
            to
          </Typography>

          {/* End Page Input Controller */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" fontWeight={700} color="#334155">
              To Page:
            </Typography>
            <TextField
              type="number"
              size="small"
              value={rangeEnd}
              onChange={(e) => setRangeEnd(parseInt(e.target.value) || 1)}
              inputProps={{ min: 1, max: totalPages, style: { width: 70, fontWeight: 700 } }}
              disabled={runState.isRunning}
              error={!numEnd || numEnd < 1 || numEnd > totalPages || numEnd < numStart}
            />
          </Box>

          {/* Resume Deal # (Optional Offset) */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" fontWeight={700} color="#334155">
              Resume Deal #:
            </Typography>
            <TextField
              type="number"
              size="small"
              placeholder="e.g. 58"
              value={startDealNumber}
              onChange={(e) => {
                const val = e.target.value === '' ? '' : parseInt(e.target.value);
                setStartDealNumber(val);
                if (typeof val === 'number' && val > 0) {
                  const p = Math.floor((val - 1) / 6) + 1;
                  setRangeStart(p);
                }
              }}
              inputProps={{ min: 1, max: totalProducts, style: { width: 80, fontWeight: 700 } }}
              disabled={runState.isRunning}
            />
          </Box>

          {/* Range Summary Badge */}
          {isRangeValid ? (
            <Chip
              label={`Range: Page ${numStart} to ${numEnd}${startDealNumber ? ` • Resuming from Deal #${startDealNumber}` : ''} • ${rangePageCount} page(s) (${rangeExpectedCards} products)`}
              color="primary"
              variant="outlined"
              sx={{ fontWeight: 700 }}
            />
          ) : (
            <Chip label={validationError} color="error" size="small" sx={{ fontWeight: 700 }} />
          )}

          <Box sx={{ ml: 'auto' }}>
            <Button
              variant="contained"
              color="primary"
              startIcon={<AutoAwesomeIcon />}
              disabled={runState.isRunning || !isRangeValid}
              onClick={handleRunRange}
              sx={{
                bgcolor: '#E60023',
                fontWeight: 800,
                textTransform: 'none',
                borderRadius: 2,
                px: 3,
                py: 1,
                boxShadow: '0 4px 14px rgba(230, 0, 35, 0.3)',
                '&:hover': { bgcolor: '#be123c' },
              }}
            >
              {runState.isRunning
                ? `Running (Page ${runState.currentPage} of ${runState.endPage || runState.selectedPages})...`
                : `Run Automation: Page ${numStart} to ${numEnd}`}
            </Button>
          </Box>
        </Box>
      </Paper>

      {/* Checkbox Selection Action Banner & Quick Controls */}
      <Paper
        elevation={0}
        sx={{
          mt: 2,
          p: 1.5,
          borderRadius: 2,
          bgcolor: selectedDealsMap.size > 0 ? '#fff1f2' : '#f8fafc',
          border: selectedDealsMap.size > 0 ? '1.5px solid #fecdd3' : '1px dashed #cbd5e1',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 1.5,
          transition: 'all 0.25s ease',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.2, flexWrap: 'wrap' }}>
          <Button
            size="small"
            variant={isCurrentPageFullySelected ? 'contained' : 'outlined'}
            color="primary"
            onClick={handleToggleSelectCurrentPage}
            disabled={runState.isRunning || selectableDeals.length === 0}
            sx={{
              textTransform: 'none',
              fontWeight: 700,
              fontSize: '0.8rem',
              borderRadius: 2,
              bgcolor: isCurrentPageFullySelected ? '#E60023' : undefined,
              borderColor: '#E60023',
              color: isCurrentPageFullySelected ? '#fff' : '#E60023',
              '&:hover': {
                bgcolor: isCurrentPageFullySelected ? '#be123c' : '#ffe4e6',
              },
            }}
          >
            {isCurrentPageFullySelected
              ? `✓ Page ${selectedPage} Selected (${selectableDeals.length} Deals)`
              : `⚡ Select Page ${selectedPage} (${selectableDeals.length} Deals)`}
          </Button>

          {selectedDealsMap.size > 0 && (
            <Button
              size="small"
              variant="text"
              onClick={handleClearSelection}
              disabled={runState.isRunning}
              sx={{
                textTransform: 'none',
                fontWeight: 600,
                fontSize: '0.8rem',
                color: '#64748b',
                '&:hover': { color: '#0f172a', bgcolor: '#f1f5f9' },
              }}
            >
              Clear Selection ({selectedDealsMap.size})
            </Button>
          )}

          <Chip
            label={
              selectedDealsMap.size > 0
                ? `🎯 ${selectedDealsMap.size} Deal Card(s) Selected for Selective Pinning`
                : '💡 Check individual cards or click "Select Page" to pin only specific deals'
            }
            size="small"
            color={selectedDealsMap.size > 0 ? 'error' : 'default'}
            variant={selectedDealsMap.size > 0 ? 'filled' : 'outlined'}
            sx={{ fontWeight: 700, fontSize: '0.75rem' }}
          />
        </Box>

        {selectedDealsMap.size > 0 && (
          <Button
            variant="contained"
            color="primary"
            startIcon={<AutoAwesomeIcon />}
            disabled={runState.isRunning}
            onClick={handleRunSelected}
            sx={{
              bgcolor: '#E60023',
              fontWeight: 800,
              textTransform: 'none',
              borderRadius: 2,
              px: 2.5,
              py: 0.75,
              boxShadow: '0 4px 14px rgba(230, 0, 35, 0.35)',
              '&:hover': { bgcolor: '#be123c' },
            }}
          >
            {runState.isRunning
              ? 'Automation Running...'
              : `🚀 Pin ${selectedDealsMap.size} Selected Deal${selectedDealsMap.size > 1 ? 's' : ''}`}
          </Button>
        )}
      </Paper>

      {/* 6 Products Grid with Equal Height, Zero Gaps, and Mobile Responsive Alignment */}
      {isLoading ? (
        <Grid container spacing={2.5} sx={{ mt: 1 }}>
          {[1, 2, 3, 4, 5, 6].map((n) => (
            <Grid item xs={12} sm={6} md={4} key={n}>
              <Skeleton variant="rectangular" height={340} sx={{ borderRadius: 2.5 }} />
            </Grid>
          ))}
        </Grid>
      ) : (
        <Grid container spacing={2.5} sx={{ mt: 1 }}>
          {deals.map((deal, idx) => {
            const isActive =
              runState.isRunning &&
              runState.currentPage === selectedPage &&
              runState.currentCardIndex === idx;
            const isChecked = selectedDealsMap.has(getDealKey(deal, idx));

            return (
              <Grid item xs={12} sm={6} md={4} key={deal.id || idx}>
                <Card
                  elevation={isActive ? 6 : (isChecked ? 3 : 1)}
                  sx={{
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    borderRadius: 2.5,
                    border: isActive
                      ? '2px solid #E60023'
                      : (isChecked ? '2px solid #E60023' : '1px solid #e2e8f0'),
                    bgcolor: isChecked ? '#fffdfd' : (deal.isPinned ? '#fcfdfd' : '#ffffff'),
                    transition: 'all 0.25s ease',
                    position: 'relative',
                    overflow: 'hidden',
                    transform: isActive ? 'scale(1.02)' : (isChecked ? 'translateY(-2px)' : 'none'),
                    boxShadow: isChecked ? '0 4px 12px rgba(230, 0, 35, 0.15)' : undefined,
                  }}
                >
                  {/* Top Badge & Tag Header */}
                  <Box
                    sx={{
                      p: 1.2,
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      bgcolor: isChecked ? '#fff5f5' : (deal.isPinned ? '#f0fdf4' : '#f8fafc'),
                      borderBottom: '1px solid #f1f5f9',
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8, flexWrap: 'wrap' }}>
                      <Checkbox
                        size="small"
                        checked={isChecked}
                        onChange={() => handleToggleCard(deal, idx)}
                        disabled={runState.isRunning || deal.isPinned}
                        sx={{
                          p: 0,
                          color: '#cbd5e1',
                          '&.Mui-checked': {
                            color: '#E60023',
                          },
                        }}
                        inputProps={{ 'aria-label': `Select deal ${deal.truncatedTitle}` }}
                      />
                      <Chip
                        label={`Page ${deal.pageNumber || selectedPage} • #${idx + 1}`}
                        size="small"
                        color={isActive ? 'error' : 'default'}
                        sx={{
                          fontSize: 10,
                          fontWeight: 800,
                          height: 22,
                          bgcolor: isActive ? '#fee2e2' : '#f1f5f9',
                          color: isActive ? '#dc2626' : '#1e293b',
                        }}
                      />
                      {deal.isPinned ? (
                        <Chip
                          icon={<CheckCircleIcon sx={{ fontSize: '11px !important', color: '#16a34a' }} />}
                          label="Moved to Pinterest"
                          size="small"
                          sx={{
                            fontSize: 9.5,
                            fontWeight: 700,
                            height: 22,
                            bgcolor: '#dcfce7',
                            color: '#15803d',
                            border: '1px solid #bbf7d0',
                          }}
                        />
                      ) : (
                        <Chip
                          label={deal.tag || 'DEAL'}
                          size="small"
                          sx={{ fontSize: 9, fontWeight: 700, height: 20, bgcolor: '#e2e8f0', color: '#475569' }}
                        />
                      )}
                    </Box>
                    <Chip
                      label={deal.discount || '45% OFF'}
                      size="small"
                      color="error"
                      sx={{ fontSize: 10, fontWeight: 700, height: 22 }}
                    />
                  </Box>

                  {/* Lazy Loaded Product Image Container */}
                  <Box
                    sx={{
                      height: 150,
                      minHeight: 150,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      p: 1.5,
                      bgcolor: '#ffffff',
                    }}
                  >
                    <Box
                      component="img"
                      src={deal.imageUrl}
                      alt={deal.title}
                      loading="lazy"
                      decoding="async"
                      width={140}
                      height={140}
                      sx={{
                        maxHeight: 140,
                        maxWidth: '100%',
                        objectFit: 'contain',
                        transition: 'transform 0.3s ease',
                        '&:hover': { transform: 'scale(1.05)' },
                      }}
                    />
                  </Box>

                  {/* Title, Board Name, Price & Actions */}
                  <CardContent
                    sx={{
                      p: 2,
                      pt: 1.25,
                      display: 'flex',
                      flexDirection: 'column',
                      flexGrow: 1,
                      '&:last-child': { pb: 2 },
                    }}
                  >
                    <Typography
                      variant="body2"
                      fontWeight={700}
                      sx={{
                        color: '#0f172a',
                        height: 40,
                        minHeight: 40,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        fontSize: '0.84rem',
                        lineHeight: 1.25,
                        mb: 1,
                      }}
                      title={deal.title}
                    >
                      {deal.title}
                    </Typography>

                    {/* 50-Character Truncation Showcase */}
                    <Paper
                      elevation={0}
                      sx={{
                        p: 0.75,
                        px: 1,
                        mb: 1.25,
                        bgcolor: '#fff1f2',
                        border: '1px dashed #fecdd3',
                        borderRadius: 1.5,
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.25 }}>
                        <ContentCutIcon sx={{ color: '#E60023', fontSize: 13 }} />
                        <Typography variant="caption" fontWeight={700} color="#E60023" sx={{ fontSize: 11 }}>
                          Board Title (Max 50 Chars):
                        </Typography>
                      </Box>
                      <Typography
                        variant="caption"
                        sx={{ fontFamily: 'monospace', fontWeight: 600, color: '#334155', fontSize: 11 }}
                        noWrap
                      >
                        "{deal.truncatedTitle}" ({deal.truncatedTitle.length} chars)
                      </Typography>
                    </Paper>

                    {/* Price & Actions (Anchored to Card Bottom with mt: auto) */}
                    <Box
                      sx={{
                        mt: 'auto',
                        pt: 1.25,
                        borderTop: '1px solid #f1f5f9',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.75 }}>
                        <Typography variant="h6" fontWeight={800} color="text.primary" sx={{ fontSize: '1.05rem', lineHeight: 1 }}>
                          {deal.price}
                        </Typography>
                        {deal.originalPrice && (
                          <Typography variant="caption" sx={{ textDecoration: 'line-through', color: '#94a3b8', fontSize: 11 }}>
                            {deal.originalPrice}
                          </Typography>
                        )}
                      </Box>

                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Tooltip title="View Amazon Product">
                          <IconButton
                            size="small"
                            component="a"
                            href={deal.dealUrl || deal.productUrl}
                            target="_blank"
                            sx={{ border: '1px solid #e2e8f0', color: '#64748b', p: 0.6 }}
                          >
                            <OpenInNewIcon sx={{ fontSize: 15 }} />
                          </IconButton>
                        </Tooltip>

                        <Tooltip title="Open Pinterest Pin Link / Creator">
                          <IconButton
                            size="small"
                            component="a"
                            href={
                              deal.shareUrl ||
                              `https://www.pinterest.com/pin/create/button/?url=${encodeURIComponent(
                                deal.dealUrl || ''
                              )}&media=${encodeURIComponent(
                                deal.imageUrl || ''
                              )}&description=${encodeURIComponent(
                                `${deal.truncatedTitle} | ${deal.price} | Dhanvi Collections on Amazon & WorldNewzs Deals`
                              )}`
                            }
                            target="_blank"
                            rel="noopener noreferrer"
                            sx={{
                              bgcolor: isActive ? '#E60023' : '#fff1f2',
                              color: isActive ? '#fff' : '#E60023',
                              border: '1px solid #fecdd3',
                              p: 0.6,
                              '&:hover': { bgcolor: '#E60023', color: '#fff' },
                            }}
                          >
                            <ShareIcon sx={{ fontSize: 15 }} />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            );
          })}
        </Grid>
      )}
    </Card>
  );
};

export default PageDeckView;
