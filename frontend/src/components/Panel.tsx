import type { ReactNode } from 'react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useService } from './ServiceProvider'

export function PageHeading({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <header className="page-heading">
    <div><h1>{title}</h1><p>{description}</p></div>
    {action}
  </header>
}

export function Panel({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return <Card className="min-w-0 gap-4 py-5">
    <CardHeader className="flex flex-wrap items-center justify-between gap-3 px-5">
      <h2 className="text-sm font-semibold tracking-wide">{title}</h2>{action}
    </CardHeader>
    <CardContent className="px-5">{children}</CardContent>
  </Card>
}

export function Empty({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <div className="empty-state" role={error ? 'alert' : 'status'}>
    <span>{children}</span>
  </div>
}

export function ResourceState({ state, unavailable }: { state: string; unavailable: string }) {
  const { capabilities } = useService()
  if (state === 'loading' || capabilities === 'loading') return <Skeleton className="h-24 w-full" aria-label="Loading" />
  if (state === 'error' || capabilities === 'error') return <Empty error>Could not load data. Check API connectivity and reload.</Empty>
  return <Empty>{unavailable}</Empty>
}
