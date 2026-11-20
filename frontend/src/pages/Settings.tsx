import { useState } from 'react'
import { toast } from 'sonner'
import { PageHeading, Panel } from '@/components/Panel'
import { useService } from '@/components/ServiceProvider'
import { apiBaseUrl } from '@/services/api'
import { reducedMotion, saveMotionPreference } from '@/lib/preferences'
import { Models } from './Analytics'

export function Settings() {
  const { health, refresh, capabilities } = useService()
  const [reduced, setReduced] = useState(reducedMotion)
  const status = { loading: 'Checking…', ok: 'Connected', degraded: 'Connected', offline: 'Unreachable' }[health.status]
  const database = { loading: 'Checking…', ok: 'Ready', degraded: 'Unavailable', offline: 'Unknown' }[health.status]
  return <>
    <PageHeading title="Settings" description="Review service connectivity, model configuration, and display preferences." />
    <div className="chart-grid">
      <Panel title="Backend connectivity" action={<button className="button" disabled={health.status === 'loading'} onClick={refresh}> Check connection</button>}>
        <dl className="detail-list" aria-live="polite">
          <div><dt>API address</dt><dd className="break-all">{apiBaseUrl}</dd></div>
          <div><dt>Inspection API</dt><dd>{status}</dd></div>
          <div><dt>SQLite</dt><dd>{database}</dd></div>
          <div><dt>API schema</dt><dd>{capabilities === 'ready' ? 'Available' : capabilities === 'loading' ? 'Checking…' : 'Unavailable'}</dd></div>
        </dl>
      </Panel>
      <Panel title="Application preferences">
        <label className="flex items-center gap-3 text-sm">
          <input type="checkbox" checked={reduced} onChange={(event) => {
            const checked = event.target.checked
            const saved = saveMotionPreference(checked)
            setReduced(checked)
            if (saved) toast.success('Preference saved')
            else toast.error('Browser storage unavailable. Preference applied for this page session.')
          }} /> Reduce interface motion
        </label>
        <p className="mt-3 text-sm text-muted-foreground">This preference is stored in this browser.</p>
      </Panel>
    </div>
    <Models thresholds />
  </>
}
