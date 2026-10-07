import { useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowRight, CheckCircle2, ImagePlus, Mail, UploadCloud } from 'lucide-react';
import { api, ApiError, type ChecklistItem } from '../../lib/api';
import { clientRequests, fileProblem } from '../../lib/journey';
import { Button, ErrorState } from '../../components/ui';

export function readSession(key: string) { try { return sessionStorage.getItem(key); } catch { return null; } }
export function writeSession(key: string, value: string | null) {
  try { if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, value); } catch { /* Memory-only access stays available. */ }
}

export default function ClientSubmission({ token, projectId, items, requestedItem, requestVersion, intakeOpen, onChanged }: {
  token: string; projectId: string; items: ChecklistItem[]; requestedItem: string; requestVersion: number; intakeOpen: boolean; onChanged: () => void;
}) {
  const available = clientRequests(items);
  const draftKey = `clientlaunch_draft_${projectId}`;
  const [draft] = useState(() => { try { return JSON.parse(readSession(draftKey) ?? '{}') as { item?: string; answer?: string; answers?: Record<string, string> }; } catch { return {}; } });
  const [drafts, setDrafts] = useState<Record<string, string>>(draft.answers ?? (draft.item ? { [draft.item]: draft.answer ?? '' } : {}));
  const [selectedItem, setSelectedItem] = useState(draft.item ?? '');
  const [answer, setAnswer] = useState(draft.answers?.[draft.item ?? ''] ?? draft.answer ?? '');
  const [file, setFile] = useState<File | null>(null);
  const [assetItem, setAssetItem] = useState('');
  const [fileError, setFileError] = useState('');
  const [fileVersion, setFileVersion] = useState(0);
  const [answerNotice, setAnswerNotice] = useState('');
  const [uploadNotice, setUploadNotice] = useState('');
  const answerRef = useRef<HTMLTextAreaElement>(null);
  const selected = items.find(item => item.id === selectedItem);
  const selectedIsOpen = available.some(item => item.id === selectedItem);
  function chooseRequest(id: string) { setSelectedItem(id); setAnswer(drafts[id] ?? ''); setAnswerNotice(''); answerMutation.reset(); }
  useEffect(() => { if (requestedItem) { chooseRequest(requestedItem); setAssetItem(requestedItem); } }, [requestedItem, requestVersion]);
  useEffect(() => { if (requestedItem && selectedItem === requestedItem) answerRef.current?.focus(); }, [selectedItem, requestedItem, requestVersion]);
  useEffect(() => { writeSession(draftKey, selectedItem || Object.values(drafts).some(Boolean) ? JSON.stringify({ item: selectedItem, answers: drafts }) : null); }, [draftKey, selectedItem, drafts]);
  const answerMutation = useMutation({ mutationFn: () => api.clientSubmit(token, [{ checklist_item_id: selectedItem, value: answer.trim() }]), onSuccess: () => {
    setDrafts(previous => ({ ...previous, [selectedItem]: '' })); setAnswer(''); setSelectedItem(''); setAnswerNotice('Answer received. Your team will review it; progress updates when processing finishes.'); onChanged();
  } });
  const uploadMutation = useMutation({ mutationFn: () => api.clientUpload(token, file!, assetItem), onSuccess: () => {
    setFile(null); setAssetItem(''); setFileVersion(v => v + 1); setUploadNotice('File received. Your team will review it.'); onChanged();
  } });
  const canAnswer = intakeOpen && selectedIsOpen && !!answer.trim();
  return <section className="client-share-section" id="share-inputs"><div className="client-section-heading"><p className="eyebrow">YOUR NEXT STEP</p><h2>Send a little context</h2><p>Answer drafts stay in this browser tab until you send them or sign out.</p></div>
    {!intakeOpen && <p role="status" className="permission-note">Your team is reviewing this project. New answers and uploads are currently closed.</p>}
    <div className="client-share-grid"><form className="client-share-card" onSubmit={event => { event.preventDefault(); if (canAnswer && !answerMutation.isPending) answerMutation.mutate(); }}>
      <span className="share-card-icon"><Mail size={20} /></span><h3>Answer a request</h3><p>Share access through your team's secure channel. Never paste passwords here.</p>
      <label htmlFor="answer-item">Checklist request</label><select id="answer-item" value={selectedItem} onChange={event => chooseRequest(event.target.value)} required disabled={!intakeOpen || answerMutation.isPending}>
        <option value="">Choose a request</option>{available.map(item => <option key={item.id} value={item.id}>{item.title}{item.required ? ' · required' : ' · optional'}</option>)}
      </select>{selected?.description && <p className="request-instructions readable-detail">{selected.description}</p>}
      <label htmlFor="answer-text">Your answer</label><textarea ref={answerRef} id="answer-text" value={answer} onChange={event => { setAnswer(event.target.value); setDrafts(previous => ({ ...previous, [selectedItem]: event.target.value })); setAnswerNotice(''); answerMutation.reset(); }} placeholder="Share the details your project team needs…" required maxLength={10000} rows={5} disabled={!intakeOpen || answerMutation.isPending || !selectedIsOpen} aria-describedby="draft-hint" />
      <p id="draft-hint" className="help-text">{answer.length}/10,000 characters · {answer ? 'Draft retained in this tab' : 'Nothing sent yet'}</p>
      <Button type="submit" disabled={!canAnswer} loading={answerMutation.isPending}>Send answer <ArrowRight size={16} /></Button>
      {!available.length && <p className="help-text">Your inputs are received. Your team handles the next step.</p>}
      {answerMutation.error && <ErrorState title={answerMutation.error instanceof ApiError && answerMutation.error.status === 0 ? 'Answer result unconfirmed · your draft is retained' : 'Answer not sent · your draft is safe'} message={answerMutation.error.message} />}
      {answerNotice && <p className="inline-success" role="status"><CheckCircle2 size={16} />{answerNotice}</p>}
    </form><form className="client-share-card" onSubmit={event => { event.preventDefault(); if (file && assetItem && intakeOpen && !fileError && !uploadMutation.isPending) uploadMutation.mutate(); }}>
      <span className="share-card-icon share-icon-peach"><ImagePlus size={20} /></span><h3>Share a project file</h3><p>Logos, approved documents or reference material.</p>
      <label htmlFor="asset-item">Related request</label><select id="asset-item" value={assetItem} onChange={event => { setAssetItem(event.target.value); setUploadNotice(''); uploadMutation.reset(); }} required disabled={!intakeOpen || uploadMutation.isPending}><option value="">Choose a request</option>{items.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select>
      <label htmlFor="asset-file" className="upload-zone"><UploadCloud size={24} /><strong>{file ? file.name : 'Choose a file'}</strong><span>PNG, JPG or PDF · maximum 5 MB</span>
        <input key={fileVersion} id="asset-file" type="file" accept=".png,.jpg,.jpeg,.pdf,image/png,image/jpeg,application/pdf" onChange={event => {
          const chosen = event.target.files?.[0] ?? null; const problem = chosen ? fileProblem(chosen) : null;
          setFile(problem ? null : chosen); setFileError(problem ?? ''); setUploadNotice(''); uploadMutation.reset();
        }} required disabled={!intakeOpen || uploadMutation.isPending} aria-describedby="file-hint" /></label>
      <p id="file-hint" className="help-text">{file ? `${(file.size / 1024).toFixed(1)} KB · ready to upload` : 'Select Upload file to send it.'}</p>
      <Button type="submit" variant="secondary" loading={uploadMutation.isPending} disabled={!intakeOpen || !file || !assetItem || !!fileError}>Upload file <ArrowRight size={16} /></Button>
      {fileError && <ErrorState title="Choose another file" message={fileError} />}{uploadMutation.error && <ErrorState title={uploadMutation.error instanceof ApiError && uploadMutation.error.status === 0 ? 'Upload result unconfirmed · check received files before retrying' : 'File not uploaded'} message={uploadMutation.error.message} />}
      {uploadNotice && <p className="inline-success" role="status"><CheckCircle2 size={16} />{uploadNotice}</p>}
    </form></div></section>;
}
