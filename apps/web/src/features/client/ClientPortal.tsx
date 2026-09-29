import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, CalendarDays, Check, CheckCircle2, ChevronDown, Compass, FileText, HeartHandshake, ImagePlus, LockKeyhole, LogOut, Mail, ShieldCheck, Sparkles, UploadCloud } from 'lucide-react';
import { api, ApiError, type ChecklistItem, type Health } from '../../lib/api';
import { formatDate, humanize, isCompleteStatus, progress } from '../../lib/format';
import { Button, EmptyState, ErrorState, LoadingState, ProgressBar, StatusBadge } from '../../components/ui';

const CLIENT_SESSION_KEY = 'clientlaunch_client_session';

function savedToken(): string | null {
  try {
    const raw = sessionStorage.getItem(CLIENT_SESSION_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as { token: string; expires_at: string };
    if (new Date(data.expires_at).getTime() <= Date.now()) { sessionStorage.removeItem(CLIENT_SESSION_KEY); return null; }
    return data.token;
  } catch { return null; }
}

function ClientAccess({ portalToken, setPortalToken, exchangeError, isPending, onOperator, onSubmit }: { portalToken: string; setPortalToken: (value: string) => void; exchangeError?: string; isPending: boolean; onOperator: () => void; onSubmit: (event: FormEvent) => void }) {
  return <div className="client-access-layout"><div className="client-access-card"><div className="client-access-brand"><span className="brand-icon"><Compass size={23} /></span> clientlaunch<span className="brand-period">.</span></div><span className="client-access-art"><HeartHandshake size={43} strokeWidth={1.4} /></span><p className="eyebrow">YOUR PROJECT STARTS HERE</p><h1>Let’s make something<br /><em>great together.</em></h1><p className="client-access-copy">Enter the private access code from your welcome message to view your checklist and share what your team needs.</p><form onSubmit={onSubmit} className="client-access-form"><label htmlFor="portal-token">Private access code</label><input id="portal-token" value={portalToken} onChange={(event) => setPortalToken(event.target.value)} autoComplete="off" placeholder="Paste your access code" required /><Button type="submit" loading={isPending}>Open my project <ArrowRight size={17} /></Button></form>{exchangeError && <ErrorState title="Access link could not be opened" message={exchangeError} />}<p className="client-access-trust"><LockKeyhole size={15} /> Your information is shared only with your project team.</p><button type="button" className="client-access-operator" onClick={onOperator}>Agency team sign in <ArrowRight size={15} /></button></div></div>;
}

function ClientChecklist({ items }: { items: ChecklistItem[] }) {
  const required = items.filter((item) => item.required);
  const complete = required.filter((item) => isCompleteStatus(item.status)).length;
  const value = progress(complete, required.length);
  return <section className="client-card"><div className="client-card-heading"><div><p className="eyebrow">YOUR CHECKLIST</p><h2>Everything in one place</h2><p>A little clarity goes a long way. Here’s what’s needed to get started.</p></div><span className="client-card-count">{complete}/{required.length}</span></div><ProgressBar value={value} label="Required checklist progress" /><div className="client-checklist">{items.length === 0 ? <EmptyState title="Your checklist is on its way">Your project team will add the approved items here.</EmptyState> : items.map((item) => <div key={item.id} className={`client-checklist-row ${isCompleteStatus(item.status) ? 'client-checklist-done' : ''}`}><span className="client-check-icon">{isCompleteStatus(item.status) ? <Check size={17} /> : null}</span><div><strong>{item.title}</strong>{item.description && <p>{item.description}</p>}<div className="client-check-meta"><span>{humanize(item.status)}</span>{item.required && <span>Required</span>}{item.due_at && <span><CalendarDays size={13} /> {formatDate(item.due_at)}</span>}</div></div></div>)}</div></section>;
}

function ClientSubmission({ token, items, onChanged }: { token: string; items: ChecklistItem[]; onChanged: () => void }) {
  const available = items.filter((item) => !isCompleteStatus(item.status));
  const [selectedItem, setSelectedItem] = useState('');
  const [answer, setAnswer] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [assetItem, setAssetItem] = useState('');
  const [answerNotice, setAnswerNotice] = useState('');
  const [uploadNotice, setUploadNotice] = useState('');
  const answerMutation = useMutation({ mutationFn: () => api.clientSubmit(token, [{ checklist_item_id: selectedItem, value: answer.trim() }]), onSuccess: () => { setAnswer(''); setSelectedItem(''); setAnswerNotice('Your answer was received and is being reviewed.'); onChanged(); } });
  const uploadMutation = useMutation({ mutationFn: () => api.clientUpload(token, file!, assetItem), onSuccess: () => { setFile(null); setAssetItem(''); setUploadNotice('Your file was received and is being reviewed.'); onChanged(); } });
  return <section className="client-share-section"><div className="client-section-heading"><p className="eyebrow">KEEP THINGS MOVING</p><h2>Share what we need next</h2><p>Your answers and files stay with this project.</p></div><div className="client-share-grid"><form className="client-share-card" onSubmit={(event) => { event.preventDefault(); if (selectedItem && answer.trim()) answerMutation.mutate(); }}><span className="share-card-icon"><Mail size={20} /></span><h3>Answer a request</h3><p>Tell us the details behind an open checklist item.</p><label htmlFor="answer-item">Checklist item</label><span className="select-wrap"><select id="answer-item" value={selectedItem} onChange={(event) => setSelectedItem(event.target.value)} required><option value="">Choose a request</option>{available.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select><ChevronDown size={15} /></span><label htmlFor="answer-text">Your answer</label><textarea id="answer-text" value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="Share the details your project team needs…" required /><Button type="submit" variant="secondary" disabled={available.length === 0} loading={answerMutation.isPending}>Send answer <ArrowRight size={16} /></Button>{available.length === 0 && <p className="help-text">No open items need an answer right now.</p>}{answerMutation.error && <ErrorState title="Answer not sent" message={answerMutation.error.message} />}{answerNotice && <p className="inline-success" role="status"><CheckCircle2 size={16} />{answerNotice}</p>}</form><form className="client-share-card" onSubmit={(event) => { event.preventDefault(); if (file && assetItem) uploadMutation.mutate(); }}><span className="share-card-icon share-icon-peach"><ImagePlus size={20} /></span><h3>Upload an asset</h3><p>Logos, reference files, or documents can be shared here.</p><label htmlFor="asset-item">Related checklist item</label><span className="select-wrap"><select id="asset-item" value={assetItem} onChange={(event) => setAssetItem(event.target.value)} required><option value="">Choose a request</option>{items.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select><ChevronDown size={15} /></span><label htmlFor="asset-file" className="upload-zone"><UploadCloud size={24} /><strong>{file ? file.name : 'Choose a file to upload'}</strong><span>PNG, JPG, or PDF · maximum 5 MB</span><input id="asset-file" type="file" accept=".png,.jpg,.jpeg,.pdf,image/png,image/jpeg,application/pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} required /></label><Button type="submit" variant="secondary" loading={uploadMutation.isPending} disabled={!file || !assetItem}>Upload file <ArrowRight size={16} /></Button>{uploadMutation.error && <ErrorState title="File not uploaded" message={uploadMutation.error.message} />}{uploadNotice && <p className="inline-success" role="status"><CheckCircle2 size={16} />{uploadNotice}</p>}</form></div></section>;
}

export default function ClientPortal({ health, onOperator }: { health?: Health; onOperator: () => void }) {
  const queryClient = useQueryClient();
  const [clientToken, setClientToken] = useState<string | null>(() => new URLSearchParams(window.location.search).has('token') ? null : savedToken());
  const [portalToken, setPortalToken] = useState(() => new URLSearchParams(window.location.search).get('token') ?? '');
  const [submittedToken, setSubmittedToken] = useState(() => new URLSearchParams(window.location.search).get('token') ?? '');
  const exchange = useQuery({ queryKey: ['client-exchange', submittedToken], queryFn: () => api.exchangeClientToken(submittedToken), enabled: !!submittedToken && !clientToken, retry: false, staleTime: Infinity });
  const client = useQuery({ queryKey: ['client-onboarding', clientToken], queryFn: () => api.clientOnboarding(clientToken!), enabled: !!clientToken, retry: false });

  useEffect(() => {
    if (!exchange.data) return;
    setClientToken(exchange.data.token);
    sessionStorage.setItem(CLIENT_SESSION_KEY, JSON.stringify(exchange.data));
    const url = new URL(window.location.href);
    url.searchParams.delete('token');
    window.history.replaceState({}, '', url.pathname + url.search);
  }, [exchange.data]);

  useEffect(() => {
    if (client.error instanceof ApiError && [401, 403].includes(client.error.status)) {
      sessionStorage.removeItem(CLIENT_SESSION_KEY);
      setClientToken(null);
      setSubmittedToken('');
    }
  }, [client.error]);

  function signOut() { sessionStorage.removeItem(CLIENT_SESSION_KEY); setClientToken(null); setSubmittedToken(''); setPortalToken(''); queryClient.removeQueries({ queryKey: ['client-onboarding'] }); }
  function submitAccess(event: FormEvent) { event.preventDefault(); if (portalToken.trim()) { if (submittedToken === portalToken.trim()) void exchange.refetch(); else setSubmittedToken(portalToken.trim()); } }

  if (!clientToken) return <ClientAccess portalToken={portalToken} setPortalToken={setPortalToken} exchangeError={exchange.error?.message} isPending={exchange.isFetching} onOperator={onOperator} onSubmit={submitAccess} />;
  if (client.isPending) return <div className="app-loading"><LoadingState label="Opening your project…" /></div>;
  if (client.error || !client.data) return <div className="app-loading"><ErrorState title="Project unavailable" message={client.error?.message ?? 'Your project could not be loaded.'} onRetry={() => void client.refetch()} /><Button variant="secondary" onClick={signOut}>Use a different link</Button></div>;
  const { onboarding, checklist, assets, next_actions } = client.data;
  const required = checklist.filter((item) => item.required);
  const completed = required.filter((item) => isCompleteStatus(item.status)).length;
  const value = progress(completed, required.length);
  return <div className="client-portal"><header className="client-header"><div className="client-header-inner"><div className="client-brand"><span className="brand-icon"><Compass size={22} /></span> clientlaunch<span className="brand-period">.</span></div><div className="client-header-actions"><span className="private-project"><LockKeyhole size={14} /> Private project space</span><button type="button" onClick={signOut} className="client-signout"><LogOut size={16} /> Sign out</button></div></div></header><main className="client-main">{health?.mode === 'DEMO' && <div className="synthetic-banner client-synthetic"><ShieldCheck size={16} /><span><strong>Synthetic demo dataset</strong> · This project and any connector responses are simulated.</span></div>}<div className="client-hero"><div className="client-hero-copy"><span className="client-hero-kicker"><Sparkles size={15} /> YOUR PROJECT SPACE</span><h1>Welcome, {onboarding.client_name}<span>.</span></h1><p>We’re glad you’re here. This is your shared starting point for a smooth project launch.</p><div className="client-hero-status"><StatusBadge status={onboarding.status} /><span>{onboarding.service_names.join(' · ') || 'Your project'}</span></div></div><div className="client-hero-art" aria-hidden="true"><div className="client-orbit orbit-one" /><div className="client-orbit orbit-two" /><div className="client-orbit-center"><HeartHandshake size={56} strokeWidth={1.2} /></div><span className="client-orbit-star star-one">✦</span><span className="client-orbit-star star-two">✦</span></div></div><div className="client-overview-grid"><section className="client-progress-panel"><div className="client-progress-top"><span className="eyebrow">YOUR PROGRESS</span><span className="client-progress-value">{value}%</span></div><h2>We’re getting there, together.</h2><p>{completed} of {required.length} required items complete</p><ProgressBar value={value} label="Required items complete" /></section><section className="next-actions-panel"><span className="next-icon"><ArrowRight size={20} /></span><div><span className="eyebrow">WHAT WE NEED FROM YOU NEXT</span>{next_actions.length ? <ul>{next_actions.map((action) => <li key={action.id}>{action.title}</li>)}</ul> : <p>You’re all caught up. Your project team will be in touch about the next step.</p>}</div></section></div><ClientChecklist items={checklist} /><ClientSubmission token={clientToken} items={checklist} onChanged={() => void queryClient.invalidateQueries({ queryKey: ['client-onboarding', clientToken] })} /><section className="client-files-card"><div><span className="share-card-icon"><FileText size={20} /></span><h2>Files shared so far</h2><p>Files received for this project.</p></div>{assets.length === 0 ? <p className="muted-copy">No files uploaded yet.</p> : <ul>{assets.map((asset) => <li key={asset.id}><FileText size={17} /><span>{asset.filename || asset.file_name || asset.name || 'Shared file'}</span><small>{formatDate(asset.created_at)}</small></li>)}</ul>}</section></main><footer className="client-footer"><div><span className="client-brand"><span className="brand-icon"><Compass size={17} /></span> clientlaunch<span className="brand-period">.</span></span><p>A thoughtful beginning for every project.</p></div><span><ShieldCheck size={15} /> Your project details stay private.</span></footer></div>;
}
