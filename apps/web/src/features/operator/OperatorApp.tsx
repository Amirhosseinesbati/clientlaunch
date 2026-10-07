import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Compass, LayoutDashboard, ListTodo, LogOut, Menu, Palette, Search, ShieldCheck, X } from 'lucide-react';
import { api, type AuthSession, type Health, type OnboardingSummary } from '../../lib/api';
import { humanize, initials, isAttentionStatus, progress } from '../../lib/format';
import { EmptyState, ErrorState, LoadingState, ProgressBar, StatusBadge } from '../../components/ui';
import ThemeControl from '../../components/ThemeControl';
import DetailPanel from './DetailPanel';
import Customization from './Customization';
import { nextStep } from '../../lib/journey';

type View = 'overview' | 'onboardings' | 'customization';
function OnboardingList({ items, selectedId, onSelect }: { items: OnboardingSummary[]; selectedId?: string; onSelect: (id: string) => void }) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'needs_attention' | 'active' | 'complete'>('all');
  const visible = useMemo(() => items.filter(item => {
    const query = search.trim().toLowerCase();
    const matchesSearch = !query || [item.client_name, item.owner_name ?? '', ...item.service_names].join(' ').toLowerCase().includes(query);
    const status = item.substate ?? item.status;
    return matchesSearch && (filter === 'all' || (filter === 'needs_attention' && (isAttentionStatus(status) || item.status === 'awaiting_approval')) || (filter === 'complete' && item.status === 'handed_off') || (filter === 'active' && item.status !== 'handed_off' && !isAttentionStatus(status)));
  }), [items, search, filter]);
  return <section className="list-panel" aria-label="Client queue">
    <div className="queue-heading"><h2>Client queue</h2><span>{items.length}</span></div>
    <div className="list-panel-top">
      <div className="search-field"><Search size={16} /><input aria-label="Search clients, services, or owners" type="search" placeholder="Search clients or owners" value={search} onChange={event => setSearch(event.target.value)} /></div>
      <label className="sr-only" htmlFor="status-filter">Filter by status</label>
      <select id="status-filter" value={filter} onChange={event => setFilter(event.target.value as typeof filter)} className="filter-select">
        <option value="all">All statuses</option><option value="needs_attention">Needs attention</option><option value="active">In progress</option><option value="complete">Handed off</option>
      </select>
    </div>
    <div className="onboarding-list">
      {visible.length === 0 ? <EmptyState title="No matching onboardings">Try a different search or status filter.</EmptyState> : visible.map(item => <button type="button" key={item.id} className={'onboarding-row ' + (selectedId === item.id ? 'row-selected' : '')} onClick={() => onSelect(item.id)} aria-pressed={selectedId === item.id}>
        <span className="client-avatar" aria-hidden="true">{initials(item.client_name)}</span>
        <span className="row-body">
          <span className="row-name-line"><strong>{item.client_name}</strong><ArrowRight size={15} className="row-arrow" /></span>
          <span className="row-services">{item.service_names.join(' · ') || 'Services pending'}</span>
          <span className="row-next-step">{nextStep(item).title}</span>
          <span className="row-footer"><StatusBadge status={item.substate || item.status} compact /><span>{item.owner_name || 'Owner unassigned'}</span></span>
          <span className="row-progress"><ProgressBar value={progress(item.required_complete, item.required_total, item.progress_percent)} label={item.client_name + ' required checklist progress'} /><span>{item.required_total ? (item.required_complete ?? 0) + '/' + item.required_total + ' required' : 'Checklist pending'}</span></span>
        </span>
      </button>)}
    </div><div className="list-panel-footer">Showing {visible.length} of {items.length} onboardings</div>
  </section>;
}

export default function OperatorApp({ session, health, healthError }: { session: AuthSession; health?: Health; healthError: Error | null }) {
  const queryClient = useQueryClient();
  const onboardings = useQuery({ queryKey: ['onboardings'], queryFn: api.onboardings });
  const [view, setView] = useState<View>('overview');
  const [selectedId, setSelectedId] = useState<string | undefined>(() => new URLSearchParams(window.location.search).get('onboarding') ?? undefined);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const navRef = useRef<HTMLElement>(null);
  const closeDetail = useCallback(() => setDetailOpen(false), []);
  const logout = useMutation({ mutationFn: () => api.logout(session.csrf_token), onSuccess: () => { queryClient.clear(); window.history.replaceState({}, '', '/'); window.location.reload(); } });
  const items = onboardings.data ?? [];
  const activeId = selectedId ?? items[0]?.id;
  const active = items.filter(item => item.status !== 'handed_off').length;
  const urgent = items.filter(item => isAttentionStatus(item.substate ?? item.status) || item.status === 'awaiting_approval').length;
  useEffect(() => {
    if (!mobileMenu) return;
    const previous = document.querySelector<HTMLButtonElement>('.mobile-menu-button');
    navRef.current?.querySelector<HTMLButtonElement>('.sidebar-close')?.focus();
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setMobileMenu(false); }
      if (event.key !== 'Tab') return;
      const focusable = Array.from(navRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]), a[href]') ?? []).filter(el => el.getClientRects().length);
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', keyboard);
    return () => { document.removeEventListener('keydown', keyboard); previous?.focus(); };
  }, [mobileMenu]);
  function select(id: string) {
    setSelectedId(id); setDetailOpen(true);
    const url = new URL(window.location.href); url.searchParams.set('onboarding', id);
    window.history.replaceState({}, '', url.pathname + url.search);
  }
  function changeView(next: View) { setView(next); setMobileMenu(false); setDetailOpen(false); }
  return <div className="workspace-shell">
    <a className="skip-link" href="#workspace-content">Skip to workspace content</a>
    <aside ref={navRef} className={'sidebar ' + (mobileMenu ? 'sidebar-open' : '')} aria-label="Workspace navigation" role={mobileMenu ? 'dialog' : undefined} aria-modal={mobileMenu || undefined}>
      <div className="sidebar-header"><span className="brand-icon"><Compass size={21} /></span><span>clientlaunch<span className="brand-period">.</span></span><button type="button" className="sidebar-close" aria-label="Close menu" onClick={() => setMobileMenu(false)}><X size={19} /></button></div>
      <div className="sidebar-workspace"><span className="workspace-symbol">A</span><span><strong>Agency workspace</strong><small>Client operations</small></span></div>
      <nav className="sidebar-nav" aria-label="Main navigation"><span className="nav-label">OPERATIONS</span>
        <button type="button" aria-current={view === 'overview' ? 'page' : undefined} className={view === 'overview' ? 'nav-active' : ''} onClick={() => changeView('overview')}><LayoutDashboard size={17} /> Overview</button>
        <button type="button" aria-current={view === 'onboardings' ? 'page' : undefined} className={view === 'onboardings' ? 'nav-active' : ''} onClick={() => changeView('onboardings')}><ListTodo size={17} /> Onboardings <span className="nav-count">{items.length}</span></button>
        <span className="nav-label nav-label-second">CONFIGURATION</span>
        <button type="button" aria-current={view === 'customization' ? 'page' : undefined} className={view === 'customization' ? 'nav-active' : ''} onClick={() => changeView('customization')}><Palette size={17} /> Templates & brand</button>
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-help"><ShieldCheck size={17} /><strong>Approval before execution</strong><p>Review scope. Confirm outcomes. Keep every handoff traceable.</p></div>
        <div className="sidebar-user"><span className="user-avatar">{initials(session.user.name)}</span><span><strong>{session.user.name}</strong><small>{humanize(session.user.role)}</small></span><button type="button" aria-label="Sign out" title="Sign out" onClick={() => logout.mutate()} disabled={logout.isPending}><LogOut size={17} /></button></div>
        {logout.error && <p className="sidebar-error" role="alert">{logout.error.message}</p>}
      </div>
    </aside>
    {mobileMenu && <button type="button" className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobileMenu(false)} tabIndex={-1} />}
    <main className="workspace-main" id="workspace-content" tabIndex={-1} inert={mobileMenu}>
      <header className="topbar"><div className="topbar-left"><button type="button" className="mobile-menu-button" aria-label="Open menu" aria-expanded={mobileMenu} onClick={() => setMobileMenu(true)}><Menu size={21} /></button><div className="breadcrumb">Workspace <span>/</span> <strong>{view === 'customization' ? 'Templates & brand' : view === 'overview' ? 'Overview' : 'Onboardings'}</strong></div></div>
        <div className="topbar-right"><span className={'connection-pill ' + (healthError ? 'connection-offline' : '')}><span />{healthError ? 'API disconnected' : health?.status === 'ok' ? health.fixture ? 'Fixture API' : 'Business API' : 'Connecting'}</span><ThemeControl /></div>
      </header>
      <div className="workspace-content">
        {health?.mode === 'DEMO' && <div className="synthetic-banner"><ShieldCheck size={15} /><span><strong>Synthetic demo dataset</strong> · {health.fixture ? 'Local fixture. Changes reset on restart. No n8n, live providers or email delivery.' : 'Clients and connector responses are simulated.'}</span></div>}
        {view === 'customization' ? <Customization session={session} /> : <>
          <div className="page-intro"><div><p className="eyebrow">ONBOARDING OPERATIONS</p><h1>{view === 'overview' ? 'Move each client forward' : 'Onboardings'}</h1><p>Review the next action, confirm ownership, and resolve blocked steps.</p></div><span className="page-count">{items.length} projects</span></div>
          <div className="metrics-strip" aria-label="Workspace summary"><div><strong>{active}</strong><span>Active onboardings</span></div><div className="metric-attention"><strong>{urgent}</strong><span>Need attention</span></div><div><strong>{items.length - active}</strong><span>Handed off</span></div></div>
          {onboardings.isPending ? <LoadingState label="Loading onboardings." /> : onboardings.error ? <ErrorState message={onboardings.error.message} onRetry={() => void onboardings.refetch()} /> : items.length === 0 ? <EmptyState title="No onboardings yet">A signed won deal appears here after the workflow receives it.</EmptyState> : <div className="onboardings-layout"><OnboardingList items={items} selectedId={activeId} onSelect={select} /><div className={'detail-column ' + (detailOpen ? 'detail-open' : '')}>{activeId && <DetailPanel key={activeId} id={activeId} session={session} onBack={closeDetail} overlayOpen={detailOpen} />}</div></div>}
        </>}
      </div>
    </main>
  </div>;
}
