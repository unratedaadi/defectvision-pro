import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { toast } from 'sonner'
import { Empty, PageHeading, Panel, ResourceState } from '@/components/Panel'
import { CategorySelect } from '@/components/InspectionControls'
import { useService } from '@/components/ServiceProvider'
import { useResource } from '@/hooks/useResource'
import { download } from '@/lib/export'
import { downloadReport, endpoints, getAnalytics, getModels } from '@/services/api'

const tooltipStyle = { background: 'var(--color-card)', borderColor: 'var(--color-border)', color: 'var(--color-foreground)' }

function categoryName(category: string) {
  return category === 'metal_nut' ? 'Metal Nut' : category.charAt(0).toUpperCase() + category.slice(1)
}

export function Models({ thresholds = false }: { thresholds?: boolean }) {
  const { supports } = useService()
  const models = useResource(supports(endpoints.models, 'get') ? getModels : null)
  return <Panel title={thresholds ? 'Models and category thresholds' : 'Model status'}>
    {models.data ? models.data.length ? <div className="table-scroll"><table>
      <thead><tr><th>Category</th><th>Status</th><th>Version</th>{thresholds && <th>Threshold</th>}<th>AUROC</th></tr></thead>
      <tbody>{models.data.map((model) => <tr key={model.category}>
        <td>{categoryName(model.category)}</td><td className="capitalize">{model.ready ? 'Ready' : model.status}</td><td>{model.version ?? 'N/A'}</td>
        {thresholds && <td>{model.threshold ?? 'N/A'}</td>}<td>{model.auroc?.toFixed(3) ?? 'N/A'}</td>
      </tr>)}</tbody>
    </table></div> : <Empty>No model records have been published.</Empty> :
      <ResourceState state={models.state} unavailable="Checkpoint status, thresholds, and evaluation metrics are unavailable on this backend." />}
  </Panel>
}

export function AnalyticsPage({ dashboard = false }: { dashboard?: boolean }) {
  const [days, setDays] = useState(30)
  const [category, setCategory] = useState('')
  const [exporting, setExporting] = useState(false)
  const { supports } = useService()
  const load = useCallback((signal: AbortSignal) => getAnalytics(days, category, signal), [days, category])
  const analytics = useResource(supports(endpoints.dashboard, 'get') ? load : null)
  const reportAvailable = supports(endpoints.report, 'get')
  const data = analytics.data
  const historyParams = new URLSearchParams(data ? { dateFrom: data.dateFrom, dateTo: data.dateTo } : {})
  if (category) historyParams.set('category', category)
  const historyUrl = { pathname: '/history', search: historyParams.toString() }

  async function report() {
    setExporting(true)
    try {
      download(await downloadReport(days, category), 'defectvision-inspection-report.pdf')
      toast.success('Report downloaded')
    } catch {
      toast.error('Could not download the inspection report')
    } finally {
      setExporting(false)
    }
  }

  return <>
    <PageHeading title={dashboard ? 'Dashboard' : 'Analytics & Reports'} description={dashboard ? 'Monitor inspection activity, defect rates, and PatchCore model readiness.' : 'Explore quality trends, compare categories, and export inspection reports.'}
      action={dashboard ? <Link className="button primary" to="/inspector">New inspection </Link> : undefined} />
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="field">Reporting period (UTC)<select value={days} onChange={(event) => setDays(Number(event.target.value))}>
          <option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option>
        </select></label>
        <CategorySelect all value={category} onChange={setCategory} />
      </div>
      {!dashboard && <button className="button" disabled={!reportAvailable || exporting} onClick={report}> {exporting ? 'Downloading…' : 'Download PDF'}</button>}
    </div>
    {!dashboard && !reportAvailable && <ResourceState state="unavailable" unavailable="PDF reports are unavailable on this backend." />}
    <div className="metric-grid analytics-metrics">
      {[
        ['Total inspections', data?.total],
        ['Normal', data?.normal],
        ['Defective', data?.defective],
        ['Defect rate', data?.defectPercentage != null ? `${data.defectPercentage.toFixed(1)}%` : undefined],
        ['Average inference latency', data?.averageInferenceLatencyMs != null ? `${data.averageInferenceLatencyMs.toFixed(1)} ms` : undefined],
      ].map(([label, value]) => <Panel key={label} title={String(label)}><div className="metric-value">{value ?? 'N/A'}</div></Panel>)}
    </div>
    {data && <p className="text-sm text-muted-foreground">
      {data.dateFrom} to {data.dateTo} UTC · {data.timedInspections} of {data.total} inspections have measured latency
    </p>}
    <div className="chart-grid">
      <Panel title="Daily inspections">
        {data?.trend.length ? <ResponsiveContainer width="100%" height={260} minWidth={0}>
          <BarChart data={data.trend}>
            <CartesianGrid stroke="var(--color-border)" vertical={false} /><XAxis dataKey="date" tickFormatter={(day: string) => day.slice(5)} />
            <YAxis allowDecimals={false} width={38} /><Tooltip contentStyle={tooltipStyle} /><Legend />
            <Bar name="Normal" dataKey="normal" isAnimationActive={false} stackId="daily" fill="#52758c" />
            <Bar name="Defective" dataKey="defective" isAnimationActive={false} stackId="daily" fill="#8b632e" />
          </BarChart>
        </ResponsiveContainer> : data ? <Empty>No inspections for these filters.</Empty> : <ResourceState state={analytics.state} unavailable="Inspection analytics are unavailable on this backend." />}
      </Panel>
      <Panel title="Defect-rate trend">
        {data?.trend.length ? <ResponsiveContainer width="100%" height={260} minWidth={0}>
          <LineChart data={data.trend}>
            <CartesianGrid stroke="var(--color-border)" vertical={false} /><XAxis dataKey="date" tickFormatter={(day: string) => day.slice(5)} /><YAxis domain={[0, 100]} unit="%" width={54} />
            <Tooltip formatter={(value) => `${Number(value).toFixed(1)}%`} contentStyle={tooltipStyle} />
            <Line isAnimationActive={false} name="Defect rate" dataKey="defectPercentage" stroke="var(--color-primary)" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer> : data ? <Empty>No trend data for this period.</Empty> : <ResourceState state={analytics.state} unavailable="Inspection analytics are unavailable on this backend." />}
      </Panel>
      <Panel title="Inspection distribution by category">
        {data?.categories.length ? <ResponsiveContainer width="100%" height={260} minWidth={0}>
          <BarChart data={data.categories}>
            <CartesianGrid stroke="var(--color-border)" vertical={false} /><XAxis dataKey="category" tickFormatter={categoryName} /><YAxis allowDecimals={false} width={38} />
            <Tooltip contentStyle={tooltipStyle} labelFormatter={(label) => categoryName(String(label))} /><Legend />
            <Bar name="Normal" dataKey="normal" isAnimationActive={false} stackId="count" fill="#52758c" /><Bar name="Defective" dataKey="defective" isAnimationActive={false} stackId="count" fill="#8b632e" />
          </BarChart>
        </ResponsiveContainer> : data ? <Empty>No category statistics for this period.</Empty> : <ResourceState state={analytics.state} unavailable="Category statistics require the analytics API." />}
      </Panel>
    {dashboard && <Panel title="Recent activity" action={<Link className="button" to={historyUrl}>Open history</Link>}>
      {data ? data.recent.length ? <ul className="divide-y divide-border">
        {data.recent.map((item) => <li className="flex flex-wrap justify-between gap-2 py-3 text-sm" key={item.id}>
          <Link className="break-all text-primary hover:underline" to={{ ...historyUrl, search: new URLSearchParams([...historyParams, ['id', item.id]]).toString() }}>{item.filename}</Link>
          <span className="text-muted-foreground">{item.prediction} · <time dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleString(undefined, { timeZone: 'UTC' })} UTC</time></span>
        </li>)}
      </ul> : <Empty>No recent inspections for these filters.</Empty> : <ResourceState state={analytics.state} unavailable="Recent activity requires the analytics API." />}
    </Panel>}
    </div>
    <Models />
  </>
}
