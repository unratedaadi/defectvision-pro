export interface ProductCategory {
  slug: string
  name: string
}

export type Health =
  | { status: 'ok'; database: 'ready'; categories: ProductCategory[] }
  | { status: 'degraded'; database: 'unavailable'; categories: [] }
