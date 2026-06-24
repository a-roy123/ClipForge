import React, { useRef, useState } from 'react';
import api from '../services/api';
import { Play, Clock, Award } from 'lucide-react';

export default function VideoPlayer({ highlights = [] }) {
  const videoRef = useRef(null);
  const [activeUrl, setActiveUrl] = useState('');
  const [activeId, setActiveId] = useState(null);
  const [loadingClip, setLoadingClip] = useState(false);

  const handleLoadHighlightAsset = async (highlight) => {
    setActiveId(highlight.id);
    setLoadingClip(true);

    try {
      const response = await api.get(`/highlights/${highlight.id}/download`);
      const signedUrl = response.data.download_url;

      setActiveUrl(signedUrl);

      if (videoRef.current) {
        videoRef.current.src = signedUrl;
        // Pre-trimmed independent files load and play immediately from second 0
        videoRef.current.play().catch((err) => console.log('Autoplay deferred:', err));
      }
    } catch (err) {
      console.error('Failed retrieving presigned playback token signature:', err);
    } finally {
      setLoadingClip(false);
    }
  };

  return (
    <div className="flex flex-col lg:flex-row gap-4">

      {/* ── Video viewport ───────────────────────────── */}
      <div className="flex-1 min-w-0">
        <div className="glass-card overflow-hidden">
          <div className="relative bg-black aspect-video">

            {/* Loading overlay */}
            {loadingClip && (
              <div
                className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/60"
                aria-live="polite"
              >
                <div aria-hidden="true" className="spinner w-6 h-6 mb-3" />
                <span className="text-[var(--text-3)] text-[11px] font-mono">
                  Loading…
                </span>
              </div>
            )}

            {/* Empty placeholder */}
            {!activeUrl && !loadingClip && (
              <div
                className="absolute inset-0 flex items-center justify-center"
                aria-label="Select a highlight from the list to begin playback"
              >
                <div className="flex flex-col items-center gap-2.5 text-center px-6">
                  <div
                    aria-hidden="true"
                    className="w-11 h-11 rounded-xl bg-[var(--surface-1)] border border-[var(--border-1)]
                               flex items-center justify-center"
                  >
                    <Play size={16} className="text-[var(--text-3)] ml-0.5" />
                  </div>
                  <p className="text-[var(--text-3)] text-[13px]">Select a clip to play</p>
                </div>
              </div>
            )}

            <video
              ref={videoRef}
              controls
              src={activeUrl}
              className="main-video-canvas w-full h-full object-contain"
              aria-label="Highlight video player"
            />
          </div>
        </div>
      </div>

      {/* ── Clips sidebar ─────────────────────────────── */}
      <div className="lg:w-64 shrink-0">
        <p
          className="text-[var(--text-3)] text-[10px] font-mono uppercase tracking-[0.12em] mb-2.5 px-0.5"
          aria-live="polite"
        >
          {highlights.length} clip{highlights.length !== 1 ? 's' : ''}
        </p>

        <div className="space-y-1.5" role="list">
          {highlights.map((clip, idx) => {
            const isActive = activeId === clip.id;
            return (
              <button
                key={clip.id}
                type="button"
                onClick={() => handleLoadHighlightAsset(clip)}
                className={`glass-card-interactive p-3.5 w-full text-left ${
                  isActive ? '!bg-[var(--surface-1)] !border-[var(--border-2)]' : ''
                }`}
                role="listitem"
                aria-label={`Play clip ${idx + 1}, score ${clip.score?.toFixed(2)}, ${Math.floor(clip.start_second)}s to ${Math.floor(clip.end_second)}s`}
                aria-pressed={isActive}
              >
                {/* Header row */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      aria-hidden="true"
                      className={`w-5 h-5 rounded-md flex items-center justify-center
                                  text-[10px] font-bold font-mono shrink-0
                                  ${isActive
                                    ? 'bg-[var(--text-1)] text-[var(--bg)]'
                                    : 'bg-[var(--surface-1)] text-[var(--text-3)]'
                                  }`}
                    >
                      {idx + 1}
                    </span>
                    <span
                      className={`text-[12px] font-semibold truncate ${
                        isActive ? 'text-[var(--text-1)]' : 'text-[var(--text-2)]'
                      }`}
                    >
                      Clip {idx + 1}
                    </span>
                  </div>

                  <span
                    className={`inline-flex items-center gap-1 font-mono text-[10px] shrink-0 ml-2 px-1.5 py-0.5 rounded-md
                      ${clip.low_confidence
                        ? 'bg-amber-400/8 border border-amber-400/15 text-amber-400'
                        : 'bg-emerald-400/8 border border-emerald-400/15 text-emerald-400'
                      }`}
                    title={clip.low_confidence ? 'Low confidence' : 'High confidence'}
                  >
                    <Award aria-hidden="true" size={8} />
                    {clip.score?.toFixed(2)}
                  </span>
                </div>

                {/* Meta */}
                <div className="flex items-center gap-2.5 font-mono text-[10px] text-[var(--text-3)] tabular-nums">
                  <span className="flex items-center gap-1">
                    <Clock aria-hidden="true" size={9} />
                    {Math.floor(clip.start_second)}s–{Math.floor(clip.end_second)}s
                  </span>
                  <span className="text-[var(--border-2)]">·</span>
                  <span>{clip.duration_seconds}s</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
