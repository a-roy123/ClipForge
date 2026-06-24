import React, { useState } from 'react';
import { useAuth } from '../hooks/useAuth.jsx';
import { useNavigate } from 'react-router-dom';
import { Cpu } from 'lucide-react';

export default function LoginRegister() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);

  const { login, register } = useAuth();
  const navigate = useNavigate();

  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setPending(true);

    try {
      if (isLogin) {
        await login(email, password);
      } else {
        await register(username, email, password);
      }
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Authentication handshake rejected.');
    } finally {
      setPending(false);
    }
  };

  return (
    <div
      className="relative min-h-dvh flex items-center justify-center px-4 overflow-hidden"
      style={{
        backgroundColor: 'var(--bg)',
        backgroundImage: [
          'linear-gradient(rgba(255,255,255,0.016) 1px, transparent 1px)',
          'linear-gradient(90deg, rgba(255,255,255,0.016) 1px, transparent 1px)',
        ].join(', '),
        backgroundSize: '64px 64px',
      }}
    >
      <div
        className="relative z-10 w-full max-w-sm"
        style={{ animation: 'scaleIn 0.28s ease-out forwards' }}
      >
        {/* Logo mark */}
        <div className="flex items-center justify-center gap-2.5 mb-7">
          <div
            aria-hidden="true"
            className="w-8 h-8 rounded-lg bg-[var(--surface-1)] border border-[var(--border-1)] flex items-center justify-center"
          >
            <Cpu size={13} className="text-[var(--text-2)]" />
          </div>
          <span className="text-[15px] font-bold text-[var(--text-1)] tracking-tight">ClipForge</span>
        </div>

        {/* Card */}
        <div className="glass-card p-7">
          <h2 className="text-lg font-bold text-[var(--text-1)] mb-1 tracking-tight">
            {isLogin ? 'Welcome back' : 'Create account'}
          </h2>
          <p className="text-[var(--text-2)] text-[13px] mb-6 leading-relaxed">
            {isLogin ? 'Sign in to access your workspace' : 'Set up your ClipForge profile'}
          </p>

          {/* Tab switcher */}
          <div
            role="tablist"
            aria-label="Authentication mode"
            className="flex gap-1 p-1 rounded-lg bg-[var(--bg)] border border-[var(--border)] mb-6"
          >
            <button
              type="button"
              role="tab"
              aria-selected={isLogin}
              onClick={() => setIsLogin(true)}
              className={`flex-1 py-1.5 text-[13px] font-semibold rounded-md cursor-pointer
                transition-[background-color,color] duration-130
                ${isLogin
                  ? 'bg-[var(--surface-1)] text-[var(--text-1)]'
                  : 'text-[var(--text-3)] hover:text-[var(--text-2)]'
                }`}
            >
              Sign In
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={!isLogin}
              onClick={() => setIsLogin(false)}
              className={`flex-1 py-1.5 text-[13px] font-semibold rounded-md cursor-pointer
                transition-[background-color,color] duration-130
                ${!isLogin
                  ? 'bg-[var(--surface-1)] text-[var(--text-1)]'
                  : 'text-[var(--text-3)] hover:text-[var(--text-2)]'
                }`}
            >
              Register
            </button>
          </div>

          {/* Error — aria-live so screen readers announce it */}
          <div aria-live="assertive" aria-atomic="true">
            {error && (
              <div
                className="mb-5 px-4 py-3 rounded-lg bg-red-500/8 border border-red-500/15 text-red-400 text-[13px] leading-relaxed"
                style={{ animation: 'slideDown 0.2s ease-out' }}
                role="alert"
              >
                {error}
              </div>
            )}
          </div>

          {/* Form */}
          <form onSubmit={handleAuthSubmit} noValidate className="space-y-4">
            {!isLogin && (
              <div>
                <label htmlFor="username" className="block text-[11px] font-semibold text-[var(--text-2)] mb-1.5 tracking-wide">
                  Username
                </label>
                <input
                  id="username"
                  type="text"
                  name="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="input-forge"
                  placeholder="your_username"
                  autoComplete="username"
                  spellCheck={false}
                />
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-[11px] font-semibold text-[var(--text-2)] mb-1.5 tracking-wide">
                Email
              </label>
              <input
                id="email"
                type="email"
                name="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input-forge"
                placeholder="you@example.com"
                autoComplete="email"
                inputMode="email"
                spellCheck={false}
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-[11px] font-semibold text-[var(--text-2)] mb-1.5 tracking-wide">
                Password
              </label>
              <input
                id="password"
                type="password"
                name="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-forge"
                placeholder="••••••••"
                autoComplete={isLogin ? 'current-password' : 'new-password'}
              />
            </div>

            <button
              type="submit"
              disabled={pending}
              aria-busy={pending}
              className="btn-forge w-full !h-[40px] !rounded-lg mt-1"
            >
              {pending ? (
                <span className="flex items-center justify-center gap-2">
                  <span aria-hidden="true" className="spinner w-3.5 h-3.5" />
                  Verifying…
                </span>
              ) : isLogin ? 'Continue' : 'Create Account'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
