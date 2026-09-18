import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { Card, EmptyState } from '../components/ui'

export default function NotFound() {
  return (
    <Card>
      <EmptyState
        icon={Compass}
        title="Page not found"
        description="The page you were looking for does not exist in this portal."
        action={
          <Link to="/dashboard" className="btn-primary btn-sm">
            Back to dashboard
          </Link>
        }
      />
    </Card>
  )
}
