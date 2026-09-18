import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { Loader } from './components/ui'
import { useAuth } from './context/AuthContext'
import ApiConfiguration from './pages/ApiConfiguration'
import Cameras from './pages/Cameras'
import Challans from './pages/Challans'
import Dashboard from './pages/Dashboard'
import LiveMonitoring from './pages/LiveMonitoring'
import Login from './pages/Login'
import MaintenanceAlerts from './pages/MaintenanceAlerts'
import NetworkStatus from './pages/NetworkStatus'
import NotFound from './pages/NotFound'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Users from './pages/Users'
import Vehicles from './pages/Vehicles'
import Violations from './pages/Violations'
import ViolationRules from './pages/ViolationRules'

function RequireAuth({ children, adminOnly = false }) {
  const { isAuthenticated, isAdmin, loading } = useAuth()
  if (loading) return <Loader label="Restoring your session..." className="min-h-screen" />
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (adminOnly && !isAdmin) return <Navigate to="/dashboard" replace />
  return children
}

export default function App() {
  const { isAuthenticated, loading } = useAuth()

  return (
    <Routes>
      <Route
        path="/login"
        element={
          loading ? (
            <Loader label="Loading..." className="min-h-screen" />
          ) : isAuthenticated ? (
            <Navigate to="/dashboard" replace />
          ) : (
            <Login />
          )
        }
      />

      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/live" element={<LiveMonitoring />} />
        <Route path="/cameras" element={<Cameras />} />
        <Route path="/violations" element={<Violations />} />
        <Route path="/challans" element={<Challans />} />
        <Route path="/vehicles" element={<Vehicles />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/network" element={<NetworkStatus />} />
        <Route path="/alerts" element={<MaintenanceAlerts />} />
        <Route path="/rules" element={<ViolationRules />} />
        <Route path="/settings" element={<Settings />} />
        <Route
          path="/api-configuration"
          element={
            <RequireAuth adminOnly>
              <ApiConfiguration />
            </RequireAuth>
          }
        />
        <Route
          path="/users"
          element={
            <RequireAuth adminOnly>
              <Users />
            </RequireAuth>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
