import { useParams, useSearchParams } from 'react-router-dom';
import { FlaskConical, Video } from 'lucide-react';
import { Logo } from '../../components/sidebar/Sidebar';

/** Landing page for mock-mode join links. Real deployments use Classify's own links. */
export default function DemoMeeting() {
  const { uniqueId } = useParams();
  const [sp] = useSearchParams();
  const role = sp.get('as') === 'host' ? 'host' : 'lead';
  return (
    <div className="demo-room">
      <div style={{ maxWidth: 680 }}>
        <div style={{ display: 'inline-flex' }}><Logo /></div>
        <div className="tile">
          <div>
            <Video size={40} color="#fb923c" />
            <h1 style={{ fontSize: 22, marginTop: 12 }}>Demo Classify meeting room</h1>
            <p style={{ color: 'rgba(255,255,255,.65)', marginTop: 6 }}>Joining as {role}</p>
          </div>
        </div>
        <p style={{ color: 'rgba(255,255,255,.7)' }}>
          <FlaskConical size={14} style={{ verticalAlign: '-2px' }} /> This link was generated in <strong>mock mode</strong>. In production the lead receives the real Classify
          meeting link. Meeting ID <span className="mono">{uniqueId}</span>.
        </p>
      </div>
    </div>
  );
}
