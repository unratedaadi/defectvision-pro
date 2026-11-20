import { useEffect, useState } from 'react'
import { getHealth } from '@/services/api'
import type { Health } from '@/types/health'

type HealthState = Health | { status: 'loading' | 'offline' }

export function useHealth() {
  const [health, setHealth] = useState<HealthState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then(
      (result) => { if (!controller.signal.aborted) setHealth(result) },
      () => { if (!controller.signal.aborted) setHealth({ status: 'offline' }) },
    )
    return () => controller.abort()
  }, [attempt])

  function refresh() {
    setHealth({ status: 'loading' })
    setAttempt((value) => value + 1)
  }

  return { health, refresh }
}
