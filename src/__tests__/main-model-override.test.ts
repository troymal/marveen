import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { writeFileSync, readFileSync, unlinkSync, mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

// The main agent's model is pinned in .env (MAIN_AGENT_MODEL), not in the
// TRACKED .claude/settings.json. scripts/channels.sh has honoured that
// precedence since it was introduced (scripts/__tests__/channels-main-model.test.sh
// locks it); the DASHBOARD side did not, so every dashboard-driven respawn --
// nightly restart, stage-3 resume, hard restart, model fallback -- relaunched
// main on the repository's settings.json model and silently reverted the
// operator's choice. These tests lock the .env accessors the dashboard now uses.
//
// Same ENFORCED sandbox as env.test.ts: env.ts resolves its own PROJECT_ROOT,
// so the redirect is the CLAUDECLAW_ENV_DIR hook read at module import time --
// set it BEFORE the dynamic imports, never write to the live repo .env.
const SANDBOX = mkdtempSync(join(tmpdir(), 'main-model-test-'))
const testEnvPath = join(SANDBOX, '.env')

beforeAll(() => {
  process.env.CLAUDECLAW_ENV_DIR = SANDBOX
})

afterAll(() => {
  delete process.env.CLAUDECLAW_ENV_DIR
  rmSync(SANDBOX, { recursive: true, force: true })
})

describe('readMainModelOverride', () => {
  it('reads MAIN_AGENT_MODEL from .env', async () => {
    writeFileSync(testEnvPath, 'MAIN_AGENT_ID=marveen\nMAIN_AGENT_MODEL=claude-opus-5\n')
    const { readMainModelOverride } = await import('../web/agent-config.js')
    expect(readMainModelOverride()).toBe('claude-opus-5')
  })

  it('returns empty when the key is absent, so settings.json stays in charge', async () => {
    writeFileSync(testEnvPath, 'MAIN_AGENT_ID=marveen\n')
    const { readMainModelOverride } = await import('../web/agent-config.js')
    expect(readMainModelOverride()).toBe('')
  })

  it('returns empty when the value is blank rather than shadowing settings.json', async () => {
    writeFileSync(testEnvPath, 'MAIN_AGENT_MODEL=\n')
    const { readMainModelOverride } = await import('../web/agent-config.js')
    expect(readMainModelOverride()).toBe('')
  })

  it('does not leak a similarly named key', async () => {
    writeFileSync(testEnvPath, 'NOT_MAIN_AGENT_MODEL=claude-haiku-4-5-20251001\n')
    const { readMainModelOverride } = await import('../web/agent-config.js')
    expect(readMainModelOverride()).toBe('')
  })

  it('keeps a bracketed suffix intact (claude-opus-4-8[1m])', async () => {
    writeFileSync(testEnvPath, 'MAIN_AGENT_MODEL=claude-opus-4-8[1m]\n')
    const { readMainModelOverride } = await import('../web/agent-config.js')
    expect(readMainModelOverride()).toBe('claude-opus-4-8[1m]')
  })

  it('re-reads the file, so an operator edit lands without a dashboard restart', async () => {
    writeFileSync(testEnvPath, 'MAIN_AGENT_MODEL=claude-sonnet-5\n')
    const { readMainModelOverride } = await import('../web/agent-config.js')
    expect(readMainModelOverride()).toBe('claude-sonnet-5')
    writeFileSync(testEnvPath, 'MAIN_AGENT_MODEL=claude-opus-5\n')
    expect(readMainModelOverride()).toBe('claude-opus-5')
  })

  it('survives a missing .env', async () => {
    try { unlinkSync(testEnvPath) } catch { /* absent */ }
    const { readMainModelOverride } = await import('../web/agent-config.js')
    expect(readMainModelOverride()).toBe('')
  })
})

describe('writeMainModelOverride', () => {
  it('rewrites the value in place and preserves the other lines', async () => {
    writeFileSync(testEnvPath, '# main\nMAIN_AGENT_ID=marveen\nMAIN_AGENT_MODEL=claude-sonnet-5\nWEB_HOST=0.0.0.0\n')
    const { writeMainModelOverride, readMainModelOverride } = await import('../web/agent-config.js')
    writeMainModelOverride('claude-opus-5')
    const written = readFileSync(testEnvPath, 'utf-8')
    expect(written).toContain('MAIN_AGENT_MODEL=claude-opus-5')
    expect(written).toContain('MAIN_AGENT_ID=marveen')
    expect(written).toContain('WEB_HOST=0.0.0.0')
    expect(written).toContain('# main')
    expect(readMainModelOverride()).toBe('claude-opus-5')
  })

  it('writes unquoted -- channels.sh parses with `cut -d= -f2-` and strips no quotes', async () => {
    writeFileSync(testEnvPath, 'MAIN_AGENT_MODEL=claude-sonnet-5\n')
    const { writeMainModelOverride } = await import('../web/agent-config.js')
    writeMainModelOverride('claude-opus-4-8[1m]')
    expect(readFileSync(testEnvPath, 'utf-8')).toContain('MAIN_AGENT_MODEL=claude-opus-4-8[1m]\n')
  })
})
