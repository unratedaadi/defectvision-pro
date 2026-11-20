import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { CategorySelect, LocalImage, SavedComparison, UploadZone } from '@/components/InspectionControls'
import { Empty, PageHeading, Panel, ResourceState } from '@/components/Panel'
import { useService } from '@/components/ServiceProvider'
import { download } from '@/lib/export'
import { downloadBatchReport, endpoints, getBatch, inspectBatch, inspectionError, mediaUrl } from '@/services/api'
import type { BatchResult, Inspection } from '@/types/inspection'

type Job = { id: number; file: File; status: 'Queued' | 'Processing' | 'Complete' | 'Failed'; result?: Inspection }

export function Batch() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [category, setCategory] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [exportingPdf, setExportingPdf] = useState(false)
  const [batch, setBatch] = useState<BatchResult>()
  const [pollError, setPollError] = useState('')
  const [selected, setSelected] = useState<Inspection>()
  const submitted = useRef<number[]>([])
  const sequence = useRef(0)
  const request = useRef<AbortController | null>(null)
  const { supports } = useService()
  const available = supports(endpoints.batch, 'post') && supports(endpoints.batchStatus, 'get')
  const activeId = batch?.status === 'processing' ? batch.id : undefined
  const busy = submitting || Boolean(activeId)
  const completed = batch ? batch.processed_images + batch.failed_images : 0
  const errors = new Map(batch?.errors.map((item) => [submitted.current[item.index], item.message]))
  useEffect(() => () => request.current?.abort(), [])

  async function run() {
    if (!available || !category || busy) return
    const controller = new AbortController()
    request.current = controller
    setSubmitting(true)
    setSelected(undefined)
    setBatch(undefined)
    const queued = jobs.filter((item) => item.status !== 'Complete')
    submitted.current = queued.map((job) => job.id)
    setJobs((current) => current.map((job) => job.status === 'Complete' ? job : { ...job, status: 'Processing' }))
    try {
      const response = await inspectBatch(queued.map((job) => job.file), category, controller.signal)
      if (!controller.signal.aborted) setBatch(response)
    } catch (error) {
      if (controller.signal.aborted) return
      setJobs((current) => current.map((job) => job.status === 'Processing' ? { ...job, status: 'Queued' } : job))
      toast.error(inspectionError(error, 'Batch could not be completed.'))
    } finally {
      if (!controller.signal.aborted) setSubmitting(false)
    }
  }

  useEffect(() => {
    if (!activeId) return
    const controller = new AbortController()
    let timer: number
    async function poll(id: string) {
      try {
        const state = await getBatch(id, controller.signal)
        if (controller.signal.aborted) return
        setPollError('')
        setBatch(state)
        const successes = new Map(state.items.map((item) => [item.batchIndex, item]))
        const failures = new Set(state.errors.map((item) => item.index))
        const indexes = new Map(submitted.current.map((jobId, index) => [jobId, index]))
        setJobs((current) => current.map((job) => {
          const index = indexes.get(job.id)
          if (index === undefined) return job
          const result = successes.get(index)
          const status = result ? 'Complete' : failures.has(index) || state.status !== 'processing' ? 'Failed' : 'Processing'
          return { ...job, result, status }
        }))
        if (state.status === 'processing') timer = window.setTimeout(() => void poll(id), 750)
        else if (state.failed_images) toast.error(`${state.failed_images} image(s) failed.`)
        else toast.success('Batch complete')
      } catch (error) {
        if (controller.signal.aborted) return
        setPollError(inspectionError(error, 'Connection lost while checking progress. Reconnecting…'))
        timer = window.setTimeout(() => void poll(id), 2500)
      }
    }
    void poll(activeId)
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [activeId])

  return <>
    <PageHeading title="Batch Inspection" description="Queue images from one product category and review individual outcomes." />
    <div className="workspace-grid">
      <Panel title="Image queue" action={<span className="status-label">{jobs.length} selected</span>}>
        {busy ? <p role="status" className="text-sm">Processing selected images…</p> : <UploadZone multiple onFiles={(files) => {
          const additions = files.map((file): Job => ({ id: ++sequence.current, file, status: 'Queued' }))
          setJobs((current) => [...current, ...additions])
        }} />}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {jobs.map((job) => <div className="preview-card" key={job.id}>
            {job.result?.heatmapUrl ? <button type="button" className="block w-full" onClick={() => setSelected(job.result)}
              aria-label={`Compare heatmap for ${job.file.name}`}><img src={mediaUrl(job.result.heatmapUrl)} alt="" loading="lazy" /></button>
              : <LocalImage file={job.file}>{(url) => <img src={url} alt="" loading="lazy" />}</LocalImage>}
            <div className="flex items-center justify-between gap-2 p-2">
              <span className="truncate text-xs" title={job.file.name}>{job.file.name}</span>
              <button type="button" className="icon-button" disabled={busy} aria-label={`Remove ${job.file.name}`} onClick={() => setJobs((items) => items.filter((item) => item.id !== job.id))}>Remove</button>
            </div>
          </div>)}
        </div>
      </Panel>
      <Panel title="Batch controls">
        <div className="grid gap-4">
          <fieldset disabled={busy}><CategorySelect value={category} onChange={(value) => {
            setCategory(value)
            setBatch(undefined)
            setSelected(undefined)
            setJobs((items) => items.map((job) => ({ ...job, status: 'Queued', result: undefined })))
          }} /></fieldset>
          <label className="field">Progress · {completed} of {batch?.total_images ?? jobs.length}
            <progress max={batch?.total_images || jobs.length || 1} value={submitting ? undefined : completed} />
          </label>
          {pollError && <Empty error>{pollError}</Empty>}
          <button className="button primary" disabled={!available || !category || busy || !jobs.some((job) => job.status !== 'Complete')} onClick={run}>{busy ? 'Processing…' : 'Run batch'}</button>
          {!available && <ResourceState state="unavailable" unavailable="Batch processing requires the inspection API." />}
        </div>
      </Panel>
    </div>
    <Panel title="Results" action={<div className="flex flex-wrap gap-2"><button className="button" disabled={busy || !batch} onClick={() => {
      if (batch) download(new Blob([JSON.stringify(batch, null, 2)], { type: 'application/json' }), `inspection-batch-${batch.id}.json`)
    }}> Export JSON</button>
      {supports(endpoints.batchReport, 'get') && <button className="button" disabled={busy || !batch || exportingPdf} onClick={async () => {
        if (!batch) return
        setExportingPdf(true)
        try {
          download(await downloadBatchReport(batch.id), `inspection-batch-${batch.id}.pdf`)
        } catch (error) {
          toast.error(inspectionError(error, 'Could not download the batch report.'))
        } finally {
          setExportingPdf(false)
        }
      }}>{exportingPdf ? 'Downloading…' : 'Download PDF'}</button>}
    </div>}>
      {jobs.length ? <div className="table-scroll"><table><thead><tr><th>Image</th><th>Status</th><th>Prediction</th><th>Score</th></tr></thead>
        <tbody>{jobs.map((job) => <tr key={job.id}>
          <td>{job.result ? <button type="button" className="text-primary underline" onClick={() => setSelected(job.result)}>{job.file.name}</button> : job.file.name}</td>
          <td>{job.status}{job.status === 'Failed' && <small className="block text-muted-foreground">{errors.get(job.id) ?? 'Processing did not complete.'}</small>}</td>
          <td>{job.result?.prediction ?? 'N/A'}</td><td>{job.result?.score.toFixed(4) ?? 'N/A'}</td>
        </tr>)}</tbody>
      </table></div> : <Empty>Add images to build the batch queue.</Empty>}
    </Panel>
    {selected && <Panel title={selected.filename}><SavedComparison result={selected} /></Panel>}
  </>
}
