import { useState } from 'react';
import { Copy, ExternalLink, Mail, ShieldCheck } from 'lucide-react';
import { Button } from '../../components/ui';
import type { OnboardingDetail } from '../../lib/api';
import { formatDate, humanize } from '../../lib/format';

export default function InvitationCard({ detail, canView }: { detail: OnboardingDetail; canView: boolean }) {
  const [notice, setNotice] = useState('');
  const item = detail.onboarding;
  const welcome = detail.welcome[detail.welcome.length - 1];
  async function copy() {
    try { await navigator.clipboard.writeText(item.portal_link!); setNotice('Private link copied. Share it only with the verified client.'); }
    catch { setNotice('Copy is unavailable here. Select the private link below and copy it manually.'); }
  }
  return <section className="detail-card invitation-card">
    <p className="eyebrow">CLIENT ACCESS</p><h3><Mail size={20} /> A clear welcome, a private link</h3>
    <p>The invitation opens this client's checklist. A link alone does not confirm that a welcome message was delivered.</p>
    <dl className="invite-facts"><div><dt>Client contact</dt><dd>{item.client_email || 'Contact not available'}</dd></div>
      <div><dt>Access</dt><dd>{item.invite_status === 'active' ? `Active · expires ${formatDate(item.invite_expires_at)}` : item.invite_status === 'expired' ? 'Expired · request a renewed invite from the operator workflow' : 'Awaiting approved plan and resource setup'}</dd></div>
      <div><dt>Welcome delivery</dt><dd>{welcome?.status === 'simulated_sent' ? 'Simulated only · no email sent' : welcome ? humanize(welcome.status) : 'No delivery recorded'}</dd></div></dl>
    {canView && item.portal_link ? <><label htmlFor="invite-link">Private client link</label><input id="invite-link" readOnly value={item.portal_link} onFocus={event => event.currentTarget.select()} />
      <div className="button-row"><Button variant="secondary" onClick={() => void copy()}><Copy size={16} /> Copy private link</Button><a className="btn btn-secondary" href={item.portal_link} target="_blank" rel="noreferrer"><ExternalLink size={16} /> Preview client portal</a></div>
      <p className="help-text">Preview opens the client view. Copying a link does not send an invitation.</p></> : <p className="permission-note"><ShieldCheck size={16} />{canView ? 'A private link appears after the workflow creates a valid invite.' : 'An operator can review the private invitation.'}</p>}
    {notice && <p role="status" className="inline-success">{notice}</p>}
  </section>;
}
