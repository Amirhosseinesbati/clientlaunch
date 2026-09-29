import { useId, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArrowLeft, ArrowRight, CalendarDays, Check, CheckCircle2, ClipboardList, Clock3, ExternalLink, FileText, FolderOpen, Inbox, ListChecks, PauseCircle, PlayCircle, RotateCcw, Send, ShieldCheck, Sparkles, Workflow } from 'lucide-react';
import { api, type AuthSession, type ChecklistItem, type FolderStructure, type OnboardingDetail, type ProjectFolder, type ProvisioningOperation } from '../../lib/api';
import { formatDate, humanize, isAttentionStatus, isCompleteStatus, progress } from '../../lib/format';
import { Button, EmptyState, ErrorState, LoadingState, ProgressBar, StatusBadge, StepList } from '../../components/ui';

type DetailTab = 'plan' | 'checklist' | 'provisioning' | 'activity' | 'handoff';
const STAGES = ['Received', 'Planning', 'Approval', 'Provisioning', 'Client intake', 'Ready', 'Handed off'];

function stageIndex(status: string): number {
  return ({ received: 0, planning: 1, awaiting_approval: 2, provisioning: 3, waiting_for_client: 4, ready: 5, handed_off: 6 } as Record<string, number>)[status] ?? 0;
}

function PlanSection({ detail, session, id, onChanged }: { detail: OnboardingDetail; session: AuthSession; id: string; onChanged: () => void }) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  const [notice, setNotice] = useState('');
  const plan = detail.plan;
  const canAct = session.user.role !== 'viewer' && detail.onboarding.status === 'awaiting_approval' && !!plan;
  const decide = useMutation({
    mutationFn: (decision: 'approve' | 'reject') => api.decidePlan(id, session.csrf_token, plan!.id, plan!.proposal_hash, decision, decision === 'reject' ? reason.trim() : undefined),
    onSuccess: (_, decision) => { setNotice(decision === 'approve' ? 'Plan approved. Provisioning will continue in the workflow.' : 'Plan sent back for revision.'); setRejecting(false); setReason(''); onChanged(); },
  });

  if (!plan) return <EmptyState icon={<FileText size={22} />} title="Plan not drafted yet">The workflow will add a proposed plan after it processes the approved scope.</EmptyState>;
  return <div className="detail-section-stack">
    <div className="plan-summary-card"><span className="card-eyebrow"><Sparkles size={15} /> PLAN REVISION {plan.revision}</span><h3>{plan.summary || 'A tailored start for this client'}</h3><div className="plan-status-line"><StatusBadge status={plan.status} /><span>Proposal fingerprint <code>{plan.proposal_hash.slice(0, 12)}…</code></span></div></div>
    {(plan.deliverables?.length ?? 0) > 0 && <div className="detail-card"><h3><CheckCircle2 size={18} /> Agreed deliverables</h3><ul className="detail-list check-list">{plan.deliverables?.map((item, index) => <li key={`${item}-${index}`}><Check size={16} />{item}</li>)}</ul></div>}
    {(plan.missing_inputs?.length ?? 0) > 0 && <div className="detail-card"><h3><Inbox size={18} /> Inputs to request</h3><ul className="detail-list dot-list">{plan.missing_inputs?.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></div>}
    {(plan.risks?.length ?? 0) > 0 && <div className="detail-card risk-card"><h3><AlertTriangle size={18} /> Internal review notes</h3><ul className="detail-list dot-list">{plan.risks?.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul><p>Visible to agency staff only.</p></div>}
    {(plan.suggestions?.length ?? 0) > 0 && <div className="detail-card"><h3><Sparkles size={18} /> Suggestions outside approved scope</h3><p className="muted-copy">These are proposals for review, not contractual deliverables.</p><ul className="detail-list dot-list">{plan.suggestions?.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></div>}
    {plan.welcome_draft && <div className="detail-card"><h3><Send size={18} /> Welcome draft</h3><p className="draft-preview">{plan.welcome_draft}</p></div>}
    {canAct && <div className="decision-panel"><div><strong>Ready for your decision?</strong><p>Approval is tied to this exact plan revision. The workflow provisions resources only after your decision.</p></div>{rejecting ? <form onSubmit={(event) => { event.preventDefault(); if (reason.trim()) decide.mutate('reject'); }} className="reject-form"><label htmlFor="reject-reason">Reason for revision</label><textarea id="reject-reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="What should change before this plan is approved?" required /><div className="button-row"><Button type="submit" variant="danger" loading={decide.isPending}>Request revision</Button><Button type="button" variant="ghost" onClick={() => setRejecting(false)}>Cancel</Button></div></form> : <div className="button-row"><Button onClick={() => decide.mutate('approve')} loading={decide.isPending}><Check size={17} /> Approve plan</Button><Button variant="secondary" onClick={() => setRejecting(true)}>Request revision</Button></div>}</div>}
    {session.user.role === 'viewer' && detail.onboarding.status === 'awaiting_approval' && <p className="permission-note"><ShieldCheck size={16} /> Your viewer role can review the plan; an operator or admin must decide.</p>}
    {decide.error && <ErrorState title="Decision not saved" message={decide.error.message} />}
    {notice && <p className="inline-success" role="status"><CheckCircle2 size={16} />{notice}</p>}
  </div>;
}

function ChecklistRow({ item, session, id, onChanged }: { item: ChecklistItem; session: AuthSession; id: string; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [owner, setOwner] = useState(item.owner_name ?? '');
  const [due, setDue] = useState(item.due_at ? item.due_at.slice(0, 16) : '');
  const save = useMutation({ mutationFn: () => api.editChecklist(id, item.id, session.csrf_token, due ? new Date(due).toISOString() : null, owner.trim() || null), onSuccess: () => { setEditing(false); onChanged(); } });
  const overdue = item.due_at && !isCompleteStatus(item.status) && new Date(item.due_at).getTime() < Date.now();
  return <div className="checklist-item"><span className={`checklist-check ${isCompleteStatus(item.status) ? 'checklist-done' : ''}`}>{isCompleteStatus(item.status) ? <Check size={15} /> : null}</span><div><div className="checklist-item-title"><strong>{item.title}</strong>{item.required ? <span className="required-tag">Required</span> : <span className="optional-tag">Optional</span>}{overdue && <span className="overdue-tag">Overdue</span>}</div>{item.description && <p>{item.description}</p>}<div className="item-meta"><span>{humanize(item.status)}</span>{item.owner_name && <span>Owner: {item.owner_name}</span>}{item.due_at && <span><CalendarDays size={13} /> {formatDate(item.due_at)}</span>}{session.user.role !== 'viewer' && <button type="button" className="inline-edit" onClick={() => setEditing(!editing)}>{editing ? 'Cancel edit' : 'Edit owner / due date'}</button>}</div>{editing && <form className="checklist-edit" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}><label>Owner<input value={owner} onChange={(event) => setOwner(event.target.value)} placeholder="Account owner" /></label><label>Due date<input type="datetime-local" value={due} onChange={(event) => setDue(event.target.value)} /></label><Button type="submit" variant="secondary" loading={save.isPending}>Save</Button></form>}{save.error && <ErrorState title="Checklist update failed" message={save.error.message} />}</div></div>;
}

function ChecklistSection({ items, session, id, onChanged }: { items: ChecklistItem[]; session: AuthSession; id: string; onChanged: () => void }) {
  const required = items.filter((item) => item.required);
  const complete = required.filter((item) => isCompleteStatus(item.status)).length;
  const value = progress(complete, required.length);
  return <div className="detail-section-stack"><div className="checklist-progress-card"><div><span className="card-eyebrow">REQUIRED ITEMS</span><strong>{complete} of {required.length} complete</strong><p>Readiness follows the required checklist, not an estimated score.</p></div><span className="progress-number">{value}%</span><ProgressBar value={value} /></div>{items.length === 0 ? <EmptyState icon={<ListChecks size={22} />} title="No checklist items yet">Items appear after the proposed plan is reviewed.</EmptyState> : <div className="checklist-items">{items.map((item) => <ChecklistRow item={item} key={item.id} session={session} id={id} onChanged={onChanged} />)}</div>}</div>;
}

function OperationRow({ operation, id, session, connectorMode, onChanged }: { operation: ProvisioningOperation; id: string; session: AuthSession; connectorMode?: string; onChanged: () => void }) {
  const [choice, setChoice] = useState<'retry' | 'reconcile' | 'compensate'>(operation.status === 'failed' ? 'retry' : 'reconcile');
  const [externalId, setExternalId] = useState('');
  const [todoListId, setTodoListId] = useState('');
  const [confirmedAbsent, setConfirmedAbsent] = useState(false);
  const [notice, setNotice] = useState('');
  const canRecover = session.user.role !== 'viewer' && isAttentionStatus(operation.status);
  const needsListId = connectorMode === 'connected' && choice === 'reconcile' && operation.system === 'trello' && operation.action === 'create_board' && !!externalId.trim() && !confirmedAbsent;
  const recover = useMutation({ mutationFn: () => api.recover(id, session.csrf_token, operation.id, choice, choice === 'reconcile' ? externalId.trim() || undefined : undefined, choice === 'reconcile' && confirmedAbsent, needsListId ? todoListId.trim() || undefined : undefined), onSuccess: () => { setNotice('Recovery request recorded. Refreshing the operation ledger.'); onChanged(); } });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (choice === 'compensate' && !window.confirm('Request operator-controlled compensation for this operation? Completed external resources will not be deleted automatically.')) return;
    recover.mutate();
  }
  return <div className="operation-row">
    <div className="operation-main">
      <span className={`operation-symbol ${isAttentionStatus(operation.status) ? 'symbol-alert' : isCompleteStatus(operation.status) ? 'symbol-done' : ''}`}><FolderOpen size={18} /></span>
      <div><strong>{humanize(operation.system)} · {humanize(operation.action)}</strong><p>{operation.external_id ? `External ID: ${operation.external_id}` : 'No confirmed external ID yet'}{operation.attempt_count ? ` · ${operation.attempt_count} attempt${operation.attempt_count === 1 ? '' : 's'}` : ''}</p></div>
      <StatusBadge status={operation.status} compact />
    </div>
    {(operation.error || operation.error_message) && <p className="operation-error"><AlertTriangle size={15} />{operation.error || operation.error_message}</p>}
    {canRecover && <form onSubmit={submit} className="recovery-form">
      <label htmlFor={`recovery-${operation.id}`}>Recovery action</label>
      <div className="recovery-controls">
        <select id={`recovery-${operation.id}`} value={choice} onChange={(event) => setChoice(event.target.value as typeof choice)}>
          {operation.status === 'failed' && <option value="retry">Retry missing step</option>}
          <option value="reconcile">Reconcile provider outcome</option>
          <option value="compensate">Request compensation review</option>
        </select>
        {choice === 'reconcile' && <input aria-label="Confirmed external resource ID" placeholder="Confirmed external ID, if known" value={externalId} onChange={(event) => setExternalId(event.target.value)} />}
        {connectorMode === 'connected' && choice === 'reconcile' && operation.system === 'trello' && operation.action === 'create_board' && !confirmedAbsent && <input aria-label="Confirmed To Do list ID" placeholder="Confirmed To Do list ID" value={todoListId} onChange={(event) => setTodoListId(event.target.value)} required={needsListId} />}
        <Button variant="secondary" loading={recover.isPending} type="submit"><RotateCcw size={15} /> Continue</Button>
      </div>
      {choice === 'reconcile' && <label className="checkbox-label"><input type="checkbox" checked={confirmedAbsent} onChange={(event) => setConfirmedAbsent(event.target.checked)} /> Provider confirmed this resource does not exist</label>}
      <p className="help-text">Unknown outcomes need reconciliation before another external write. For a connected Trello board, confirm its To Do list ID.</p>
    </form>}
    {recover.error && <ErrorState title="Recovery request failed" message={recover.error.message} />}
    {notice && <p className="inline-success" role="status"><CheckCircle2 size={16} />{notice}</p>}
  </div>;
}

type FolderBranch = { key: string; folder: ProjectFolder; children: FolderBranch[] };

function folderBranches(folders: ProjectFolder[]): FolderBranch[] {
  const branches = folders.map((folder, index) => ({ key: folder.id ?? `${folder.service_code}:${folder.folder_key}:${index}`, folder, children: [] as FolderBranch[] }));
  const byId = new Map(branches.filter((branch) => branch.folder.id).map((branch) => [branch.folder.id, branch]));
  const byKey = new Map(branches.map((branch) => [`${branch.folder.service_code}:${branch.folder.folder_key}`, branch]));
  const roots: FolderBranch[] = [];
  for (const branch of branches) {
    const folder = branch.folder;
    const parent = (folder.parent_id ? byId.get(folder.parent_id) : undefined)
      ?? (folder.parent_folder_key && folder.parent_folder_key !== 'root'
        ? byKey.get(`${folder.service_code}:${folder.parent_folder_key}`) : undefined);
    if (parent && parent !== branch) parent.children.push(branch);
    else roots.push(branch);
  }
  return roots;
}

function trustedDriveFolderUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname === 'drive.google.com' && /\/folders\/[^/]+/.test(url.pathname) ? url.href : null;
  } catch { return null; }
}

function FolderRow({ name, status, externalId, url, label }: { name: string; status: string; externalId: string | null; url: string | null; label: string }) {
  const href = trustedDriveFolderUrl(url);
  return <div className="folder-tree-row">
    <span className="folder-tree-icon" aria-hidden="true"><FolderOpen size={17} /></span>
    <div className="folder-tree-copy"><span className="folder-tree-label">{label}</span><strong>{name}</strong>{externalId && <small>Drive ID: <code>{externalId}</code></small>}</div>
    <div className="folder-tree-actions"><StatusBadge status={status} compact />{href && <a href={href} target="_blank" rel="noopener noreferrer" aria-label={`Open ${name} in Google Drive`}>Open <ExternalLink size={13} aria-hidden="true" /></a>}</div>
  </div>;
}

function FolderBranchItem({ branch }: { branch: FolderBranch }) {
  return <li key={branch.key}>
    <FolderRow name={branch.folder.name} status={branch.folder.status} externalId={branch.folder.external_id} url={branch.folder.url} label={branch.folder.folder_key === 'service' ? 'Service folder' : 'Folder'} />
    {branch.children.length > 0 && <ul>{branch.children.map((child) => <FolderBranchItem key={child.key} branch={child} />)}</ul>}
  </li>;
}

function FolderStructureCard({ structure }: { structure?: FolderStructure }) {
  const headingId = useId();
  if (!structure) return null;
  return <section className="detail-card folder-structure-card" aria-labelledby={headingId}>
    <div className="folder-structure-heading"><div><h3 id={headingId}><FolderOpen size={18} /> Drive folder structure</h3><p>{structure.complete ? 'All planned folders are confirmed.' : 'Planned folders remain visible while provisioning continues.'}</p></div><strong>{structure.complete_count} / {structure.planned_count}<span> subfolders confirmed</span></strong></div>
    {structure.planned_count > 0 && <ProgressBar value={progress(structure.complete_count, structure.planned_count)} label="Folder provisioning progress" />}
    <div className="folder-tree-root"><FolderRow name={structure.root.name} status={structure.root.status} externalId={structure.root.external_id} url={structure.root.url} label="Project root" /></div>
    {structure.folders.length > 0 ? <ul className="folder-tree" aria-label="Service and child folders">{folderBranches(structure.folders).map((branch) => <FolderBranchItem key={branch.key} branch={branch} />)}</ul> : <p className="muted-copy folder-empty">No service subfolders are planned yet.</p>}
  </section>;
}

function ProvisioningSection({ detail, session, id, onChanged }: { detail: OnboardingDetail; session: AuthSession; id: string; onChanged: () => void }) {
  return <div className="detail-section-stack">
    <div className="section-intro"><h3>Provisioning ledger</h3><p>Confirmed folders and boards stay attached to this onboarding. Uncertain results require a review before retry.</p></div>
    {detail.operations.length === 0 ? <EmptyState icon={<Workflow size={22} />} title="No operations yet">Folder and board provisioning begins after the plan is approved.</EmptyState> : <div className="operation-list">{detail.operations.map((operation) => <OperationRow key={operation.id} operation={operation} id={id} session={session} connectorMode={detail.onboarding.connector_mode} onChanged={onChanged} />)}</div>}
    <FolderStructureCard structure={detail.folder_structure} />
    <div className="detail-card"><h3><FolderOpen size={18} /> Created resources</h3>{detail.resources.length === 0 ? <p className="muted-copy">No external resources confirmed yet.</p> : <div className="resource-list">{detail.resources.map((resource) => <div key={resource.id}><span className="resource-icon"><FolderOpen size={17} /></span><div><strong>{resource.name || humanize(resource.resource_type || resource.system)}</strong><p>{humanize(resource.system)} · {resource.external_id}</p></div><CheckCircle2 size={18} className="resource-confirmed" /></div>)}</div>}</div>
  </div>;
}

function ReminderReview({ detail, session, onChanged }: { detail: OnboardingDetail; session: AuthSession; onChanged: () => void }) {
  const reminders = detail.reminders ?? [];
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  async function decide(id: string, decision: 'approve' | 'reject') {
    setPendingId(id); setError(''); setNotice('');
    try { await api.decideReminder(id, session.csrf_token, decision); setNotice(`Reminder ${decision === 'approve' ? 'approved for workflow dispatch' : 'rejected'}.`); onChanged(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not save the reminder decision.'); }
    finally { setPendingId(null); }
  }
  return <div className="detail-card"><h3><Clock3 size={18} /> Reminder review</h3>{reminders.length === 0 ? <p className="muted-copy">No reminders have been drafted for this client.</p> : <div className="reminder-list">{reminders.map((reminder) => { const related = detail.checklist.find((item) => item.id === reminder.checklist_item_id); return <div key={reminder.id} className="reminder-row"><div><strong>{related?.title ?? 'Checklist reminder'}</strong><p>Due {formatDate(reminder.due_at)} · Drafted {formatDate(reminder.created_at)}</p></div><StatusBadge status={reminder.status} compact />{reminder.status === 'drafted' && session.user.role !== 'viewer' && <div className="button-row"><Button variant="secondary" disabled={!!pendingId} onClick={() => void decide(reminder.id, 'approve')}>Approve</Button><Button variant="ghost" disabled={!!pendingId} onClick={() => void decide(reminder.id, 'reject')}>Reject</Button></div>}</div>; })}</div>}{error && <ErrorState title="Reminder decision failed" message={error} />}{notice && <p className="inline-success" role="status"><CheckCircle2 size={16} />{notice}</p>}</div>;
}

function ActivitySection({ detail, session, onChanged }: { detail: OnboardingDetail; session: AuthSession; onChanged: () => void }) {
  const events = [...detail.events].sort((a, b) => new Date(b.occurred_at ?? b.created_at ?? 0).getTime() - new Date(a.occurred_at ?? a.created_at ?? 0).getTime());
  return <div className="detail-section-stack"><div className="section-intro"><h3>Observed activity</h3><p>Events and recorded connector results from this onboarding.</p></div><ReminderReview detail={detail} session={session} onChanged={onChanged} />{events.length === 0 ? <EmptyState icon={<Clock3 size={22} />} title="No activity recorded">The timeline fills as the workflow processes this onboarding.</EmptyState> : <ol className="activity-timeline">{events.map((event) => <li key={event.id}><span className="timeline-marker" /><div><span className="timeline-date">{formatDate(event.occurred_at ?? event.created_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span><strong>{event.message || event.title || humanize(event.kind || event.event_type || event.type)}</strong>{(event.description || event.detail) && <p>{event.description || event.detail}</p>}{event.actor && <small>By {event.actor}</small>}</div></li>)}</ol>}{detail.welcome.length > 0 && <div className="detail-card"><h3><Send size={18} /> Welcome outbox</h3>{detail.welcome.map((entry) => <div className="welcome-entry" key={entry.id}><div><strong>{entry.subject || 'Welcome message'}</strong><StatusBadge status={entry.status || 'drafted'} compact /></div><p>To {entry.recipient || 'configured recipient'} · {formatDate(entry.sent_at || entry.created_at)}</p>{entry.body && <details><summary>View recorded message</summary><pre>{entry.body}</pre></details>}</div>)}</div>}</div>;
}

function HandoffRecordCard({ detail }: { detail: OnboardingDetail }) {
  const record = detail.handoff;
  if (!record) return null;
  const sourceSubmissions = detail.submissions.filter((item) => record.evidence.submission_ids.includes(item.id));
  const sourceAssets = detail.assets.filter((item) => record.evidence.asset_ids.includes(item.id));
  const sourceResources = detail.resources.filter((item) => record.evidence.resource_ids.includes(item.id));
  return <section className="detail-card" aria-label="Recorded handoff">
    <h3><ShieldCheck size={18} /> Recorded delivery handoff</h3>
    <p className="draft-preview">{record.summary}</p>
    <p className="muted-copy">Recorded {formatDate(record.created_at)} · Evidence from this onboarding</p>
    <h4>Client answers</h4>
    <ul className="detail-list dot-list">{sourceSubmissions.flatMap((submission) => (submission.answers ?? []).map((answer) => (
      <li key={`${submission.id}:${answer.checklist_item_id}`}><strong>{detail.checklist.find((item) => item.id === answer.checklist_item_id)?.title ?? 'Checklist answer'}:</strong> {answer.value}</li>
    )))}</ul>
    <h4>Shared files</h4>
    {sourceAssets.length ? <ul className="asset-list">{sourceAssets.map((asset) => <li key={asset.id}><FileText size={15} /> <a href={`/api/assets/${encodeURIComponent(asset.id)}`} target="_blank" rel="noopener noreferrer">{asset.filename || 'Download file'}</a></li>)}</ul> : <p className="muted-copy">No files were included.</p>}
    <h4>Confirmed resources</h4>
    <ul className="detail-list dot-list">{sourceResources.map((resource) => <li key={resource.id}>{humanize(resource.system)} · <code>{resource.external_id}</code></li>)}</ul>
  </section>;
}

function HandoffSection({ detail, session, id, onChanged }: { detail: OnboardingDetail; session: AuthSession; id: string; onChanged: () => void }) {
  const [summary, setSummary] = useState('');
  const [notice, setNotice] = useState('');
  const ready = detail.onboarding.status === 'ready';
  const canSubmit = ready && session.user.role !== 'viewer';
  const handoff = useMutation({ mutationFn: () => api.handoff(id, session.csrf_token, summary.trim()), onSuccess: () => { setNotice('Delivery handoff recorded.'); setSummary(''); onChanged(); } });
  return <div className="detail-section-stack">
    <div className="handoff-panel">
      <span className="handoff-icon"><ShieldCheck size={25} /></span>
      <h3>{detail.onboarding.status === 'handed_off' ? 'Handoff complete' : ready ? 'Ready for delivery' : 'Preparing for handoff'}</h3>
      <p>{ready ? 'The required client checklist is complete. Add a factual summary that links the delivery team to recorded answers and assets.' : detail.onboarding.status === 'handed_off' ? 'This onboarding has been passed to the delivery team.' : 'The required client checklist must be complete before the delivery handoff can be recorded.'}</p>
    </div>
    <HandoffRecordCard detail={detail} />
    <div className="detail-card">
      <h3><Inbox size={18} /> Intake evidence</h3>
      <div className="evidence-metrics">
        <div><strong>{detail.submissions.length}</strong><span>Submissions</span></div>
        <div><strong>{detail.assets.length}</strong><span>Assets</span></div>
        <div><strong>{detail.checklist.filter((item) => item.required && isCompleteStatus(item.status)).length}/{detail.checklist.filter((item) => item.required).length}</strong><span>Required complete</span></div>
      </div>
      {detail.assets.length > 0 && <ul className="asset-list">{detail.assets.map((asset) => <li key={asset.id}><FileText size={15} /> {asset.filename || asset.file_name || asset.name || 'Uploaded asset'}</li>)}</ul>}
    </div>
    {canSubmit && <form className="handoff-form" onSubmit={(event) => { event.preventDefault(); if (summary.trim()) handoff.mutate(); }}>
      <label htmlFor="handoff-summary">Delivery handoff summary</label>
      <textarea id="handoff-summary" value={summary} onChange={(event) => setSummary(event.target.value)} placeholder="Summarize the approved scope, completed intake, key assets, and remaining delivery context…" required minLength={20} />
      <p className="help-text">Keep this factual. Refer to answers and assets already recorded for this client.</p>
      <Button type="submit" loading={handoff.isPending}>Record handoff <ArrowRight size={16} /></Button>
    </form>}
    {session.user.role === 'viewer' && ready && <p className="permission-note"><ShieldCheck size={16} /> An operator or admin must record the handoff.</p>}
    {handoff.error && <ErrorState title="Handoff not recorded" message={handoff.error.message} />}
    {notice && <p className="inline-success" role="status"><CheckCircle2 size={16} />{notice}</p>}
  </div>;
}

export default function DetailPanel({ id, session, onBack }: { id: string; session: AuthSession; onBack: () => void }) {
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: ['onboarding', id], queryFn: () => api.detail(id) });
  const [tab, setTab] = useState<DetailTab>('plan');
  const [pausing, setPausing] = useState(false);
  const [pauseReason, setPauseReason] = useState('');
  const stateChange = useMutation({ mutationFn: (action: 'pause' | 'resume') => api.changeState(id, session.csrf_token, action, action === 'pause' ? pauseReason.trim() || undefined : undefined), onSuccess: () => { setPausing(false); setPauseReason(''); refresh(); } });
  const data = detail.data;
  const tabs: { id: DetailTab; label: string; icon: typeof FileText; count?: number }[] = [
    { id: 'plan', label: 'Plan', icon: FileText },
    { id: 'checklist', label: 'Checklist', icon: ClipboardList, count: data?.checklist.length },
    { id: 'provisioning', label: 'Resources', icon: FolderOpen, count: data?.operations.length },
    { id: 'activity', label: 'Activity', icon: Clock3 },
    { id: 'handoff', label: 'Handoff', icon: ShieldCheck },
  ];
  function refresh() { void queryClient.invalidateQueries({ queryKey: ['onboarding', id] }); void queryClient.invalidateQueries({ queryKey: ['onboardings'] }); }

  if (detail.isPending) return <div className="detail-panel"><LoadingState label="Loading client details…" /></div>;
  if (detail.error || !data) return <div className="detail-panel"><ErrorState message={detail.error?.message ?? 'This onboarding could not be found.'} onRetry={() => void detail.refetch()} /></div>;
  const item = data.onboarding;
  const value = progress(item.required_complete, item.required_total, item.progress_percent);
  return <div className="detail-panel"><button type="button" className="detail-back" onClick={onBack}><ArrowLeft size={16} /> Back to list</button><div className="detail-header"><div className="detail-header-top"><span className="eyebrow">CLIENT ONBOARDING</span><StatusBadge status={item.substate || item.status} /></div><h2>{item.project_name || item.client_name}</h2><p>{item.client_name} · {item.service_names.join(' · ') || 'Services pending'}{item.owner_name ? ` · Owned by ${item.owner_name}` : ''}</p><div className="detail-meta"><span><CalendarDays size={15} /> Started {formatDate(item.created_at)}</span>{item.target_date && <span>Target {formatDate(item.target_date)}</span>}</div>{session.user.role !== 'viewer' && item.status !== 'handed_off' && <div className="lifecycle-controls">{item.status === 'paused' ? <Button variant="secondary" loading={stateChange.isPending} onClick={() => stateChange.mutate('resume')}><PlayCircle size={16} /> Resume onboarding</Button> : <Button variant="ghost" onClick={() => setPausing(!pausing)}><PauseCircle size={16} /> Pause onboarding</Button>}{pausing && <form onSubmit={(event) => { event.preventDefault(); stateChange.mutate('pause'); }}><label htmlFor="pause-reason">Reason for pause (optional)</label><input id="pause-reason" value={pauseReason} onChange={(event) => setPauseReason(event.target.value)} placeholder="Reason visible in activity timeline" /><Button type="submit" loading={stateChange.isPending}>Confirm pause</Button></form>}{stateChange.error && <ErrorState title="Status not changed" message={stateChange.error.message} />}</div>}</div><div className="detail-progress"><div><span>Overall readiness</span><strong>{item.required_complete ?? 0}/{item.required_total ?? data.checklist.filter((i) => i.required).length} required items</strong></div><span className="detail-progress-number">{value}%</span><ProgressBar value={value} /></div><div className="detail-stage"><StepList steps={STAGES} activeIndex={stageIndex(item.status)} /></div><div className="detail-tabs" role="tablist" aria-label="Onboarding details">{tabs.map(({ id: tabId, label, icon: Icon, count }) => <button type="button" key={tabId} role="tab" aria-selected={tab === tabId} className={tab === tabId ? 'tab-active' : ''} onClick={() => setTab(tabId)}><Icon size={16} />{label}{count !== undefined && <span>{count}</span>}</button>)}</div><div className="detail-content" role="tabpanel">{tab === 'plan' && <PlanSection detail={data} session={session} id={id} onChanged={refresh} />}{tab === 'checklist' && <ChecklistSection items={data.checklist} session={session} id={id} onChanged={refresh} />}{tab === 'provisioning' && <ProvisioningSection detail={data} session={session} id={id} onChanged={refresh} />}{tab === 'activity' && <ActivitySection detail={data} session={session} onChanged={refresh} />}{tab === 'handoff' && <HandoffSection detail={data} session={session} id={id} onChanged={refresh} />}</div></div>;
}
