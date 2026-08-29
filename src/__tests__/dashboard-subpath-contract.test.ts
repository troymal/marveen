// String-contract guard for the dashboard's reverse-proxy subpath support
// (DASHBOARD_PREFIX). The client must use document-relative asset/API paths
// (no leading slash) so the dashboard works mounted under e.g. /dashboard/,
// and the server-side cache-bust injection must keep rewriting both the
// relative and absolute asset forms to a relative, versioned URL -- otherwise
// the ?v= token is silently dropped and the 86400s max-age serves stale
// assets forever under a prefix.
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { injectCacheBust } from '../web/routes/static.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(__dirname, '..', '..')
const HTML = readFileSync(join(REPO_ROOT, 'web', 'index.html'), 'utf-8')

describe('dashboard subpath (DASHBOARD_PREFIX) contract', () => {
  it('index.html references app.js and style.css relatively (no leading slash)', () => {
    expect(HTML).toMatch(/<script\s+src="app\.js"/)
    expect(HTML).toMatch(/<link\s+rel="stylesheet"\s+href="style\.css"/)
    expect(HTML).not.toMatch(/src="\/app\.js"/)
    expect(HTML).not.toMatch(/href="\/style\.css"/)
  })

  it('injectCacheBust rewrites the relative asset form to a versioned relative URL', () => {
    const out = injectCacheBust(
      '<script src="app.js"></script><link rel="stylesheet" href="style.css">',
      'v1',
      'v2',
    )
    expect(out).toContain('src="app.js?v=v1"')
    expect(out).toContain('href="style.css?v=v2"')
  })

  it('injectCacheBust rewrites the absolute asset form (develop) to relative too', () => {
    const out = injectCacheBust(
      '<script src="/app.js"></script><link rel="stylesheet" href="/style.css">',
      'v1',
      'v2',
    )
    expect(out).toContain('src="app.js?v=v1"')
    expect(out).toContain('href="style.css?v=v2"')
  })

  it('sidebar brand links to the dashboard home relative to the current prefix', () => {
    expect(HTML).toMatch(/class="sidebar-brand"\s+href="\.\/"/)
  })
})
