import React, { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useJobSocket } from '../hooks/useJobSocket';
import api from '../services/api';
import ProgressBar from '../components/ProgressBar';
import VideoPlayer from '../components/VideoPlayer';
import { ArrowLeft, Wifi, WifiOff, AlertTriangle, CheckCircle2 } from 'lucide-react';

export default function JobDetail() {
  const { jobId } = useParams();
  const navigate = useNavigate();

  const { jobData, isConnected } = useJobSocket(jobId);
  const [fallback, setFallback] = useState(null);
  const [highlightsLoading, setHighlightsLoading] = useState(true);

  const fetchJobREST = async () => {
    try {
      const response = await api.get(`/jobs/${jobId}`);
      setFallback(response.data);
    } catch (err) {
      console.error('REST database synchronization failed:', err);
    } finally {
      setHighlightsLoading(false);
    }
  };

  // Always fetch REST on mount — WebSocket carries live status/progress but not highlights
  useEffect(() => {
    fetchJobREST();
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Merge: WebSocket overlays live fields; REST is authoritative for highlights
  const job = useMemo(() => {
    if (!jobData && !fallback) return null;
    const base = fallback ?? {};
    const ws = jobData ?? {};
    return {
      ...base,
      ...ws,
      highlights: ws.highlights?.length ? ws.highlights : base.highlights,
    };
  }, [jobData, fallback]);

  if (!job) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]" aria-label="Loading job details">
        <div className="flex flex-col items-center gap-3">
          <div aria-hidden="true" className="spinner w-8 h-8" />
          <p className="text-slate-600 text-xs font-mono tracking-widest uppercase">
            Connecting cluster node…
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="max-w-5xl mx-auto px-4 sm:px-6 py-8"
      style={{ animation: 'fadeUp 0.4s ease-out forwards' }}
    >
      {/* Back */}
      <button
        type="button"
        onClick={() => navigate('/dashboard')}
        className="btn-ghost mb-6 -ml-2 !text-slate-600 hover:!text-slate-300"
        aria-label="Back to workspace"
      >
        <ArrowLeft aria-hidden="true" size={14} />
        Workspace
      </button>

      {/* Job header card */}
      <div className="glass-card p-5 mb-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h2 className="text-slate-100 font-bold text-base leading-snug mb-1 truncate">
              {job.original_filename || 'Processing Multi-Modal Ingestion…'}
            </h2>
            <p className="text-slate-700 text-xs font-mono truncate">
              {jobId}
            </p>
          </div>
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono shrink-0
              ${isConnected
                ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
                : 'bg-white/[0.04] border border-white/[0.07] text-slate-600'
              }`}
            aria-label={isConnected ? 'Connected via WebSocket' : 'Polling via REST'}
          >
            {isConnected
              ? <Wifi aria-hidden="true" size={11} />
              : <WifiOff aria-hidden="true" size={11} />
            }
            {isConnected ? 'WebSocket Link' : 'REST Polling'}
          </span>
        </div>
      </div>

      {/* Processing */}
      {job.status !== 'COMPLETE' && job.status !== 'FAILED' && (
        <div className="glass-card p-5 mb-5">
          <p className="text-slate-600 text-xs font-semibold uppercase tracking-widest mb-4">
            Processing
          </p>
          <ProgressBar
            progressPct={job.progress_pct || 0}
            stage={job.stage || job.progress_stage || 'Analyzing media chunks…'}
          />
        </div>
      )}

      {/* Failed */}
      {job.status === 'FAILED' && (
        <div
          className="glass-card p-5 mb-5"
          style={{ borderColor: 'rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.04)' }}
          role="alert"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle aria-hidden="true" size={17} className="text-red-400 shrink-0 mt-0.5" />
            <div>
              <h3 className="text-red-400 font-semibold text-sm mb-1">Pipeline Exception Fault</h3>
              <p className="text-slate-400 text-sm leading-relaxed">
                {job.error_message || 'An internal container execution fault occurred.'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Complete */}
      {job.status === 'COMPLETE' && (
        <div style={{ animation: 'fadeUp 0.45s ease-out forwards' }}>
          {highlightsLoading ? (
            <div className="flex items-center justify-center py-16" aria-label="Loading highlights">
              <div aria-hidden="true" className="spinner w-6 h-6" />
            </div>
          ) : job.highlights && job.highlights.length > 0 ? (
            <VideoPlayer highlights={job.highlights} />
          ) : (
            <div className="glass-card p-14 text-center">
              <div
                aria-hidden="true"
                className="w-12 h-12 rounded-2xl bg-white/[0.04] border border-white/[0.06] flex items-center justify-center mx-auto mb-4"
              >
                <CheckCircle2 size={20} className="text-slate-700" />
              </div>
              <p className="text-slate-300 font-semibold mb-1">Processing complete</p>
              <p className="text-slate-600 text-sm">
                Zero highlights breached confidence thresholds.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
