import { AlertTriangle, Check, CircleHelp, Flame, ListTodo, Quote, Sparkles, Target, ThumbsUp, TrendingUp, X } from 'lucide-react';
import { Card } from '../cards/Card';
import { AIBadge, LevelBadge } from '../badges/Badge';
import { NotAvailable } from '../common/States';
import { formatDuration, formatPercent, titleCase } from '../../utils/formatting';
import { OBJECTION_LABELS } from '../../utils/status';

const cap = (s) => (s ? titleCase(s) : '—');

/** Top-of-page summary for completed meetings (spec §75). */
export function MeetingIntelligenceCard({ meeting, result }) {
  const cov = result.pitch_coverage || [];
  const covered = cov.filter((c) => c.covered).length;
  const mainObjection = result.lead_objections?.[0];
  const ai = <Sparkles aria-label="AI generated" />;
  const cells = [
    ['Meeting Duration', meeting.attendance?.duration_seconds ? formatDuration(meeting.attendance.duration_seconds) : 'Not reported', false],
    ['Lead Engagement', cap(result.engagement?.level), true],
    ['Purchase Intent', cap(result.purchase_intent), true],
    ['Main Objection', mainObjection ? OBJECTION_LABELS[mainObjection.category] || mainObjection.objection : 'None raised', true],
    ['Follow-up', result.follow_up?.required ? 'Required' : 'Not required', true],
    ['Pitch Coverage', cov.length ? `${covered} / ${cov.length} topics` : '—', true],
    ['Questions Asked', String(result.lead_questions?.length ?? 0), true],
    ['Action Items', String(result.action_items?.length ?? 0), true],
  ];
  return (
    <section className="intel-hero" aria-label="Meeting intelligence">
      <div className="row-between" style={{ position: 'relative', zIndex: 1, marginBottom: 14 }}>
        <div className="section-label" style={{ margin: 0 }}>Meeting Intelligence</div>
        <span className="badge" style={{ background: 'rgba(196,181,253,.16)', color: '#ddd6fe' }}><Sparkles size={12} /> AI generated · {Math.round((result.confidence || 0) * 100)}% confidence</span>
      </div>
      <div className="intel-grid">
        {cells.map(([label, value, isAi]) => (
          <div className="intel-cell" key={label}>
            <span>{label} {isAi && ai}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

/** AI insight cards (spec §34). */
export function AIInsightsPanel({ result }) {
  const strong = result.positive_signals?.[0];
  const obj = result.lead_objections?.[0];
  const cards = [
    ['🎯', 'Purchase Intent', cap(result.purchase_intent)],
    ['💬', 'Lead Engagement', cap(result.engagement?.level)],
    ['⚠', 'Main Objection', obj ? OBJECTION_LABELS[obj.category] || obj.objection : 'None raised'],
    ['📌', 'Follow-up', result.follow_up?.required ? 'Required' : 'Not required'],
    ['🔥', 'Strong Signal', strong?.signal || 'None detected'],
  ];
  return (
    <div className="insight-grid">
      {cards.map(([emoji, label, value]) => (
        <div className="insight-card" key={label}>
          <span className="insight-label"><span aria-hidden="true">{emoji}</span> {label}</span>
          <span className="insight-value">{value}</span>
          <span className="cell-secondary row" style={{ gap: 4, color: 'var(--ai)' }}><Sparkles size={11} /> AI generated</span>
        </div>
      ))}
    </div>
  );
}

function SignalList({ items, empty, icon: Icon, tone }) {
  if (!items?.length) return <p className="muted">{empty}</p>;
  return (
    <div>
      {items.map((s, i) => (
        <div className="signal-item" key={i}>
          <span className="row" style={{ gap: 6, fontWeight: 550 }}>
            <Icon size={14} color={tone} aria-hidden="true" /> {s.signal}
          </span>
          {s.evidence && <span className="evidence">Evidence: {s.evidence}</span>}
        </div>
      ))}
    </div>
  );
}

/** Lead intelligence with direct statements separated from AI inference (spec §20). */
export function LeadIntelligence({ result }) {
  return (
    <Card title="Lead Intelligence" badge={<AIBadge label="AI Analysis" />} subtitle="What the lead said, kept separate from what the AI infers">
      <div className="row wrap" style={{ gap: 8, marginBottom: 14 }}>
        <LevelBadge level={result.interest_level} prefix="Interest" />
        <LevelBadge level={result.purchase_intent} prefix="Intent" />
        <span className="badge">Lead sentiment: {cap(result.lead_sentiment)}</span>
        {result.conversation_language && <span className="badge badge-outline">{result.conversation_language}</span>}
      </div>
      {result.lead_intent && <p style={{ marginBottom: 14 }}><strong>Stated goal:</strong> {result.lead_intent}</p>}

      <div className="grid grid-2" style={{ marginBottom: 14 }}>
        <div className="fact-block">
          <div className="section-label row" style={{ gap: 6 }}><Quote size={12} /> Lead explicitly said</div>
          {result.explicit_statements?.length ? (
            <ul className="statement-list">
              {result.explicit_statements.map((s, i) => (
                <li key={i}>
                  <div className="quote">“{s.quote}”</div>
                  <div className="cell-secondary" style={{ marginTop: 2 }}>{s.speaker === 'sales' ? 'Sales' : 'Lead'}{s.topic ? ` · ${s.topic}` : ''}{s.timestamp ? ` · ${s.timestamp}` : ''}</div>
                </li>
              ))}
            </ul>
          ) : <p className="muted">No direct statements extracted.</p>}
        </div>
        <div className="ai-block">
          <div className="section-label row" style={{ gap: 6, color: 'var(--ai)' }}><Sparkles size={12} /> AI interpretation</div>
          {result.ai_interpretations?.length ? (
            <ul className="statement-list">
              {result.ai_interpretations.map((s, i) => (
                <li key={i}>
                  <div style={{ fontWeight: 550 }}>{s.interpretation}</div>
                  <div className="cell-secondary" style={{ marginTop: 2 }}>Basis: {s.basis || '—'} · {formatPercent((s.confidence || 0) * 100)} confidence</div>
                </li>
              ))}
            </ul>
          ) : <p className="muted">No interpretations.</p>}
        </div>
      </div>

      <div className="grid grid-2">
        <div>
          <div className="section-label">Objections</div>
          {result.lead_objections?.length ? result.lead_objections.map((o, i) => (
            <div className="signal-item" key={i}>
              <span className="row wrap" style={{ gap: 6, fontWeight: 550 }}>
                <AlertTriangle size={14} color="var(--warning)" /> {o.objection}
                <span className="badge badge-sm badge-warning">{OBJECTION_LABELS[o.category] || o.category}</span>
                {o.handled === true && <span className="badge badge-sm badge-success">Handled</span>}
                {o.handled === false && <span className="badge badge-sm badge-error">Not handled</span>}
              </span>
              {o.evidence && <span className="evidence">Evidence: {o.evidence}</span>}
              {o.handling_notes && <span className="evidence">Response: {o.handling_notes}</span>}
            </div>
          )) : <p className="muted">No objection detected.</p>}
        </div>
        <div>
          <div className="section-label">Questions asked by the lead</div>
          {result.lead_questions?.length ? result.lead_questions.map((q, i) => (
            <div className="signal-item" key={i}>
              <span className="row" style={{ gap: 6, fontWeight: 550 }}><CircleHelp size={14} color="var(--info)" /> {q.question}</span>
              {q.evidence && <span className="evidence">{q.answered === false ? 'Unanswered · ' : ''}{q.evidence}</span>}
            </div>
          )) : <p className="muted">No questions detected.</p>}
        </div>
        <div>
          <div className="section-label">Pain points</div>
          {result.pain_points?.length ? <div className="tag-list">{result.pain_points.map((p) => <span key={p} className="tag">{p}</span>)}</div> : <p className="muted">None identified.</p>}
          <div className="section-label" style={{ marginTop: 14 }}>Requirements</div>
          {result.lead_requirements?.length ? <div className="tag-list">{result.lead_requirements.map((p) => <span key={p} className="tag">{p}</span>)}</div> : <p className="muted">None identified.</p>}
          <div className="section-label" style={{ marginTop: 14 }}>Interests</div>
          {result.interests?.length ? <div className="tag-list">{result.interests.map((p) => <span key={p} className="tag">{p}</span>)}</div> : <p className="muted">None identified.</p>}
          {result.competitor_mentions?.length > 0 && (
            <>
              <div className="section-label" style={{ marginTop: 14 }}>Competitor mentions</div>
              <div className="tag-list">{result.competitor_mentions.map((p) => <span key={p} className="tag">{p}</span>)}</div>
            </>
          )}
        </div>
        <div>
          <div className="section-label">Positive signals</div>
          <SignalList items={result.positive_signals} empty="None detected." icon={ThumbsUp} tone="var(--success)" />
          <div className="section-label" style={{ marginTop: 14 }}>Risk signals</div>
          <SignalList items={result.risk_signals} empty="None detected." icon={Flame} tone="var(--error)" />
        </div>
      </div>
    </Card>
  );
}

export function PitchCoverage({ items }) {
  if (!items?.length) return <p className="muted">Pitch coverage unavailable.</p>;
  return (
    <ul className="coverage-list">
      {items.map((c) => (
        <li key={c.topic} className={`coverage-item ${c.covered ? 'yes' : 'no'}`} title={c.evidence}>
          <span className="ci-icon" aria-hidden="true">{c.covered ? <Check size={13} strokeWidth={3} /> : <X size={13} strokeWidth={3} />}</span>
          <span>{c.topic}</span>
          <span className="sr-only">{c.covered ? 'covered' : 'not covered'}</span>
          <span className="ci-conf tabular">{Math.round((c.confidence || 0) * 100)}%</span>
        </li>
      ))}
    </ul>
  );
}

export function SalesAnalysis({ result }) {
  const cov = result.pitch_coverage || [];
  const covered = cov.filter((c) => c.covered).length;
  return (
    <Card title="Sales Analysis" badge={<AIBadge label="AI Analysis" />} subtitle={cov.length ? `Pitch coverage ${covered} / ${cov.length} checklist topics` : ''}>
      {cov.length > 0 && <div className="progress" style={{ marginBottom: 14 }}><span style={{ width: `${(covered / cov.length) * 100}%` }} /></div>}
      <div className="section-label">Pitch coverage</div>
      <PitchCoverage items={cov} />
      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <div>
          <div className="section-label">Topics discussed</div>
          <div className="tag-list">{(result.topics_discussed || []).map((t) => <span key={t} className="tag">{t}</span>)}</div>
          {result.pricing_discussion?.discussed && (
            <>
              <div className="section-label" style={{ marginTop: 14 }}>Pricing discussion</div>
              <p style={{ fontSize: 13 }}>{result.pricing_discussion.details}</p>
            </>
          )}
        </div>
        <div>
          <div className="section-label">Missing topics</div>
          {result.sales_pitch?.missing_topics?.length ? <div className="tag-list">{result.sales_pitch.missing_topics.map((t) => <span key={t} className="tag" style={{ background: 'var(--error-bg)', color: 'var(--error)' }}>{t}</span>)}</div> : <p className="muted">None — full pitch covered.</p>}
          <div className="section-label" style={{ marginTop: 14 }}>Objection handling</div>
          <p style={{ fontSize: 13 }}>{result.objection_handling || '—'}</p>
        </div>
      </div>
      <div className="section-label" style={{ marginTop: 16 }}>Next steps & action items</div>
      {result.action_items?.length ? (
        <div className="list">
          {result.action_items.map((a, i) => (
            <div className="list-item" key={i} style={{ padding: '8px 0' }}>
              <ListTodo size={15} color="var(--text-3)" />
              <span style={{ flex: 1 }}>{a.item}</span>
              <span className={`badge badge-sm ${a.owner === 'sales' ? 'badge-accent' : 'badge-info'}`}>{a.owner === 'sales' ? 'Sales' : a.owner === 'lead' ? 'Lead' : 'Owner?'}</span>
              {a.due_hint && <span className="cell-secondary">{a.due_hint}</span>}
            </div>
          ))}
        </div>
      ) : <p className="muted">No action items.</p>}
    </Card>
  );
}

export function FollowUpRecommendation({ followUp, onOpen }) {
  if (!followUp) return null;
  return (
    <div className="ai-block">
      <div className="row-between" style={{ marginBottom: 8 }}>
        <span className="section-label row" style={{ gap: 6, margin: 0, color: 'var(--ai)' }}><Target size={12} /> AI Recommendation</span>
        {followUp.required ? <span className="badge badge-warning">Follow-up required</span> : <span className="badge badge-success">No follow-up needed</span>}
      </div>
      {followUp.required ? (
        <dl className="kv" style={{ gridTemplateColumns: '130px minmax(0,1fr)' }}>
          <dt>Recommended action</dt><dd>{followUp.recommended_next_action || '—'}</dd>
          <dt>Reason</dt><dd>{followUp.reason || '—'}</dd>
          <dt>Suggested timing</dt><dd>{followUp.suggested_timing || '—'}</dd>
        </dl>
      ) : <p className="muted">{followUp.reason || 'The AI did not identify a follow-up requirement.'}</p>}
      {onOpen && followUp.required && <button className="btn btn-sm" style={{ marginTop: 10 }} onClick={onOpen}>Open in Follow-up Center</button>}
    </div>
  );
}

export function CallQuality({ quality }) {
  if (!quality) return null;
  const q = quality;
  const talk = q.talk_ratio;
  const row = (label, m, fmt = (v) => v) => (
    <>
      <dt className="row" style={{ gap: 4 }}>{label}{m?.ai_generated && <Sparkles size={11} color="var(--ai)" aria-label="AI generated" />}</dt>
      <dd>{m?.available ? fmt(m.value) : <NotAvailable>{m?.note || 'Not available from meeting data'}</NotAvailable>}</dd>
    </>
  );
  return (
    <Card title="Call Quality" subtitle="Non-authoritative metrics from available data" icon={TrendingUp}>
      {talk?.available && (
        <div style={{ marginBottom: 14 }}>
          <div className="row-between cell-secondary" style={{ marginBottom: 6 }}>
            <span>Lead {formatPercent(talk.value.lead_pct)}</span><span>Sales {formatPercent(talk.value.sales_pct)}</span>
          </div>
          <div className="talk-bar" role="img" aria-label={`Talk ratio: lead ${talk.value.lead_pct}%, sales ${talk.value.sales_pct}%`}>
            <span style={{ width: `${talk.value.lead_pct}%`, background: 'var(--series-2)' }} />
            <span style={{ width: `${talk.value.sales_pct}%`, background: 'var(--series-1)' }} />
          </div>
          <p className="cell-secondary" style={{ marginTop: 6 }}>{talk.note}</p>
        </div>
      )}
      <dl className="kv" style={{ gridTemplateColumns: '150px minmax(0,1fr)' }}>
        {row('Total duration', q.total_duration_seconds, formatDuration)}
        {row('Lead talk time', q.lead_talk_seconds, formatDuration)}
        {row('Sales talk time', q.sales_talk_seconds, formatDuration)}
        {row('Questions', q.questions)}
        {row('Objections', q.objections)}
        {row('Interruptions', q.interruptions)}
        {row('Silence / gaps', q.silence_seconds, formatDuration)}
        {row('Topics discussed', q.topics_discussed)}
        {row('Pitch coverage', q.pitch_coverage, (v) => `${v.covered} / ${v.total}`)}
        {row('Follow-up required', q.follow_up_required, (v) => (v ? 'Yes' : 'No'))}
      </dl>
    </Card>
  );
}

