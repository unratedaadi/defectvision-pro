import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useHealth } from '@/hooks/useHealth'
import { apiBaseUrl } from '@/services/api'

export function Workspace({ system = false }: { system?: boolean }) {
  const { health, refresh } = useHealth()
  const connected = health.status === 'ok' || health.status === 'degraded'
  const loading = health.status === 'loading'
  return (
    <>
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{system ? 'System status' : 'Inspection overview'}</h1>
          <p className="mt-2 text-muted-foreground">{system ? 'API connectivity and SQLite readiness.' : 'Product catalog and inspection service readiness.'}</p>
        </div>
        <button type="button" disabled={loading} onClick={() => { refresh(); toast('Refreshing service status') }}
          className="flex items-center gap-2 rounded-none border border-border px-3 py-2 text-sm hover:bg-muted disabled:opacity-50">
           Refresh
        </button>
      </header>
      <div className="grid gap-4 sm:grid-cols-2" aria-live="polite">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"> Inspection API</CardTitle>
            <CardDescription className="break-all">{apiBaseUrl}</CardDescription>
          </CardHeader>
          <CardContent>{loading ? <Skeleton className="h-5 w-28" aria-label="Checking API" /> : connected ? 'Connected' : 'Unreachable'}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"> SQLite</CardTitle>
            <CardDescription>Product catalog storage</CardDescription>
          </CardHeader>
          <CardContent>{loading ? <Skeleton className="h-5 w-28" aria-label="Checking database" /> :
            health.status === 'ok' ? 'Ready' : connected ? 'Unavailable' : 'Unknown'}</CardContent>
        </Card>
      </div>
      {health.status === 'offline' && <p role="alert" className="mt-5 text-muted-foreground">Start the API and check the configured API URL, then refresh.</p>}
      {health.status === 'degraded' && <p role="alert" className="mt-5 text-muted-foreground">Check the SQLite path and run the database migration, then refresh.</p>}
      {!system && (
        <section className="mt-10 border-t border-border pt-7" aria-labelledby="catalog">
          <h2 id="catalog" className="text-xl font-semibold">Product catalog</h2>
          {health.status === 'ok' && (
            <ul className="mt-5 divide-y divide-border rounded-none border border-border bg-card">
              {health.categories.map((category) => <li className="px-5 py-4" key={category.slug}>{category.name}</li>)}
            </ul>
          )}
        </section>
      )}
    </>
  )
}
