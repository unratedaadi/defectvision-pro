import { NavLink, Outlet } from 'react-router-dom'
import { useService } from './ServiceProvider'
import { apiBaseUrl } from '@/services/api'

const navigation = [
  ['/', 'Dashboard'],
  ['/inspector', 'AI Inspector'],
  ['/batch', 'Batch Inspection'],
  ['/live', 'Live Inspection'],
  ['/history', 'Inspection History'],
  ['/analytics', 'Analytics & Reports'],
  ['/evaluation', 'Model Evaluation'],
  ['/settings', 'Settings'],
  ['/overview', 'Product catalog'],
  ['/system', 'System status'],
] as const

export function Shell() {
  const { health } = useService()
  const status = { ok: 'API connected', degraded: 'Database unavailable', offline: 'API unreachable', loading: 'Checking API…' }[health.status]
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">Skip to content</a>
      <aside className="sidebar">
        <div className="sidebar-brand">DefectVision Pro</div>
        <nav aria-label="Workspace" className="sidebar-nav">
          {navigation.map(([path, label]) => <NavLink key={path} to={path} end className="nav-item">{label}</NavLink>)}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-status" role="status"><span data-ready={health.status === 'ok'} />{status}</div>
          <nav aria-label="Application policies" className="policy-links">
            <NavLink to="/terms">Terms of Use</NavLink>
            <NavLink to="/privacy">Privacy</NavLink>
          </nav>
        </div>
      </aside>
      <main id="main-content" tabIndex={-1} className="main-content">
        {!apiBaseUrl && <p role="status" className="empty-state">The inspection server is not connected to this deployment. Image analysis, saved records, and reports will be available when the server is connected.</p>}
        <Outlet />
      </main>
    </div>
  )
}
