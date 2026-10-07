import { MessageSquareText } from 'lucide-react';
import type { ChecklistItem, Submission } from '../../lib/api';
import { formatDate } from '../../lib/format';

export default function ReceivedInputs({ submissions, items }: { submissions: Submission[]; items: ChecklistItem[] }) {
  return <section className="client-received-inputs"><div className="client-section-heading"><p className="eyebrow">YOUR RECEIPTS</p><h2>Answers saved to this project</h2><p>Check this record before resending after a connection issue. Checklist progress may update after workflow processing.</p></div>
    {!submissions.length ? <p className="muted-copy">No answers received yet. Your browser drafts are not submissions.</p> : <div className="received-list">{[...submissions].reverse().slice(0, 5).map(submission => <details key={submission.id} className="scope-disclosure"><summary><MessageSquareText size={16} /> Saved answer · {formatDate(submission.created_at ?? submission.submitted_at)}</summary>{submission.answers?.map((answer, i) => <div key={`${answer.checklist_item_id}-${i}`}><h3>{items.find(item => item.id === answer.checklist_item_id)?.title ?? 'Project request'}</h3><p className="readable-detail">{answer.value}</p></div>)}</details>)}</div>}
  </section>;
}
