import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, BrainCircuit, CalendarClock, Copy, Download, FileDown, Flag, Loader2, Mail,
  PlayCircle, RefreshCw, Sparkles, UserX, Video, Wand2,
} from 'lucide-react';
import { useMeeting } from '../../hooks/useMeetings';
import { usePolling } from '../../hooks/usePolling';
import { useToast } from '../../hooks/useToast';
import { invalidateCache } from '../../hooks/useAsync';
import { meetingApi } from '../../services/meetingApi';
import { errorText } from '../../services/api';
import { Card } from '../../components/cards/Card';
import { AIBadge, DemoBadge, FlagChip, NotificationBadge, StatusBadge } from '../../components/badges/Badge';
import { JourneyStepper, Timeline } from '../../components/timeline/Timeline';
import { ProcessingProgress } from '../../components/meeting/ProcessingProgress';
import {
  AIInsightsPanel, CallQuality, FollowUpRecommendation, LeadIntelligence, MeetingIntelligenceCard, SalesAnalysis,
} from '../../components/meeting/IntelligenceSections';
import { TranscriptView } from '../../components/transcript/TranscriptView';
import { EmptyState, ErrorState, NotAvailable } from '../../components/common/States';
import { SkeletonCard } from '../../components/common/Skeleton';
import { Modal } from '../../components/modals/Modal';
import { formatBytes, formatDuration } from '../../utils/formatting';
import { formatDate, formatDateTime, formatTime } from '../../utils/date';
import { FLAG_CATEGORIES } from '../../utils/status';

const SYNC_LABELS = {
  pending: 'Scheduled after the meeting ends',
  requesting: 'Requesting from Classify…',
  waiting: 'Waiting — Classify reports the class in progress',
  retrying: 'Retrying',
  completed: 'Received from Classify',
  failed: 'Failed',
};

function syncLabel(sync) {
  if (!sync) return '—';
  const base = SYNC_LABELS[sync.status] || sync.status;
  const extra = sync.status === 'failed' || sync.status === 'retrying' ? ` — ${sync.last_message || ''}` : '';
  const attempts = sync.attempt_count > 1 && sync.status !== 'completed' ? ` (attempt ${sync.attempt_count})` : '';
  return `${base}${extra}${attempts}`;
}

function MeetingInfo({ m }) {
  const att = m.attendance || {};
  const join = m.status.no_show ? 'Lead did not join' : m.status.lead_joined ? `Lead joined${att.lead?.attended_seconds ? ` · attended ${formatDuration(att.lead.attended_seconds)}` : ''}` : m.status.meeting_completed ? 'Not reported by Classify' : 'Not started';
  return (
    <Card title="Meeting Information" icon={CalendarClock}>
      <dl className="kv">
        <dt>Scheduled</dt><dd>{formatDateTime(m.schedule.start_time)} · {m.schedule.duration_minutes} min</dd>
        <dt>Timezone</dt><dd>{m.schedule.timezone}</dd>
        <dt>Min. attendance</dt><dd>{m.schedule.min_duration} min</dd>
        <dt>Actual start</dt><dd>{att.actual_start ? formatDateTime(att.actual_start) : <NotAvailable />}</dd>
        <dt>Actual end</dt><dd>{att.actual_end ? formatDateTime(att.actual_end) : <NotAvailable />}</dd>
        <dt>Duration</dt><dd>{att.duration_seconds ? formatDuration(att.duration_seconds) : <NotAvailable />}</dd>
        <dt>Join status</dt><dd>{join}</dd>
        <dt>Recording</dt><dd>{m.status.recording_available ? `Available${m.recording?.is_mock ? ' (demo)' : ''}` : m.processing.recording.status === 'unavailable' ? 'Recording unavailable' : m.status.no_show ? '—' : 'Pending'}</dd>
        <dt>Transcript</dt><dd>{m.status.transcript_available ? `Available · ${m.transcript?.segment_count} segments` : m.processing.transcript.status === 'unavailable' ? 'Transcript unavailable' : m.status.no_show ? '—' : 'Pending'}</dd>
        <dt>Attendance sync</dt><dd>{syncLabel(m.attendance_sync)}</dd>
        <dt>Classify ID</dt><dd className="mono" style={{ fontSize: 11 }}>{m.classify?.unique_id || '—'}</dd>
      </dl>
    </Card>
  );
}

function Invitations({ m, onResend, busy, disabled }) {
  const n = m.notifications || {};
  const row = (channel, Icon, label, target) => (
    <div className="list-item" style={{ alignItems: 'center' }}>
      <Icon size={16} color="var(--text-3)" />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="cell-primary">{label}</div>
        <div className="cell-secondary">{n[channel]?.error ? n[channel].error : n[channel]?.sent_at ? `Sent ${formatDateTime(n[channel].sent_at)}` : target}</div>
      </div>
      <NotificationBadge status={n[channel]?.status} />
      {!disabled && (
        <button className="btn btn-sm" onClick={() => onResend(channel)} disabled={busy === channel} title={`Resend ${label}`}>
          {busy === channel ? <Loader2 className="spin" /> : <RefreshCw />} Resend
        </button>
      )}
    </div>
  );
  return (
    <Card title="Invitations">
      <div className="list">
        {row('email', Mail, 'Email', m.lead_snapshot?.email)}
      </div>
    </Card>
  );
}

function Flags({ m }) {
  const groups = FLAG_CATEGORIES.map((c) => ({ ...c, flags: (m.flag_details || []).filter((f) => f.category === c.key) })).filter((g) => g.flags.length);
  return (
    <Card title="Flags" icon={Flag}>
      {!groups.length ? <p className="muted">No flags yet.</p> : groups.map((g) => (
        <div key={g.key} style={{ marginBottom: 10 }}>
          <div className="section-label" style={{ marginBottom: 6 }}>{g.label}</div>
          <div className="tag-list">{g.flags.map((f) => <FlagChip key={f.key} flag={f.key} ai={f.ai_generated} />)}</div>
        </div>
      ))}
    </Card>
  );
}

function Recording({ meetingId, available }) {
  const [rec, setRec] = useState(null);
  useEffect(() => {
    if (available) meetingApi.recording(meetingId).then(setRec).catch(() => setRec(null));
  }, [meetingId, available]);
  if (!available || !rec) return null;
  return (
    <Card title="Recording" icon={PlayCircle}>
      {rec.playable ? (
        <video controls preload="metadata" style={{ width: '100%', borderRadius: 10, background: '#000' }} src={rec.playback_url} />
      ) : (
        <p className="muted">{rec.is_mock ? 'Demo recording — no media file in mock mode.' : 'Recording processed; file not stored for playback.'}</p>
      )}
      <p className="cell-secondary" style={{ marginTop: 8 }}>
        {rec.duration_seconds ? formatDuration(rec.duration_seconds) : ''} {rec.size_bytes ? `· ${formatBytes(rec.size_bytes)}` : ''} · streamed securely via the backend
      </p>
    </Card>
  );
}

export default function MeetingDetails() {
  const { meetingId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { data: m, error, loading, refetch, setData } = useMeeting(meetingId);
  const [busy, setBusy] = useState('');
  const [simOpen, setSimOpen] = useState(false);
  const [transcriptVersion, setTranscriptVersion] = useState(0);
  const prev = useRef(null);

  usePolling(() => refetch({ silent: true }), Boolean(m?.polling?.active), 5000);

  // Announce lifecycle changes discovered while polling.
  useEffect(() => {
    if (!m) return;
    const p = prev.current;
    if (p && p.id === m.id) {
      if (!p.status.meeting_completed && m.status.meeting_completed) toast.info('Meeting completed', 'Recording processing started.');
      if (!p.status.no_show && m.status.no_show) toast.warning('Lead did not join', 'Classify attendance shows a no-show.');
      if (!p.status.transcript_available && m.status.transcript_available) {
        if (m.transcript?.source === 'mock') {
          toast.warning('Sample transcript shown', 'No real recording exists for this meeting, so a scripted example transcript is shown instead.');
        } else {
          toast.success('Transcript ready');
        }
        setTranscriptVersion((v) => v + 1);
      }
      if (!p.status.analysis_completed && m.status.analysis_completed) toast.ai('AI analysis completed', m.status.follow_up_required ? 'Follow-up required' : undefined);
      if (p.processing?.analysis?.status !== 'failed' && m.processing?.analysis?.status === 'failed') toast.error('AI analysis failed', m.processing.analysis.error_message);
      if (p.processing?.recording?.status !== 'failed' && m.processing?.recording?.status === 'failed') toast.error('Recording unavailable', m.processing.recording.error_message);
    }
    prev.current = m;
  }, [m, toast]);

  if (error) return <div className="page"><ErrorState error={error} onRetry={refetch} title="Meeting not available" /></div>;
  if (loading || !m) {
    return (
      <div className="page">
        <SkeletonCard lines={2} />
        <div style={{ height: 16 }} />
        <div className="split"><SkeletonCard lines={0} height={320} /><SkeletonCard lines={6} /></div>
      </div>
    );
  }

  const result = m.analysis_result?.result;
  const upcoming = new Date(m.schedule.end_time) > new Date() && !m.status.meeting_completed && !m.status.no_show;
  const analysisStatus = m.processing?.analysis?.status;
  // No scheduled-end-time gate — a host can end the meeting early and want
  // results right away. Still available after a no-show verdict too, since
  // Classify's attendance API is known to miss guests who genuinely joined.
  const canSync = m.status.meeting_created && !m.status.meeting_completed;

  const act = async (key, fn, success) => {
    setBusy(key);
    try {
      const out = await fn();
      if (success) toast.success(success);
      return out;
    } catch (err) {
      toast.error('Action failed', errorText(err));
      return undefined;
    } finally {
      setBusy('');
    }
  };

  const resend = async () => {
    const state = await act('email', () => meetingApi.resendEmail(m.id));
    if (!state) return;
    if (state.status === 'sent') toast.success('Invitation sent');
    else toast.error('Email delivery failed', state.error);
    refetch({ silent: true });
  };

  const reanalyze = async () => {
    const out = await act('reanalyze', () => meetingApi.reanalyze(m.id, 'Requested from meeting page'));
    if (out) {
      setData(out);
      toast.ai('AI analysis completed', `Version ${out.analysis?.version_count} saved; previous versions kept.`);
      invalidateCache('dash');
    }
  };

  const retry = async (stage) => {
    const out = await act('retry', () => meetingApi.retry(m.id, stage), 'Retry queued');
    if (out) setData(out);
  };

  const simulate = async (outcome) => {
    setSimOpen(false);
    const out = await act('simulate', () => meetingApi.simulate(m.id, { outcome, duration_minutes: Math.max(2, Math.min(m.schedule.duration_minutes - 2, 28)) }));
    if (out) {
      setData(out);
      toast.info(outcome === 'completed' ? 'Attendance simulated' : 'No-show simulated', outcome === 'completed' ? 'Recording processing started…' : undefined);
      invalidateCache('dash');
      invalidateCache('meetings');
    }
  };

  const syncAttendance = async () => {
    const out = await act('sync', () => meetingApi.syncAttendance(m.id));
    if (!out) return;
    setData(out);
    const r = out.sync_result || {};
    if (r.outcome === 'ok') toast.success('Attendance received from Classify', out.status.no_show ? 'Lead did not join' : 'Recording processing started…');
    else if (r.outcome === 'in_progress') toast.info('Classify reports the class in progress', 'Data is available after the session ends — we will keep checking.');
    else toast.error('Attendance sync failed', r.message);
    invalidateCache('dash');
  };

  const copyLink = () => navigator.clipboard?.writeText(m.classify.student_join_url).then(() => toast.success('Lead joining link copied'));

  return (
    <div className="page">
      <button className="btn btn-sm btn-ghost" onClick={() => navigate(-1)} style={{ marginBottom: 10 }}><ArrowLeft /> Back</button>

      <div className="card card-body" style={{ marginBottom: 16 }}>
        <div className="row-between wrap" style={{ alignItems: 'flex-start' }}>
          <div>
            <div className="row wrap" style={{ gap: 8 }}>
              <h1 style={{ fontSize: 'var(--fs-xl)' }}>
                <Link to={`/leads/${m.lead_id}`}>{m.lead_snapshot?.name}</Link>
              </h1>
              <StatusBadge state={m.status.overall} />
              {m.is_demo && <DemoBadge />}
              {m.polling?.active && <span className="badge badge-accent pulse"><span className="dot" /> Live</span>}
            </div>
            <p className="secondary" style={{ marginTop: 4 }}>
              {m.label} · {formatDate(m.schedule.start_time)}, {formatTime(m.schedule.start_time)} IST · with {m.sales_person_snapshot?.name}
            </p>
          </div>
          <div className="page-actions">
            {upcoming && m.classify?.host_join_url && (
              <a className="btn btn-primary" href={m.classify.host_join_url} target="_blank" rel="noreferrer"><Video /> Join as host</a>
            )}
            {upcoming && m.classify?.student_join_url && (
              <button className="btn" onClick={copyLink}><Copy /> Copy lead link</button>
            )}
            {m.polling && m.classify?.is_mock && upcoming && (
              <button className="btn" onClick={() => setSimOpen(true)} disabled={busy === 'simulate'} title="Demo mode only">
                {busy === 'simulate' ? <Loader2 className="spin" /> : <Wand2 />} Simulate meeting
              </button>
            )}
            {canSync && (
              <button className="btn" onClick={syncAttendance} disabled={busy === 'sync'} title="Pull attendance and recording from Classify (SendAttendanceDetails)">
                {busy === 'sync' ? <Loader2 className="spin" /> : <RefreshCw />} {busy === 'sync' ? 'Requesting attendance…' : 'Sync attendance'}
              </button>
            )}
            {m.status.transcript_available && (
              <button className="btn" onClick={reanalyze} disabled={busy === 'reanalyze'}>
                {busy === 'reanalyze' ? <Loader2 className="spin" /> : <BrainCircuit />} {busy === 'reanalyze' ? 'Analyzing conversation…' : 'Re-analyze Meeting'}
              </button>
            )}
            <button className="btn" onClick={() => act('report', () => meetingApi.downloadReport(m.id), 'Meeting report downloaded')} disabled={busy === 'report'}>
              {busy === 'report' ? <Loader2 className="spin" /> : <FileDown />} Download PDF
            </button>
          </div>
        </div>
        <div className="divider" />
        <JourneyStepper steps={m.journey} />
      </div>

      {m.status.no_show && (
        <div className="notice error" style={{ marginBottom: 16 }}>
          <UserX />
          <div><strong>Lead did not join.</strong> Classify attendance data shows the lead did not attend, so there is nothing to analyse. Consider rescheduling from the lead page.</div>
        </div>
      )}
      {m.status.meeting_data_pending && !m.status.meeting_completed && (
        <div className="notice warning" style={{ marginBottom: 16 }}>
          <CalendarClock />
          <div><strong>Awaiting meeting data from Classify.</strong> The meeting time has passed but attendance hasn't been received yet — attendance is not assumed. {syncLabel(m.attendance_sync)}.</div>
        </div>
      )}

      {result && <div style={{ marginBottom: 16 }}><MeetingIntelligenceCard meeting={m} result={result} /></div>}

      <div className="split">
        <div className="stack">
          {result ? (
            <>
              <Card title="AI Summary" badge={<AIBadge label="AI Analysis" />}
                    subtitle={`Model ${m.analysis_result.model} · prompt v${m.analysis_result.prompt_version} · ${formatDateTime(m.analysis_result.created_at)}`}>
                <p style={{ fontSize: 14.5, lineHeight: 1.65 }}>{result.summary}</p>
                {result.meeting_outcome && <p style={{ marginTop: 10 }}><span className="section-label">Outcome</span><br /><strong>{result.meeting_outcome}</strong></p>}
                <div style={{ marginTop: 14 }}><AIInsightsPanel result={result} /></div>
              </Card>
              <FollowUpRecommendation followUp={result.follow_up} />
              <LeadIntelligence result={result} />
              <SalesAnalysis result={result} />
            </>
          ) : m.status.meeting_completed && !m.status.no_show ? (
            <Card title="AI Analysis" badge={<AIBadge />}>
              {['failed', 'unavailable'].includes(analysisStatus) ? (
                <EmptyState icon={BrainCircuit} title="AI analysis unavailable"
                            description={m.processing.analysis.error_message || (m.processing.transcript.status === 'unavailable' ? 'Transcript unavailable — nothing to analyse.' : 'The analysis could not be completed.')}
                            action={m.status.transcript_available && <button className="btn btn-primary btn-sm" onClick={reanalyze} disabled={busy === 'reanalyze'}><RefreshCw /> Retry Analysis</button>} />
              ) : (
                <EmptyState icon={Sparkles} title={m.processing.recording.status !== 'completed' ? 'Processing recording…' : m.processing.transcript.status !== 'completed' ? 'Generating transcript…' : 'Analyzing conversation…'}
                            description="This page updates automatically. You don't need to stay here." />
              )}
            </Card>
          ) : !m.status.no_show ? (
            <Card title="Meeting → Intelligence">
              <EmptyState icon={CalendarClock} title={upcoming ? 'Waiting for the meeting' : 'Waiting for Classify'}
                          description="After the meeting ends, attendance and the recording are fetched from Classify automatically. The transcript, AI summary, objections, pitch coverage and follow-up then appear here." />
            </Card>
          ) : null}

          {m.status.meeting_completed && !m.status.no_show && (
            <TranscriptView meetingId={m.id} meeting={m} status={m.processing.transcript.status} version={transcriptVersion}
                            onDownload={() => act('transcript', () => meetingApi.downloadTranscript(m.id), 'Transcript downloaded')} />
          )}
          {m.status.meeting_completed && !m.status.no_show && <CallQuality quality={m.call_quality} />}
        </div>

        <div className="stack">
          <Card title="Processing"><ProcessingProgress meeting={m} onRetry={retry} retrying={busy === 'retry'} /></Card>
          <MeetingInfo m={m} />
          <Recording meetingId={m.id} available={m.status.recording_available} />
          <Invitations m={m} onResend={resend} busy={busy} disabled={!upcoming} />
          <Flags m={m} />
          <Card title="Meeting timeline"><Timeline events={m.timeline} /></Card>
          {m.analysis_versions?.length > 0 && (
            <Card title="Analysis versions" subtitle="Earlier analyses are kept for audit and comparison">
              <div className="list">
                {m.analysis_versions.map((v) => (
                  <div key={v.id} className="list-item" style={{ padding: '8px 0' }}>
                    <Sparkles size={14} color="var(--ai)" />
                    <div style={{ flex: 1 }}>
                      <div className="cell-primary">{v.model} · prompt v{v.prompt_version}</div>
                      <div className="cell-secondary">{formatDateTime(v.created_at)} · {v.trigger}</div>
                    </div>
                    {v.is_current && <span className="badge badge-success">Current</span>}
                  </div>
                ))}
              </div>
            </Card>
          )}
          {m.follow_ups?.length > 0 && (
            <Card title="Follow-ups">
              {m.follow_ups.map((f) => (
                <div key={f.id} className="list-item">
                  <span className={`badge ${f.status === 'completed' ? 'badge-success' : 'badge-warning'}`}>{f.status}</span>
                  <div style={{ flex: 1 }}>
                    <div className="cell-primary">{f.recommended_action}</div>
                    <div className="cell-secondary">Due {formatDate(f.due_date)}</div>
                  </div>
                </div>
              ))}
            </Card>
          )}
        </div>
      </div>

      <Modal open={simOpen} onClose={() => setSimOpen(false)} title="Simulate meeting result" subtitle="Demo mode only — feeds a SendAttendanceDetails response (documented shape) through the real pipeline." width={480}
             footer={<>
               <button className="btn" onClick={() => simulate('no_show')}><UserX /> Lead did not join</button>
               <button className="btn btn-primary" onClick={() => simulate('completed')}><Download /> Meeting completed</button>
             </>}>
        <p className="secondary">“Meeting completed” posts attendance plus a demo recording, then the backend runs recording → transcript → Gemini (mock) analysis in the background while this page updates live.</p>
      </Modal>
    </div>
  );
}
