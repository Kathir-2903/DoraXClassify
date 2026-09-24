/** Meeting lifecycle → label + tone. Tones map to badge classes. */
export const MEETING_STATES = {
  DRAFT: { label: 'Draft', tone: 'neutral' },
  SCHEDULED: { label: 'Scheduled', tone: 'info' },
  INVITATION_SENT: { label: 'Scheduled', tone: 'info' },
  WAITING_FOR_LEAD: { label: 'Waiting for Lead', tone: 'warning', pulse: true },
  LEAD_JOINED: { label: 'Lead Joined', tone: 'success' },
  SALES_PERSON_JOINED: { label: 'Sales Person Joined', tone: 'info' },
  IN_PROGRESS: { label: 'In Progress', tone: 'success', pulse: true },
  MEETING_COMPLETED: { label: 'Completed', tone: 'success' },
  RECORDING_PROCESSING: { label: 'Recording Processing', tone: 'accent', pulse: true },
  TRANSCRIPT_PROCESSING: { label: 'Transcript Processing', tone: 'accent', pulse: true },
  AI_ANALYSIS_PROCESSING: { label: 'Analysis Processing', tone: 'ai', pulse: true },
  ANALYSIS_COMPLETED: { label: 'Analysis Complete', tone: 'success' },
  FOLLOW_UP_REQUIRED: { label: 'Follow-up Required', tone: 'warning' },
  CLOSED: { label: 'Closed', tone: 'neutral' },
  NO_SHOW: { label: 'No Show', tone: 'error' },
  FAILED: { label: 'Failed', tone: 'error' },
};

export const MEETING_STATUS_FILTERS = [
  { value: 'SCHEDULED,INVITATION_SENT,WAITING_FOR_LEAD', label: 'Scheduled' },
  { value: 'LEAD_JOINED,IN_PROGRESS,SALES_PERSON_JOINED', label: 'In progress' },
  { value: 'MEETING_COMPLETED,ANALYSIS_COMPLETED,FOLLOW_UP_REQUIRED,CLOSED', label: 'Completed' },
  { value: 'RECORDING_PROCESSING,TRANSCRIPT_PROCESSING,AI_ANALYSIS_PROCESSING', label: 'Processing' },
  { value: 'FOLLOW_UP_REQUIRED', label: 'Follow-up required' },
  { value: 'NO_SHOW', label: 'No show' },
  { value: 'FAILED', label: 'Failed' },
];

export function meetingState(state) {
  return MEETING_STATES[state] || { label: state || 'Unknown', tone: 'neutral' };
}

export const LEAD_STATUSES = {
  new: { label: 'New', tone: 'neutral' },
  meeting_scheduled: { label: 'Meeting Scheduled', tone: 'info' },
  engaged: { label: 'Engaged', tone: 'success' },
  follow_up: { label: 'Follow-up', tone: 'warning' },
  no_show: { label: 'No Show', tone: 'error' },
  won: { label: 'Won', tone: 'success' },
  lost: { label: 'Lost', tone: 'neutral' },
};

export const LEVELS = {
  high: { label: 'High', tone: 'success' },
  medium: { label: 'Medium', tone: 'warning' },
  low: { label: 'Low', tone: 'error' },
  unknown: { label: 'Unknown', tone: 'neutral' },
};

export const STAGE_STATUS = {
  pending: { label: 'Pending', tone: 'neutral' },
  processing: { label: 'Processing', tone: 'accent', pulse: true },
  completed: { label: 'Completed', tone: 'success' },
  failed: { label: 'Failed', tone: 'error' },
  skipped: { label: 'Skipped', tone: 'neutral' },
  unavailable: { label: 'Unavailable', tone: 'warning' },
};

export const NOTIFICATION_STATUS = {
  pending: { label: 'Pending', tone: 'neutral' },
  sent: { label: 'Sent', tone: 'success' },
  delivered: { label: 'Delivered', tone: 'success' },
  failed: { label: 'Failed', tone: 'error' },
  skipped: { label: 'Not sent', tone: 'neutral' },
};

export const FLAG_LABELS = {
  MEETING_SCHEDULED: 'Meeting scheduled',
  INVITATION_SENT: 'Invitation sent',
  EMAIL_SENT: 'Email sent',
  EMAIL_FAILED: 'Email failed',
  LEAD_JOINED: 'Lead joined',
  SALES_PERSON_JOINED: 'Sales person joined',
  MEETING_STARTED: 'Meeting started',
  MEETING_COMPLETED: 'Meeting completed',
  MEETING_DATA_PENDING: 'Awaiting Classify data',
  ATTENDANCE_SYNC_FAILED: 'Attendance sync failed',
  NO_SHOW: 'No show',
  RECORDING_AVAILABLE: 'Recording available',
  RECORDING_MISSING: 'Recording missing',
  TRANSCRIPT_AVAILABLE: 'Transcript available',
  ANALYSIS_PENDING: 'Analysis pending',
  ANALYSIS_COMPLETE: 'Analysis complete',
  PITCH_COMPLETED: 'Pitch completed',
  PITCH_INCOMPLETE: 'Pitch incomplete',
  PRICING_DISCUSSED: 'Pricing discussed',
  PRICING_NOT_DISCUSSED: 'Pricing not discussed',
  OBJECTION_RAISED: 'Objection raised',
  NO_OBJECTION_DETECTED: 'No objection detected',
  FOLLOW_UP_REQUIRED: 'Follow-up required',
  FOLLOW_UP_NOT_REQUIRED: 'No follow-up needed',
  HIGH_INTEREST_SIGNAL: 'High interest signal',
  LOW_INTEREST_SIGNAL: 'Low interest signal',
  PURCHASE_INTENT_SIGNAL: 'Purchase intent signal',
  PRICE_CONCERN: 'Price concern',
  TIME_CONCERN: 'Time concern',
  DECISION_PENDING: 'Decision pending',
  REQUESTED_MORE_INFORMATION: 'Requested more info',
  RECORDING_PROCESSING: 'Recording processing',
  TRANSCRIPT_PROCESSING: 'Transcript processing',
  AI_ANALYSIS_PROCESSING: 'AI analysis processing',
  RECORDING_FAILED: 'Recording failed',
  TRANSCRIPT_FAILED: 'Transcript failed',
  AI_ANALYSIS_FAILED: 'AI analysis failed',
  WEBHOOK_RECEIVED: 'Webhook received',
  WEBHOOK_PROCESSING_FAILED: 'Webhook processing failed',
};

const NEGATIVE = new Set([
  'EMAIL_FAILED', 'NO_SHOW', 'RECORDING_MISSING', 'RECORDING_FAILED', 'TRANSCRIPT_FAILED',
  'AI_ANALYSIS_FAILED', 'WEBHOOK_PROCESSING_FAILED',
]);
const CAUTION = new Set([
  'MEETING_DATA_PENDING', 'PITCH_INCOMPLETE', 'PRICING_NOT_DISCUSSED', 'OBJECTION_RAISED', 'FOLLOW_UP_REQUIRED',
  'LOW_INTEREST_SIGNAL', 'PRICE_CONCERN', 'TIME_CONCERN', 'DECISION_PENDING', 'ANALYSIS_PENDING',
]);
const ACTIVE = new Set(['RECORDING_PROCESSING', 'TRANSCRIPT_PROCESSING', 'AI_ANALYSIS_PROCESSING']);

export function flagTone(flag) {
  if (NEGATIVE.has(flag)) return 'error';
  if (CAUTION.has(flag)) return 'warning';
  if (ACTIVE.has(flag)) return 'accent';
  return 'success';
}

export const FLAG_CATEGORIES = [
  { key: 'meeting', label: 'Meeting' },
  { key: 'sales', label: 'Sales' },
  { key: 'lead', label: 'Lead' },
  { key: 'technical', label: 'Technical' },
];

export const OBJECTION_LABELS = {
  price: 'Pricing',
  time: 'Time commitment',
  approval: 'Needs approval',
  competition: 'Competition',
  uncertainty: 'Uncertainty',
  relevance: 'Relevance',
  other: 'Other',
};
