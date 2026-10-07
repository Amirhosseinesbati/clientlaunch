import { useEffect, useState, type CSSProperties, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, CalendarDays, Check, Compass, FileText, LockKeyhole, LogOut, Mail, ShieldCheck } from 'lucide-react';
import { api, ApiError, type ChecklistItem, type Health } from '../../lib/api';
import { formatDate, isCompleteStatus, progress } from '../../lib/format';
import { brandStyle, clientRequests, inviteCode } from '../../lib/journey';
import ClientSubmission, { readSession, writeSession } from './ClientSubmission';
import ReceivedInputs from './ReceivedInputs';
import ThemeControl from '../../components/ThemeControl';
import { Button, EmptyState, ErrorState, LoadingState, ProgressBar, StatusBadge } from '../../components/ui';

const CLIENT_SESSION_KEY = 'clientlaunch_client_session';

function savedToken(): string | null {
  try {
    const raw = readSession(CLIENT_SESSION_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as { token: string; expires_at: string };
    if (!data.token || !Number.isFinite(Date.parse(data.expires_at)) || Date.parse(data.expires_at) <= Date.now()) { writeSession(CLIENT_SESSION_KEY, null); return null; }
    return data.token;
  } catch { return null; }
}

function ClientAccess({ portalToken, setPortalToken, exchangeError, isPending, onOperator, onSubmit }: { portalToken: string; setPortalToken: (value: string) => void; exchangeError?: string; isPending: boolean; onOperator: () => void; onSubmit: (event: FormEvent) => void }) {
  return <div className="client-access-layout"><div className="client-access-card"><div className="client-access-brand"><span className="brand-icon"><Compass size={23} /></span> ClientLaunch</div><div className="access-appearance"><ThemeControl /></div><p className="eyebrow">PRIVATE CLIENT ACCESS</p><h1>Let’s make something<br /><em>great together.</em></h1><p className="client-access-copy">Paste the complete invitation link or private code from your project team. You'll see only your project's requests.</p><form onSubmit={onSubmit} className="client-access-form"><label htmlFor="portal-token">Invitation link or private code</label><input id="portal-token" value={portalToken} onChange={(event) => setPortalToken(event.target.value)} autoComplete="off" autoCapitalize="none" spellCheck={false} aria-describedby="invite-help" placeholder="Paste your invitation here" required /><p id="invite-help" className="help-text">No invite yet, or has it expired? Ask your project contact for a new link.</p><Button type="submit" loading={isPending}>Open my project <ArrowRight size={17} /></Button></form>{exchangeError && <ErrorState title="Access link could not be opened" message={exchangeError} />}<p className="client-access-trust"><LockKeyhole size={15} /> Your information is shared only with your project team.</p><button type="button" className="client-access-operator" onClick={onOperator}>Agency team sign in <ArrowRight size={15} /></button></div></div>;
}

function ClientChecklist({ items, onSelect, intakeOpen }: { items: ChecklistItem[]; onSelect: (id: string) => void; intakeOpen: boolean }) {
  const required = items.filter((item) => item.required);
  const complete = required.filter((item) => isCompleteStatus(item.status)).length;
  const value = progress(complete, required.length);
  return <section className="client-card"><div className="client-card-heading"><div><p className="eyebrow">YOUR CHECKLIST</p><h2>Project requests</h2><p>A little clarity goes a long way. Here’s what’s needed to get started.</p></div><span className="client-card-count">{complete}/{required.length}</span></div><ProgressBar value={value} label="Required checklist progress" /><div className="client-checklist">{items.length === 0 ? <EmptyState title="Your checklist is on its way">Your project team will add the approved items here.</EmptyState> : [...clientRequests(items), ...items.filter(item => isCompleteStatus(item.status))].map((item) => <div key={item.id} className={`client-checklist-row ${isCompleteStatus(item.status) ? 'client-checklist-done' : ''}`}><span className="client-check-icon">{isCompleteStatus(item.status) ? <Check size={17} /> : null}</span><div><strong>{item.title}</strong>{item.description && <p className="readable-detail">{item.description}</p>}<div className="client-check-meta"><span>{isCompleteStatus(item.status) ? "Received" : "Awaiting your input"}</span>{item.required && <span>Required</span>}{item.due_at && <span><CalendarDays size={13} /> {formatDate(item.due_at)}</span>}</div></div>{!isCompleteStatus(item.status) && intakeOpen && <Button variant="ghost" onClick={() => onSelect(item.id)}>Respond <ArrowRight size={15} /></Button>}</div>)}</div></section>;
}

export default function ClientPortal({ health, onOperator }: { health?: Health; onOperator: () => void }) {
  const queryClient = useQueryClient();
  const [clientToken, setClientToken] = useState<string | null>(() => new URLSearchParams(window.location.search).has('token') ? null : savedToken());
  const [portalToken, setPortalToken] = useState(() => new URLSearchParams(window.location.search).get('token') ?? '');
  const [requestedItem, setRequestedItem] = useState('');
  const [requestVersion, setRequestVersion] = useState(0);
  const [accessError, setAccessError] = useState('');
  const [submittedToken, setSubmittedToken] = useState(() => new URLSearchParams(window.location.search).get('token') ?? '');
  const exchange = useQuery({ queryKey: ['client-exchange', submittedToken], queryFn: () => api.exchangeClientToken(submittedToken), enabled: !!submittedToken && !clientToken, retry: false, staleTime: Infinity });
  const client = useQuery({ queryKey: ['client-onboarding', clientToken], queryFn: () => api.clientOnboarding(clientToken!), enabled: !!clientToken, retry: false });

  useEffect(() => {
    const url = new URL(window.location.href); url.searchParams.delete('token');
    window.history.replaceState({}, '', url.pathname + url.search);
  }, []);

  useEffect(() => {
    if (!exchange.data) return;
    setClientToken(exchange.data.token);
    writeSession(CLIENT_SESSION_KEY, JSON.stringify(exchange.data));
    const url = new URL(window.location.href);
    url.searchParams.delete('token');
    window.history.replaceState({}, '', url.pathname + url.search);
  }, [exchange.data]);

  useEffect(() => {
    if (client.error instanceof ApiError && [401, 403].includes(client.error.status)) {
      writeSession(CLIENT_SESSION_KEY, null);
      setClientToken(null);
      setSubmittedToken('');
      queryClient.removeQueries({ queryKey: ['client-exchange'] });
      setAccessError('Your session expired. Open your invitation again or ask your team for a new link.');
    }
  }, [client.error, queryClient]);

  function signOut() { if (client.data) writeSession(`clientlaunch_draft_${client.data.onboarding.id}`, null); queryClient.removeQueries({ queryKey: ['client-exchange'] }); setAccessError(''); writeSession(CLIENT_SESSION_KEY, null); setClientToken(null); setSubmittedToken(''); setPortalToken(''); queryClient.removeQueries({ queryKey: ['client-onboarding'] }); }
  function selectRequest(id: string) { setRequestedItem(id); setRequestVersion(v => v + 1); }
  function submitAccess(event: FormEvent) {
    event.preventDefault(); setAccessError('');
    try { const code = inviteCode(portalToken); if (code === submittedToken) void exchange.refetch(); else setSubmittedToken(code); }
    catch (error) { setAccessError((error as Error).message); }
  }

  if (!clientToken) return <ClientAccess portalToken={portalToken} setPortalToken={setPortalToken} exchangeError={accessError || exchange.error?.message} isPending={exchange.isFetching} onOperator={onOperator} onSubmit={submitAccess} />;
  if (client.isPending) return <div className="app-loading"><LoadingState label="Opening your project…" /></div>;
  if (client.error || !client.data) return <div className="app-loading"><ErrorState title="Project unavailable" message={client.error?.message ?? 'Your project could not be loaded.'} onRetry={() => void client.refetch()} /><Button variant="secondary" onClick={signOut}>Use a different link</Button></div>;
  const { onboarding, checklist, assets, submissions, brand } = client.data;
  const next_actions = clientRequests(checklist);
  const required = checklist.filter((item) => item.required);
  const completed = required.filter((item) => isCompleteStatus(item.status)).length;
  const value = progress(completed, required.length);
  const intakeOpen = onboarding.intake_open ?? ['waiting_for_client', 'ready'].includes(onboarding.status);
  return <div className="client-portal" style={brandStyle(brand?.accent) as CSSProperties}><a className="skip-link" href="#client-content">Skip to project requests</a><header className="client-header"><div className="client-header-inner"><div className="client-brand"><span className="brand-icon"><Compass size={22} /></span> {brand?.agency_name ?? "ClientLaunch"}</div><div className="client-header-actions"><ThemeControl /><span className="private-project"><LockKeyhole size={14} /> Private project space</span><button type="button" onClick={signOut} className="client-signout"><LogOut size={16} /> Sign out</button></div></div></header><main className="client-main" id="client-content" tabIndex={-1}>{health?.mode === 'DEMO' && <div className="synthetic-banner client-synthetic"><ShieldCheck size={16} /><span><strong>Synthetic demo dataset</strong> · {health.fixture ? "Local fixture: changes stay in memory. No n8n, email delivery or live providers." : "This project and connector responses are simulated."}</span></div>}<div className="client-hero"><div className="client-hero-copy"><span className="client-hero-kicker">{onboarding.client_name}</span><h1>{brand?.welcome_heading ?? `Welcome, ${onboarding.client_name}`}</h1><p className="readable-detail">{brand?.welcome_message ?? "Share a few details with your project team. Come back and finish at your own pace."}</p><div className="client-hero-status"><StatusBadge status={onboarding.status} /><span>{onboarding.service_names.join(' · ') || 'Your project'}</span></div></div></div><div className="client-overview-grid"><section className="client-progress-panel"><div className="client-progress-top"><span className="eyebrow">INPUTS RECEIVED</span><span className="client-progress-value">{value}%</span></div><h2>{completed === required.length && required.length ? "Your required inputs are in." : "Your onboarding inputs"}</h2><p>{completed} of {required.length} required items complete</p><ProgressBar value={value} label="Required inputs received" /><p className="help-text">This tracks your inputs. Project delivery is a separate stage.</p></section><section className="next-actions-panel"><span className="next-icon"><ArrowRight size={20} /></span><div><span className="eyebrow">WHAT WE NEED FROM YOU NEXT</span>{next_actions.length && intakeOpen ? <><ul>{next_actions.slice(0, 1).map((action) => <li key={action.id}>{action.title}</li>)}</ul><Button variant="secondary" onClick={() => selectRequest(next_actions[0]!.id)}>Start this request <ArrowRight size={16} /></Button></> : <p>{intakeOpen ? "Your inputs are received. Your team will confirm the next stage." : "Your team is preparing or reviewing this project. Inputs are closed for now."}</p>}</div></section></div><ClientChecklist items={checklist} onSelect={selectRequest} intakeOpen={intakeOpen} /><ReceivedInputs submissions={submissions} items={checklist} /><ClientSubmission key={onboarding.id} projectId={onboarding.id} requestedItem={requestedItem} requestVersion={requestVersion} intakeOpen={intakeOpen} token={clientToken} items={checklist} onChanged={() => void queryClient.invalidateQueries({ queryKey: ['client-onboarding', clientToken] })} /><section className="client-files-card"><div><span className="share-card-icon"><FileText size={20} /></span><h2>Files shared so far</h2><p>{health?.fixture ? "Fixture metadata only; file content is discarded." : "Files received for this project."}</p></div>{assets.length === 0 ? <p className="muted-copy">No files uploaded yet.</p> : <ul>{assets.map((asset) => <li key={asset.id}><FileText size={17} /><span>{asset.filename || asset.file_name || asset.name || 'Shared file'}</span><small>{formatDate(asset.created_at)}</small></li>)}</ul>}</section>{brand?.support_email && <aside className="client-help"><Mail size={20} /><div><h2>Need a hand?</h2><p>Questions about a request? <a href={`mailto:${brand.support_email}`}>Contact {brand.agency_name}</a>.</p></div></aside>}</main><footer className="client-footer"><div><span className="client-brand"><span className="brand-icon"><Compass size={17} /></span> {brand?.agency_name ?? "ClientLaunch"}</span><p>Project intake · Scope review · Delivery handoff</p></div><span><ShieldCheck size={15} /> Your project details stay private.</span></footer></div>;
}
