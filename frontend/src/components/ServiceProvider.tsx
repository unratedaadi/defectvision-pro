import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { useHealth } from '@/hooks/useHealth'
import { useResource } from '@/hooks/useResource'
import { getCapabilities } from '@/services/api'

function useServiceState() {
  const health = useHealth()
  const [revision, setRevision] = useState(0)
  const loadCapabilities = useCallback((signal: AbortSignal) => {
    void revision
    return getCapabilities(signal)
  }, [revision])
  const capabilities = useResource(loadCapabilities)
  return {
    ...health,
    refresh: () => { health.refresh(); setRevision((value) => value + 1) },
    capabilities: capabilities.state,
    supports: (path: string, method: string) => Boolean(capabilities.data?.[path]?.[method]),
  }
}

const ServiceContext = createContext<ReturnType<typeof useServiceState> | null>(null)

export function ServiceProvider({ children }: { children: ReactNode }) {
  const state = useServiceState()
  return <ServiceContext.Provider value={state}>{children}</ServiceContext.Provider>
}

export function useService() {
  const service = useContext(ServiceContext)
  if (!service) throw new Error('ServiceProvider is required')
  return service
}
