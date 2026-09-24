import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';
import { EmptyState } from '../../components/common/States';

export default function NotFound() {
  return (
    <div className="page">
      <EmptyState icon={Compass} title="Page not found" description="The page you were looking for doesn't exist." action={<Link className="btn btn-primary" to="/dashboard">Go to dashboard</Link>} />
    </div>
  );
}
