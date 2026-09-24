import { AlertTriangle, Check, Clock, Loader2, Minus, X } from 'lucide-react';

const STATE = {
  completed: { icon: Check, label: 'Done', cls: 'pp-done' },
  processing: { icon: Loader2, label: 'Processing…', cls: 'pp-active', spin: true },
  pending: { icon: Clock, label: 'Waiting', cls: 'pp-pending' },
  failed: { icon: X, label: 'Failed', cls: 'pp-error' },
  unavailable: { icon: AlertTriangle, label: 'Unavailable', cls: 'pp-warning' },
  skipped: { icon: Minus, label: 'Not needed', cls: 'pp-pending' },
};

/** Meeting → Recording → Transcript → AI Analysis → Final Intelligence */
export function ProcessingProgress({ meeting, onRetry, retrying }) {
  const p = meeting.processing || {};
  const st = meeting.status || {};
  const meetingState = st.no_show ? 'skipped' : st.meeting_completed ? 'completed' : 'pending';
  const final = st.analysis_completed ? 'completed' : ['failed', 'unavailable'].includes(p.analysis?.status) ? 'unavailable' : st.no_show ? 'skipped' : 'pending';
  const rows = [
    { key: 'meeting', label: 'Meeting', status: meetingState, note: st.no_show ? 'Lead did not join' : null },
    { key: 'recording', label: 'Recording', status: st.no_show ? 'skipped' : p.recording?.status, stage: 'recording' },
    { key: 'transcript', label: 'Transcript', status: st.no_show ? 'skipped' : p.transcript?.status, stage: 'transcript' },
    { key: 'analysis', label: 'AI Analysis', status: st.no_show ? 'skipped' : p.analysis?.status, stage: 'analysis' },
    { key: 'final', label: 'Final Intelligence', status: final },
  ];
  return (
    <ul className="pp-list">
      {rows.map((r) => {
        const s = STATE[r.status] || STATE.pending;
        const Icon = s.icon;
        const stage = r.stage ? p[r.stage] : null;
        return (
          <li key={r.key} className={`pp-row ${s.cls}`}>
            <span className="pp-icon" aria-hidden="true">
              <Icon size={13} strokeWidth={2.6} className={s.spin ? 'spin' : ''} />
            </span>
            <div className="pp-main">
              <div className="row-between">
                <span className="pp-label">{r.label}</span>
                <span className="pp-state">{s.label}</span>
              </div>
              {(r.note || stage?.error_message) && <div className="pp-note">{r.note || stage.error_message}</div>}
              {stage?.attempt_count > 1 && <div className="pp-note">Attempt {stage.attempt_count}</div>}
              {r.status === 'failed' && onRetry && (
                <button className="btn btn-sm" style={{ marginTop: 6 }} onClick={() => onRetry(r.stage)} disabled={retrying}>
                  Retry {r.label.toLowerCase()}
                </button>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
