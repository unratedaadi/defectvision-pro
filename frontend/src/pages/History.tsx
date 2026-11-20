import { useCallback, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { CategorySelect, ResultDetails, SavedComparison } from '@/components/InspectionControls'
import { Empty, PageHeading, Panel, ResourceState } from '@/components/Panel'
import { useService } from '@/components/ServiceProvider'
import { useResource } from '@/hooks/useResource'
import { download } from '@/lib/export'
import { deleteInspection, downloadInspectionMedia, downloadInspectionReport, endpoints, getHistory, getInspection, inspectionMedia, isMissing, mediaUrl } from '@/services/api'
import type { HistoryQuery } from '@/types/inspection'

export function History() {
  const [params] = useSearchParams()
  const [query, setQuery] = useState<HistoryQuery>(() => ({
    search: params.get('id') ?? '', category: params.get('category') ?? '', prediction: '',
    dateFrom: params.get('dateFrom') ?? '', dateTo: params.get('dateTo') ?? '', sort: 'newest', page: 1,
  }))
  const [revision, setRevision] = useState(0)
  const [selectedId, setSelectedId] = useState(params.get('id') ?? '')
  const [deleting, setDeleting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const { supports } = useService()
  const invalidRange = Boolean(query.dateFrom && query.dateTo && query.dateFrom > query.dateTo)
  const load = useCallback((signal: AbortSignal) => {
    void revision
    return getHistory(query, signal)
  }, [query, revision])
  const history = useResource(!invalidRange && supports(endpoints.inspections, 'get') ? load : null)
  const loadDetails = useCallback((signal: AbortSignal) => getInspection(selectedId, signal), [selectedId])
  const details = useResource(selectedId && supports(endpoints.inspection, 'get') ? loadDetails : null)
  const selected = details.data
  const pages = Math.max(1, Math.ceil((history.data?.total ?? 0) / 10))

  function filter(update: Partial<HistoryQuery>) {
    setQuery((previous) => ({ ...previous, ...update, page: 1 }))
    setSelectedId('')
  }

  function changePage(page: number) {
    setQuery((previous) => ({ ...previous, page }))
    setSelectedId('')
  }

  async function remove() {
    if (!selected || !supports(endpoints.inspection, 'delete') || deleting) return
    if (!window.confirm(`Delete the saved inspection for "${selected.filename}"?`)) return
    setDeleting(true)
    try {
      await deleteInspection(selected.id)
      setSelectedId('')
      if (history.data?.items.length === 1 && query.page > 1) changePage(query.page - 1)
      setRevision((value) => value + 1)
      toast.success('Inspection deleted')
    } catch (error) {
      if (isMissing(error)) {
        setSelectedId('')
        setRevision((value) => value + 1)
        toast.error('This inspection has already been deleted.')
      } else toast.error('Could not delete inspection')
    } finally {
      setDeleting(false)
    }
  }

  async function exportInspection(id: string, kind: 'pdf' | 'original' | 'heatmap') {
    setExporting(true)
    try {
      const blob = kind === 'pdf' ? await downloadInspectionReport(id) : await downloadInspectionMedia(id, kind)
      download(blob, kind === 'pdf' ? `inspection-${id}.pdf` : `inspection-${id}-${kind}.png`)
    } catch (error) {
      toast.error(isMissing(error) ? 'The inspection or requested file is no longer available.' : 'Could not download the inspection file.')
    } finally {
      setExporting(false)
    }
  }

  return <>
    <PageHeading title="Inspection History" description="Find, compare, and manage saved inspections." />
    <Panel title="Saved inspections">
      <fieldset className="filter-grid" disabled={deleting}>
        <label className="field">Search inspections<input type="search" placeholder="Inspection ID or filename" maxLength={255} value={query.search} onChange={(event) => filter({ search: event.target.value })} /></label>
        <CategorySelect all value={query.category} onChange={(category) => filter({ category })} />
        <label className="field">Prediction<select value={query.prediction} onChange={(event) => filter({ prediction: event.target.value })}>
          <option value="">All predictions</option><option value="normal">Normal</option><option value="defective">Defective</option>
        </select></label>
        <label className="field">From date (UTC)<input type="date" value={query.dateFrom} onChange={(event) => filter({ dateFrom: event.target.value })} /></label>
        <label className="field">To date (UTC)<input type="date" value={query.dateTo} onChange={(event) => filter({ dateTo: event.target.value })} /></label>
        <label className="field">Sort by<select value={query.sort} onChange={(event) => filter({ sort: event.target.value === 'oldest' ? 'oldest' : 'newest' })}>
          <option value="newest">Newest first</option><option value="oldest">Oldest first</option>
        </select></label>
      </fieldset>
      <div className="mt-4">
        {invalidRange ? <Empty error>Start date must be on or before end date.</Empty> : history.data ? history.data.items.length ? <div className="table-scroll"><table>
          <thead><tr><th>Image</th><th>Category</th><th>Prediction</th><th>Inspected (UTC)</th><th>Details</th></tr></thead>
          <tbody>{history.data.items.map((item) => <tr key={item.id}>
            <td><span className="flex items-center gap-3"><img src={mediaUrl(inspectionMedia(item.id, 'thumbnail'))} alt="" className="size-10 rounded-none bg-muted object-cover" loading="lazy" onError={(event) => { event.currentTarget.style.visibility = 'hidden' }} />
              <span>{item.filename}<small className="block font-mono text-muted-foreground">{item.id}</small></span></span></td>
            <td className="capitalize">{item.category.replaceAll('_', ' ')}</td><td className="capitalize">{item.prediction}</td><td><time dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleString(undefined, { timeZone: 'UTC' })}</time></td>
            <td><button className="button" aria-pressed={selectedId === item.id} disabled={deleting} onClick={() => setSelectedId(item.id)}>View</button></td>
          </tr>)}</tbody>
        </table></div> : <Empty>No inspections match these filters.</Empty> :
          <ResourceState state={history.state} unavailable="Saved inspection history is unavailable on this backend." />}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        <button className="button" disabled={deleting || query.page <= 1 || !history.data} onClick={() => changePage(Math.min(query.page - 1, pages))}>Previous</button>
        <span>{history.data ? query.page > pages ? `Page unavailable · ${history.data.total} matching` :
          `Page ${query.page} of ${pages} · ${history.data.total} matching` : 'Pagination unavailable'}</span>
        <button className="button" disabled={deleting || query.page >= pages || !history.data} onClick={() => changePage(query.page + 1)}>Next</button>
      </div>
    </Panel>
    {selectedId && !selected && <Panel title="Inspection details">{details.state === 'ready'
      ? <Empty>The inspection no longer exists.</Empty>
      : <ResourceState state={details.state} unavailable="Inspection details are unavailable." />}</Panel>}
    {selected && <Panel title={selected.filename} action={<div className="flex flex-wrap gap-2">
      <button className="button" disabled={exporting || deleting} onClick={() => exportInspection(selected.id, 'original')}>Download image</button>
      <button className="button" disabled={exporting || deleting || !selected.heatmapUrl} onClick={() => exportInspection(selected.id, 'heatmap')}>Download heatmap</button>
      <button className="button" disabled={exporting || deleting || !supports(endpoints.inspectionReport, 'get')} onClick={() => exportInspection(selected.id, 'pdf')}>Download PDF</button>
      <button className="button danger" disabled={deleting || !supports(endpoints.inspection, 'delete')} onClick={remove}>{deleting ? 'Deleting…' : 'Delete inspection'}</button>
    </div>}>
      <div className="workspace-grid"><SavedComparison result={selected} /><div className="grid gap-4">
        <ResultDetails result={selected} />
        <dl className="detail-list">
          <div><dt>Inspection ID</dt><dd className="break-all font-mono">{selected.id}</dd></div>
          <div><dt>Source</dt><dd className="capitalize">{selected.source ?? 'N/A'}</dd></div>
          {selected.batchId && <div><dt>Batch ID</dt><dd className="break-all font-mono">{selected.batchId}</dd></div>}
          <div><dt>Inference latency</dt><dd>{selected.inferenceLatencyMs == null ? 'Unavailable' : `${selected.inferenceLatencyMs.toFixed(1)} ms`}</dd></div>
        </dl>
      </div></div>
    </Panel>}
  </>
}
