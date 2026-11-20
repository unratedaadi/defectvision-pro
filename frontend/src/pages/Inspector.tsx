import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { CategorySelect, ImageComparison, LocalImage, ResultDetails, SavedComparison, UploadZone } from '@/components/InspectionControls'
import { Empty, PageHeading, Panel, ResourceState } from '@/components/Panel'
import { useService } from '@/components/ServiceProvider'
import { endpoints, inspect, inspectionError } from '@/services/api'
import type { Inspection } from '@/types/inspection'

export function Inspector() {
  const [file, setFile] = useState<File>()
  const [category, setCategory] = useState('')
  const [result, setResult] = useState<Inspection>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const request = useRef<AbortController | null>(null)
  const { supports } = useService()
  const available = supports(endpoints.inspect, 'post')
  useEffect(() => () => request.current?.abort(), [])

  function resetResult() {
    request.current?.abort()
    setResult(undefined)
    setError('')
    setBusy(false)
  }

  async function analyze() {
    if (!file || !category || !available) return
    resetResult()
    const controller = new AbortController()
    request.current = controller
    setBusy(true)
    try {
      const response = await inspect(file, category, controller.signal)
      if (!controller.signal.aborted) { setResult(response); toast.success('Inspection complete') }
    } catch (error) {
      if (!controller.signal.aborted) setError(inspectionError(error, 'Inspection failed. Check model readiness and retry.'))
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return <>
    <PageHeading title="AI Inspector" description="Analyze one product image and compare it with the defect heatmap." />
    <div className="workspace-grid">
      <Panel title="Image comparison">
        {result ? <SavedComparison result={result} /> : file ? <LocalImage file={file}>{(url) => <ImageComparison image={url} name={file.name} />}</LocalImage> :
          <div className="image-stage"><Empty>Upload an image to open the viewer.</Empty></div>}
      </Panel>
      <div className="grid content-start gap-4">
        <Panel title="Inspection input">
          <div className="grid gap-4">
            <CategorySelect value={category} onChange={(value) => { setCategory(value); resetResult() }} />
            <UploadZone onFiles={([image]) => { setFile(image); resetResult() }} />
            {file && <p className="break-all text-sm">{file.name}</p>}
            <button className="button primary" disabled={!available || !file || !category || busy} onClick={analyze}>{busy ? 'Analyzing…' : 'Analyze image'}</button>
          </div>
        </Panel>
        <Panel title="Inspection result">
          {!available ? <ResourceState state="unavailable" unavailable="PatchCore inference is unavailable on this backend." /> :
            error ? <Empty error>{error}</Empty> :
            result ? <ResultDetails result={result} /> : <Empty>{busy ? 'Analyzing image…' : 'Run an inspection to see the prediction.'}</Empty>}
        </Panel>
      </div>
    </div>
  </>
}
