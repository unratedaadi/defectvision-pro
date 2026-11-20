export type Prediction = 'normal' | 'defective'

export interface Inspection {
  id: string
  filename: string
  category: string
  createdAt: string
  prediction: Prediction
  score: number
  imageUrl: string
  heatmapUrl: string | null
  overlayUrl?: string | null
  modelVersion: string
  threshold: number
  batchIndex?: number | null
  batchId?: string | null
  source?: 'upload' | 'webcam' | 'batch'
  inferenceLatencyMs?: number | null
}

export interface BatchResult {
  id: string
  status: 'processing' | 'completed' | 'partial' | 'failed'
  total_images: number
  processed_images: number
  failed_images: number
  items: Inspection[]
  errors: { index: number; filename: string; code: string; message: string }[]
}

export interface ModelStatus {
  category: string
  ready: boolean
  status: string
  version: string | null
  threshold: number | null
  auroc: number | null
}

interface Counts {
  total: number
  normal: number
  defective: number
  defectPercentage: number | null
}

export interface Analytics extends Counts {
  trend: (Counts & { date: string })[]
  categories: (Counts & { category: string })[]
  averageInferenceLatencyMs: number | null
  timedInspections: number
  dateFrom: string
  dateTo: string
  recent: Inspection[]
}

export interface HistoryQuery {
  search: string
  category: string
  prediction: string
  date?: string
  dateFrom?: string
  dateTo?: string
  sort?: 'newest' | 'oldest'
  page: number
}

export interface Evaluation {
  category: string
  modelVersion: string
  metrics: {
    image_auroc?: number | null
    precision?: number | null
    recall?: number | null
    f1?: number | null
    pixel_auroc?: number | null
    average_inference_latency_ms?: number | null
    confusion_matrix?: number[][]
  }
  provenance: null | {
    dataset_split?: string
    evaluated_at?: string
    threshold?: number
    calibration?: { method: string; split: string; sample_count: number }
    test_count?: number
    labeled_count?: number
    pixel_image_count?: number
    pixel_metric_size?: number[]
    inference_devices?: string[]
    hardware?: Record<string, string>
    latency_scope?: string
    latency_by_device?: Record<string, { count: number; mean_ms: number }>
    roc?: { fpr: number; tpr: number }[]
    samples?: { file: string; image: string; url: string }[]
  }
}
