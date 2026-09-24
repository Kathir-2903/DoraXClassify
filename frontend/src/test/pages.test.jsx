import { screen, within } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from './utils';
import { lead, meeting } from './fixtures';

vi.mock('../services/leadApi', () => ({
  leadApi: {
    list: vi.fn(async () => ({ items: [lead], total: 1, page: 1, page_size: 20 })),
    get: vi.fn(async () => lead),
    analytics: vi.fn(async () => ({
      intelligence: lead.intelligence,
      summary: { total_meetings: 2, completed_meetings: 2, no_shows: 0, total_conversation_seconds: 3000, average_duration_seconds: 1500,
                 first_interaction: '2026-09-10T05:30:00Z', latest_interaction: '2026-09-20T11:30:00Z', open_follow_ups: 1 },
      history: [
        { meeting_id: 'm0', sequence: 1, label: 'Meeting 1', start_time: '2026-09-10T05:30:00Z', status: 'ANALYSIS_COMPLETED', duration_seconds: 1080, interest_level: 'medium', purchase_intent: 'low', engagement_level: 'medium', objection_categories: ['time'], follow_up_required: false, analysis_available: true },
        { meeting_id: 'm1', sequence: 2, label: 'Meeting 2', start_time: '2026-09-20T11:30:00Z', status: 'FOLLOW_UP_REQUIRED', duration_seconds: 1920, interest_level: 'high', purchase_intent: 'medium', engagement_level: 'high', objection_categories: ['price'], follow_up_required: true, analysis_available: true },
      ],
      objections_over_time: [],
      follow_up_history: [{ id: 'f1', status: 'pending', recommended_action: 'Send EMI breakdown', reason: 'Asked about EMI', due_date: '2026-09-24T04:30:00Z', ai_generated: true }],
      journey: [
        { event: 'lead_created', label: 'Lead Created', at: '2026-09-01T04:30:00Z', source: 'user' },
        { event: 'objection', label: 'Objection: Pricing', at: '2026-09-20T12:10:00Z', source: 'ai' },
      ],
    })),
    salesPeople: vi.fn(async () => [{ id: 'u1', name: 'Arjun Mehta', role: 'sales' }]),
    exportCsv: vi.fn(),
  },
}));
vi.mock('../services/analyticsApi', () => ({
  analyticsApi: { settings: vi.fn(async () => ({ lead_sources: ['Website'], products: [], integrations: { classify: { mock_mode: false } } })) },
  adminApi: {},
}));
vi.mock('../services/meetingApi', () => ({
  meetingApi: {
    get: vi.fn(async () => meeting()),
    transcript: vi.fn(async () => ({
      available: true, source: 'gemini', ai_generated: true, has_speaker_labels: true, has_timestamps: true, total_segments: 2,
      actual_start: '2026-09-20T11:32:00Z',
      segments: [
        { index: 0, speaker: 'sales', speaker_name: 'Arjun', start_seconds: 4, end_seconds: 9, text: 'Welcome to the demo' },
        { index: 1, speaker: 'lead', speaker_name: 'Rahul', start_seconds: 12, end_seconds: 16, text: 'Can I pay in installments?' },
      ],
    })),
    recording: vi.fn(async () => ({ playable: false, is_mock: true })),
    list: vi.fn(async () => ({ items: [], total: 0, page: 1, page_size: 20 })),
  },
  followUpApi: {},
}));

const { default: Leads } = await import('../pages/Leads/Leads');
const { default: LeadDetails } = await import('../pages/LeadDetails/LeadDetails');
const { default: MeetingDetails } = await import('../pages/MeetingDetails/MeetingDetails');

describe('Lead table', () => {
  it('renders lead rows with status, AI levels and actions', async () => {
    renderWithProviders(<Leads />, { route: '/leads' });
    expect(await screen.findByText('Rahul Kumar')).toBeInTheDocument();
    const table = screen.getByRole('table');
    expect(within(table).getByText('rahul@example.com')).toBeInTheDocument();
    expect(within(table).getByText('Follow-up Required')).toBeInTheDocument();
    expect(within(table).getAllByText('High').length).toBeGreaterThan(0);
    expect(within(table).getByRole('button', { name: /Schedule Video Call/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Export CSV/i })).toBeInTheDocument();
  });
});

describe('Lead details', () => {
  it('shows profile, meeting history, journey and follow-ups', async () => {
    renderWithProviders(<LeadDetails />, { route: '/leads/l1', path: '/leads/:leadId' });
    expect(await screen.findByRole('heading', { name: 'Rahul Kumar' })).toBeInTheDocument();
    expect((await screen.findAllByText('Meeting 2')).length).toBeGreaterThan(0);
    expect(screen.getByText('Lead Intelligence')).toBeInTheDocument();
    expect(screen.getByText('Signals over time')).toBeInTheDocument();
    expect(screen.getByText('Objection: Pricing')).toBeInTheDocument();
    expect(screen.getAllByText('Send EMI breakdown').length).toBeGreaterThan(0);
  });
});

describe('Meeting details', () => {
  it('separates explicit statements from AI interpretation and never fabricates talk time', async () => {
    renderWithProviders(<MeetingDetails />, { route: '/meetings/m1', path: '/meetings/:meetingId' });
    expect(await screen.findByText('Meeting Intelligence')).toBeInTheDocument();
    expect(screen.getByText('Lead explicitly said')).toBeInTheDocument();
    expect(screen.getByText('“I need to discuss this with my manager.”')).toBeInTheDocument();
    expect(screen.getByText('AI interpretation')).toBeInTheDocument();
    expect(screen.getByText('Decision authority may not be with the lead.')).toBeInTheDocument();
    expect(screen.getByText('AI Recommendation')).toBeInTheDocument();
    expect(screen.getByText('Send detailed pricing breakdown.')).toBeInTheDocument();
    expect(screen.getAllByText('Speaker talk-time data unavailable').length).toBeGreaterThan(0);
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    expect(await screen.findByText('Can I pay in installments?', { selector: '.msg-bubble' })).toBeInTheDocument();
    expect(screen.getByText('Email failed')).toBeInTheDocument();
  });

  it('offers an attendance sync after the meeting ends and shows its status', async () => {
    const { meetingApi } = await import('../services/meetingApi');
    meetingApi.get.mockResolvedValueOnce(meeting({
      status: { overall: 'WAITING_FOR_LEAD', meeting_created: true, meeting_completed: false, no_show: false },
      analysis_result: null, attendance: null,
      attendance_sync: { status: 'waiting', attempt_count: 2, last_message: 'Class in progress. Please check back after the class ends.' },
      processing: { recording: { status: 'pending' }, transcript: { status: 'pending' }, analysis: { status: 'pending' } },
    }));
    renderWithProviders(<MeetingDetails />, { route: '/meetings/m1', path: '/meetings/:meetingId' });
    expect(await screen.findByRole('button', { name: /Sync attendance/i })).toBeInTheDocument();
    expect(screen.getByText('Waiting — Classify reports the class in progress (attempt 2)')).toBeInTheDocument();
  });

  it('shows the no-show state instead of analysis', async () => {
    const { meetingApi } = await import('../services/meetingApi');
    meetingApi.get.mockResolvedValueOnce(meeting({
      status: { overall: 'NO_SHOW', no_show: true, meeting_created: true }, analysis_result: null, attendance: null,
      processing: { recording: { status: 'skipped' }, transcript: { status: 'skipped' }, analysis: { status: 'skipped' } },
    }));
    renderWithProviders(<MeetingDetails />, { route: '/meetings/m1', path: '/meetings/:meetingId' });
    expect(await screen.findByText('Lead did not join.')).toBeInTheDocument();
    expect(screen.queryByText('Meeting Intelligence')).not.toBeInTheDocument();
  });
});
