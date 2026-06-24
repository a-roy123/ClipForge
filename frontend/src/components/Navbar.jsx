import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth.jsx';
import { Cpu, LayoutDashboard, Settings, LogOut } from 'lucide-react';

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  if (!user) return null;

  const isActive = (path) => location.pathname === path;

  return (
    <nav
      className="sticky top-0 z-50 glass border-b border-[var(--border)]"
      aria-label="Main navigation"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-12 flex items-center justify-between">

        {/* Brand */}
        <button
          type="button"
          onClick={() => navigate('/')}
          className="flex items-center gap-2 group cursor-pointer min-h-[44px] -mx-1 px-1"
          aria-label="ClipForge — go to home"
        >
          <div
            aria-hidden="true"
            className="w-6 h-6 rounded-md bg-[var(--surface-1)] border border-[var(--border-1)]
                       flex items-center justify-center
                       group-hover:border-[var(--border-2)] transition-[border-color] duration-130"
          >
            <Cpu size={11} className="text-[var(--text-2)]" />
          </div>
          <span className="font-bold text-[var(--text-1)] text-[13px] tracking-tight">ClipForge</span>
        </button>

        {/* Right controls */}
        <div className="flex items-center gap-0.5">

          <button
            type="button"
            onClick={() => navigate('/dashboard')}
            className={`btn-ghost text-[12px] !h-[30px] !gap-1.5 ${
              isActive('/dashboard')
                ? '!text-[var(--text-1)] !bg-[var(--surface-1)] !border-[var(--border)]'
                : ''
            }`}
            aria-label="Dashboard"
            aria-current={isActive('/dashboard') ? 'page' : undefined}
          >
            <LayoutDashboard aria-hidden="true" size={13} />
            <span className="hidden sm:inline">Dashboard</span>
          </button>

          <button
            type="button"
            onClick={() => navigate('/settings')}
            className={`btn-ghost text-[12px] !h-[30px] !gap-1.5 ${
              isActive('/settings')
                ? '!text-[var(--text-1)] !bg-[var(--surface-1)] !border-[var(--border)]'
                : ''
            }`}
            aria-label="Settings"
            aria-current={isActive('/settings') ? 'page' : undefined}
          >
            <Settings aria-hidden="true" size={13} />
            <span className="hidden sm:inline">Settings</span>
          </button>

          <div
            aria-hidden="true"
            role="separator"
            className="w-px h-4 bg-[var(--border)] mx-2"
          />

          <span
            className="hidden sm:block text-[11px] text-[var(--text-3)] font-mono px-2 py-1 rounded-md
                       bg-[var(--surface)] border border-[var(--border)]"
          >
            {user.username || user.email}
          </span>

          <button
            type="button"
            onClick={logout}
            className="btn-ghost ml-1 !h-[30px] !text-[var(--text-3)]
                       hover:!text-red-400 hover:!bg-red-500/6 hover:!border-red-500/12"
            aria-label="Sign out"
          >
            <LogOut aria-hidden="true" size={13} />
          </button>
        </div>
      </div>
    </nav>
  );
}
