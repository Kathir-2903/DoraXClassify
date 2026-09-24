import { useEffect, useMemo, useState } from 'react';
import { Download, FileText, Search, Sparkles } from 'lucide-react';
import { meetingApi } from '../../services/meetingApi';
import { useDebounce } from '../../hooks/useDebounce';
import { Card } from '../cards/Card';
import { EmptyState, Spinner } from '../common/States';
import { formatTimeSeconds, offsetClock } from '../../utils/date';

function highlight(text, q) {
  if (!q) return text;
  const parts = text.split(new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'ig'));
  return parts.map((p, i) => (p.toLowerCase() === q.toLowerCase() ? <mark key={i}>{p}</mark> : p));
}

/** Chat-style transcript. Speaker labels / timestamps only when the source has them. */
export function TranscriptView({ meetingId, meeting, status, onDownload, version }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const q = useDebounce(search, 250);

  useEffect(() => {
    let off = false;
    setLoading(true);
    meetingApi.transcript(meetingId, q).then((d) => !off && setData(d)).catch(() => !off && setData(null)).finally(() => !off && setLoading(false));
    return () => { off = true; };
  }, [meetingId, q, version]);

  const start = data?.actual_start ? new Date(data.actual_start).getTime() : null;
  const names = useMemo(() => ({ lead: meeting?.lead_snapshot?.name || 'Lead', sales: meeting?.sales_person_snapshot?.name || 'Sales' }), [meeting]);

  const stamp = (s) => {
    if (!data?.has_timestamps || s.start_seconds === null || s.start_seconds === undefined) return null;
    return start ? formatTimeSeconds(new Date(start + s.start_seconds * 1000)) : offsetClock(s.start_seconds);
  };

  const unavailable = !loading && (!data || !data.available);
  return (
    <Card title="Conversation" icon={FileText}
          subtitle={data?.available ? `${data.total_segments} segments · source: ${
            data.source === 'classify' ? 'Classify'
              : data.source === 'mock' ? 'demo transcript'
              : data.source === 'whisper' ? 'local transcription (faster-whisper)'
              : 'Gemini transcription'
          }` : ''}
          badge={data?.ai_generated ? <span className="badge badge-ai badge-sm"><Sparkles size={10} /> AI transcribed</span> : null}
          actions={data?.available && <button className="btn btn-sm" onClick={onDownload}><Download /> Download</button>}>
      {unavailable ? (
        <EmptyState icon={FileText} title={status === 'processing' || status === 'pending' ? 'Generating transcript…' : 'Transcript unavailable'}
                    description={status === 'processing' || status === 'pending' ? 'The transcript appears here as soon as processing finishes.' : 'No transcript was produced for this meeting.'} />
      ) : (
        <>
          <div className="row wrap" style={{ marginBottom: 12, gap: 10 }}>
            <div className="input-icon" style={{ flex: '1 1 240px', maxWidth: 360 }}>
              <Search />
              <input className="input" placeholder="Search transcript" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search transcript" />
            </div>
            {q && data && <span className="muted">{data.segments.length} match{data.segments.length === 1 ? '' : 'es'}</span>}
            {data?.ai_generated && <span className="cell-secondary">Speaker labels and timings are AI estimates.</span>}
            {data && !data.has_timestamps && <span className="cell-secondary">Timestamps not provided by the source.</span>}
          </div>
          {loading && !data ? <Spinner label="Loading transcript…" /> : (
            <div className="transcript" aria-live="polite">
              {data.segments.length === 0 && <p className="muted">No lines match “{q}”.</p>}
              {data.segments.map((s) => {
                const who = data.has_speaker_labels ? s.speaker : 'unknown';
                const ts = stamp(s);
                return (
                  <div key={s.index} className={`msg msg-${who}`}>
                    <div>
                      <div className="msg-meta">
                        {ts && <span className="tabular">{ts}</span>}
                        {who !== 'unknown' && <span>{who === 'lead' ? 'LEAD' : 'SALES'} · {s.speaker_name || names[who]}</span>}
                      </div>
                      <div className="msg-bubble">{highlight(s.text, q)}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </Card>
  );
}
