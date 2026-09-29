import type { ButtonHTMLAttributes, PropsWithChildren, ReactNode } from 'react';
import { AlertCircle, ArrowRight, Check, CircleHelp, LoaderCircle, RefreshCw } from 'lucide-react';
import { humanize, isAttentionStatus, isCompleteStatus } from '../lib/format';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  loading?: boolean;
};

export function Button({ variant = 'primary', loading = false, children, className = '', disabled, ...props }: ButtonProps) {
  return (
    <button className={`btn btn-${variant} ${className}`} disabled={disabled || loading} {...props}>
      {loading ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

export function StatusBadge({ status, compact = false }: { status?: string | null; compact?: boolean }) {
  const tone = isCompleteStatus(status ?? undefined) ? 'success' : isAttentionStatus(status ?? undefined) ? 'danger' : ['awaiting_approval', 'waiting_for_client', 'pending', 'paused'].includes(status ?? '') ? 'warning' : 'neutral';
  return <span className={`status-badge status-${tone} ${compact ? 'status-compact' : ''}`}><span className="status-dot" />{humanize(status)}</span>;
}

export function SectionHeading({ eyebrow, title, action, children }: PropsWithChildren<{ eyebrow?: string; title: string; action?: ReactNode }>) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h2>{title}</h2>
        {children && <p className="section-description">{children}</p>}
      </div>
      {action}
    </div>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  return (
    <div className="progress-wrap">
      <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value} aria-label={label ?? 'Onboarding progress'}>
        <span style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

export function EmptyState({ icon, title, children, action }: PropsWithChildren<{ icon?: ReactNode; title: string; action?: ReactNode }>) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon ?? <CircleHelp size={22} />}</div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry, title = 'Something went wrong' }: { message: string; onRetry?: () => void; title?: string }) {
  return (
    <div className="error-state" role="alert">
      <AlertCircle size={20} aria-hidden="true" />
      <div><strong>{title}</strong><p>{message}</p></div>
      {onRetry && <Button variant="secondary" onClick={onRetry}><RefreshCw size={15} /> Retry</Button>}
    </div>
  );
}

export function LoadingState({ label = 'Loading workspace…' }: { label?: string }) {
  return <div className="loading-state" role="status"><LoaderCircle className="animate-spin" size={24} /><span>{label}</span></div>;
}

export function StepList({ steps, activeIndex }: { steps: string[]; activeIndex: number }) {
  return (
    <ol className="step-list" aria-label="Onboarding stages">
      {steps.map((step, index) => <li key={step} className={index < activeIndex ? 'step-done' : index === activeIndex ? 'step-active' : ''}>
        <span className="step-marker">{index < activeIndex ? <Check size={13} strokeWidth={3} /> : index + 1}</span>
        <span>{step}</span>
        {index === activeIndex && <ArrowRight size={14} className="step-arrow" />}
      </li>)}
    </ol>
  );
}
