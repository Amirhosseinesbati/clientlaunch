import { useState, type FormEvent } from 'react';
import { ArrowRight, CheckCircle2, Compass, LockKeyhole, ShieldCheck, Sparkles } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, type AuthSession, type Health } from '../../lib/api';
import { Button, ErrorState } from '../../components/ui';

export default function LoginScreen({ health, onClientPortal, connectionError, onRetryConnection }: { health?: Health; onClientPortal: () => void; connectionError?: string; onRetryConnection?: () => void }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const login = useMutation({
    mutationFn: () => api.login(email.trim(), password),
    onSuccess: (session: AuthSession) => queryClient.setQueryData(['me'], session),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (email.trim() && password) login.mutate();
  }

  return (
    <div className="auth-layout">
      <div className="auth-story">
        <div className="auth-brand"><span className="brand-icon"><Compass size={23} strokeWidth={2.2} /></span><span>clientlaunch<span className="brand-period">.</span></span></div>
        <div className="auth-story-body">
          <span className="auth-kicker"><Sparkles size={15} /> OPERATIONS, BEAUTIFULLY IN ORDER</span>
          <h1>Every great project deserves a <em>better beginning.</em></h1>
          <p>Bring sales and delivery together in one calm, considered onboarding experience.</p>
          <div className="auth-journey" aria-label="Onboarding journey">
            <div><span className="journey-check"><CheckCircle2 size={18} /></span><span>Deal approved</span><strong>01</strong></div>
            <div><span className="journey-check"><CheckCircle2 size={18} /></span><span>Plan reviewed</span><strong>02</strong></div>
            <div><span className="journey-orb"><Compass size={18} /></span><span>Work begins</span><strong>03</strong></div>
          </div>
        </div>
        <p className="auth-footnote">One shared view from the first handshake to handoff.</p>
      </div>
      <main className="auth-form-side">
        <div className="auth-form-wrap">
          {health?.mode === 'DEMO' && <span className="demo-label">SYNTHETIC DEMO DATASET</span>}
          <div className="auth-heading"><span className="auth-heading-icon"><LockKeyhole size={23} /></span><h2>Welcome back</h2><p>Sign in to your agency workspace.</p></div>
          {connectionError && <div className="auth-connection-error"><ErrorState title="Workspace connection unavailable" message={connectionError} onRetry={onRetryConnection} /></div>}
          <form onSubmit={submit} className="auth-form">
            <label htmlFor="email">Work email</label>
            <input id="email" type="email" autoComplete="username" placeholder="you@agency.example.com" value={email} onChange={(event) => setEmail(event.target.value)} required />
            <label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete="current-password" placeholder="Enter your password" value={password} onChange={(event) => setPassword(event.target.value)} required />
            {login.error && <ErrorState title="Unable to sign in" message={login.error.message} />}
            <Button type="submit" loading={login.isPending} className="auth-submit">Open workspace <ArrowRight size={17} /></Button>
          </form>
          <div className="auth-divider"><span>or</span></div>
          <button type="button" className="client-entry" onClick={onClientPortal}><span><Compass size={19} /> Have a client invite?</span><ArrowRight size={17} /></button>
          <p className="auth-trust"><ShieldCheck size={15} /> Access is limited to your workspace and role.</p>
        </div>
      </main>
    </div>
  );
}
