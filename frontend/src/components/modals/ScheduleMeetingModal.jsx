import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, CalendarClock, Check, CheckCircle2, Copy, Loader2, Mail, Video, XCircle } from 'lucide-react';
import { Modal } from './Modal';
import { meetingApi } from '../../services/meetingApi';
import { parseError } from '../../services/api';
import { useToast } from '../../hooks/useToast';
import { invalidateCache } from '../../hooks/useAsync';
import { formatDateTime, formatTime, localToDate, nowLocalTime, todayLocalISO } from '../../utils/date';
import { newIdempotencyKey } from '../../utils/formatting';

// Classify's live API enforces a hard 2-minute floor even though our own
// validation allows 1 (see MIN_MEETING_SECONDS) — no preset below 5 avoids
// offering a duration Classify is known to always reject.
const DURATIONS = [5, 15, 30, 45, 60, 90, 120];

function defaultSlot() {
  // Next half hour at least 15 minutes out, in Asia/Kolkata.
  const [h, m] = nowLocalTime().split(':').map(Number);
  let mins = h * 60 + m + 15;
  mins = Math.ceil(mins / 30) * 30;
  const dayOffset = mins >= 24 * 60 ? 1 : 0;
  mins %= 24 * 60;
  return { date: todayLocalISO(dayOffset), time: `${String(Math.floor(mins / 60)).padStart(2, '0')}:${String(mins % 60).padStart(2, '0')}` };
}

export function validateSchedule({ date, time, duration, minDuration }, now = Date.now()) {
  const errors = {};
  const start = localToDate(date, time);
  if (!date) errors.date = 'Choose a date';
  if (!time) errors.time = 'Choose a time';
  if (start && start.getTime() < now + 60 * 1000) errors.time = 'Meeting start time must be in the future (at least 1 minute ahead).';
  const d = Number(duration);
  if (!d || d < 1) errors.duration = 'Meetings must be at least 1 minute long.';
  else if (d > 480) errors.duration = 'Meetings cannot be longer than 8 hours.';
  const md = Number(minDuration);
  if (!md || md < 1) errors.minDuration = 'Minimum attendance must be at least 1 minute.';
  else if (d && md > d) errors.minDuration = 'Minimum attendance cannot exceed the meeting duration.';
  return errors;
}

function ChannelResult({ icon: Icon, label, state, onResend, resending }) {
  const ok = ['sent', 'delivered'].includes(state?.status);
  const skipped = state?.status === 'skipped';
  return (
    <li className="result-row">
      <Icon size={16} aria-hidden="true" />
      <span style={{ flex: 1 }}>{label}</span>
      {ok && <span className="badge badge-success"><Check size={12} /> Sent</span>}
      {skipped && <span className="badge">Not sent</span>}
      {!ok && !skipped && (
        <>
          <span className="badge badge-error" title={state?.error || ''}><XCircle size={12} /> Failed</span>
          {onResend && (
            <button className="btn btn-sm" onClick={onResend} disabled={resending}>
              {resending ? <Loader2 className="spin" /> : null} Resend
            </button>
          )}
        </>
      )}
    </li>
  );
}

export function ScheduleMeetingModal({ lead, open, onClose, onScheduled }) {
  const toast = useToast();
  const [form, setForm] = useState(() => ({ ...defaultSlot(), duration: 30, minDuration: 1, notes: '', sendEmail: true }));
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [phase, setPhase] = useState('');
  const [serverError, setServerError] = useState(null);
  const [result, setResult] = useState(null);
  const [resending, setResending] = useState('');
  const keyRef = useRef(newIdempotencyKey());

  useEffect(() => {
    if (open) {
      setForm({ ...defaultSlot(), duration: 30, minDuration: 1, notes: '', sendEmail: true });
      setErrors({});
      setServerError(null);
      setResult(null);
      keyRef.current = newIdempotencyKey();
    }
  }, [open]);

  const start = localToDate(form.date, form.time);
  const end = start ? new Date(start.getTime() + Number(form.duration || 0) * 60000) : null;
  const preview = useMemo(() => (start && !Number.isNaN(start.getTime()) ? `${formatDateTime(start)} – ${formatTime(end)} IST` : ''), [start, end]);

  const set = (field) => (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm((f) => ({ ...f, [field]: value }));
    setErrors((er) => ({ ...er, [field]: undefined }));
    setServerError(null);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (submitting) return; // double-click guard (server is idempotent too)
    const v = validateSchedule(form);
    setErrors(v);
    if (Object.keys(v).length) return;
    setSubmitting(true);
    setPhase('Scheduling meeting…');
    const timer = setTimeout(() => setPhase('Sending invitation…'), 1200);
    try {
      const meeting = await meetingApi.schedule(
        {
          lead_id: lead.id,
          meeting_date: form.date,
          meeting_time: form.time,
          duration_minutes: Number(form.duration),
          min_duration: Number(form.minDuration),
          timezone: 'Asia/Kolkata',
          notes: form.notes || undefined,
          send_email: form.sendEmail,
        },
        keyRef.current,
      );
      setResult(meeting);
      invalidateCache('meetings');
      invalidateCache('leads');
      invalidateCache(`lead`);
      invalidateCache('dash');
      toast.success('Meeting scheduled successfully', `${lead.name} · ${formatDateTime(meeting.schedule.start_time)}`);
      const n = meeting.notifications || {};
      if (n.email?.status === 'sent') toast.info('Invitation sent', 'Email delivered to the lead.');
      if (n.email?.status === 'failed') toast.error('Email delivery failed', n.email.error);
      onScheduled?.(meeting);
    } catch (err) {
      const parsed = parseError(err, 'Unable to schedule meeting.');
      setServerError(parsed);
      keyRef.current = newIdempotencyKey();
      toast.error(parsed.message, parsed.reason);
    } finally {
      clearTimeout(timer);
      setSubmitting(false);
      setPhase('');
    }
  };

  const resend = async () => {
    setResending('email');
    try {
      const state = await meetingApi.resendEmail(result.id);
      setResult((r) => ({ ...r, notifications: { ...r.notifications, email: state } }));
      if (state.status === 'sent') toast.success('Invitation sent');
      else toast.error('Email delivery failed', state.error);
    } catch (err) {
      toast.error('Resend failed', parseError(err).message);
    } finally {
      setResending('');
    }
  };

  if (!lead) return null;

  if (result) {
    const joinUrl = result.classify?.student_join_url;
    return (
      <Modal open={open} onClose={onClose} title="Meeting scheduled" width={520}
             footer={<>
               <button className="btn" onClick={onClose}>Done</button>
               <Link className="btn btn-primary" to={`/meetings/${result.id}`} onClick={onClose}>View meeting</Link>
             </>}>
        <div className="notice success" style={{ marginBottom: 14 }}>
          <CheckCircle2 />
          <div>
            <strong>Classify meeting created</strong>
            <div>{formatDateTime(result.schedule.start_time)} · {result.schedule.duration_minutes} min · Minimum attendance {result.schedule.min_duration} min</div>
          </div>
        </div>
        <ul className="result-list">
          <li className="result-row"><CalendarClock size={16} /><span style={{ flex: 1 }}>Scheduled in Classify</span><span className="badge badge-success"><Check size={12} /> Done</span></li>
          <ChannelResult icon={Mail} label={`Email invitation · ${lead.email}`} state={result.notifications?.email}
                         onResend={resend} resending={resending === 'email'} />
        </ul>
        {joinUrl ? (
          <div className="copy-row">
            <span className="mono" style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{joinUrl}</span>
            <button className="btn btn-sm" onClick={() => navigator.clipboard?.writeText(joinUrl).then(() => toast.success('Lead link copied'))}>
              <Copy /> Copy lead link
            </button>
          </div>
        ) : (
          <p className="muted" style={{ marginTop: 12 }}>Classify emails the personal joining link directly to the lead.</p>
        )}
      </Modal>
    );
  }

  return (
    <Modal open={open} onClose={onClose} busy={submitting} title="Schedule Classify Meeting" subtitle="Creates a scheduled meeting in Classify and invites the lead." width={580}
           footer={<>
             <button className="btn" onClick={onClose} disabled={submitting}>Cancel</button>
             <button className="btn btn-primary" type="submit" form="schedule-form" disabled={submitting}>
               {submitting ? <><Loader2 className="spin" /> {phase}</> : <><Video /> Schedule &amp; Send Meeting</>}
             </button>
           </>}>
      <form id="schedule-form" onSubmit={submit} noValidate>
        <dl className="kv schedule-summary">
          <dt>Lead</dt><dd>{lead.name}</dd>
          <dt>Email</dt><dd>{lead.email}</dd>
          <dt>Phone</dt><dd className="tabular">{lead.phone}</dd>
          <dt>Sales Person</dt><dd>{lead.sales_person?.name || '—'}</dd>
        </dl>
        <div className="form-grid" style={{ marginTop: 16 }}>
          <div className="field">
            <label htmlFor="sm-date">Meeting Date</label>
            <input id="sm-date" type="date" className={`input ${errors.date ? 'invalid' : ''}`} value={form.date} min={todayLocalISO()} onChange={set('date')} required />
            {errors.date && <span className="error-text">{errors.date}</span>}
          </div>
          <div className="field">
            <label htmlFor="sm-time">Meeting Time (IST)</label>
            <input id="sm-time" type="time" className={`input ${errors.time ? 'invalid' : ''}`} value={form.time} onChange={set('time')} required />
            {errors.time && <span className="error-text">{errors.time}</span>}
          </div>
          <div className="field">
            <label htmlFor="sm-duration">Duration</label>
            <select id="sm-duration" className={`select ${errors.duration ? 'invalid' : ''}`} value={form.duration} onChange={set('duration')}>
              {DURATIONS.map((d) => <option key={d} value={d}>{d} minute{d === 1 ? '' : 's'}</option>)}
            </select>
            {errors.duration && <span className="error-text">{errors.duration}</span>}
          </div>
          <div className="field">
            <label htmlFor="sm-min">Minimum Attendance</label>
            <div className="input-suffix">
              <input id="sm-min" type="number" min={1} max={form.duration} className={`input ${errors.minDuration ? 'invalid' : ''}`} value={form.minDuration} onChange={set('minDuration')} />
              <span>minute{Number(form.minDuration) === 1 ? '' : 's'}</span>
            </div>
            {errors.minDuration ? <span className="error-text">{errors.minDuration}</span> : <span className="hint">How long the lead must attend to count as present.</span>}
          </div>
          <div className="field full">
            <label htmlFor="sm-notes">Notes for the lead <span className="muted">(optional)</span></label>
            <textarea id="sm-notes" className="textarea" rows={2} maxLength={2000} value={form.notes} onChange={set('notes')} placeholder="Shared with the lead in Classify" />
          </div>
          <div className="field full">
            <span className="section-label" style={{ marginBottom: 2 }}>Send invitation via</span>
            <div className="row wrap" style={{ gap: 16 }}>
              <label className="check"><input type="checkbox" checked={form.sendEmail} onChange={set('sendEmail')} /> <Mail size={14} /> Email</label>
            </div>
          </div>
        </div>
        {preview && !errors.time && (
          <div className="schedule-preview"><CalendarClock size={15} /> {preview}</div>
        )}
        {serverError && (
          <div className="notice error" role="alert" style={{ marginTop: 12 }}>
            <AlertCircle />
            <div>
              <strong>{serverError.message}</strong>
              {serverError.reason && <div><span className="muted" style={{ color: 'inherit', opacity: 0.8 }}>Reason:</span> {serverError.reason}</div>}
              {serverError.hint && <div>{serverError.hint}</div>}
            </div>
          </div>
        )}
      </form>
    </Modal>
  );
}
