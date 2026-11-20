import { useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Empty, PageHeading, Panel, ResourceState } from '@/components/Panel'
import { useService } from '@/components/ServiceProvider'
import { useResource } from '@/hooks/useResource'
import { endpoints, getEvaluation, mediaUrl } from '@/services/api'
import type { Evaluation } from '@/types/inspection'

const categories = [['bottle', 'Bottle'], ['metal_nut', 'Metal Nut'], ['tile', 'Tile']] as const
const fields = [
  ['Image AUROC', 'image_auroc'], ['Precision', 'precision'], ['Recall', 'recall'], ['F1-score', 'f1'],
  ['Pixel AUROC', 'pixel_auroc'], ['Mean latency', 'average_inference_latency_ms'],
] as const

function loadEvaluations(signal: AbortSignal) {
  return Promise.all(categories.map(([slug]) => getEvaluation(slug, signal)))
}

function format(value: number | null | undefined, latency: boolean) {
  return typeof value !== 'number' || !Number.isFinite(value) ? 'N/A' : latency ? `${value.toFixed(1)} ms` : value.toFixed(3)
}

function LocalizationSample({ sample }: { sample: { image: string; url: string } }) {
  const [failed, setFailed] = useState(false)
  return <figure>
    {failed ? <Empty>This localization sample is unavailable.</Empty> : <img
      className="w-full max-w-3xl rounded-none border border-border" loading="lazy"
      src={mediaUrl(sample.url)} onError={() => setFailed(true)}
      alt="Original product, anomaly overlay, and ground-truth mask" />}
    <figcaption className="mt-2 break-all text-sm text-muted-foreground">{sample.image}</figcaption>
  </figure>
}

function EvaluationDetail({ evaluation }: { evaluation: Evaluation }) {
  const { provenance: run, metrics } = evaluation
  const matrix = metrics.confusion_matrix
  return <>
    <Panel title="Evaluation provenance">
      {run ? <dl className="detail-list">
        <div><dt>Dataset split</dt><dd>{run.dataset_split ?? 'N/A'}</dd></div>
        <div><dt>Model version</dt><dd>{evaluation.modelVersion}</dd></div>
        <div><dt>Evaluated</dt><dd>{run.evaluated_at ? new Date(run.evaluated_at).toLocaleString() : 'N/A'}</dd></div>
        <div><dt>Samples</dt><dd>{run.test_count ?? 'N/A'} total · {run.labeled_count ?? 'N/A'} image labels · {run.pixel_image_count ?? 'N/A'} pixel labels</dd></div>
        <div><dt>Pixel evaluation grid</dt><dd>{run.pixel_metric_size?.join(' × ') ?? 'N/A'}</dd></div>
        <div><dt>Threshold</dt><dd>{run.threshold ?? 'N/A'}</dd></div>
        <div><dt>Calibration</dt><dd>{run.calibration ? `${run.calibration.method} · ${run.calibration.split} · n=${run.calibration.sample_count}` : 'N/A'}</dd></div>
        <div><dt>Hardware</dt><dd>{Object.values(run.hardware ?? {}).join(' · ') || 'N/A'}</dd></div>
        <div><dt>Latency protocol</dt><dd>{[run.inference_devices?.join(', '), run.latency_scope].filter(Boolean).join(' · ') || 'N/A'}</dd></div>
        {Object.entries(run.latency_by_device ?? {}).map(([device, timing]) => <div key={device}>
          <dt>Mean latency ({device})</dt><dd>{format(timing.mean_ms, true)} · n={timing.count}</dd>
        </div>)}
      </dl> : <Empty>Provenance is unavailable for this evaluation.</Empty>}
    </Panel>
    <div className="chart-grid">
      <Panel title="Image-level ROC curve">
        {run?.roc?.length ? <ResponsiveContainer width="100%" height={280} minWidth={0}>
          <LineChart data={run.roc} margin={{ bottom: 22, left: 12 }}>
            <CartesianGrid stroke="var(--color-border)" />
            <XAxis type="number" dataKey="fpr" domain={[0, 1]} label={{ value: 'False positive rate', position: 'bottom' }} />
            <YAxis type="number" domain={[0, 1]} label={{ value: 'True positive rate', angle: -90, position: 'insideLeft' }} />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#8896ad" strokeDasharray="4 4" />
            <Tooltip contentStyle={{ background: 'var(--color-card)', borderColor: 'var(--color-border)', color: 'var(--color-foreground)' }} />
            <Line type="linear" dataKey="tpr" name="True positive rate" stroke="var(--color-primary)" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer> : <Empty>ROC is unavailable. It requires both image labels and saved curve data.</Empty>}
      </Panel>
      <Panel title="Confusion matrix">
        {matrix?.length === 2 ? <div className="table-scroll"><table>
          <caption className="sr-only">Rows are actual labels. Columns are predicted labels.</caption>
          <thead><tr><th scope="col">Actual / predicted</th><th scope="col">Normal</th><th scope="col">Defective</th></tr></thead>
          <tbody>{matrix.map((row, index) => <tr key={index}>
            <th scope="row">{index === 0 ? 'Normal' : 'Defective'}</th>
            {row.map((count, column) => <td key={column} className={index === column ? 'bg-primary/10 text-primary' : 'bg-rose-500/10 text-rose-200'}>{count}</td>)}
          </tr>)}</tbody>
        </table></div> : <Empty>No confusion matrix has been recorded.</Empty>}
      </Panel>
    </div>
    <Panel title="Anomaly localization samples">
      {run?.samples?.length ? <div className="grid gap-4">
        {run.samples.map((sample) => <LocalizationSample key={sample.url} sample={sample} />)}
      </div> : <Empty>No localization samples have been recorded.</Empty>}
    </Panel>
  </>
}

export function EvaluationPage() {
  const [index, setIndex] = useState(0)
  const { supports } = useService()
  const runs = useResource(supports(endpoints.evaluation, 'get') ? loadEvaluations : null)
  const selected = runs.data?.[index]
  return <>
    <PageHeading title="Model Evaluation" description="Compare recorded test results for each independently trained category." />
    <Panel title="Evaluation comparison">
      {runs.data ? <div className="table-scroll"><table>
        <thead><tr><th>Category</th><th>Model version</th>{fields.map(([name]) => <th key={name}>{name}</th>)}</tr></thead>
        <tbody>{categories.map(([slug, label], row) => {
          const run = runs.data?.[row]
          return <tr key={slug}><th scope="row"><button className="button" aria-pressed={index === row} onClick={() => setIndex(row)}>{label}</button></th>
            <td>{run?.modelVersion ?? 'Unavailable'}</td>{fields.map(([name, key]) => <td key={key}>{format(run?.metrics[key], name === 'Mean latency')}</td>)}</tr>
        })}</tbody>
      </table></div> : <ResourceState state={runs.state} unavailable="The evaluation API is unavailable." />}
    </Panel>
    {selected ? <EvaluationDetail evaluation={selected} /> : runs.data && <Empty>No evaluation has been recorded for {categories[index][1]}.</Empty>}
  </>
}
