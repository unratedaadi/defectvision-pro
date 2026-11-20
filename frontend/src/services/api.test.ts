import { beforeEach, expect, it, vi } from 'vitest'
import { endpoints, getAnalytics, getCapabilities, getHealth, getHistory, getInspection, inspect } from './api'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('axios', () => ({ default: {
  create: () => ({ get, post }),
  isAxiosError: (error: { isAxiosError?: boolean }) => error.isAxiosError === true,
} }))

beforeEach(() => { get.mockReset(); post.mockReset() })

it('returns the real catalog from the health response', async () => {
  const signal = new AbortController().signal
  const data = { status: 'ok', database: 'ready', categories: [{ slug: 'tile', name: 'Tile' }] }
  get.mockResolvedValue({ status: 200, data })
  await expect(getHealth(signal)).resolves.toEqual(data)
  expect(get).toHaveBeenCalledWith('/api/v1/health', expect.objectContaining({ signal }))
})

it('recognizes database unavailability', async () => {
  const data = { status: 'degraded', database: 'unavailable', categories: [] }
  get.mockResolvedValue({ status: 503, data })
  await expect(getHealth(new AbortController().signal)).resolves.toEqual(data)
})

it('rejects malformed categories', async () => {
  get.mockResolvedValue({ status: 200, data: { status: 'ok', database: 'ready', categories: [null] } })
  await expect(getHealth(new AbortController().signal)).rejects.toThrow('Unexpected health response')
})

it('discovers only the routes advertised by the backend', async () => {
  const paths = { '/api/v1/health': { get: {} } }
  const signal = new AbortController().signal
  get.mockResolvedValue({ data: { paths } })
  await expect(getCapabilities(signal)).resolves.toEqual(paths)
  expect(get).toHaveBeenCalledWith('/openapi.json', { signal })
})

it('sends a multipart image and selected category to inference', async () => {
  const file = new File(['fixture'], 'test.png', { type: 'image/png' })
  const signal = new AbortController().signal
  const data = { id: 'inspection-id' }
  post.mockResolvedValue({ data })
  await expect(inspect(file, 'tile', signal)).resolves.toEqual(data)
  const [path, body, config] = post.mock.calls[0]
  expect(path).toBe(endpoints.inspect)
  expect(body.get('file')).toEqual(file)
  expect(body.get('category')).toBe('tile')
  expect(config.signal).toBe(signal)
})

it('passes history filters and pagination through to the API', async () => {
  const query = { search: 'inspection-id', category: 'tile', prediction: 'normal',
    dateFrom: '2026-11-10', dateTo: '2026-11-12', sort: 'oldest' as const, page: 2 }
  const signal = new AbortController().signal
  get.mockResolvedValue({ data: { items: [], total: 0 } })
  await expect(getHistory(query, signal)).resolves.toEqual({ items: [], total: 0 })
  expect(get).toHaveBeenCalledWith(endpoints.inspections, { params: { ...query, pageSize: 10 }, signal })
})

it('fetches all dashboard data with a single shared filter', async () => {
  const data = { total: 0, normal: 0, defective: 0, trend: [], recent: [], categories: [] }
  const signal = new AbortController().signal
  get.mockResolvedValue({ data })
  await expect(getAnalytics(7, 'bottle', signal)).resolves.toEqual(data)
  expect(get).toHaveBeenCalledExactlyOnceWith(endpoints.dashboard, { params: { days: 7, category: 'bottle' }, signal })
})

it('distinguishes deleted inspections from a network failure', async () => {
  const signal = new AbortController().signal
  get.mockRejectedValueOnce({ isAxiosError: true, response: { status: 404 } })
  await expect(getInspection('deleted', signal)).resolves.toBeNull()
  get.mockRejectedValueOnce(new Error('offline'))
  await expect(getInspection('deleted', signal)).rejects.toThrow('offline')
})
