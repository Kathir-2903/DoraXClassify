import { Sparkles } from 'lucide-react';

/** Cards for AI insights; never shows a value unless the backend has enough data. */
export function InsightCards({ insights }) {
  const items = [
    ['top_objection', 'Top Objection', '⚠'],
    ['top_topic', 'Most Discussed Topic', '💬'],
    ['top_question', 'Most Common Question', '❓'],
    ['top_product', 'Most Requested Product', '🎯'],
    ['top_follow_up_reason', 'Most Common Follow-up Reason', '📌'],
  ];
  return (
    <div className="insight-grid">
      {items.map(([key, label, emoji]) => {
        const v = insights?.[key];
        const ok = v?.available;
        return (
          <div key={key} className={`insight-card ${ok ? '' : 'na'}`}>
            <span className="insight-label">
              <span aria-hidden="true">{emoji}</span> {label}
            </span>
            <span className="insight-value">{ok ? v.value : v?.reason || 'Not enough data yet'}</span>
            {ok && (
              <span className="cell-secondary row" style={{ gap: 4 }}>
                <Sparkles size={11} color="var(--ai)" aria-label="AI generated" /> {v.count} meetings
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
