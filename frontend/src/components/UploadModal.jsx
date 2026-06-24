import React, { useState, useCallback, useRef } from 'react';
import { useDropzone } from 'react-dropzone';
import axios from 'axios';
import api from '../services/api';
import { Upload, X, FileVideo } from 'lucide-react';

export default function UploadModal({ isOpen, onClose, onUploadComplete }) {
  const [file, setFile] = useState(null);
  const [stage, setStage] = useState('idle'); // idle | presigning | uploading | confirming | error
  const [percent, setPercent] = useState(0);
  const [error, setError] = useState('');

  const abortRef = useRef(null);
  const jobIdRef = useRef(null); // tracks the created job so cancel can clean it up

  const resetState = () => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setFile(null);
    setStage('idle');
    setPercent(0);
    setError('');
  };

  const handleClose = () => {
    // If a job was created but never completed, delete it so it doesn't linger on the dashboard
    if (jobIdRef.current) {
      api.delete(`/jobs/${jobIdRef.current}`).catch(() => {});
      jobIdRef.current = null;
    }
    resetState();
    onClose();
  };

  const onDrop = useCallback((files) => {
    if (files?.length > 0) setFile(files[0]);
  }, []);

  const { getRootProps, getInputProps } = useDropzone({
    onDrop,
    accept: {
      'video/mp4':        ['.mp4'],
      'video/quicktime':  ['.mov'],
      'video/x-msvideo':  ['.avi'],
      'video/x-matroska': ['.mkv'],
    },
    multiple: false,
    disabled: stage !== 'idle',
  });

  const runIngestionPipeline = async () => {
    if (!file) return;
    setError('');
    abortRef.current = new AbortController();

    try {
      setStage('presigning');
      const presign = await api.post('/upload/presign', {
        filename: file.name,
        file_size_bytes: file.size,
        content_type: file.type || 'video/mp4',
      });
      const { job_id, presigned_url } = presign.data;
      jobIdRef.current = job_id; // job now exists in DB — track it for cleanup

      setStage('uploading');
      await axios.put(presigned_url, file, {
        headers: { 'Content-Type': file.type || 'video/mp4' },
        signal: abortRef.current.signal,
        onUploadProgress: (e) => {
          setPercent(Math.round((e.loaded * 100) / e.total));
        },
      });

      setStage('confirming');
      await api.post('/upload/confirm', { job_id });

      // Success — clear ref so handleClose doesn't delete a completed job
      jobIdRef.current = null;
      setStage('idle');
      setFile(null);
      onUploadComplete(job_id);
    } catch (err) {
      if (axios.isCancel(err) || err.name === 'AbortError' || err.name === 'CanceledError') {
        return;
      }
      setStage('error');
      setError(err.response?.data?.detail || 'Upload failed. Please try again.');
    }
  };

  if (!isOpen) return null;

  const isProcessing = stage !== 'idle' && stage !== 'error';

  const stageLabel = {
    presigning: 'Generating upload token…',
    uploading:  `Uploading — ${percent}%`,
    confirming: 'Confirming with server…',
  }[stage];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{
        background: 'rgba(0,0,0,0.72)',
        backdropFilter: 'blur(8px)',
        animation: 'fadeIn 0.18s ease-out',
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-modal-title"
      onClick={(e) => { if (e.target === e.currentTarget) handleClose(); }}
    >
      <div
        className="glass-card modal-content w-full max-w-md p-6"
        style={{ animation: 'scaleIn 0.22s ease-out' }}
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-5">
          <div>
            <h3
              id="upload-modal-title"
              className="text-[var(--text-1)] font-bold text-[15px]"
            >
              Upload Gameplay
            </h3>
            <p className="text-[var(--text-3)] text-[11px] font-mono mt-0.5">
              MP4 · MOV · AVI · MKV — up to 5 GB
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="btn-ghost !h-[28px] !w-[28px] !p-0"
            aria-label="Close upload dialog"
          >
            <X aria-hidden="true" size={14} />
          </button>
        </div>

        {/* Dropzone */}
        {stage === 'idle' && (
          <div
            {...getRootProps()}
            className="border border-dashed border-[var(--border-1)] rounded-lg p-8 text-center cursor-pointer mb-4
                       hover:border-[var(--border-2)] hover:bg-[var(--surface-1)]
                       transition-[border-color,background-color] duration-130"
          >
            <input {...getInputProps()} aria-label="Drop video file here or click to browse" />
            {file ? (
              <div className="flex flex-col items-center gap-2">
                <div
                  aria-hidden="true"
                  className="w-9 h-9 rounded-lg bg-[var(--surface-1)] border border-[var(--border-1)]
                             flex items-center justify-center"
                >
                  <FileVideo size={15} className="text-[var(--text-2)]" />
                </div>
                <p className="text-[var(--text-1)] text-[13px] font-semibold truncate max-w-full">
                  {file.name}
                </p>
                <p className="text-[var(--text-3)] text-[11px] font-mono tabular-nums">
                  {(file.size / 1024 / 1024).toFixed(1)} MB
                </p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <div
                  aria-hidden="true"
                  className="w-9 h-9 rounded-lg bg-[var(--surface-1)] border border-[var(--border-1)]
                             flex items-center justify-center mb-1"
                >
                  <Upload size={14} className="text-[var(--text-3)]" />
                </div>
                <p className="text-[var(--text-2)] text-[13px] font-medium">Drop video file here</p>
                <p className="text-[var(--text-3)] text-[11px]">or click to browse</p>
              </div>
            )}
          </div>
        )}

        {/* Progress */}
        {isProcessing && (
          <div
            className="mb-4 p-4 rounded-lg bg-[var(--surface-1)] border border-[var(--border)]"
            style={{ animation: 'fadeIn 0.18s ease-out' }}
            aria-live="polite"
            aria-atomic="true"
          >
            <div className="flex items-center gap-2.5 mb-3">
              <div aria-hidden="true" className="spinner w-3 h-3 shrink-0" />
              <span className="text-[var(--text-2)] text-[13px]">{stageLabel}</span>
            </div>
            {stage === 'uploading' && (
              <div
                className="progress-track"
                role="progressbar"
                aria-valuenow={percent}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div className="progress-fill" style={{ width: `${percent}%` }} />
              </div>
            )}
          </div>
        )}

        {/* Error */}
        <div aria-live="polite" aria-atomic="true">
          {stage === 'error' && (
            <div
              className="mb-4 px-4 py-3 rounded-lg bg-red-500/6 border border-red-500/12 text-red-400 text-[13px] leading-relaxed"
              style={{ animation: 'slideDown 0.2s ease-out' }}
              role="alert"
            >
              {error}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={handleClose}
            className="btn-ghost"
          >
            Cancel
          </button>
          {stage === 'idle' && (
            <button
              type="button"
              onClick={runIngestionPipeline}
              disabled={!file}
              className="btn-forge"
            >
              Upload
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
