import { useEffect, useId, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { mediaUrl } from '@/services/api'
import type { Inspection } from '@/types/inspection'
import { useService } from './ServiceProvider'
import { Empty } from './Panel'

export function CategorySelect({ value, onChange, all = false }: { value: string; onChange: (value: string) => void; all?: boolean }) {
  const { health } = useService()
  return <label className="field">Product category
    <select value={value} onChange={(event) => onChange(event.target.value)} disabled={health.status !== 'ok'}>
      <option value="">{all ? 'All categories' : health.status === 'loading' ? 'Loading categories…' : 'Select category'}</option>
      {health.status === 'ok' && health.categories.map(({ slug, name }) => <option key={slug} value={slug}>{name}</option>)}
    </select>
  </label>
}

export function UploadZone({ multiple = false, onFiles }: { multiple?: boolean; onFiles: (files: File[]) => void }) {
  const id = useId()
  const [dragging, setDragging] = useState(false)
  function accept(list: FileList) {
    const files = Array.from(list)
    const valid = files.filter((file) => ['image/jpeg', 'image/png', 'image/webp'].includes(file.type) && file.size > 0 && file.size <= 10 * 1024 * 1024)
    if (valid.length !== files.length) toast.error('Use non-empty JPEG, PNG or WebP images up to 10 MB.')
    if (valid.length) onFiles(multiple ? valid : valid.slice(0, 1))
  }
  return <div className="upload-zone" data-dragging={dragging}
    onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
    onDragLeave={() => setDragging(false)}
    onDrop={(event) => { event.preventDefault(); setDragging(false); accept(event.dataTransfer.files) }}>
    
    <p>Drop {multiple ? 'images' : 'an image'} here</p>
    <label htmlFor={id} className="button">Browse files</label>
    <input id={id} className="sr-only" type="file" multiple={multiple} accept="image/jpeg,image/png,image/webp"
      onChange={(event) => { if (event.target.files) accept(event.target.files); event.target.value = '' }} />
    <small>JPEG, PNG, WebP · Up to 10 MB each</small>
  </div>
}

export function LocalImage({ file, children }: { file: File; children: (url: string) => ReactNode }) {
  const [preview, setPreview] = useState<{ file: File; url: string }>()
  useEffect(() => {
    const url = URL.createObjectURL(file)
    setPreview({ file, url })
    return () => URL.revokeObjectURL(url)
  }, [file])
  return preview?.file === file ? children(preview.url) : <Empty>Preparing preview…</Empty>
}

export function ImageComparison({ image, heatmap, overlay, name }: { image: string; heatmap?: string | null; overlay?: string | null; name: string }) {
  const [view, setView] = useState('Original')
  const [opacity, setOpacity] = useState(55)
  const [missing, setMissing] = useState<string[]>([])
  const active = view === 'Heatmap' && !heatmap || view === 'Overlay' && !overlay && !heatmap ? 'Original' : view
  const overlaySource = overlay || heatmap
  const visibleImage = active === 'Heatmap' && heatmap ? heatmap : image
  function markMissing(url: string) {
    setMissing((previous) => previous.includes(url) ? previous : [...previous, url])
  }
  return <div className="flex flex-col gap-3">
    <div className="flex flex-wrap gap-2" role="group" aria-label="Image view">
      {['Original', 'Heatmap', 'Overlay'].map((option) => <button key={option} className="button"
        disabled={option === 'Heatmap' && !heatmap || option === 'Overlay' && !overlaySource} aria-pressed={active === option} onClick={() => setView(option)}>{option}</button>)}
    </div>
    <div className="image-stage comparison-stage">
      {missing.includes(visibleImage) ? <Empty>Image file is unavailable.</Empty> :
        <img key={visibleImage} src={visibleImage} onError={() => markMissing(visibleImage)}
          alt={active === 'Heatmap' ? 'Defect localization heatmap' : name} />}
      {active === 'Overlay' && overlaySource && !missing.includes(image) && !missing.includes(overlaySource) &&
        <img className="heatmap-overlay" src={overlaySource} onError={() => markMissing(overlaySource)}
          alt="Heatmap overlay" style={{ opacity: opacity / 100 }} />}
    </div>
    <label className="field">Heatmap opacity · {opacity}%
      <input type="range" min="0" max="100" value={opacity} disabled={active !== 'Overlay'} onChange={(event) => setOpacity(Number(event.target.value))} />
    </label>
    {active === 'Overlay' && overlaySource && missing.includes(overlaySource) ?
      <small role="status" className="text-muted-foreground">Overlay file is unavailable.</small> :
      active !== 'Original' && <small className="text-muted-foreground">Colors show relative anomaly intensity within this image.</small>}
  </div>
}

export function ResultDetails({ result }: { result: Inspection }) {
  const { health } = useService()
  const category = health.status === 'ok' ? health.categories.find((item) => item.slug === result.category)?.name : undefined
  return <dl className="detail-list tabular-nums">
    <div><dt>Prediction</dt><dd className={result.prediction === 'defective' ? 'text-rose-300 capitalize' : 'text-emerald-300 capitalize'}>{result.prediction}</dd></div>
    <div><dt>Raw anomaly score</dt><dd>{result.score}</dd></div>
    <div><dt>Model</dt><dd>PatchCore · {result.modelVersion}</dd></div>
    <div><dt>Decision threshold</dt><dd>{result.threshold}</dd></div>
    <div><dt>Product category</dt><dd className="capitalize">{category ?? result.category.replaceAll('_', ' ')}</dd></div>
    <div><dt>Inspected at</dt><dd><time dateTime={result.createdAt}>{new Date(result.createdAt).toLocaleString()}</time></dd></div>
  </dl>
}

export function SavedComparison({ result }: { result: Inspection }) {
  return <ImageComparison key={result.id} image={mediaUrl(result.imageUrl)}
    heatmap={result.heatmapUrl && mediaUrl(result.heatmapUrl)}
    overlay={result.overlayUrl && mediaUrl(result.overlayUrl)} name={result.filename} />
}
