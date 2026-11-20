import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'
import { Shell } from '@/components/Shell'
import { Workspace } from '@/pages/Workspace'
import { ServiceProvider } from '@/components/ServiceProvider'
import { Batch } from '@/pages/Batch'
import { History } from '@/pages/History'
import { Inspector } from '@/pages/Inspector'
import { Live } from '@/pages/Live'
import { Skeleton } from '@/components/ui/skeleton'
import { Policies } from '@/pages/Policies'
import { applyMotionPreference, reducedMotion } from '@/lib/preferences'
import './styles.css'

const AnalyticsPage = lazy(() => import('@/pages/Analytics').then((module) => ({ default: module.AnalyticsPage })))
const Settings = lazy(() => import('@/pages/Settings').then((module) => ({ default: module.Settings })))
const Evaluation = lazy(() => import('@/pages/Evaluation').then((module) => ({ default: module.EvaluationPage })))

function App() {
  return <BrowserRouter>
    <ServiceProvider>
      <Suspense fallback={<Skeleton className="m-6 h-24" aria-label="Loading page" />}>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<AnalyticsPage key="dashboard" dashboard />} />
          <Route path="inspector" element={<Inspector />} />
          <Route path="batch" element={<Batch />} />
          <Route path="live" element={<Live />} />
          <Route path="history" element={<History />} />
          <Route path="analytics" element={<AnalyticsPage key="analytics" />} />
          <Route path="evaluation" element={<Evaluation />} />
          <Route path="settings" element={<Settings />} />
          <Route path="terms" element={<Policies />} />
          <Route path="privacy" element={<Policies privacy />} />
          <Route path="overview" element={<Workspace />} />
          <Route path="system" element={<Workspace system />} />
          <Route path="*" element={<><h1>Page not found</h1><Link to="/">Return to overview</Link></>} />
        </Route>
      </Routes>
      </Suspense>
      <Toaster theme="light" icons={{ success: null, error: null, warning: null, info: null, loading: null }} toastOptions={{ style: { borderRadius: 0, boxShadow: 'none', background: 'var(--color-card)', border: '1px solid var(--color-border)', color: 'var(--color-foreground)' } }} />
    </ServiceProvider>
  </BrowserRouter>
}

applyMotionPreference(reducedMotion())
createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
