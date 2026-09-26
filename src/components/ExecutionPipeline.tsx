import React from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  Paper,
  Grid,
  LinearProgress,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import ErrorIcon from '@mui/icons-material/Error';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { RunState, StepLogEntry } from '../types/index.ts';

interface ExecutionPipelineProps {
  runState: RunState;
  stepLogs: StepLogEntry[];
}

const PIPELINE_STEPS = [
  { num: 1, name: 'Navigate Deals URL', desc: 'Confirm https://worldnewzs.in/amazon-products' },
  { num: 2, name: 'Select Deal Card', desc: 'Extract 6 deal cards on active page' },
  { num: 3, name: 'Open Pin Creation', desc: 'Launch Pinterest pin creation tab' },
  { num: 4, name: 'Click "Create board"', desc: 'Trigger board creation modal' },
  { num: 5, name: 'Truncate Title (50 chars)', desc: 'Strict hard-cut truncation at 50 chars' },
  { num: 6, name: 'Paste to Board Name', desc: 'Fill Board input with truncated title' },
  { num: 7, name: 'Add Collaborators', desc: 'Dynamically discover & assign all account collaborators' },
  { num: 8, name: 'Create Board & "See it"', desc: 'Submit board & navigate via "See it now"' },
  { num: 9, name: 'Click Red "Save" Pin', desc: 'Trigger red pin save button' },
  { num: 10, name: 'Verify Save State', desc: 'Confirm Red button turns Dark Grey (Saved)' },
  { num: 11, name: 'Close Tab & Next Card', desc: 'Close tab and loop to next deal card' },
];

export const ExecutionPipeline: React.FC<ExecutionPipelineProps> = ({ runState, stepLogs }) => {
  // Find current step number
  const latestLog = stepLogs[stepLogs.length - 1];
  const activeStepNum = runState.isRunning && latestLog ? latestLog.stepNumber : 0;

  return (
    <Card elevation={2} sx={{ borderRadius: 3, border: '1px solid #e2e8f0', p: 3, mt: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
        <Box>
          <Typography variant="h6" fontWeight={800} color="#0f172a">
            11-Step Automation Pipeline
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Python Browser-Use CDP Agent strictly validates each step before proceeding.
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          {runState.isRunning && (
            <Chip
              label={`Page ${runState.currentPage || 1} • Product ${(runState.currentCardIndex || 0) + 1} of 6`}
              size="small"
              color="error"
              sx={{ fontWeight: 800 }}
            />
          )}
          <Chip
            icon={runState.isRunning ? <PlayArrowIcon /> : <HourglassEmptyIcon />}
            label={runState.isRunning ? `Executing Step ${activeStepNum || 1} of 11` : 'Standby / Ready'}
            color={runState.isRunning ? 'primary' : 'default'}
            sx={{ fontWeight: 700 }}
          />
        </Box>
      </Box>

      {/* Real-time Automation Process Bar */}
      {runState.isRunning && (() => {
        const startP = runState.startPage || runState.currentPage || 1;
        const endP = runState.endPage || runState.currentPage || 1;
        const totalP = Math.max(1, endP - startP + 1);
        const totalCardsExpected = totalP * 6;
        const currentCardOverall = (runState.currentPage - startP) * 6 + (runState.currentCardIndex || 0);
        const overallProgress = Math.min(
          99,
          Math.max(2, Math.round(((currentCardOverall * 11 + (activeStepNum || 1)) / (totalCardsExpected * 11)) * 100))
        );

        return (
          <Paper
            elevation={0}
            sx={{
              p: 2,
              mb: 2.5,
              borderRadius: 2.5,
              bgcolor: '#f8fafc',
              border: '1px solid #e2e8f0',
            }}
          >
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1, flexWrap: 'wrap', gap: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                <Typography variant="subtitle2" fontWeight={800} color="#0f172a">
                  ⚡ Automation Progress: Page {runState.currentPage} of {endP}
                </Typography>
                <Chip
                  label={`Product ${(runState.currentCardIndex || 0) + 1} of 6 (Card ${(runState.currentCardIndex || 0) + 1}/6)`}
                  size="small"
                  sx={{ bgcolor: '#fee2e2', color: '#dc2626', fontWeight: 800, fontSize: '0.72rem' }}
                />
                <Chip
                  label={`Step ${activeStepNum || 1}/11: ${PIPELINE_STEPS[(activeStepNum || 1) - 1]?.name || 'Initializing'}`}
                  size="small"
                  variant="outlined"
                  sx={{ fontWeight: 700, fontSize: '0.72rem' }}
                />
              </Box>
              <Typography variant="body2" fontWeight={800} color="#E60023">
                {overallProgress}%
              </Typography>
            </Box>

            <LinearProgress
              variant="determinate"
              value={overallProgress}
              sx={{
                height: 10,
                borderRadius: 5,
                bgcolor: '#e2e8f0',
                '& .MuiLinearProgress-bar': {
                  bgcolor: '#E60023',
                  borderRadius: 5,
                },
              }}
            />

            {runState.currentProductTitle && (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1, fontStyle: 'italic' }}>
                Currently automating: "{runState.currentProductTitle}" (Card {(runState.currentCardIndex || 0) + 1} of 6 on Page {runState.currentPage})
              </Typography>
            )}
          </Paper>
        );
      })()}

      {/* 11 Step Tiles Grid */}
      <Grid container spacing={1.5}>
        {PIPELINE_STEPS.map((step) => {
          const isCurrent = runState.isRunning && activeStepNum === step.num;
          const isCompleted = runState.isRunning && activeStepNum > step.num;
          const isDone = !runState.isRunning && runState.totalCardsProcessed > 0;

          return (
            <Grid item xs={12} sm={6} md={4} lg={2.4} key={step.num}>
              <Paper
                elevation={isCurrent ? 4 : 0}
                sx={{
                  p: 1.5,
                  borderRadius: 2,
                  border: isCurrent
                    ? '2px solid #E60023'
                    : isCompleted || isDone
                    ? '1px solid #bbf7d0'
                    : '1px solid #e2e8f0',
                  bgcolor: isCurrent
                    ? '#fff1f2'
                    : isCompleted || isDone
                    ? '#f0fdf4'
                    : '#ffffff',
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  transition: 'all 0.25s ease',
                }}
              >
                <Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                    <Chip
                      label={`Step ${step.num}`}
                      size="small"
                      sx={{
                        fontSize: 10,
                        fontWeight: 800,
                        height: 20,
                        bgcolor: isCurrent ? '#E60023' : '#f1f5f9',
                        color: isCurrent ? '#fff' : '#475569',
                      }}
                    />

                    {isCurrent ? (
                      <Chip label="RUNNING" size="small" color="primary" sx={{ fontSize: 9, height: 18, fontWeight: 700 }} />
                    ) : isCompleted || isDone ? (
                      <CheckCircleIcon sx={{ color: '#16a34a', fontSize: 16 }} />
                    ) : null}
                  </Box>

                  <Typography variant="body2" fontWeight={700} color="#0f172a" sx={{ fontSize: '0.82rem', mt: 0.5 }}>
                    {step.name}
                  </Typography>

                  <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.72rem', display: 'block', mt: 0.25 }}>
                    {step.desc}
                  </Typography>
                </Box>
              </Paper>
            </Grid>
          );
        })}
      </Grid>
    </Card>
  );
};

export default ExecutionPipeline;
