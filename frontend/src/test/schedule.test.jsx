import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { ScheduleMeetingModal, validateSchedule } from '../components/modals/ScheduleMeetingModal';
import { renderWithProviders } from './utils';
import { lead, meeting } from './fixtures';
import { todayLocalISO } from '../utils/date';

// Plain functions (not vi.fn) so a rejected promise is only observed by the component.
const calls = [];
let impl = async () => ({});
vi.mock('../services/meetingApi', () => ({
  meetingApi: { schedule: (...a) => { calls.push(a); return impl(...a); }, resendEmail: vi.fn() },
  followUpApi: {},
}));

describe('validateSchedule', () => {
  const tomorrow = todayLocalISO(1);
  it('requires a future start (at least a minute ahead)', () => {
    expect(validateSchedule({ date: '2020-01-01', time: '10:00', duration: 30, minDuration: 1 }).time).toMatch(/future/);
    expect(validateSchedule({ date: tomorrow, time: '10:00', duration: 30, minDuration: 1 })).toEqual({});
  });
  it('keeps minimum attendance separate from meeting duration', () => {
    expect(validateSchedule({ date: tomorrow, time: '10:00', duration: 30, minDuration: 45 }).minDuration).toMatch(/cannot exceed/);
    expect(validateSchedule({ date: tomorrow, time: '10:00', duration: 0, minDuration: 1 }).duration).toMatch(/at least 1 minute/);
    expect(validateSchedule({ date: tomorrow, time: '10:00', duration: 1, minDuration: 1 })).toEqual({});
    expect(validateSchedule({ date: tomorrow, time: '10:00', duration: 30, minDuration: 0 }).minDuration).toMatch(/at least 1 minute/);
  });
});

describe('Schedule meeting modal', () => {
  beforeEach(() => {
    calls.length = 0;
    impl = async () => ({});
  });

  it('shows lead details and submits with an idempotency key', async () => {
    const created = meeting({
      status: { overall: 'INVITATION_SENT', meeting_created: true },
      classify: { student_join_url: 'https://join.example/x' },
      notifications: { email: { status: 'sent', sent_at: '2026-09-19T10:00:00Z' } },
    });
    impl = async () => created;
    renderWithProviders(<ScheduleMeetingModal open lead={lead} onClose={() => {}} />);
    expect(screen.getByText('Schedule Classify Meeting')).toBeInTheDocument();
    expect(screen.getByText('rahul@example.com')).toBeInTheDocument();
    expect(screen.getByLabelText('Minimum Attendance')).toHaveValue(1);

    await userEvent.click(screen.getByRole('button', { name: /Schedule & Send Meeting/i }));
    await waitFor(() => expect(calls).toHaveLength(1));
    const [body, key] = calls[0];
    expect(body).toMatchObject({ lead_id: 'l1', duration_minutes: 30, min_duration: 1, timezone: 'Asia/Kolkata', send_email: true });
    expect(body).not.toHaveProperty('send_whatsapp');
    expect(key).toMatch(/^ui-/);
    expect(await screen.findByText('Meeting scheduled')).toBeInTheDocument();
    expect(screen.getByText('Sent')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Copy lead link/i })).toBeInTheDocument();
  });

  it('renders the friendly Classify error with reason and hint', async () => {
    impl = async () => {
      throw Object.assign(new Error('Request failed with status code 400'), { response: { status: 400, data: { error: { code: 'classify_validation_error', message: 'Unable to schedule meeting.', reason: 'Meeting start time must be in the future.', hint: 'Please select another time.' } } } });
    };
    renderWithProviders(<ScheduleMeetingModal open lead={lead} onClose={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: /Schedule & Send Meeting/i }));
    const alert = (await screen.findAllByRole('alert')).find((el) => el.classList.contains('notice'));
    expect(alert).toHaveTextContent('Unable to schedule meeting.');
    expect(alert).toHaveTextContent('Meeting start time must be in the future.');
    expect(alert).toHaveTextContent('Please select another time.');
  });

  it('blocks invalid input client-side without calling the API', async () => {
    renderWithProviders(<ScheduleMeetingModal open lead={lead} onClose={() => {}} />);
    const min = screen.getByLabelText('Minimum Attendance');
    await userEvent.clear(min);
    await userEvent.type(min, '90');
    await userEvent.click(screen.getByRole('button', { name: /Schedule & Send Meeting/i }));
    expect(await screen.findByText(/cannot exceed the meeting duration/)).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });
});
