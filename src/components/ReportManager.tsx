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
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import DownloadIcon from '@mui/icons-material/Download';
import RefreshIcon from '@mui/icons-material/Refresh';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import { api } from '../services/api.ts';

export const ReportManager: React.FC = () => {
  const [reports, setReports] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const fetchReports = async () => {
    setIsLoading(true);
    try {
      const res = await api.getReports();
      setReports(res.reports || []);
    } catch (err) {
      console.error('Error fetching reports:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  return (
    <Card elevation={2} sx={{ borderRadius: 3, border: '1px solid #e2e8f0', p: 3, mt: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <PictureAsPdfIcon sx={{ color: '#E60023', fontSize: 28 }} />
          <Box>
            <Typography variant="h6" fontWeight={800} color="#0f172a">
              Daily PDF Activity Reports
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Saved in: C:\Downloads\AutomatePinterest
            </Typography>
          </Box>
        </Box>

        <Button
          startIcon={<RefreshIcon />}
          size="small"
          onClick={fetchReports}
          variant="outlined"
          sx={{ textTransform: 'none', borderRadius: 2 }}
        >
          Refresh Reports
        </Button>
      </Box>

      {reports.length === 0 ? (
        <Paper
          elevation={0}
          sx={{
            p: 4,
            textAlign: 'center',
            bgcolor: '#f8fafc',
            border: '1px dashed #cbd5e1',
            borderRadius: 2,
          }}
        >
          <Typography variant="body2" color="text.secondary">
            No PDF reports generated yet today. Reports are automatically compiled upon completing each automation batch.
          </Typography>
        </Paper>
      ) : (
        <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #e2e8f0', borderRadius: 2 }}>
          <Table size="small">
            <TableHead sx={{ bgcolor: '#f8fafc' }}>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>Report File</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Generated At</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Size</TableCell>
                <TableCell sx={{ fontWeight: 700 }} align="right">
                  Action
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {reports.map((rep) => (
                <TableRow key={rep.fileName} hover>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <PictureAsPdfIcon sx={{ color: '#E60023', fontSize: 18 }} />
                      <Typography variant="body2" fontWeight={600} color="#0f172a">
                        {rep.fileName}
                      </Typography>
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" color="text.secondary">
                      {rep.createdAt}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={`${Math.round((rep.sizeBytes || 0) / 1024)} KB`}
                      size="small"
                      sx={{ fontSize: 10, height: 20 }}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      startIcon={<DownloadIcon />}
                      component="a"
                      href={api.getDownloadUrl(rep.fileName)}
                      target="_blank"
                      download
                      sx={{ textTransform: 'none', fontWeight: 700 }}
                    >
                      Download
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Card>
  );
};

export default ReportManager;
