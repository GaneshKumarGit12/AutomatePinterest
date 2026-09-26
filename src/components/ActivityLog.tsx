import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Tabs,
  Tab,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Button,
  Tooltip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import DownloadIcon from '@mui/icons-material/Download';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import RefreshIcon from '@mui/icons-material/Refresh';
import ContentCutIcon from '@mui/icons-material/ContentCut';
import GroupIcon from '@mui/icons-material/Group';
import { ProductDeal, StepLogEntry, GeneratedReport } from '../types/index.ts';
import { api } from '../services/api.ts';
import { sseClient } from '../services/sse.ts';

interface ActivityLogProps {
  processedDeals: ProductDeal[];
  stepLogs: StepLogEntry[];
  liveLogs: Array<{ message: string; level: string; timestamp: string }>;
}

export const ActivityLog: React.FC<ActivityLogProps> = ({ processedDeals, stepLogs, liveLogs }) => {
  const [currentTab, setCurrentTab] = useState<number>(0);
  const [reports, setReports] = useState<GeneratedReport[]>([]);
  const [reportsDir, setReportsDir] = useState<string>('');
  const [isLoadingReports, setIsLoadingReports] = useState<boolean>(false);
  const [socialLogs, setSocialLogs] = useState<Array<{ message: string; level: string; timestamp: string }>>([]);

  useEffect(() => {
    const unsub = sseClient.subscribe('social_log', (data: any) => {
      setSocialLogs((prev) => [...prev.slice(-300), data]);
    });
    return () => {
      unsub();
    };
  }, []);

  const fetchReports = async () => {
    setIsLoadingReports(true);
    try {
      const data = await api.getReports();
      setReports(data.reports || []);
      if (data.directory) {
        setReportsDir(data.directory);
      }
    } catch (e) {
      console.error('Error fetching reports:', e);
    } finally {
      setIsLoadingReports(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, [processedDeals.length]);

  const getStatusChip = (status: StepLogEntry['status']) => {
    switch (status) {
      case 'success':
        return <Chip label="SUCCESS" color="success" size="small" sx={{ fontWeight: 700, fontSize: '0.7rem' }} />;
      case 'failed':
        return <Chip label="FAILED" color="error" size="small" sx={{ fontWeight: 700, fontSize: '0.7rem' }} />;
      case 'in_progress':
        return <Chip label="RUNNING" color="primary" size="small" sx={{ fontWeight: 700, fontSize: '0.7rem' }} />;
      default:
        return <Chip label="PENDING" size="small" sx={{ fontWeight: 700, fontSize: '0.7rem' }} />;
    }
  };

  return (
    <Card elevation={2} sx={{ borderRadius: 3, border: '1px solid #e2e8f0', mt: 3 }}>
      <CardContent sx={{ p: 3 }}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider', display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Tabs value={currentTab} onChange={(_, v) => setCurrentTab(v)} textColor="primary" indicatorColor="primary" variant="scrollable" scrollButtons="auto">
            <Tab label={`Deals Processed (${processedDeals.length})`} />
            <Tab label={`11-Step Timeline (${stepLogs.length})`} />
            <Tab label={`Live Terminal Stream (${liveLogs.length})`} />
            <Tab label={`Social Activity Hub (${socialLogs.length})`} />
            <Tab label={`PDF Reports (${reports.length})`} />
          </Tabs>

          {currentTab === 4 && (
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button size="small" variant="outlined" startIcon={<RefreshIcon />} onClick={fetchReports} disabled={isLoadingReports}>
                Refresh
              </Button>
            </Box>
          )}
        </Box>

        {/* Tab 0: Processed Deals View */}
        {currentTab === 0 && (
          <Box>
            {processedDeals.length === 0 ? (
              <Box sx={{ py: 6, textAlign: 'center', color: 'text.secondary' }}>
                <HourglassEmptyIcon sx={{ fontSize: 48, mb: 1, color: '#94a3b8' }} />
                <Typography variant="body1">No product deals processed yet. Click Start Automation to begin.</Typography>
              </Box>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {processedDeals.map((deal, idx) => {
                  const dealSteps = stepLogs.filter((s) => s.productId === deal.id);
                  const isSuccess = deal.status === 'success' || deal.success === true;
                  return (
                    <Accordion key={deal.id || idx} defaultExpanded={idx === 0} sx={{ border: '1px solid #e2e8f0', borderRadius: '8px !important' }}>
                      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%', pr: 2, flexWrap: 'wrap' }}>
                          <Chip label={`#${idx + 1} • Page ${deal.pageNumber}`} size="small" color="default" sx={{ fontWeight: 600 }} />
                          <Typography variant="subtitle2" fontWeight={700} sx={{ flexGrow: 1, maxWidth: { xs: '100%', md: '55%' } }} noWrap>
                            {deal.title}
                          </Typography>
                          {deal.isTruncated && (
                            <Tooltip title="Hard truncated to 50 characters for Pinterest board name">
                              <Chip icon={<ContentCutIcon />} label="50 Chars" color="warning" size="small" sx={{ fontWeight: 600 }} />
                            </Tooltip>
                          )}
                          <Chip
                            icon={<GroupIcon />}
                            label="Collaborators Assigned"
                            color="info"
                            size="small"
                            variant="outlined"
                          />
                          {isSuccess ? (
                            <Chip icon={<CheckCircleOutlineIcon />} label="Saved & Confirmed" color="success" size="small" sx={{ fontWeight: 700 }} />
                          ) : (
                            <Chip icon={<ErrorOutlineIcon />} label="Failed" color="error" size="small" sx={{ fontWeight: 700 }} />
                          )}
                        </Box>
                      </AccordionSummary>
                      <AccordionDetails sx={{ bgcolor: '#f8fafc', borderTop: '1px solid #e2e8f0' }}>
                        <Box sx={{ mb: 2 }}>
                          <Typography variant="caption" color="text.secondary" fontWeight={600}>
                            CREATED BOARD NAME:
                          </Typography>
                          <Typography variant="body2" sx={{ fontWeight: 600, color: '#1e293b' }}>
                            "{deal.truncatedTitle}" ({deal.truncatedTitle.length} characters)
                          </Typography>
                          {deal.error && (
                            <Typography variant="body2" color="error.main" sx={{ mt: 1 }}>
                              Error: {deal.error}
                            </Typography>
                          )}
                        </Box>

                        <Typography variant="caption" color="text.secondary" fontWeight={700} sx={{ mb: 1, display: 'block' }}>
                          STEP BREAKDOWN:
                        </Typography>
                        <List dense disablePadding>
                          {dealSteps.map((s) => (
                            <ListItem key={s.id} sx={{ py: 0.5, px: 1, bgcolor: '#ffffff', mb: 0.5, borderRadius: 1, border: '1px solid #edf2f7' }}>
                              <ListItemIcon sx={{ minWidth: 32 }}>
                                {s.status === 'success' ? (
                                  <CheckCircleOutlineIcon color="success" fontSize="small" />
                                ) : s.status === 'failed' ? (
                                  <ErrorOutlineIcon color="error" fontSize="small" />
                                ) : (
                                  <HourglassEmptyIcon color="disabled" fontSize="small" />
                                )}
                              </ListItemIcon>
                              <ListItemText
                                primary={
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                    <Typography variant="caption" fontWeight={700}>
                                      Step {s.stepNumber}: {s.stepName}
                                    </Typography>
                                    {getStatusChip(s.status)}
                                    {s.durationMs !== undefined && (
                                      <Typography variant="caption" color="text.secondary">
                                        ({s.durationMs}ms)
                                      </Typography>
                                    )}
                                  </Box>
                                }
                                secondary={s.message}
                              />
                            </ListItem>
                          ))}
                        </List>
                      </AccordionDetails>
                    </Accordion>
                  );
                })}
              </Box>
            )}
          </Box>
        )}

        {/* Tab 1: Detailed 11-Step Audit Table */}
        {currentTab === 1 && (
          <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 2 }}>
            <Table size="small">
              <TableHead sx={{ bgcolor: '#f1f5f9' }}>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700 }}>Time</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Product / Card</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Step</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Status</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Duration</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Details</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {stepLogs.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                      No step logs recorded yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  [...stepLogs].reverse().map((log) => {
                    const deal = processedDeals.find(d => d.id === log.productId);
                    return (
                    <TableRow key={log.id} hover>
                      <TableCell sx={{ fontSize: '0.75rem', color: '#64748b' }}>
                        {deal?.processedAt ? new Date(deal.processedAt).toLocaleTimeString() : (log.startedAt ? new Date(log.startedAt).toLocaleTimeString() : '-')}
                      </TableCell>
                      <TableCell sx={{ maxWidth: 200, fontSize: '0.8rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {log.productTitle || log.productId}
                      </TableCell>
                      <TableCell sx={{ fontWeight: 600, fontSize: '0.8rem' }}>
                        Step {log.stepNumber}: {log.stepName}
                      </TableCell>
                      <TableCell>{getStatusChip(log.status)}</TableCell>
                      <TableCell sx={{ fontSize: '0.75rem' }}>{log.durationMs ? `${log.durationMs}ms` : '-'}</TableCell>
                      <TableCell sx={{ fontSize: '0.75rem', color: '#334155' }}>{log.message || '-'}</TableCell>
                    </TableRow>
                  );
                })
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {/* Tab 2: Live Terminal Log Stream */}
        {currentTab === 2 && (
          <Paper
            variant="outlined"
            sx={{
              p: 2,
              bgcolor: '#0f172a',
              color: '#f8fafc',
              fontFamily: 'monospace',
              fontSize: '0.85rem',
              borderRadius: 2,
              maxHeight: 400,
              overflowY: 'auto',
            }}
          >
            {liveLogs.length === 0 ? (
              <Typography variant="body2" sx={{ color: '#64748b', fontStyle: 'italic' }}>
                Waiting for logs...
              </Typography>
            ) : (
              liveLogs.map((item, idx) => (
                <Box key={idx} sx={{ py: 0.25, display: 'flex', gap: 1 }}>
                  <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                    [{new Date(item.timestamp).toLocaleTimeString()}]
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{
                      color:
                        item.level === 'error'
                          ? '#f87171'
                          : item.level === 'warn'
                          ? '#fbbf24'
                          : item.level === 'success'
                          ? '#4ade80'
                          : '#e2e8f0',
                      fontWeight: item.level === 'success' || item.level === 'error' ? 700 : 400,
                    }}
                  >
                    {item.message}
                  </Typography>
                </Box>
              ))
            )}
          </Paper>
        )}

        {/* Tab 3: Social Media Activity (Twitter & Facebook) */}
        {currentTab === 3 && (
          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
              <Typography variant="body2" color="text.secondary">
                Real-time execution logs for <strong>Twitter (@ganeshkumard1)</strong> and <strong>Facebook (ganeshkumard56 -&gt; Worldnewzs -&gt; Amazon Affiliate Group)</strong>
              </Typography>
              {socialLogs.length > 0 && (
                <Button size="small" onClick={() => setSocialLogs([])} sx={{ textTransform: 'none', fontSize: '0.72rem' }}>
                  Clear Social Feed
                </Button>
              )}
            </Box>
            <Paper
              sx={{
                p: 2,
                bgcolor: '#0f172a',
                color: '#f8fafc',
                borderRadius: 2,
                fontFamily: 'monospace',
                fontSize: '0.82rem',
                maxHeight: 480,
                overflowY: 'auto',
                border: '1px solid #1e293b',
              }}
            >
              {socialLogs.length === 0 ? (
                <Typography variant="body2" sx={{ color: '#64748b', fontStyle: 'italic' }}>
                  No social media activity recorded yet. Select pins in Section 2 and click "Share to Twitter" or "Share to Facebook" to view real-time browser steps and confirmation here.
                </Typography>
              ) : (
                socialLogs.map((item, idx) => (
                  <Box key={idx} sx={{ py: 0.3, display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                    <Typography variant="caption" sx={{ color: '#94a3b8', whiteSpace: 'nowrap' }}>
                      [{item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString()}]
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{
                        fontFamily: 'monospace',
                        color:
                          item.level === 'error'
                            ? '#f87171'
                            : item.level === 'warning'
                            ? '#fbbf24'
                            : item.level === 'success'
                            ? '#4ade80'
                            : '#e2e8f0',
                        fontWeight: item.level === 'success' || item.level === 'error' ? 700 : 400,
                      }}
                    >
                      {item.message}
                    </Typography>
                  </Box>
                ))
              )}
            </Paper>
          </Box>
        )}

        {/* Tab 4: Generated PDF Reports */}
        {currentTab === 4 && (
          <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Target Directory: <code>{reportsDir || 'C:\\Downloads\\AutomatePinterest'}</code>
            </Typography>

            <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 2 }}>
              <Table size="small">
                <TableHead sx={{ bgcolor: '#f1f5f9' }}>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 700 }}>Report File</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Generated Date & Time</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>File Size</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 700 }}>
                      Action
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {reports.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                        No PDF reports generated yet. Reports are automatically created upon run completion.
                      </TableCell>
                    </TableRow>
                  ) : (
                    reports.map((rep) => (
                      <TableRow key={rep.fileName} hover>
                        <TableCell sx={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 1 }}>
                          <PictureAsPdfIcon color="error" fontSize="small" />
                          {rep.fileName}
                        </TableCell>
                        <TableCell sx={{ fontSize: '0.8rem' }}>
                          {rep.generatedAt ? new Date(rep.generatedAt).toLocaleString() : rep.createdAt ? new Date(rep.createdAt).toLocaleString() : '-'}
                        </TableCell>
                        <TableCell sx={{ fontSize: '0.8rem' }}>
                          {(rep.sizeBytes / 1024).toFixed(1)} KB
                        </TableCell>
                        <TableCell align="right">
                          <Button
                            variant="outlined"
                            size="small"
                            startIcon={<DownloadIcon />}
                            href={api.getDownloadUrl(rep.fileName)}
                            target="_blank"
                            download={rep.fileName}
                          >
                            Download PDF
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default ActivityLog;
