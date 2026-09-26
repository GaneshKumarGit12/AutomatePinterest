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
} from '@mui/material';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import ShoppingBagIcon from '@mui/icons-material/ShoppingBag';
import ShareIcon from '@mui/icons-material/Share';
import ContentCutIcon from '@mui/icons-material/ContentCut';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import SyncIcon from '@mui/icons-material/Sync';
import { ProductDeal, RunState } from '../types/index.ts';
import { api } from '../services/api.ts';

interface PageDeckViewProps {
  selectedPage: number;
  onPageChange: (page: number) => void;
  runState: RunState;
  onStartForPage: (page: number) => void;
  onStartForRange?: (startPage: number, endPage: number, startDealNumber?: number) => void;
  onSync?: () => Promise<void>;
}

export const PageDeckView: React.FC<PageDeckViewProps> = ({
  selectedPage,
  onPageChange,
  runState,
  onStartForPage,
  onStartForRange,
  onSync,
}) => {
  const [deals, setDeals] = useState<ProductDeal[]>([]);
  const [totalPages, setTotalPages] = useState<number>(265);
  const [totalProducts, setTotalProducts] = useState<number>(1588);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);

  // Page range automation controller states
  const [rangeStart, setRangeStart] = useState<number>(1);
  const [rangeEnd, setRangeEnd] = useState<number>(1);
  const [startDealNumber, setStartDealNumber] = useState<number | ''>('');

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

  const fetchPageDeals = async () => {
    setIsLoading(true);
    try {
      const res = await api.getDeals(selectedPage, 6);
      setDeals(res.deals || []);
      setTotalPages(res.totalPages || 230);
      setTotalProducts(res.totalProducts || 1380);
    } catch (err) {
      console.error('Failed to load page deals:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchPageDeals();
  }, [selectedPage]);

  const handleSyncDeals = async () => {
    setIsSyncing(true);
    try {
      const res = await api.syncDeals();
      if (res && res.success) {
        setTotalProducts(res.totalProducts);
        setTotalPages(res.totalPages);
        await fetchPageDeals();
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
    <Card elevation={2} sx={{ borderRadius: 3, border: '1px solid #e2e8f0', p: 3 }}>
      {/* Header Bar with Pagination */}
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 2,
          pb: 2.5,
          borderBottom: '1px solid #f1f5f9',
        }}
      >
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Typography variant="h6" fontWeight={800} color="#0f172a">
              Amazon Deal Cards (Page {selectedPage})
            </Typography>
            <Chip
              label={`Showing Products 1 to 6 on Page ${selectedPage} • ${totalProducts} total deals (${totalPages} pages)`}
              size="small"
              sx={{ bgcolor: '#f1f5f9', fontWeight: 700, color: '#475569' }}
            />
          </Box>
          <Typography variant="caption" color="text.secondary">
            Products 1 to 6 for Page {selectedPage} with 50-character title truncation. Synced live from https://worldnewzs.in/amazon-products.
          </Typography>
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

          <Tooltip title="Fetch latest live Amazon deals directly from WorldNewzs.in">
            <Button
              variant="outlined"
              color="primary"
              startIcon={isSyncing ? <CircularProgress size={16} color="inherit" /> : <SyncIcon />}
              disabled={isSyncing || runState.isRunning}
              onClick={handleSyncDeals}
              sx={{
                fontWeight: 700,
                textTransform: 'none',
                borderRadius: 2,
                px: 2,
              }}
            >
              {isSyncing ? 'Syncing...' : 'Sync WorldNewzs Deals'}
            </Button>
          </Tooltip>

          <Button
            variant="contained"
            color="primary"
            startIcon={<AutoAwesomeIcon />}
            disabled={runState.isRunning}
            onClick={() => onStartForPage(selectedPage)}
            sx={{
              bgcolor: '#E60023',
              fontWeight: 700,
              textTransform: 'none',
              borderRadius: 2,
              px: 2.5,
              '&:hover': { bgcolor: '#be123c' },
            }}
          >
            Run 11-Steps for Page {selectedPage}
          </Button>
        </Box>
      </Box>

      {/* Page Range Automation Controller (Pagination Range: e.g. 6 to 8 or 1 to 10) */}
      <Paper
        elevation={0}
        sx={{
          mt: 2.5,
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
              label="Page 5 (Test)"
              size="small"
              onClick={() => {
                setRangeStart(5);
                setRangeEnd(5);
                onPageChange(5);
              }}
              color={numStart === 5 && numEnd === 5 ? 'primary' : 'default'}
              variant={numStart === 5 && numEnd === 5 ? 'filled' : 'outlined'}
              sx={{ fontWeight: 700, cursor: 'pointer' }}
            />
            <Chip
              label="Pages 6 - 8"
              size="small"
              onClick={() => {
                setRangeStart(6);
                setRangeEnd(8);
              }}
              color={numStart === 6 && numEnd === 8 ? 'primary' : 'default'}
              variant={numStart === 6 && numEnd === 8 ? 'filled' : 'outlined'}
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
              label="⚡ Resume from Deal #58 (Page 10 to 20)"
              size="small"
              onClick={() => {
                setRangeStart(10);
                setRangeEnd(20);
                setStartDealNumber(58);
                onPageChange(10);
              }}
              color={startDealNumber === 58 ? 'secondary' : 'default'}
              variant={startDealNumber === 58 ? 'filled' : 'outlined'}
              sx={{
                fontWeight: 700,
                cursor: 'pointer',
                bgcolor: startDealNumber === 58 ? '#7c3aed' : undefined,
                color: startDealNumber === 58 ? '#fff' : undefined,
              }}
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
            <Chip
              label={validationError}
              color="error"
              size="small"
              sx={{ fontWeight: 700 }}
            />
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

      {/* 6 Products Grid with Lazy Loading */}
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

            return (
              <Grid item xs={12} sm={6} md={4} key={deal.id || idx}>
                <Card
                  elevation={isActive ? 6 : 1}
                  sx={{
                    borderRadius: 2.5,
                    border: isActive ? '2px solid #E60023' : '1px solid #e2e8f0',
                    bgcolor: '#ffffff',
                    transition: 'all 0.3s ease',
                    position: 'relative',
                    overflow: 'hidden',
                    transform: isActive ? 'scale(1.02)' : 'none',
                  }}
                >
                  {/* Top Badge & Tag */}
                  <Box
                    sx={{
                      p: 1.2,
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      bgcolor: '#f8fafc',
                      borderBottom: '1px solid #f1f5f9',
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
                      <Chip
                        label={`Page ${deal.pageNumber || selectedPage} • Product #${idx + 1} of 6`}
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
                      <Chip
                        label={deal.tag || 'DEAL'}
                        size="small"
                        sx={{ fontSize: 9, fontWeight: 700, height: 20, bgcolor: '#e2e8f0', color: '#475569' }}
                      />
                    </Box>
                    <Chip
                      label={deal.discount || '45% OFF'}
                      size="small"
                      color="error"
                      sx={{ fontSize: 10, fontWeight: 700, height: 22 }}
                    />
                  </Box>

                  {/* Lazy Loaded Product Image */}
                  <Box
                    sx={{
                      height: 150,
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
                      loading="eager"
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

                  {/* Title, Truncation Indicator & Pricing */}
                  <CardContent sx={{ p: 2, pt: 1, '&:last-child': { pb: 2 } }}>
                    <Typography
                      variant="body2"
                      fontWeight={700}
                      sx={{
                        color: '#0f172a',
                        height: 42,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        fontSize: '0.84rem',
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
                        p: 1,
                        mb: 1.5,
                        bgcolor: '#fff1f2',
                        border: '1px dashed #fecdd3',
                        borderRadius: 1.5,
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.5 }}>
                        <ContentCutIcon sx={{ color: '#E60023', fontSize: 14 }} />
                        <Typography variant="caption" fontWeight={700} color="#E60023">
                          Board Title (Max 50 Chars):
                        </Typography>
                      </Box>
                      <Typography
                        variant="caption"
                        sx={{ fontFamily: 'monospace', fontWeight: 600, color: '#334155' }}
                        noWrap
                      >
                        "{deal.truncatedTitle}" ({deal.truncatedTitle.length} chars)
                      </Typography>
                    </Paper>

                    {/* Price & Actions */}
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
                        <Typography variant="h6" fontWeight={800} color="text.primary" sx={{ fontSize: '1.1rem' }}>
                          {deal.price}
                        </Typography>
                        {deal.originalPrice && (
                          <Typography variant="caption" sx={{ textDecoration: 'line-through', color: '#94a3b8' }}>
                            {deal.originalPrice}
                          </Typography>
                        )}
                      </Box>

                      <Box sx={{ display: 'flex', gap: 0.75 }}>
                        <Tooltip title="View Amazon Product">
                          <IconButton
                            size="small"
                            component="a"
                            href={deal.dealUrl}
                            target="_blank"
                            sx={{ border: '1px solid #e2e8f0', color: '#64748b' }}
                          >
                            <OpenInNewIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>

                        <Tooltip title="Open Pinterest Pin Creation Link">
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
                              '&:hover': { bgcolor: '#E60023', color: '#fff' },
                            }}
                          >
                            <ShareIcon fontSize="small" />
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
