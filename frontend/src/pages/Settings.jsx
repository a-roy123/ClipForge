import React from 'react';
import { useAuth } from '../hooks/useAuth.jsx';
import { User, ShieldCheck } from 'lucide-react';

function MetaRow({ label, value, mono = false }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-[var(--border)] last:border-0 gap-4">
      <span className="text-[var(--text-2)] text-[13px] shrink-0">{label}</span>
      <span
        className={`text-[var(--text-1)] text-[13px] max-w-[60%] truncate text-right min-w-0
                    ${mono ? 'font-mono tabular-nums' : ''}`}
      >
        {value}
      </span>
    </div>
  );
}

export default function Settings() {
  const { user } = useAuth();

  return (
    <div
      className="max-w-xl mx-auto px-4 sm:px-6 py-10"
      style={{ animation: 'fadeUp 0.4s ease-out forwards' }}
    >
      {/* Page heading */}
      <div className="mb-7">
        <h2 className="text-xl font-bold text-[var(--text-1)] tracking-tight">Settings</h2>
        <p className="text-[var(--text-2)] text-[13px] mt-0.5">
          Profile and security configuration
        </p>
      </div>

      {/* Profile card */}
      <div className="glass-card p-5 mb-3">
        <div className="flex items-center gap-2.5 mb-4">
          <User aria-hidden="true" size={13} className="text-[var(--text-3)]" />
          <h3 className="text-[var(--text-1)] font-semibold text-[13px]">Profile</h3>
        </div>
        <MetaRow label="Account ID" value={user?.id || '—'} mono />
        <MetaRow label="Email"      value={user?.email || '—'} />
        <MetaRow label="Username"   value={user?.username || '—'} />
      </div>

      {/* Security card */}
      <div className="glass-card p-5">
        <div className="flex items-center gap-2.5 mb-3">
          <ShieldCheck aria-hidden="true" size={13} className="text-[var(--text-3)]" />
          <h3 className="text-[var(--text-1)] font-semibold text-[13px]">Security</h3>
        </div>
        <p className="text-[var(--text-2)] text-[13px] mb-4 leading-relaxed">
          Session tokens are rotated per request and verified server-side.
        </p>
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/6 border border-emerald-500/12">
          <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
          <span className="text-emerald-400 text-[11px] font-semibold font-mono">Session Active</span>
        </div>
      </div>
    </div>
  );
}
