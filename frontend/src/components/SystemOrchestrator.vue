<template>
  <div class="system-orchestrator">
    <!-- Overlay Header -->
    <div class="orchestrator-nav">
      <div class="nav-brand" @click="$router.push('/')">UNIVERRA</div>

      <!-- The requested Two Buttons Top Notch -->
      <div class="two-buttons">
        <button class="toggle-btn" :class="{ active: appMode === 'backend' }" @click="appMode = 'backend'">Backend</button>
        <button class="toggle-btn" :class="{ active: appMode === 'frontend' }" @click="appMode = 'frontend'">Frontend</button>
      </div>

      <div class="nav-profile">
        <div class="status-dot"></div> System Active
      </div>
    </div>

    <!-- Frontend Wrapper -->
    <PlaygroundFrontend
      v-show="appMode === 'frontend'"
      :chatHistory="chatHistory"
      :systemState="systemState"
      :actionRequired="actionRequired"
      @submit-prompt="handlePromptSubmit"
      @submit-action="handleActionSubmit"
    />

    <!-- Backend Wrapper (preserved state via v-show, never destroyed) -->
    <div class="backend-container" v-show="appMode === 'backend'">
      <ConsoleBackend
        v-if="backendActive"
        :key="backendKey"
        :projectId="activeProjectId"
        :autoPilot="true"
        @project-created="handleProjectCreated"
        @state-update="handleStateUpdate"
        @action-required="handleActionRequired"
      />
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PlaygroundFrontend from '../components/PlaygroundFrontend.vue'
import ConsoleBackend from '../components/ConsoleBackend.vue'
import { setPendingUpload } from '../store/pendingUpload'

const route = useRoute()
const router = useRouter()

// appMode is frontend by default
const appMode = ref('frontend')

// Data links
const activeProjectId = ref(route.params.projectId || 'new')
const backendKey = ref(0)
const backendActive = ref(false)

const systemState = ref({ step: 1, phase: -1, projectData: null })
const actionRequired = ref(false)

// Chat History state
const chatHistory = ref([])

onMounted(() => {
  // If we load straight into a project (e.g. /app/proj_123), launch backend immediately
  if (activeProjectId.value && activeProjectId.value !== 'new') {
    backendActive.value = true
    chatHistory.value.push({
      role: 'user',
      text: 'Resumed Project: ' + activeProjectId.value
    })
    chatHistory.value.push({ role: 'system', type: 'system-monitor' })
  }
})

// Listen for state updates from ConsoleBackend via window events
const onStateUpdate = (e) => {
  if (e.detail) {
    systemState.value = { ...systemState.value, ...e.detail }
  }
}
const onProjectCreated = (e) => {
  if (e.detail) {
    activeProjectId.value = e.detail
    // Silently update URL without full navigation
    window.history.replaceState({}, '', `/app/${e.detail}`)
  }
}

window.addEventListener('frontend-state-update', onStateUpdate)
window.addEventListener('project-created', onProjectCreated)

onUnmounted(() => {
  window.removeEventListener('frontend-state-update', onStateUpdate)
  window.removeEventListener('project-created', onProjectCreated)
})

const handlePromptSubmit = (promptText) => {
  // 1. Add user message to chat
  chatHistory.value.push({ role: 'user', text: promptText })

  // 2. Set backend upload state so ConsoleBackend picks it up on mount
  setPendingUpload([], promptText)

  // 3. Mount backend with a fresh key (forces re-init if already mounted)
  activeProjectId.value = 'new'
  backendKey.value++
  backendActive.value = true

  // 4. Show the system monitor in-line
  chatHistory.value.push({ role: 'system', type: 'system-monitor' })
}

const handleProjectCreated = (newId) => {
  activeProjectId.value = newId
  window.history.replaceState({}, '', `/app/${newId}`)
}

const handleStateUpdate = (newState) => {
  systemState.value = newState

  // When simulation reaches step 5, inject summary
  if (newState.step === 5 && !chatHistory.value.some(msg => msg.type === 'summary')) {
    chatHistory.value.push({
      role: 'system',
      type: 'summary',
      reportText: "The simulation has completed. Full interaction traces have been firmly logged in the backend. Destabilization vectors were minimal."
    })
  }
}

const handleActionRequired = (actionData) => {
  actionRequired.value = true
}

const handleActionSubmit = (actionCommand) => {
  actionRequired.value = false
  const event = new CustomEvent('frontend-authorize-action', { detail: actionCommand })
  window.dispatchEvent(event)
}
</script>

<style scoped>
.system-orchestrator {
  position: relative;
  height: 100vh;
  width: 100vw;
  background: #0a0a0a;
  overflow: hidden;
}

.orchestrator-nav {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 60px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 40px;
  z-index: 1000;
  pointer-events: none;
}

.nav-brand {
  font-family: var(--font-mono), 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 16px;
  color: #fff;
  cursor: pointer;
  pointer-events: auto;
  letter-spacing: 1px;
}

.two-buttons {
  background: rgba(25, 25, 25, 0.9);
  backdrop-filter: blur(10px);
  padding: 4px;
  border-radius: 8px;
  display: flex;
  gap: 4px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  pointer-events: auto;
}

.toggle-btn {
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.5);
  font-family: var(--font-mono), 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 700;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.toggle-btn.active {
  background: #E8F5A2;
  color: #000;
}

.nav-profile {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono), 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #888;
  pointer-events: none;
}

.status-dot {
  width: 6px; height: 6px;
  background: #E8F5A2;
  border-radius: 50%;
}

.backend-container {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  z-index: 500;
  overflow: hidden;
}

/* Hide the native header inside ConsoleBackend since we have our own */
:deep(.app-header) {
  display: none !important;
}
:deep(.content-area) {
  top: 60px !important;
}
:deep(.main-view) {
  height: 100vh;
}
</style>
