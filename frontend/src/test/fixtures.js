export const salesUser = { id: 'u1', name: 'Arjun Mehta', email: 'arjun@classify.demo', role: 'sales', is_active: true };

export const lead = {
  id: 'l1',
  name: 'Rahul Kumar',
  email: 'rahul@example.com',
  phone: '+919876543210',
  company: 'Paytm',
  lead_source: 'Website',
  interested_product: 'Full Stack Development',
  lead_status: 'follow_up',
  is_demo: true,
  created_at: '2026-09-01T04:30:00Z',
  last_activity_at: '2026-09-20T04:30:00Z',
  sales_person: { id: 'u1', name: 'Arjun Mehta' },
  intelligence: {
    meetings_count: 2, last_meeting_at: '2026-09-20T11:30:00Z', last_meeting_status: 'FOLLOW_UP_REQUIRED',
    last_duration_seconds: 1920, interest_level: 'high', purchase_intent: 'medium', engagement_level: 'high',
    main_concern: 'Pricing', next_action: 'Send EMI breakdown', follow_up_required: true, follow_up_due: '2026-09-24T04:30:00Z',
    analysis_status: 'completed',
  },
};

const coverage = ['Introduction', 'Pricing', 'Placement'].map((topic, i) => ({ topic, covered: i !== 2, confidence: 0.9, evidence: 'q' }));

export const analysisResult = {
  summary: 'The sales representative explained pricing and placement. The lead asked about EMI.',
  conversation_language: 'English',
  lead_intent: 'Move into a developer role',
  interest_level: 'high',
  purchase_intent: 'medium',
  lead_sentiment: 'positive',
  engagement: { level: 'high', signals: [], rationale: '' },
  topics_discussed: ['Pricing', 'Placement'],
  lead_questions: [{ question: 'Can I pay in installments?', answered: true, evidence: 'EMI offered' }],
  lead_objections: [{ objection: 'Fee feels high', category: 'price', evidence: '"Ninety thousand is a lot"', handled: true, handling_notes: 'EMI' }],
  lead_requirements: ['Placement support'],
  pain_points: ['Inconsistent self-study'],
  interests: ['EMI options'],
  competitor_mentions: [],
  pricing_discussion: { discussed: true, details: '₹90,000' },
  product_discussion: [],
  sales_pitch: { pitch_detected: true, topics_covered: ['Pricing'], missing_topics: ['Placement'] },
  pitch_coverage: coverage,
  objection_handling: 'Handled with EMI',
  follow_up: { required: true, reason: 'Asked about EMI', recommended_next_action: 'Send detailed pricing breakdown.', suggested_timing: 'Within 24 hours' },
  action_items: [{ owner: 'sales', item: 'Send EMI breakdown', due_hint: 'Today' }],
  risk_signals: [{ signal: 'Price concern', evidence: 'q' }],
  positive_signals: [{ signal: 'Asked enrollment process', evidence: 'q' }],
  explicit_statements: [{ speaker: 'lead', quote: 'I need to discuss this with my manager.', topic: 'Decision' }],
  ai_interpretations: [{ interpretation: 'Decision authority may not be with the lead.', basis: 'Manager mention', confidence: 0.7 }],
  meeting_outcome: 'Interested',
  confidence: 0.86,
};

const stage = (status) => ({ status, attempt_count: 1, error_message: null });

export function meeting(overrides = {}) {
  return {
    id: 'm1',
    lead_id: 'l1',
    label: 'Sales Discussion - Rahul Kumar',
    is_demo: false,
    lead_snapshot: { name: 'Rahul Kumar', email: 'rahul@example.com', phone: '+919876543210' },
    sales_person_snapshot: { name: 'Arjun Mehta', email: 'arjun@classify.demo' },
    classify: { unique_id: 'uuid-1', student_join_url: null, host_join_url: null, is_mock: false },
    schedule: { start_time: '2026-09-20T11:30:00Z', end_time: '2026-09-20T12:00:00Z', timezone: 'Asia/Kolkata', duration_minutes: 30, min_duration: 1 },
    status: {
      overall: 'FOLLOW_UP_REQUIRED', meeting_created: true, invitation_sent: true, lead_joined: true, meeting_completed: true,
      recording_available: true, transcript_available: true, analysis_completed: true, follow_up_required: true, no_show: false,
    },
    status_label: 'Follow-up Required',
    attendance: { actual_start: '2026-09-20T11:32:00Z', actual_end: '2026-09-20T12:04:00Z', duration_seconds: 1920, lead: { attended_seconds: 1860 } },
    processing: { recording: stage('completed'), transcript: stage('completed'), analysis: stage('completed'), active: false },
    notifications: { email: { status: 'failed', error: 'SMTP timeout' } },
    flags: ['MEETING_SCHEDULED', 'EMAIL_FAILED', 'PRICE_CONCERN'],
    flag_details: [
      { key: 'MEETING_SCHEDULED', category: 'meeting', ai_generated: false },
      { key: 'EMAIL_FAILED', category: 'meeting', ai_generated: false },
      { key: 'PRICE_CONCERN', category: 'lead', ai_generated: true },
    ],
    timeline: [
      { key: 'meeting_scheduled', label: 'Meeting Scheduled', level: 'success', source: 'classify', at: '2026-09-19T10:00:00Z' },
      { key: 'analysis_completed', label: 'AI Analysis Complete', level: 'success', source: 'gemini', at: '2026-09-20T12:10:00Z', ai_generated: true },
    ],
    journey: [
      { key: 'scheduled', label: 'Scheduled', state: 'done', at: '2026-09-19T10:00:00Z' },
      { key: 'analysis', label: 'AI Analysis Ready', state: 'done', at: '2026-09-20T12:10:00Z' },
      { key: 'follow_up', label: 'Follow-up Required', state: 'warning' },
    ],
    analysis: { snapshot: { interest_level: 'high' }, version_count: 1 },
    analysis_result: { id: 'a1', result: analysisResult, model: 'gemini-2.5-flash', prompt_version: '1.0', created_at: '2026-09-20T12:10:00Z' },
    transcript: { segment_count: 2 },
    call_quality: {
      total_duration_seconds: { value: 1920, available: true, source: 'classify' },
      lead_talk_seconds: { value: null, available: false, note: 'Speaker talk-time data unavailable' },
      sales_talk_seconds: { value: null, available: false, note: 'Speaker talk-time data unavailable' },
      talk_ratio: { value: null, available: false },
      interruptions: { value: null, available: false, note: 'Speaker talk-time data unavailable' },
      silence_seconds: { value: null, available: false, note: 'Speaker talk-time data unavailable' },
      questions: { value: 1, available: true, ai_generated: true },
      objections: { value: 1, available: true, ai_generated: true },
      topics_discussed: { value: 2, available: true, ai_generated: true },
      pitch_coverage: { value: { covered: 2, total: 3 }, available: true, ai_generated: true },
      follow_up_required: { value: true, available: true, ai_generated: true },
    },
    analysis_versions: [],
    follow_ups: [],
    polling: { active: false, interval_seconds: 5 },
    ...overrides,
  };
}
