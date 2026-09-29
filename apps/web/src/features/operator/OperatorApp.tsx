import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Bell, CircleAlert, Compass, LayoutDashboard, ListTodo, LogOut, Menu, Search, ShieldCheck, X } from 'lucide-react';
import { api, type AuthSession, type Health, type OnboardingSummary } from '../../lib/api';
import { compactDate, humanize, initials, isAttentionStatus, progress } from '../../lib/format';
import { Button, EmptyState, ErrorState, LoadingState, ProgressBar, SectionHeading, StatusBadge } from '../../components/ui';
import DetailPanel from './DetailPanel';

type View = 'overview' | 'onboardings';

function OnboardingList({ items, selectedId, onSelect, expanded = false, totalCount }: { items: OnboardingSummary[]; selectedId?: string; onSelect: (id: string) => void; expanded?: boolean; totalCount?: number }) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'needs_attention' | 'active' | 'complete'>('all');
  const visible = useMemo(() => items.filter((item) => {
    const query = search.trim().toLowerCase();
    const matchesSearch = !query || [item.client_name, item.owner_name ?? '', ...item.service_names].join(' ').toLowerCase().includes(query);
    const status = item.substate ?? item.status;
    const matchesFilter = filter === 'all' || (filter === 'needs_attention' && (isAttentionStatus(status) || item.status === 'awaiting_approval')) || (filter === 'complete' && item.status === 'handed_off') || (filter === 'active' && item.status !== 'handed_off' && !isAttentionStatus(status));
    return matchesSearch && matchesFilter;
  }), [items, search, filter]);

  return (
    <div className="list-panel">
      <div className="list-panel-top">
        <div className="search-field"><Search size={17} /><input aria-label="Search clients, services, or owners" type="search" placeholder="Search clients…" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
        <label className="sr-only" htmlFor="status-filter">Filter by status</label>
        <select id="status-filter" value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)} className="filter-select">
          <option value="all">All statuses</option><option value="needs_attention">Needs attention</option><option value="active">In progress</option><option value="complete">Handed off</option>
        </select>
      </div>
      <div className={`onboarding-list ${expanded ? 'list-expanded' : ''}`}>
        {visible.length === 0 ? <EmptyState title="No matching onboardings">Try a different search or status filter.</EmptyState> : visible.map((item) => {
          const value = progress(item.required_complete, item.required_total, item.progress_percent);
          return <button type="button" key={item.id} className={`onboarding-row ${selectedId === item.id ? 'row-selected' : ''}`} onClick={() => onSelect(item.id)} aria-pressed={selectedId === item.id}>
            <span className="client-avatar" aria-hidden="true">{initials(item.client_name)}</span>
            <span className="row-body">
              <span className="row-name-line"><strong>{item.client_name}</strong><ArrowRight size={15} className="row-arrow" /></span>
              <span className="row-services">{item.service_names.length ? item.service_names.join(' · ') : 'Services pending'}</span>
              <span className="row-footer"><StatusBadge status={item.substate || item.status} compact /><span>{compactDate(item.created_at)}</span></span>
              <span className="row-progress"><ProgressBar value={value} label={`${item.client_name} checklist progress`} /><span>{value}%</span></span>
            </span>
          </button>;
        })}
      </div>
      <div className="list-panel-footer">Showing {visible.length} of {totalCount ?? items.length} onboardings</div>
    </div>
  );
}

function Metrics({ items }: { items: OnboardingSummary[] }) {
  const active = items.filter((item) => item.status !== 'handed_off').length;
  const attention = items.filter((item) => isAttentionStatus(item.substate ?? item.status) || item.status === 'awaiting_approval').length;
  const completed = items.filter((item) => item.status === 'handed_off').length;
  return <div className="metrics-strip">
    <div><span className="metric-icon"><ListTodo size={20} /></span><strong>{active}</strong><span>Active onboardings</span></div>
    <div><span className="metric-icon metric-warm"><Bell size={20} /></span><strong>{attention}</strong><span>Need your attention</span></div>
    <div><span className="metric-icon metric-muted"><ShieldCheck size={20} /></span><strong>{completed}</strong><span>Handed off</span></div>
  </div>;
}

export default function OperatorApp({ session, health, healthError }: { session: AuthSession; health?: Health; healthError: Error | null }) {
  const queryClient = useQueryClient();
  const onboardings = useQuery({ queryKey: ['onboardings'], queryFn: api.onboardings });
  const [view, setView] = useState<View>('overview');
  const [selectedId, setSelectedId] = useState<string | undefined>(() => new URLSearchParams(window.location.search).get('onboarding') ?? undefined);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const logout = useMutation({ mutationFn: () => api.logout(session.csrf_token), onSuccess: () => { queryClient.clear(); window.history.replaceState({}, '', '/'); window.location.reload(); } });
  const items = onboardings.data ?? [];
  const activeId = selectedId ?? items[0]?.id;
  const selected = items.find((item) => item.id === activeId);
  const urgent = items.filter((item) => isAttentionStatus(item.substate ?? item.status) || item.status === 'awaiting_approval').length;

  function select(id: string) {
    setSelectedId(id);
    setDetailOpen(true);
    const url = new URL(window.location.href);
    url.searchParams.set('onboarding', id);
    window.history.replaceState({}, '', url.pathname + url.search);
  }

  function changeView(next: View) {
    setView(next);
    setMobileMenu(false);
    setDetailOpen(false);
  }

  return (
    <div className="workspace-shell">
      <aside className={`sidebar ${mobileMenu ? 'sidebar-open' : ''}`} aria-label="Workspace navigation">
        <div className="sidebar-header"><span className="brand-icon"><Compass size={23} strokeWidth={2.2} /></span><span>clientlaunch<span className="brand-period">.</span></span><button type="button" className="sidebar-close" aria-label="Close menu" onClick={() => setMobileMenu(false)}><X size={19} /></button></div>
        <div className="sidebar-workspace"><span className="workspace-symbol">A</span><span><strong>Agency workspace</strong><small>{health?.mode === 'DEMO' ? 'Synthetic demo dataset' : 'Client operations'}</small></span></div>
        <nav className="sidebar-nav" aria-label="Main navigation">
          <span className="nav-label">WORKSPACE</span>
          <button type="button" className={view === 'overview' ? 'nav-active' : ''} onClick={() => changeView('overview')}><LayoutDashboard size={19} /> Overview</button>
          <button type="button" className={view === 'onboardings' ? 'nav-active' : ''} onClick={() => changeView('onboardings')}><ListTodo size={19} /> Onboardings <span className="nav-count">{items.length}</span></button>
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-help"><span className="sidebar-help-icon"><Compass size={18} /></span><strong>Good work starts here.</strong><p>Every step, from approved scope to a confident handoff.</p></div>
          <div className="sidebar-user"><span className="user-avatar">{initials(session.user.name)}</span><span><strong>{session.user.name}</strong><small>{humanize(session.user.role)}</small></span><button type="button" aria-label="Sign out" title="Sign out" onClick={() => logout.mutate()} disabled={logout.isPending}><LogOut size={17} /></button></div>
          {logout.error && <p className="sidebar-error" role="alert">{logout.error.message}</p>}
        </div>
      </aside>
      {mobileMenu && <button type="button" className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobileMenu(false)} />}
      <main className="workspace-main">
        <header className="topbar"><div className="topbar-left"><button type="button" className="mobile-menu-button" aria-label="Open menu" onClick={() => setMobileMenu(true)}><Menu size={21} /></button><div className="breadcrumb">Workspace <span>/</span> <strong>{view === 'overview' ? 'Overview' : 'Onboardings'}</strong></div></div><div className="topbar-right"><span className={`connection-pill ${healthError ? 'connection-offline' : ''}`}><span />{healthError ? 'API disconnected' : health?.status === 'ok' ? 'All systems connected' : 'Checking connection'}</span><span className="topbar-divider" /><span className="topbar-avatar">{initials(session.user.name)}</span></div></header>
        <div className="workspace-content">
          {health?.mode === 'DEMO' && <div className="synthetic-banner"><ShieldCheck size={16} /><span><strong>Synthetic demo dataset</strong> · Clients, activity, and connector responses shown here are fictional or simulated.</span></div>}
          {view === 'overview' ? <>
            <div className="page-intro"><div><p className="eyebrow">YOUR WORKSPACE, AT A GLANCE</p><h1>Good morning, {session.user.name.split(' ')[0]}<span className="heading-period">.</span></h1><p>Here’s how every new project is getting started.</p></div><Button variant="secondary" onClick={() => changeView('onboardings')}>View all onboardings <ArrowRight size={16} /></Button></div>
            <div className="hero-panel"><div className="hero-copy"><span className="hero-kicker"><span /> THE HANDOFF, MADE HUMAN</span><h2>Make every first step<br />feel like the right one.</h2><p>Review plans, keep client requests moving, and catch a missed handoff before it becomes a delay.</p><button type="button" className="hero-link" onClick={() => changeView('onboardings')}>Explore your onboardings <ArrowRight size={17} /></button></div><div className="hero-art" aria-hidden="true"><div className="art-sheet art-back" /><div className="art-sheet art-front"><div className="art-top"><span /><span /><span /></div><div className="art-line long" /><div className="art-line" /><div className="art-check"><span>✓</span><i /></div><div className="art-check"><span>✓</span><i /></div><div className="art-check art-check-last"><span>·</span><i /></div></div><div className="art-spark art-spark-one">✦</div><div className="art-spark art-spark-two">✧</div></div></div>
            <Metrics items={items} />
            <div className="overview-bottom"><SectionHeading eyebrow="CURRENT WORK" title="Your onboardings" action={<button type="button" className="text-action" onClick={() => changeView('onboardings')}>See all <ArrowRight size={16} /></button>}>A clear view of each project’s next step.</SectionHeading>{urgent > 0 && <div className="attention-note"><CircleAlert size={18} /><span><strong>{urgent} onboarding{urgent === 1 ? '' : 's'} need attention.</strong> Review approvals and recovery items below.</span></div>}{onboardings.isPending ? <LoadingState label="Loading onboardings…" /> : onboardings.error ? <ErrorState message={onboardings.error.message} onRetry={() => void onboardings.refetch()} /> : items.length === 0 ? <EmptyState title="No onboardings yet">A signed won deal will appear here once the workflow receives it.</EmptyState> : <OnboardingList items={items.slice(0, 5)} selectedId={activeId} onSelect={select} totalCount={items.length} />}</div>
          </> : <>
            <div className="page-intro"><div><p className="eyebrow">CLIENT OPERATIONS</p><h1>Onboardings<span className="heading-period">.</span></h1><p>Track the work between a won deal and a ready team.</p></div><span className="page-count">{items.length} total</span></div>
            {onboardings.isPending ? <LoadingState label="Loading onboardings…" /> : onboardings.error ? <ErrorState message={onboardings.error.message} onRetry={() => void onboardings.refetch()} /> : items.length === 0 ? <EmptyState title="No onboardings yet">A signed won deal will appear here once the workflow receives it.</EmptyState> : <div className="onboardings-layout"><OnboardingList items={items} selectedId={activeId} onSelect={select} expanded /><div className={`detail-column ${detailOpen ? 'detail-open' : ''}`}>{activeId ? <DetailPanel id={activeId} session={session} onBack={() => setDetailOpen(false)} /> : <EmptyState title="Select an onboarding">Choose a client to review their plan and progress.</EmptyState>}</div></div>}
          </>}
          {view === 'overview' && selected && detailOpen && <div className="detail-modal-wrap"><button type="button" className="detail-modal-scrim" aria-label="Close details" onClick={() => setDetailOpen(false)} /><div className="detail-modal"><DetailPanel id={selected.id} session={session} onBack={() => setDetailOpen(false)} /></div></div>}
        </div>
      </main>
    </div>
  );
}
