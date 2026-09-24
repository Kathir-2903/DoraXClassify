import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { AlertCircle, ArrowRight, BrainCircuit, CalendarClock, ListChecks, Loader2, MessageSquareText } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { parseError } from '../../services/api';
import { Logo } from '../../components/sidebar/Sidebar';

const DEMO = [
  { email: 'admin@classify.demo', password: 'Admin@123', label: 'Admin', who: 'Priya Raman' },
  { email: 'arjun@classify.demo', password: 'Sales@123', label: 'Sales', who: 'Arjun Mehta' },
  { email: 'neha@classify.demo', password: 'Sales@123', label: 'Sales', who: 'Neha Kapoor' },
  { email: 'kathirvelan@hclguvi.com', password: 'Sales@123', label: 'Sales', who: 'Kathir Velan S' },
];

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const showDemo = import.meta.env.DEV || import.meta.env.VITE_SHOW_DEMO_LOGINS === 'true';

  if (user) return <Navigate to={location.state?.from || '/dashboard'} replace />;

  const submit = async (e, creds) => {
    e?.preventDefault();
    const em = creds?.email ?? email;
    const pw = creds?.password ?? password;
    if (!em || !pw) {
      setError('Enter your email and password.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(em.trim(), pw);
      navigate(location.state?.from || '/dashboard', { replace: true });
    } catch (err) {
      setError(parseError(err, 'Sign in failed').message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <section className="login-brand">
        <Logo />
        <div className="login-hero">
          <h1>
            Every sales call,<br />turned into <em>intelligence.</em>
          </h1>
          <p>Schedule Classify meetings, capture what the lead actually said, and know exactly what to do next.</p>
          <ul className="login-flow">
            <li><CalendarClock /> Schedule &amp; invite by email</li>
            <li><MessageSquareText /> Recording → transcript, automatically</li>
            <li><BrainCircuit /> Gemini-powered objections, intent &amp; pitch coverage</li>
            <li><ListChecks /> Follow-ups that never slip</li>
          </ul>
        </div>
        <p className="login-brand-foot" style={{ color: 'rgba(255,255,255,.45)', fontSize: 12, position: 'relative', zIndex: 1 }}>
          Meeting → Intelligence
        </p>
      </section>
      <section className="login-form-wrap">
        <div className="login-card">
          <h2>Sign in</h2>
          <p className="muted" style={{ marginTop: 4, marginBottom: 20 }}>Use your Dora X Classify workspace account.</p>
          <form onSubmit={submit} className="stack" style={{ gap: 14 }} noValidate>
            <div className="field">
              <label htmlFor="email">Email</label>
              <input id="email" className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input id="password" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            {error && (
              <div className="notice error" role="alert"><AlertCircle /> {error}</div>
            )}
            <button className="btn btn-dark" type="submit" disabled={busy} style={{ height: 40 }}>
              {busy ? <Loader2 className="spin" /> : null} Sign in {!busy && <ArrowRight />}
            </button>
          </form>
          {showDemo && (
            <div className="demo-logins">
              <div className="section-label">Demo accounts (seed data)</div>
              {DEMO.map((d) => (
                <button key={d.email} onClick={() => submit(null, d)} disabled={busy}>
                  <span><strong>{d.who}</strong> <span className="muted">· {d.email}</span></span>
                  <span className="badge">{d.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
