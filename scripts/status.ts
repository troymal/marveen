import { execSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { platform } from 'node:os'
import { SERVICE_ID, launchdStatusPattern, systemdStatusUnits } from '../src/config.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const PROJECT_ROOT = join(__dirname, '..')

const GREEN = '\x1b[32m'
const YELLOW = '\x1b[33m'
const RED = '\x1b[31m'
const BOLD = '\x1b[1m'
const RESET = '\x1b[0m'

const ok = (label: string, detail?: string) =>
  console.log(`  ${GREEN}✓${RESET} ${label}${detail ? ` — ${detail}` : ''}`)
const warn = (label: string, detail?: string) =>
  console.log(`  ${YELLOW}⚠${RESET} ${label}${detail ? ` — ${detail}` : ''}`)
const fail = (label: string, detail?: string) =>
  console.log(`  ${RED}✗${RESET} ${label}${detail ? ` — ${detail}` : ''}`)

console.log(`\n${BOLD}Marveen Allapot${RESET}\n`)

// Node.js
const nodeVersion = process.version
const major = parseInt(nodeVersion.slice(1), 10)
if (major >= 20) {
  ok('Node.js', nodeVersion)
} else {
  fail('Node.js', `${nodeVersion} — minimum v20 szukseges`)
}

// Claude CLI
try {
  const cv = execSync('claude --version 2>/dev/null', { encoding: 'utf-8' }).trim()
  ok('Claude CLI', cv)
} catch {
  fail('Claude CLI', 'nem talalhato')
}

// .env
const envPath = join(PROJECT_ROOT, '.env')
if (existsSync(envPath)) {
  const envContent = readFileSync(envPath, 'utf-8')
  const getVal = (key: string) => {
    const m = envContent.match(new RegExp(`^${key}=(.+)$`, 'm'))
    return m?.[1]?.trim()
  }

  // Telegram token
  const token = getVal('TELEGRAM_BOT_TOKEN')
  if (token) {
    ok('Telegram bot token', 'beallitva')
  } else {
    fail('Telegram bot token', 'hianyzik')
  }

  // Chat ID
  const chatId = getVal('ALLOWED_CHAT_ID')
  if (chatId) {
    ok('Chat ID', chatId)
  } else {
    warn('Chat ID', 'nincs beallitva — a bot mindenkit fogad')
  }

  // ElevenLabs
  const elKey = getVal('ELEVENLABS_API_KEY')
  const elVoice = getVal('ELEVENLABS_VOICE_ID')
  if (elKey && elVoice) {
    ok('ElevenLabs TTS', 'konfigurálva')
  } else if (elKey) {
    warn('ElevenLabs TTS', 'API kulcs megvan, de Voice ID hianyzik')
  } else {
    warn('ElevenLabs TTS', 'nincs konfigurálva')
  }
} else {
  fail('.env fajl', 'nem talalhato — futtasd: npm run setup')
}

// Adatbázis
const dbPath = join(PROJECT_ROOT, 'store', 'claudeclaw.db')
if (existsSync(dbPath)) {
  ok('Adatbazis', 'letezik')
  try {
    const sqlite = execSync(
      `sqlite3 "${dbPath}" "SELECT COUNT(*) FROM memories;" 2>/dev/null`,
      { encoding: 'utf-8' }
    ).trim()
    ok('Emlekek szama', sqlite)
  } catch {
    warn('Emlekek szama', 'nem sikerult lekerdezni')
  }
  try {
    const taskCount = execSync(
      `sqlite3 "${dbPath}" "SELECT COUNT(*) FROM scheduled_tasks;" 2>/dev/null`,
      { encoding: 'utf-8' }
    ).trim()
    ok('Utemezett feladatok', taskCount)
  } catch {
    warn('Utemezett feladatok', 'nem sikerult lekerdezni')
  }
} else {
  warn('Adatbazis', 'meg nem letezik (elso inditaskor jon letre)')
}

// Szolgáltatás állapot
const os = platform()
if (os === 'darwin') {
  try {
    const out = execSync(`launchctl list | grep -E "${launchdStatusPattern(SERVICE_ID)}" 2>/dev/null`, {
      encoding: 'utf-8',
    }).trim()
    if (out) {
      ok('Hatterszolgaltatas (launchd)', 'fut')
    } else {
      warn('Hatterszolgaltatas (launchd)', 'nem fut')
    }
  } catch {
    warn('Hatterszolgaltatas (launchd)', 'nem talalhato')
  }
} else if (os === 'linux') {
  // Scope-aware, mirroring doctor.sh: the stack runs as SYSTEM units
  // (root-style install / service account converted via install-system-units.sh),
  // USER units (default install-linux.sh), or a direct nohup launch (no systemd
  // at all) tracked by store/*.pid. Only probing `systemctl --user` reported a
  // live service as down on every non-user-manager shape.
  const units = systemdStatusUnits(SERVICE_ID)
  const isActive = (cmd: string) => {
    try {
      execSync(cmd, { encoding: 'utf-8' })
      return true
    } catch {
      return false
    }
  }
  const systemScope = units.map((u) => `systemctl is-active ${u} 2>/dev/null`).join(' || ')
  const userScope = units.map((u) => `systemctl --user is-active ${u} 2>/dev/null`).join(' || ')
  const pidAlive = (file: string) => {
    const p = join(PROJECT_ROOT, 'store', file)
    if (!existsSync(p)) return false
    try {
      process.kill(parseInt(readFileSync(p, 'utf-8').trim(), 10), 0)
      return true
    } catch {
      return false
    }
  }
  if (isActive(systemScope)) {
    ok('Hatterszolgaltatas (systemd)', 'aktiv (system unit)')
  } else if (isActive(userScope)) {
    ok('Hatterszolgaltatas (systemd)', 'aktiv (user unit)')
  } else if (pidAlive('dashboard.pid') || pidAlive('channels.pid')) {
    ok('Hatterszolgaltatas (nohup)', 'aktiv')
  } else {
    warn('Hatterszolgaltatas', 'nem aktiv')
  }
}

// PID
const pidPath = join(PROJECT_ROOT, 'store', 'claudeclaw.pid')
if (existsSync(pidPath)) {
  const pid = readFileSync(pidPath, 'utf-8').trim()
  try {
    process.kill(parseInt(pid, 10), 0)
    ok('Folyamat', `fut (PID: ${pid})`)
  } catch {
    warn('Folyamat', `PID fajl letezik (${pid}) de a folyamat nem fut`)
  }
} else {
  warn('Folyamat', 'nem fut (nincs PID fajl)')
}

console.log('')
