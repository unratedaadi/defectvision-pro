import axios from 'axios'
import type { Health } from '@/types/health'
import type { Analytics, BatchResult, HistoryQuery, Inspection, ModelStatus } from '@/types/inspection'

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || (import.meta.env.PROD ? '' : 'http://127.0.0.1:8000')

const api = axios.create({ baseURL: apiBaseUrl, timeout: 5000 })

const root = '/api'
export const endpoints = {
  inspect: root + '/inspect',
  batch: root + '/inspect/batch',
  batchStatus: root + '/inspect/batch/{id}',
  webcam: root + '/inspect/webcam',
  saveWebcam: root + '/inspect/webcam/{id}/save',
  inspections: root + '/inspections',
  inspection: root + '/inspections/{id}',
  analytics: root + '/analytics/summary',
  trends: root + '/analytics/trends',
  dashboard: root + '/analytics/dashboard',
  models: root + '/models',
  report: root + '/reports/inspections.pdf',
  inspectionReport: root + '/reports/{id}',
  batchReport: root + '/reports/batch/{id}',
  evaluation: root + '/evaluation/{category}',
}

export async function getEvaluation(category: string, signal: AbortSignal) {
  try {
    return (await api.get<import('@/types/inspection').Evaluation>(
      endpoints.evaluation.replace('{category}', encodeURIComponent(category)), { signal },
    )).data
  } catch (error) {
    if (isMissing(error)) return null
    throw error
  }
}

export async function downloadBatchReport(id: string) {
  return (await api.get<Blob>(endpoints.batchReport.replace('{id}', encodeURIComponent(id)), { responseType: 'blob' })).data
}

export async function getCapabilities(signal: AbortSignal) {
  const { data } = await api.get<{ paths: Record<string, Record<string, unknown>> }>('/openapi.json', { signal })
  return data.paths
}

export async function inspect(file: File, category: string, signal: AbortSignal, source = 'upload') {
  const body = new FormData()
  body.append('file', file)
  body.append('category', category)
  body.append('source', source)
  return (await api.post<Inspection>(endpoints.inspect, body, { signal, timeout: 60_000 })).data
}

export async function inspectBatch(files: File[], category: string, signal: AbortSignal) {
  const body = new FormData()
  files.forEach((file) => body.append('files', file))
  body.append('category', category)
  return (await api.post<BatchResult>(
    endpoints.batch, body, { signal, timeout: 120_000 },
  )).data
}

export async function getBatch(id: string, signal: AbortSignal) {
  return (await api.get<BatchResult>(endpoints.batchStatus.replace('{id}', encodeURIComponent(id)), { signal })).data
}

export async function previewWebcam(file: File, category: string, signal: AbortSignal) {
  const body = new FormData()
  body.append('file', file)
  body.append('category', category)
  return (await api.post<Inspection>(endpoints.webcam, body, { signal, timeout: 60_000 })).data
}

export async function saveWebcam(id: string, signal: AbortSignal) {
  return (await api.post<Inspection>(endpoints.saveWebcam.replace('{id}', encodeURIComponent(id)), undefined, { signal })).data
}

export function inspectionError(error: unknown, fallback: string) {
  if (axios.isAxiosError<{ detail?: { message?: string } }>(error)) {
    const message = error.response?.data?.detail?.message
    if (typeof message === 'string') return message
  }
  return fallback
}

export function isMissing(error: unknown) {
  return axios.isAxiosError(error) && error.response?.status === 404
}

export async function getHistory(query: HistoryQuery, signal: AbortSignal) {
  return (await api.get<{ items: Inspection[]; total: number }>(endpoints.inspections, {
    params: { ...query, ...(query.date === '' ? { date: undefined } : {}),
      ...(query.dateFrom === '' ? { dateFrom: undefined } : {}),
      ...(query.dateTo === '' ? { dateTo: undefined } : {}), pageSize: 10 }, signal,
  })).data
}

export async function deleteInspection(id: string) {
  await api.delete(endpoints.inspection.replace('{id}', encodeURIComponent(id)))
}

export async function getInspection(id: string, signal: AbortSignal) {
  const path = endpoints.inspection.replace('{id}', encodeURIComponent(id))
  try {
    return (await api.get<Inspection>(path, { signal })).data
  } catch (error) {
    if (isMissing(error)) return null
    throw error
  }
}

export async function getAnalytics(days: number, category: string, signal: AbortSignal) {
  return (await api.get<Analytics>(endpoints.dashboard, { params: { days, category: category || undefined }, signal })).data
}

export function inspectionMedia(id: string, kind: 'original' | 'heatmap' | 'thumbnail') {
  return endpoints.inspection.replace('{id}', encodeURIComponent(id)) + '/media/' + kind
}

export async function downloadInspectionMedia(id: string, kind: 'original' | 'heatmap') {
  return (await api.get<Blob>(inspectionMedia(id, kind), { responseType: 'blob' })).data
}

export async function getModels(signal: AbortSignal) {
  return (await api.get<ModelStatus[]>(endpoints.models, { signal })).data
}

export async function downloadReport(days: number, category = '') {
  return (await api.get<Blob>(endpoints.report, { responseType: 'blob', params: { days, category: category || undefined } })).data
}

export async function downloadInspectionReport(id: string) {
  const path = endpoints.inspectionReport.replace('{id}', encodeURIComponent(id))
  return (await api.get<Blob>(path, { responseType: 'blob' })).data
}

export function mediaUrl(path: string) {
  return new URL(path, apiBaseUrl).href
}

export async function getHealth(signal: AbortSignal): Promise<Health> {
  const response = await api.get<Health>('/api/v1/health', {
    signal,
    validateStatus: (status) => status === 200 || status === 503,
  })
  const health = response.data
  if (response.status === 200 && health?.status === 'ok' && health.database === 'ready' &&
      Array.isArray(health.categories) && health.categories.every(
        (category) => typeof category?.slug === 'string' && typeof category?.name === 'string',
      )) {
    return health
  }
  if (response.status === 503 && health?.status === 'degraded' && health.database === 'unavailable') {
    return { status: 'degraded', database: 'unavailable', categories: [] }
  }
  throw new Error('Unexpected health response')
}
