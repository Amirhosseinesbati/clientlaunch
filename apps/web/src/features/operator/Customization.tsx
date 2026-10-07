import { useState, type CSSProperties, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, CheckCircle2, FolderOpen, Palette, Plus, Save, Trash2 } from 'lucide-react';
import { api, ApiError, type AuthSession, type BrandSettings, type ServiceTemplate } from '../../lib/api';
import { brandStyle } from '../../lib/journey';
import { Button, EmptyState, ErrorState, LoadingState } from '../../components/ui';

function BrandEditor({ initial, session }: { initial: BrandSettings; session: AuthSession }) {
  const cache = useQueryClient();
  const [draft, setDraft] = useState(initial);
  const [notice, setNotice] = useState('');
  const writable = session.user.role !== 'viewer';
  const changed = JSON.stringify(initial) !== JSON.stringify(draft);
  const save = useMutation({ mutationFn: () => api.saveBrand(draft, session.csrf_token), onSuccess: data => {
    cache.setQueryData(['brand'], data); setDraft(data); setNotice('Brand settings saved. Clients see them on their next project load.');
  } });
  function field<K extends keyof BrandSettings>(key: K, value: BrandSettings[K]) { setDraft({ ...draft, [key]: value }); setNotice(''); save.reset(); }
  return <div className="customization-grid"><form className="settings-card" onSubmit={(event: FormEvent) => { event.preventDefault(); save.mutate(); }}>
    <div className="settings-card-title"><Palette size={20} /><div><h2>Make the welcome yours</h2><p>Workspace branding appears only in your clients' portal.</p></div></div>
    <fieldset disabled={!writable || save.isPending}><label htmlFor="agency-name">Agency name</label><input id="agency-name" value={draft.agency_name} onChange={e => field('agency_name', e.target.value)} required maxLength={160} />
      <label htmlFor="brand-accent">Brand accent</label><div className="color-field"><input type="color" id="brand-accent" value={draft.accent} onChange={e => field('accent', e.target.value)} /><code>{draft.accent}</code><span>Text contrast adapts automatically</span></div>
      <label htmlFor="welcome-heading">Welcome heading</label><input id="welcome-heading" value={draft.welcome_heading} onChange={e => field('welcome_heading', e.target.value)} required maxLength={160} />
      <label htmlFor="welcome-message">Welcome message</label><textarea id="welcome-message" value={draft.welcome_message} onChange={e => field('welcome_message', e.target.value)} required maxLength={3000} rows={4} />
      <label htmlFor="support-email">Project support email <span>(optional)</span></label><input id="support-email" type="email" value={draft.support_email ?? ''} onChange={e => field('support_email', e.target.value || null)} placeholder="projects@your-agency.example" />
    </fieldset>
    {save.error && <ErrorState title={save.error instanceof ApiError && save.error.status === 0 ? 'Save result unconfirmed · check latest settings before retrying' : 'Settings not saved'} message={save.error.message} />}
    {notice && <p role="status" className="inline-success"><CheckCircle2 size={16} />{notice}</p>}
    <div className="settings-save"><span>{changed ? 'Unsaved changes' : `Saved version ${initial.version}`}</span><Button type="submit" loading={save.isPending} disabled={!writable || !changed}><Save size={16} /> Save brand</Button></div>
  </form><aside className="brand-preview" style={brandStyle(draft.accent) as CSSProperties} aria-label="Client welcome preview"><p className="eyebrow">LIVE PREVIEW · UNSAVED EDITS</p><div className="preview-browser"><i /><i /><i /><span>Private project space</span></div><div className="preview-content"><strong>{draft.agency_name || 'Your agency'}</strong><div className="preview-welcome"><span>WELCOME, WILLOW HARBOR</span><h2>{draft.welcome_heading}</h2><p>{draft.welcome_message}</p></div><div className="preview-request"><CheckCircle2 size={21} /><div><strong>A clear first step</strong><p>Share your project goals with the team.</p></div><ArrowRight size={18} /></div><span className="preview-primary">Send answer <ArrowRight size={14} /></span><p className="help-text">Primary action preview</p>{draft.support_email && <p className="help-text">Questions? {draft.support_email}</p>}</div><p className="help-text">Preview content is fictional. Nothing is sent from this page.</p></aside></div>;
}

function TemplateEditor({ initial, session }: { initial: ServiceTemplate; session: AuthSession }) {
  const cache = useQueryClient();
  const [draft, setDraft] = useState(initial);
  const [folders, setFolders] = useState(initial.folder_blueprint.join('\n'));
  const [notice, setNotice] = useState('');
  const writable = session.user.role !== 'viewer';
  const save = useMutation({ mutationFn: () => api.saveTemplate({ ...draft, folder_blueprint: folders.split('\n').map(s => s.trim()).filter(Boolean) }, session.csrf_token), onSuccess: data => {
    cache.setQueryData<ServiceTemplate[]>(['templates'], old => old?.map(t => t.service_code === data.service_code ? data : t));
    setDraft(data);
    setNotice('A new template version was saved. Existing plans and checklists keep their approved content.');
  } });
  const changed = JSON.stringify(initial) !== JSON.stringify(draft) || folders !== initial.folder_blueprint.join('\n');
  function updateItem(index: number, patch: Partial<ServiceTemplate['checklist'][number]>) {
    setDraft({ ...draft, checklist: draft.checklist.map((item, i) => i === index ? { ...item, ...patch } : item) }); save.reset();
  }
  function addItem() {
    let counter = draft.checklist.length + 1;
    while (draft.checklist.some(item => item.key === `request_${counter}`)) counter++;
    setDraft({ ...draft, checklist: [...draft.checklist, { key: `request_${counter}`, title: '', description: '', required: true }] });
  }
  return <form className="settings-card template-editor" onSubmit={event => { event.preventDefault(); save.mutate(); }}>
    <div className="settings-card-title"><FolderOpen size={20} /><div><h2>{initial.name}</h2><p>Version {initial.version} · {initial.service_code} · Save creates the next version for future drafts.</p></div></div>
    <fieldset disabled={!writable || save.isPending}><div className="settings-two-fields"><div><label htmlFor="template-name">Service name</label><input id="template-name" value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} required maxLength={160} /></div><div><label htmlFor="template-description">Service description</label><input id="template-description" value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} maxLength={3000} /></div></div>
      <div className="template-section-heading"><div><h3>Client requests</h3><p>Use specific instructions. Never ask clients to paste passwords.</p></div><Button type="button" variant="secondary" onClick={addItem} disabled={draft.checklist.length >= 40}><Plus size={16} /> Add request</Button></div>
      <div className="template-request-list">{draft.checklist.map((item, index) => <div className="template-request" key={item.key}>
        <span className="request-number">{String(index + 1).padStart(2, '0')}</span><div><label htmlFor={`title-${item.key}`}>Request title</label><input id={`title-${item.key}`} value={item.title} onChange={e => updateItem(index, { title: e.target.value })} required maxLength={240} />
          <label htmlFor={`description-${item.key}`}>Instructions <span>(optional)</span></label><textarea id={`description-${item.key}`} value={item.description ?? ''} onChange={e => updateItem(index, { description: e.target.value })} rows={2} maxLength={3000} /><label className="checkbox-label"><input type="checkbox" checked={item.required} onChange={e => updateItem(index, { required: e.target.checked })} /> Required before handoff</label></div>
        <Button type="button" variant="ghost" aria-label={`Remove request ${index + 1}`} disabled={draft.checklist.length <= 1} onClick={() => setDraft({ ...draft, checklist: draft.checklist.filter((_, i) => i !== index) })}><Trash2 size={17} /></Button>
      </div>)}</div>
      <div className="settings-two-fields folder-editor"><div><label htmlFor="template-folders">Project folders · one name per line</label><textarea id="template-folders" value={folders} onChange={e => setFolders(e.target.value)} rows={6} required /><p className="help-text">Up to 30 unique names. Slashes are not allowed. Existing folder trees stay as approved.</p></div><aside><h3>Folder preview</h3><ul>{folders.split('\n').filter(s => s.trim()).map((folder, i) => <li key={i}><FolderOpen size={15} />{folder}</li>)}</ul><p className="help-text">The workflow provisions folders after a plan is reviewed.</p></aside></div>
    </fieldset>
    {save.error && <ErrorState title={save.error instanceof ApiError && save.error.status === 0 ? 'Save result unconfirmed · check latest template before retrying' : 'Template not saved'} message={save.error.message} />}
    {notice && <p role="status" className="inline-success"><CheckCircle2 size={16} />{notice}</p>}
    <div className="settings-save"><span>{changed ? 'Unsaved changes' : `Version ${initial.version} saved`}</span><Button type="submit" loading={save.isPending} disabled={!writable || !changed}><Save size={16} /> Save new version</Button></div>
  </form>;
}

export default function Customization({ session }: { session: AuthSession }) {
  const brand = useQuery({ queryKey: ['brand'], queryFn: api.brand });
  const templates = useQuery({ queryKey: ['templates'], queryFn: api.templates });
  const [section, setSection] = useState<'brand' | 'templates'>('brand');
  const [selected, setSelected] = useState('');
  const current = templates.data?.find(t => t.service_code === selected) ?? templates.data?.[0];
  return <><div className="page-intro"><div><p className="eyebrow">BUILT FOR YOUR WAY OF WORKING</p><h1>Templates & brand<span className="heading-period">.</span></h1><p>A repeatable beginning, with room for every client's needs.</p></div><span className="page-count">{session.user.role === 'viewer' ? 'View only' : 'Workspace settings'}</span></div>
    <div className="settings-switch" aria-label="Customization sections"><button type="button" aria-pressed={section === 'brand'} onClick={() => setSection('brand')}>Portal brand</button><button type="button" aria-pressed={section === 'templates'} onClick={() => setSection('templates')}>Service templates <span>{templates.data?.length ?? 0}</span></button></div>
    {section === 'brand' ? brand.isPending ? <LoadingState /> : brand.error ? <ErrorState message={brand.error.message} onRetry={() => void brand.refetch()} /> : brand.data && <BrandEditor initial={brand.data} session={session} /> : <>
      <div className="template-selector"><label htmlFor="service-template">Service template</label><select id="service-template" value={current?.service_code ?? ''} onChange={e => setSelected(e.target.value)}>{templates.data?.map(t => <option key={t.service_code} value={t.service_code}>{t.name} · v{t.version}</option>)}</select><span>Changes apply to future plan drafts.</span></div>
      {templates.isPending ? <LoadingState /> : templates.error ? <ErrorState message={templates.error.message} onRetry={() => void templates.refetch()} /> : current ? <TemplateEditor key={current.service_code} initial={current} session={session} /> : <EmptyState title="No service templates">Configure a service before accepting a won deal.</EmptyState>}
    </>}
  </>;
}
