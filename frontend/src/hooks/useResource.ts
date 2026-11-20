import { useEffect, useState } from 'react'

type Result<T> =
  | { state: 'unavailable' | 'loading' | 'error'; data?: undefined }
  | { state: 'ready'; data: T }

export function useResource<T>(loader: ((signal: AbortSignal) => Promise<T>) | null): Result<T> {
  const [result, setResult] = useState<{ loader: typeof loader; value: Result<T> }>()
  useEffect(() => {
    if (!loader) return
    const controller = new AbortController()
    loader(controller.signal).then(
      (data) => { if (!controller.signal.aborted) setResult({ loader, value: { state: 'ready', data } }) },
      () => { if (!controller.signal.aborted) setResult({ loader, value: { state: 'error' } }) },
    )
    return () => controller.abort()
  }, [loader])
  if (!loader) return { state: 'unavailable' } as const
  return result?.loader === loader ? result.value : { state: 'loading' } as const
}
