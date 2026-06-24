import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import UploadModal from '../components/UploadModal';
import { Plus, Clock, CheckCircle, Loader, XCircle, Film } from 'lucide-react';

const STATUS = {
  PENDING:    { Icon: Clock,       color: 'text-amber-400',   bg: 'bg-amber-400/8',   border: 'border-amber-400/15',   dot: 'bg-amber-400',   label: 'Pending' },
  PROCESSING: { Icon: Loader,      color: 'text-blue-400',    bg: 'bg-blue-400/8',    border: 'border-blue-400/15',    dot: 'bg-blue-400',    label: 'Processing' },
  COMPLETE:   { Icon: CheckCircle, color: 'text-emerald-400', bg: 'bg-emerald-400/8', border: 'border-emerald-400/15', dot: 'bg-emerald-400', label: 'Complete' },
  FAILED:     { Icon: XCircle,     color: 'text-red-400',     bg: 'bg-red-400/8',     border: 'border-red-400/15',     dot: 'bg-red-400',     label: 'Failed' },
};

export default function Dashboard() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const navigate = useNavigate();

  const fetchJobsList = async () => {
    try {
      const response = await api.get('/jobs');
      setJobs(Array.isArray(response.data) ? response.data : []);
    } catch (err) {
      console.error('Failed syncing cluster jobs layout:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobsList();
  }, []);

  const handleUploadRedirect = (jobId) => {
    setModalOpen(false);
    navigate(`/jobs/${jobId}`);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-10">

      {/* Header */}
      <div
        className="flex items-center justify-between mb-8"
        style={{ animation: 'fadeUp 0.4s ease-out forwards' }}
      >
        <div>
          <h2 className="text-xl font-bold text-[var(--text-1)] tracking-tight">Workspace</h2>
          <p className="text-[var(--text-3)] text-[12px] mt-0.5 font-mono tabular-nums">
            {!loading ? (
              jobs.length > 0
                ? `${jobs.length} project${jobs.length !== 1 ? 's' : ''}`
                : 'No projects yet'
            ) : null}
          </p>
        </div>
        <button type="button" onClick={() => setModalOpen(true)} className="btn-forge gap-1.5">
          <Plus aria-hidden="true" size={13} />
          New Job
        </button>
      </div>

      {/* Loading skeletons */}
      {loading ? (
        <div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
          aria-label="Loading projects…"
        >
          {[...Array(3)].map((_, i) => (
            <div key={i} className="glass-card h-28 skeleton" aria-hidden="true" />
          ))}
        </div>
      ) : jobs.length === 0 ? (
        /* Empty state */
        <div
          className="flex flex-col items-center justify-center py-32 text-center"
          style={{ animation: 'fadeUp 0.5s ease-out forwards' }}
        >
          <div
            aria-hidden="true"
            className="w-12 h-12 rounded-xl bg-[var(--surface-1)] border border-[var(--border-1)]
                       flex items-center justify-center mb-5"
          >
            <Film size={20} className="text-[var(--text-3)]" />
          </div>
          <p className="text-[var(--text-1)] text-sm font-semibold mb-1.5">No projects yet</p>
          <p className="text-[var(--text-2)] text-[13px] mb-7 max-w-xs leading-relaxed">
            Upload your first gameplay video and the ML pipeline will find your highlights.
          </p>
          <button type="button" onClick={() => setModalOpen(true)} className="btn-forge gap-1.5">
            <Plus aria-hidden="true" size={13} />
            Upload Video
          </button>
        </div>
      ) : (
        /* Job grid */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {jobs.map((job, i) => {
            const cfg = STATUS[job.status] || STATUS.PENDING;
            return (
              <button
                key={job.id}
                type="button"
                onClick={() => navigate(`/jobs/${job.id}`)}
                className="glass-card-interactive p-5 text-left w-full"
                style={{ animation: `fadeUp 0.4s ease-out ${i * 0.05}s forwards`, opacity: 0 }}
                aria-label={`Open job: ${job.original_filename || 'Untitled'}`}
              >
                {/* Top row */}
                <div className="flex items-start justify-between mb-4">
                  <div
                    aria-hidden="true"
                    className="w-8 h-8 rounded-lg bg-[var(--surface-1)] border border-[var(--border-1)]
                               flex items-center justify-center shrink-0"
                  >
                    <Film size={13} className="text-[var(--text-3)]" />
                  </div>

                  {/* Status badge */}
                  <span className={`status-badge ${cfg.bg} ${cfg.color} border ${cfg.border}`}>
                    <span
                      className={`status-dot ${cfg.dot} ${job.status === 'PROCESSING' ? 'status-dot-processing' : ''}`}
                      aria-hidden="true"
                    />
                    {cfg.label}
                  </span>
                </div>

                {/* Filename */}
                <div className="min-w-0">
                  <h4 className="text-[var(--text-1)] font-medium text-[13px] mb-1 truncate">
                    {job.original_filename || new Intl.DateTimeFormat('en-US', {
                      month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
                    }).format(new Date(job.created_at))}
                  </h4>
                  <p className="text-[var(--text-3)] text-[11px] font-mono tabular-nums">
                    {new Intl.DateTimeFormat('en-US', {
                      month: 'short', day: 'numeric', year: 'numeric',
                    }).format(new Date(job.created_at))}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      )}

      <UploadModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onUploadComplete={handleUploadRedirect}
      />
    </div>
  );
}
