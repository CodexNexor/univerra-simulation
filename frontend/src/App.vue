<template>
  <div id="app-root">
    <!-- The normal page content (route view) -->
    <router-view v-show="!showPlayground || viewMode === 'backend'" />

    <!-- Playground overlay: appears on work routes, toggleable -->
    <div v-if="isWorkRoute" class="playground-layer" v-show="showPlayground && viewMode === 'frontend'">
      <PlaygroundFrontend
        :chatHistory="chatHistory"
        :systemState="systemState"
        :actionRequired="actionRequired"
        @submit-prompt="handlePromptSubmit"
        @submit-action="handleActionSubmit"
      />
    </div>

    <!-- Floating toggle: appears on work routes -->
    <div v-if="isWorkRoute" class="mode-toggle">
      <button :class="{ active: viewMode === 'frontend' }" @click="viewMode = 'frontend'">Frontend</button>
      <button :class="{ active: viewMode === 'backend' }" @click="viewMode = 'backend'">Backend</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PlaygroundFrontend from './components/PlaygroundFrontend.vue'
import { setPendingUpload } from './store/pendingUpload'
import { getReport, getReportBySimulation } from './api/report'

const route = useRoute()
const router = useRouter()

// Determine if the current route is a "work" route (not landing/about/terms)
const workRoutes = ['Home', 'Process', 'Simulation', 'SimulationRun', 'Report', 'Interaction']
const isWorkRoute = computed(() => workRoutes.includes(route.name))

// Show playground on /app (Home) by default
const showPlayground = computed(() => isWorkRoute.value)

// View mode: frontend (playground) or backend (normal view)
const viewMode = ref('frontend')

// When route changes to a non-Home work route, switch to backend view so user sees the process
watch(() => route.name, (newName) => {
  if (newName === 'Home') {
    viewMode.value = 'frontend'
  }
  updateSystemState(newName)
})

// Persistent chat + system state
const chatHistory = ref([])
const systemState = ref({ step: 0, phase: -1, projectData: null, answerReady: false })
const actionRequired = ref(null)
const surfacedReportId = ref(null)

const updateSystemState = (routeName) => {
  if (routeName === 'Process') systemState.value.step = 1
  if (routeName === 'Simulation') systemState.value.step = 2
  if (routeName === 'SimulationRun') systemState.value.step = 3
  if (routeName === 'Report') systemState.value.step = 4
  if (routeName === 'Interaction') {
    systemState.value.step = 5
  }
}

// Listen for backend log events to track phases
const onBackendLog = (e) => {
  if (e.detail?.msg) {
    const msg = e.detail.msg
    // Track phases from log messages
    if (msg.includes('ontology generation')) systemState.value.phase = 0
    if (msg.includes('graph build')) systemState.value.phase = 1
    if (msg.includes('Graph data loaded') || msg.includes('Graph build task completed')) systemState.value.phase = 2
    if (msg.includes('Agent Personas')) systemState.value.step = 2
    if (msg.includes('Simulation')) systemState.value.step = 3
  }
}

const onActionRequired = (e) => {
  actionRequired.value = e.detail || {
    type: 'start-dual',
    title: 'Custom Simulation Details',
    message: 'The backend is waiting for your input before continuing.',
    actionLabel: 'Continue'
  }
}

const onAuthExpired = () => {
  if (route.meta.requiresAuth) {
    router.push({ name: 'Login', query: { redirect: route.fullPath } })
  }
}

const escapeHtml = (text = '') => text
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')

const markdownToHtml = (markdown = '') => {
  const lines = String(markdown || '').split('\n')
  let html = ''
  let inList = false

  const closeList = () => {
    if (inList) {
      html += '</ul>'
      inList = false
    }
  }

  const inline = (value) => escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')

  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) {
      closeList()
      continue
    }

    if (line.startsWith('### ')) {
      closeList()
      html += `<h3>${inline(line.slice(4))}</h3>`
    } else if (line.startsWith('## ')) {
      closeList()
      html += `<h2>${inline(line.slice(3))}</h2>`
    } else if (line.startsWith('# ')) {
      closeList()
      html += `<h1>${inline(line.slice(2))}</h1>`
    } else if (line.startsWith('- ')) {
      if (!inList) {
        html += '<ul>'
        inList = true
      }
      html += `<li>${inline(line.slice(2))}</li>`
    } else {
      closeList()
      html += `<p>${inline(line)}</p>`
    }
  }

  closeList()
  return html
}

const surfaceFinalAnswer = async ({ reportId = null, simulationId = null } = {}) => {
  try {
    let reportData = null

    if (reportId) {
      const reportRes = await getReport(reportId)
      if (reportRes.success) {
        reportData = reportRes.data
      }
    } else if (simulationId) {
      const reportRes = await getReportBySimulation(simulationId)
      if (reportRes.success) {
        reportData = reportRes.data
      }
    }

    if (!reportData?.report_id || surfacedReportId.value === reportData.report_id) {
      return
    }

    surfacedReportId.value = reportData.report_id
    systemState.value = {
      ...systemState.value,
      answerReady: true,
      reportId: reportData.report_id
    }

    chatHistory.value = chatHistory.value.filter(msg => msg.type !== 'summary')
    chatHistory.value.push({
      role: 'assistant',
      type: 'final-answer',
      title: reportData.outline?.title || 'Univerra Result',
      html: markdownToHtml(reportData.markdown_content || reportData.outline?.summary || ''),
      content: reportData.markdown_content || reportData.outline?.summary || '',
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    console.warn('Failed to surface final answer in frontend overlay:', error)
  }
}

onMounted(() => {
  window.addEventListener('univerra-log', onBackendLog)
  window.addEventListener('univerra-action-required', onActionRequired)
  window.addEventListener('univerra-auth-expired', onAuthExpired)
})

onUnmounted(() => {
  window.removeEventListener('univerra-log', onBackendLog)
  window.removeEventListener('univerra-action-required', onActionRequired)
  window.removeEventListener('univerra-auth-expired', onAuthExpired)
})

// Handle prompt from PlaygroundFrontend
const handlePromptSubmit = (promptText) => {
  // Add user message to chat
  chatHistory.value.push({ role: 'user', text: promptText })

  // Show the system monitor
  chatHistory.value.push({ role: 'system', type: 'system-monitor' })

  // Set the pending upload state (same as Home.vue does)
  setPendingUpload([], promptText)
  viewMode.value = 'frontend'
  surfacedReportId.value = null
  systemState.value = { step: 1, phase: -1, projectData: null, answerReady: false }

  // Navigate to /process/new — this is EXACTLY what the old Home.vue did
  router.push({ name: 'Process', params: { projectId: 'new' } })
}

const handleActionSubmit = (payload) => {
  actionRequired.value = null
  if (payload?.type === 'dismiss-action' || payload?.dismissed) {
    return
  }
  window.dispatchEvent(new CustomEvent('frontend-authorize-action', { detail: payload }))
}

watch(
  () => [route.name, route.params.reportId, route.params.simulationId],
  async ([routeName, reportId, simulationId]) => {
    if (routeName === 'Report' && reportId) {
      await surfaceFinalAnswer({ reportId })
    } else if (routeName === 'Interaction' && reportId) {
      await surfaceFinalAnswer({ reportId })
    } else if (routeName === 'SimulationRun' && simulationId) {
      systemState.value = { ...systemState.value, answerReady: false }
    }
  },
  { immediate: true }
)
</script>

<style>
/* Global style reset */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html {
  scroll-behavior: smooth;
}

:root {
  /* Global Dark Theme Variables */
  --bg-primary: #050505;
  --bg-secondary: rgba(255, 255, 255, 0.03);
  --bg-blur: blur(20px);
  --text-main: #FAFAFA;
  --text-muted: #A0A0A0;
  --accent-primary: #FF4500;
  --accent-glow: rgba(255, 69, 0, 0.4);
  --border-color: rgba(255, 255, 255, 0.1);
  --gradient-text: linear-gradient(90deg, #FFFFFF 0%, #A0A0A0 100%);
  --gradient-accent: linear-gradient(135deg, #FF4500 0%, #FF8C00 100%);

  /* Fonts */
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

body {
  background-color: var(--bg-primary);
  color: var(--text-main);
  overflow-x: hidden;
}

#app {
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  min-height: 100vh;
}

/* Scrollbar styles */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--bg-primary);
}

::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}

/* Global button styles */
button {
  font-family: inherit;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Scroll Animation Utilities */
.reveal-element {
  opacity: 0;
  transform: translateY(30px);
  transition: opacity 0.8s cubic-bezier(0.16, 1, 0.3, 1), transform 0.8s cubic-bezier(0.16, 1, 0.3, 1);
  will-change: opacity, transform;
}

.reveal-element.is-revealed {
  opacity: 1;
  transform: translateY(0);
}

/* Delay modifiers */
.delay-100 { transition-delay: 100ms; }
.delay-200 { transition-delay: 200ms; }
.delay-300 { transition-delay: 300ms; }
.delay-400 { transition-delay: 400ms; }
.delay-500 { transition-delay: 500ms; }

/* Custom Selection */
::selection {
  background: var(--accent-primary);
  color: #fff;
}

/* --- App-level Playground & Toggle --- */
#app-root {
  position: relative;
  min-height: 100vh;
}

.playground-layer {
  position: fixed;
  inset: 0;
  z-index: 900;
  background: #0a0a0a;
}

.mode-toggle {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2000;
  background: rgba(15, 15, 15, 0.95);
  backdrop-filter: blur(12px);
  padding: 4px;
  border-radius: 10px;
  display: flex;
  gap: 4px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
}

.mode-toggle button {
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.4);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  padding: 8px 18px;
  border-radius: 6px;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  transition: all 0.2s;
}

.mode-toggle button.active {
  background: #E8F5A2;
  color: #000;
}

.mode-toggle button:hover:not(.active) {
  color: rgba(255, 255, 255, 0.7);
}
</style>
