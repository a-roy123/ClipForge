import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth.jsx';
import { Cpu, Zap, Shield, ArrowRight } from 'lucide-react';

const features = [
  {
    icon: Cpu,
    label: '01',
    title: 'Audio CNN Modeling',
    desc: 'Acoustic processing targets match footprints like ult lines, sound events, and eliminations.',
  },
  {
    icon: Zap,
    label: '02',
    title: 'Optical Variance Slicing',
    desc: 'Motion vector metrics track pixel delta thresholds to crop high-intensity sequences.',
  },
  {
    icon: Shield,
    label: '03',
    title: 'Secure Storage Bridge',
    desc: 'Direct upload handshakes bypass intermediate routing, streaming video data to isolated clouds.',
  },
];

export default function Landing() {
  const navigate = useNavigate();
  const { user } = useAuth();

  return (
    <div
      className="relative min-h-dvh flex flex-col items-center overflow-hidden"
      style={{
        backgroundColor: 'var(--bg)',
        backgroundImage: [
          'linear-gradient(rgba(255,255,255,0.016) 1px, transparent 1px)',
          'linear-gradient(90deg, rgba(255,255,255,0.016) 1px, transparent 1px)',
        ].join(', '),
        backgroundSize: '64px 64px',
      }}
    >
      {/* ── Hero ─────────────────────────────────────────── */}
      <header
        className="relative z-10 flex flex-col items-center text-center pt-32 pb-24 px-6 max-w-3xl mx-auto w-full"
        style={{ animation: 'fadeUp 0.5s ease-out forwards' }}
      >
        {/* Eyebrow */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[var(--border-1)] bg-[var(--surface)] mb-9">
          <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-[var(--text-3)]" />
          <span className="text-[11px] text-[var(--text-2)] font-mono tracking-wider">
            Multi-modal ML — Gaming Highlights
          </span>
        </div>

        {/* Headline — plain white, no gradient */}
        <h1 className="text-5xl sm:text-[68px] lg:text-7xl font-bold tracking-[-0.03em] leading-[1.02] text-[var(--text-1)] mb-5">
          ClipForge
        </h1>

        <p className="text-base sm:text-lg text-[var(--text-2)] max-w-md leading-relaxed mb-10 font-normal">
          Upload your gameplay. The multi-modal ML pipeline finds the moments
          that matter — automatically extracted and ready to share.
        </p>

        <button
          type="button"
          onClick={() => navigate(user ? '/dashboard' : '/login')}
          className="btn-forge gap-2 !h-[42px] !px-7 !text-sm !rounded-lg"
          aria-label={user ? 'Go to your dashboard' : 'Get started with ClipForge'}
        >
          {user ? 'Go to Dashboard' : 'Enter Console'}
          <ArrowRight aria-hidden="true" size={14} />
        </button>
      </header>

      {/* ── Divider ──────────────────────────────────────── */}
      <div
        aria-hidden="true"
        className="relative z-10 w-full max-w-4xl mx-auto px-6"
        style={{ animation: 'fadeIn 0.5s ease-out 0.2s forwards', opacity: 0 }}
      >
        <div className="h-px bg-[var(--border)]" />
      </div>

      {/* ── Signal table ─────────────────────────────────── */}
      <section
        className="relative z-10 w-full max-w-4xl mx-auto px-6 pt-0 pb-28"
        aria-label="How it works"
        style={{ animation: 'fadeUp 0.5s ease-out 0.25s forwards', opacity: 0 }}
      >
        <p className="text-[11px] font-mono text-[var(--text-3)] tracking-[0.15em] uppercase px-1 py-5">
          Three independent signals
        </p>

        {/* Bordered grid — shares borders instead of floating cards */}
        <div
          className="grid grid-cols-1 md:grid-cols-3 border border-[var(--border)] rounded-xl overflow-hidden
                     divide-y md:divide-y-0 md:divide-x divide-[var(--border)]"
        >
          {features.map(({ icon: Icon, label, title, desc }) => (
            <div key={title} className="p-7 bg-[var(--surface)]">
              <div className="flex items-center gap-3 mb-5">
                <span className="text-[10px] font-mono text-[var(--text-3)]">{label}</span>
                <div className="w-px h-3 bg-[var(--border-1)]" aria-hidden="true" />
                <Icon aria-hidden="true" size={13} className="text-[var(--text-3)]" />
              </div>
              <h3 className="text-[var(--text-1)] text-sm font-semibold mb-2 tracking-tight">
                {title}
              </h3>
              <p className="text-[var(--text-2)] text-[13px] leading-relaxed">
                {desc}
              </p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
