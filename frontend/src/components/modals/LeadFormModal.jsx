import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Modal } from './Modal';
import { leadApi } from '../../services/leadApi';
import { parseError } from '../../services/api';
import { useToast } from '../../hooks/useToast';
import { useSalesPeople } from '../../hooks/useLeads';
import { useSettings } from '../../hooks/useAnalytics';
import { invalidateCache } from '../../hooks/useAsync';

const EMPTY = { name: '', email: '', phone: '', company: '', lead_source: '', interested_product: '', notes: '', sales_person_id: '' };
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateLead(f) {
  const e = {};
  if (!f.name || f.name.trim().length < 2) e.name = 'Name is required';
  if (!f.email) e.email = 'Email is required';
  else if (!EMAIL_RE.test(f.email.trim())) e.email = 'Enter a valid email address';
  const digits = (f.phone || '').replace(/\D/g, '');
  if (!f.phone) e.phone = 'Phone is required';
  else if (digits.length < 10 || digits.length > 15) e.phone = 'Enter a valid phone number, e.g. +91 98765 43210';
  if (!f.sales_person_id) e.sales_person_id = 'Assign this lead to a sales person';
  return e;
}

export function LeadFormModal({ open, onClose, lead, onSaved }) {
  const toast = useToast();
  const { data: salesPeople } = useSalesPeople();
  const { data: settings } = useSettings();
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [serverError, setServerError] = useState(null);

  useEffect(() => {
    if (!open) return;
    setErrors({});
    setServerError(null);
    setForm(lead ? {
      name: lead.name || '', email: lead.email || '', phone: lead.phone || '', company: lead.company || '',
      lead_source: lead.lead_source || '', interested_product: lead.interested_product || '', notes: lead.notes || '',
      sales_person_id: lead.sales_person?.id || '',
    } : EMPTY);
  }, [open, lead]);

  const set = (k) => (e) => {
    setForm((f) => ({ ...f, [k]: e.target.value }));
    setErrors((er) => ({ ...er, [k]: undefined }));
  };

  const submit = async (e) => {
    e.preventDefault();
    const v = validateLead(form);
    setErrors(v);
    if (Object.keys(v).length) return;
    setSaving(true);
    setServerError(null);
    const body = Object.fromEntries(Object.entries(form).map(([k, val]) => [k, typeof val === 'string' ? val.trim() || null : val]));
    try {
      const saved = lead ? await leadApi.update(lead.id, body) : await leadApi.create(body);
      invalidateCache('leads');
      invalidateCache(`lead:${saved.id}`);
      invalidateCache('dash');
      toast.success(lead ? 'Lead updated' : 'Lead created', saved.name);
      onSaved?.(saved);
      onClose();
    } catch (err) {
      const p = parseError(err, 'Could not save lead');
      setErrors(p.fields || {});
      setServerError(p);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} busy={saving} title={lead ? 'Edit Lead' : 'Add Lead'} width={620}
           footer={<>
             <button className="btn" onClick={onClose} disabled={saving}>Cancel</button>
             <button className="btn btn-primary" type="submit" form="lead-form" disabled={saving}>
               {saving && <Loader2 className="spin" />} {lead ? 'Save changes' : 'Create lead'}
             </button>
           </>}>
      <form id="lead-form" onSubmit={submit} noValidate className="form-grid">
        {[
          ['name', 'Name', 'text', 'Rahul Kumar', true],
          ['email', 'Email', 'email', 'rahul@example.com', true],
          ['phone', 'Phone', 'tel', '+91 98765 43210', true],
          ['company', 'Company', 'text', 'Company or college', false],
        ].map(([k, label, type, ph, req]) => (
          <div className="field" key={k}>
            <label htmlFor={`lf-${k}`}>{label}{req && <span aria-hidden="true" style={{ color: 'var(--accent)' }}> *</span>}</label>
            <input id={`lf-${k}`} type={type} className={`input ${errors[k] ? 'invalid' : ''}`} value={form[k]} onChange={set(k)} placeholder={ph}
                   aria-invalid={Boolean(errors[k])} required={req} />
            {errors[k] && <span className="error-text">{errors[k]}</span>}
          </div>
        ))}
        <div className="field">
          <label htmlFor="lf-source">Lead Source</label>
          <select id="lf-source" className="select" value={form.lead_source} onChange={set('lead_source')}>
            <option value="">Select source</option>
            {(settings?.lead_sources || []).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="lf-product">Interested Product</label>
          <input id="lf-product" className="input" list="lf-products" value={form.interested_product} onChange={set('interested_product')} placeholder="e.g. Full Stack Development" />
          <datalist id="lf-products">{(settings?.products || []).map((p) => <option key={p} value={p} />)}</datalist>
        </div>
        <div className="field full">
          <label htmlFor="lf-sp">Assigned Sales Person{<span aria-hidden="true" style={{ color: 'var(--accent)' }}> *</span>}</label>
          <select id="lf-sp" className={`select ${errors.sales_person_id ? 'invalid' : ''}`} value={form.sales_person_id} onChange={set('sales_person_id')} required>
            <option value="">Select a sales person</option>
            {(salesPeople || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          {errors.sales_person_id && <span className="error-text">{errors.sales_person_id}</span>}
        </div>
        <div className="field full">
          <label htmlFor="lf-notes">Notes</label>
          <textarea id="lf-notes" className="textarea" value={form.notes} onChange={set('notes')} maxLength={4000} />
        </div>
        {serverError && serverError.code !== 'duplicate_lead' && !Object.keys(serverError.fields || {}).length && (
          <div className="notice error full" role="alert">{serverError.message}{serverError.reason ? ` — ${serverError.reason}` : ''}</div>
        )}
        {serverError?.code === 'duplicate_lead' && (
          <div className="notice warning full">{serverError.message}. {serverError.reason}</div>
        )}
      </form>
    </Modal>
  );
}
