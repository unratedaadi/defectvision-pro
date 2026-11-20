import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { CategorySelect, ResultDetails, SavedComparison } from '@/components/InspectionControls'
import { Empty, PageHeading, Panel, ResourceState } from '@/components/Panel'
import { useService } from '@/components/ServiceProvider'
import { useResource } from '@/hooks/useResource'
import { CameraSession, cameraErrorMessage } from '@/lib/camera'
import { endpoints, getModels, inspectionError, previewWebcam, saveWebcam } from '@/services/api'
import type { Inspection } from '@/types/inspection'

export function Live() {
  const [camera, setCamera] = useState<'idle' | 'requesting' | 'active'>('idle')
  const [cameraError, setCameraError] = useState('')
  const [frameError, setFrameError] = useState('')
  const [category, setCategory] = useState('')
  const [interval, setIntervalSeconds] = useState(3)
  const [summary, setSummary] = useState({ total: 0, defective: 0 })
  const [frames, setFrames] = useState<Inspection[]>([])
  const [selectedId, setSelectedId] = useState<string>()
  const [saved, setSaved] = useState<Inspection[]>([])
  const [sources, setSources] = useState<MediaDeviceInfo[]>([])
  const [source, setSource] = useState('')
  const [saving, setSaving] = useState(false)
  const [modelRevision, setModelRevision] = useState(0)
  const video = useRef<HTMLVideoElement>(null)
  const [session] = useState(() => new CameraSession())
  const pending = useRef(false)
  const saveRequest = useRef<AbortController | null>(null)
  const { supports } = useService()
  const available = supports(endpoints.webcam, 'post')
  const loadModels = useCallback((signal: AbortSignal) => {
    void modelRevision
    return getModels(signal)
  }, [modelRevision])
  const models = useResource(supports(endpoints.models, 'get') ? loadModels : null)
  const ready = models.data?.some((model) => model.category === category && model.ready) ?? false
  const latest = frames[0]
  const selected = frames.find((frame) => frame.id === selectedId) ?? latest
  const stored = saved.find((frame) => frame.id === selected?.id)

  useEffect(() => () => { session.stop(); saveRequest.current?.abort() }, [session])

  function stop() {
    session.stop()
    setCamera('idle')
  }

  async function start(deviceId = source) {
    setCameraError('')
    const devices = navigator.mediaDevices
    if (!devices?.getUserMedia || !video.current) {
      setCameraError('Camera access requires a supported browser on HTTPS or localhost.')
      return
    }
    setCamera('requesting')
    try {
      if (await session.start(devices, video.current, deviceId, () => {
        setCamera('idle')
        setCameraError('The camera disconnected. Reconnect it, then start the camera again.')
      })) {
        setCamera('active')
      }
    } catch (error) {
      setCamera('idle')
      setCameraError(cameraErrorMessage(error))
    }
  }

  useEffect(() => {
    const devices = navigator.mediaDevices
    if (!devices?.enumerateDevices) return
    let current = true
    async function refresh() {
      try {
        const list = await devices.enumerateDevices()
        if (current) setSources(list.filter((device) => device.kind === 'videoinput' && device.deviceId))
      } catch {
        if (current) setSources([])
      }
    }
    void refresh()
    devices.addEventListener('devicechange', refresh)
    return () => { current = false; devices.removeEventListener('devicechange', refresh) }
  }, [camera])

  useEffect(() => {
    if (camera !== 'active' || !available || !ready) return
    const controller = new AbortController()
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('2d')
    const timer = window.setInterval(async () => {
      const frame = video.current
      if (pending.current || !context || !frame?.videoWidth || controller.signal.aborted) return
      pending.current = true
      try {
        const scale = Math.min(1, 960 / Math.max(frame.videoWidth, frame.videoHeight))
        canvas.width = Math.max(1, Math.round(frame.videoWidth * scale))
        canvas.height = Math.max(1, Math.round(frame.videoHeight * scale))
        context.drawImage(frame, 0, 0, canvas.width, canvas.height)
        const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9))
        if (!blob || controller.signal.aborted) return
        const result = await previewWebcam(new File([blob], 'camera-frame.jpg', { type: 'image/jpeg' }), category, controller.signal)
        if (controller.signal.aborted) return
        setFrames((recent) => [result, ...recent].slice(0, 8))
        setFrameError('')
        setSummary((previous) => ({ total: previous.total + 1, defective: previous.defective + Number(result.prediction === 'defective') }))
      } catch (error) {
        if (!controller.signal.aborted) setFrameError(inspectionError(error, 'Latest frame failed. The next interval will retry.'))
      } finally {
        pending.current = false
      }
    }, interval * 1000)
    return () => { window.clearInterval(timer); controller.abort() }
  }, [camera, available, category, interval, ready])

  async function saveSelected() {
    if (!selected || stored || saving) return
    const controller = new AbortController()
    saveRequest.current = controller
    setSaving(true)
    try {
      const result = await saveWebcam(selected.id, controller.signal)
      if (controller.signal.aborted) return
      setSaved((recent) => [result, ...recent].slice(0, 8))
      toast.success('Frame saved to inspection history.')
    } catch (error) {
      if (!controller.signal.aborted) toast.error(inspectionError(error, 'Could not save this frame.'))
    } finally {
      if (!controller.signal.aborted) setSaving(false)
    }
  }

  return <>
    <PageHeading title="Live Inspection" description="Preview your camera and inspect frames at a configurable interval." />
    <div className="workspace-grid">
      <Panel title="Camera preview" action={<span className="status-label">{camera === 'active' ? 'Camera active' : 'Camera idle'}</span>}>
        <div className="image-stage">
          <video ref={video} muted playsInline aria-label="Camera preview" hidden={camera !== 'active'} />
          {camera !== 'active' && <Empty>{camera === 'requesting' ? 'Waiting for camera permission…' : 'Start the camera to preview video.'}</Empty>}
        </div>
        {cameraError && <Empty error>{cameraError}</Empty>}
      </Panel>
      <Panel title="Capture controls">
        <div className="grid gap-4">
          <CategorySelect value={category} onChange={(value) => {
            setCategory(value)
            setFrameError('')
          }} />
          <label className="field">Camera source
            <select value={source} disabled={camera === 'requesting'} onChange={(event) => {
              const id = event.target.value
              setSource(id)
              if (camera === 'active') void start(id)
            }}>
              <option value="">Default camera</option>
              {source && !sources.some((device) => device.deviceId === source) && <option value={source}>Previously selected camera</option>}
              {sources.map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `Camera ${index + 1}`}</option>)}
            </select>
          </label>
          <label className="field">Capture interval
            <select value={interval} onChange={(event) => setIntervalSeconds(Number(event.target.value))}>
              {[1, 2, 3, 5, 10].map((seconds) => <option key={seconds} value={seconds}>{seconds} second{seconds === 1 ? '' : 's'}</option>)}
            </select>
          </label>
          <div className="flex flex-wrap gap-2">
            <button className="button primary" disabled={camera !== 'idle'} onClick={() => void start()}> {cameraError ? 'Reconnect camera' : 'Start camera'}</button>
            <button className="button" disabled={camera === 'idle'} onClick={stop}> Stop</button>
          </div>
          {!available && <ResourceState state="unavailable" unavailable="Camera preview works locally. Frame predictions require the inspection API." />}
          {available && category && !ready && (models.data
            ? <Empty>The selected category has no ready model. Camera preview stays local.</Empty>
            : <ResourceState state={models.state} unavailable="Model readiness is unavailable." />)}
          {available && category && (!ready || frameError) &&
            <button type="button" className="button" onClick={() => setModelRevision((value) => value + 1)}>Check model again</button>}
        </div>
      </Panel>
    </div>
    <Panel title="Session summary">
      <p className="mb-3 text-sm text-muted-foreground">Frames analyzed: {summary.total} · Defective frames: {summary.defective}</p>
      {frameError && <Empty error>{frameError}</Empty>}
      {latest ? <div className="mt-3 flex flex-wrap gap-2" aria-label="Recent predictions">
        <button type="button" className="button" aria-pressed={!selectedId} onClick={() => setSelectedId(undefined)}>Follow latest</button>
        {frames.map((frame) => <button key={frame.id} type="button" className="button"
          aria-pressed={selectedId === frame.id} onClick={() => setSelectedId(frame.id)}>
          {new Date(frame.createdAt).toLocaleTimeString()} · {frame.prediction}
        </button>)}
      </div> : <Empty>{ready ? 'No frame predictions in this session.' : 'Frame predictions require a ready model.'}</Empty>}
    </Panel>
    {selected && <Panel title="Selected frame" action={<button className="button primary"
      disabled={saving || Boolean(stored) || !supports(endpoints.saveWebcam, 'post')} onClick={() => void saveSelected()}>
      {stored ? 'Saved' : saving ? 'Saving…' : 'Save selected frame'}
    </button>}>
      <div className="workspace-grid">
        <SavedComparison result={stored ?? selected} />
        <ResultDetails result={stored ?? selected} />
      </div>
    </Panel>}
  </>
}
