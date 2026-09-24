import { render, screen } from '@testing-library/react';
import { AIBadge, FlagChip, LevelBadge, StatusBadge } from '../components/badges/Badge';
import { KpiCard } from '../components/cards/KpiCard';
import { JourneyStepper } from '../components/timeline/Timeline';
import { ProcessingProgress } from '../components/meeting/ProcessingProgress';
import { DataTable } from '../components/tables/DataTable';
import { meeting } from './fixtures';

describe('Meeting status', () => {
  it('renders friendly lifecycle labels', () => {
    render(<><StatusBadge state="WAITING_FOR_LEAD" /><StatusBadge state="NO_SHOW" /><StatusBadge state="AI_ANALYSIS_PROCESSING" /></>);
    expect(screen.getByText('Waiting for Lead')).toBeInTheDocument();
    expect(screen.getByText('No Show')).toBeInTheDocument();
    expect(screen.getByText('Analysis Processing')).toBeInTheDocument();
  });

  it('labels AI output and AI-derived flags', () => {
    render(<><AIBadge /><FlagChip flag="PRICE_CONCERN" ai /><LevelBadge level="high" prefix="Interest" /></>);
    expect(screen.getByText('AI generated')).toBeInTheDocument();
    expect(screen.getByText('Price concern')).toBeInTheDocument();
    expect(screen.getByLabelText('AI generated')).toBeInTheDocument();
    expect(screen.getByText('Interest: High')).toBeInTheDocument();
  });

  it('shows the sales-person journey with states', () => {
    render(<JourneyStepper steps={[
      { key: 'scheduled', label: 'Scheduled', state: 'done' },
      { key: 'joined', label: 'Waiting for Lead…', state: 'active' },
      { key: 'completed', label: 'Meeting Completed', state: 'pending' },
    ]} />);
    expect(screen.getByText('Scheduled')).toBeInTheDocument();
    expect(screen.getByText('Waiting for Lead…')).toBeInTheDocument();
    expect(screen.getByText('(active)')).toBeInTheDocument();
  });

  it('shows processing progress and marks no-shows as not needed', () => {
    const { rerender } = render(<ProcessingProgress meeting={meeting({ processing: { recording: { status: 'completed' }, transcript: { status: 'processing' }, analysis: { status: 'pending' } }, status: { meeting_completed: true } })} />);
    expect(screen.getByText('Processing…')).toBeInTheDocument();
    expect(screen.getByText('Final Intelligence')).toBeInTheDocument();
    rerender(<ProcessingProgress meeting={meeting({ status: { no_show: true }, processing: {} })} />);
    expect(screen.getByText('Lead did not join')).toBeInTheDocument();
    expect(screen.getAllByText('Not needed').length).toBeGreaterThan(0);
  });
});

describe('DataTable', () => {
  const columns = [
    { key: 'name', header: 'Name' },
    { key: 'status', header: 'Status' },
  ];
  const rows = [{ id: '1', name: 'Rohan Gupta', status: 'Scheduled' }];

  it('renders without crashing when no sort prop is passed and columns have no sortKey', () => {
    // Regression: DataTable used to read `sort.order` even when `sort` was
    // undefined, as long as `col.sortKey` was also undefined (both undefined
    // compared equal), crashing pages like Meetings that render unsortable columns.
    render(<DataTable columns={columns} rows={rows} />);
    expect(screen.getByText('Rohan Gupta')).toBeInTheDocument();
    expect(screen.getByText('Scheduled')).toBeInTheDocument();
  });

  it('still sorts correctly when sort/onSort are provided', () => {
    const sortable = [{ key: 'name', header: 'Name', sortKey: 'name' }];
    render(<DataTable columns={sortable} rows={rows} sort={{ key: 'name', order: 'asc' }} onSort={() => {}} />);
    expect(screen.getByText('Rohan Gupta')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Name/ })).toHaveAttribute('aria-sort', 'ascending');
  });
});

describe('Dashboard cards', () => {
  it('renders value, hint and AI marker', () => {
    render(<KpiCard label="Follow-ups Required" value={8} hint="7 overdue" ai />);
    expect(screen.getByText('Follow-ups Required')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('7 overdue')).toBeInTheDocument();
    expect(screen.getByText('AI')).toBeInTheDocument();
  });

  it('shows a skeleton while loading', () => {
    const { container } = render(<KpiCard label="Total Leads" value={10} loading />);
    expect(container.querySelector('.skeleton')).toBeInTheDocument();
    expect(screen.queryByText('10')).not.toBeInTheDocument();
  });
});
