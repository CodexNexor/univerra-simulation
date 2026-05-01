<template>
  <div class="main-view" v-reveal>
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <div class="brand" @click="router.push('/')">UNIVERRA</div>
      </div>

      <div class="header-center">
        <div class="view-switcher">
          <button
            v-for="mode in ['graph', 'split', 'workbench']"
            :key="mode"
            class="switch-btn"
            :class="{ active: viewMode === mode }"
            @click="viewMode = mode"
          >
            {{ { graph: 'Graph', split: 'Split', workbench: 'Workbench' }[mode] }}
          </button>
        </div>
      </div>

      <div class="header-right">
        <div class="workflow-step">
          <span class="step-num">Step {{ currentStep }}/5</span>
          <span class="step-name">{{ stepNames[currentStep - 1] }}</span>
        </div>
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass">
          <span class="dot"></span>
          {{ statusText }}
        </span>
      </div>
    </header>

    <!-- Main Content Area -->
    <main class="content-area">
      <!-- Left Panel: Graph -->
      <div class="panel-wrapper left" :style="leftPanelStyle">
        <GraphPanel
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="currentPhase"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>

      <!-- Right Panel: Step Components -->
      <div class="panel-wrapper right" :style="rightPanelStyle">
        <!-- Step 1: Graph Building -->
        <Step1GraphBuild
          v-if="currentStep === 1"
          :currentPhase="currentPhase"
          :projectData="projectData"
          :ontologyProgress="ontologyProgress"
          :buildProgress="buildProgress"
          :graphData="graphData"
          :systemLogs="systemLogs"
          :errorMessage="error"
          @next-step="handleNextStep"
        />
        <!-- Step 2: Environment Setup -->
        <Step2EnvSetup
          v-else-if="currentStep === 2"
          :projectData="projectData"
          :graphData="graphData"
          :systemLogs="systemLogs"
          @go-back="handleGoBack"
          @next-step="handleNextStep"
          @add-log="addLog"
          @refresh-graph="refreshGraph"
        />
      </div>
    </main>

    <Transition name="modal">
      <div
        v-if="clarificationModal.visible"
        class="clarification-modal-overlay"
        @click.self="closeClarificationModal"
      >
        <div class="clarification-modal">
          <div class="clarification-header">
            <div>
              <div class="clarification-kicker">Custom Simulation Details</div>
              <div class="clarification-title">A bit more detail will make this run more accurate</div>
            </div>
            <button class="clarification-close" @click="closeClarificationModal">×</button>
          </div>

          <div class="clarification-body">
            <p class="clarification-copy">
              The backend paused because the prompt is missing a few grounding details. Add what you know below and Univerra will continue from here.
            </p>

            <div v-if="clarificationModal.missingContext.length" class="clarification-hints">
              <div
                v-for="item in clarificationModal.missingContext"
                :key="item"
                class="hint-chip"
              >
                {{ item }}
              </div>
            </div>

            <div
              v-for="(question, index) in clarificationModal.questions"
              :key="`${index}-${question}`"
              class="clarification-question"
            >
              <label class="clarification-label">{{ question }}</label>
              <textarea
                v-model="clarificationModal.answers[index]"
                class="clarification-input"
                rows="3"
                :placeholder="clarificationPlaceholders[index] || 'Add the detail here...'"
              ></textarea>
            </div>
          </div>

          <div class="clarification-actions">
            <button class="modal-btn secondary" @click="continueWithoutClarification">
              Continue Anyway
            </button>
            <button
              class="modal-btn primary"
              :disabled="submittingClarification || !hasClarificationAnswer"
              @click="submitClarification"
            >
              {{ submittingClarification ? 'Continuing...' : 'Submit Details' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '../components/GraphPanel.vue'
import Step1GraphBuild from '../components/Step1GraphBuild.vue'
import Step2EnvSetup from '../components/Step2EnvSetup.vue'
import { generateOntology, getProject, buildGraph, getTaskStatus, getGraphData } from '../api/graph'
import { getPendingUpload, clearPendingUpload, setPendingUpload } from '../store/pendingUpload'

const route = useRoute()
const router = useRouter()

// Layout State
const viewMode = ref('split') // graph | split | workbench

// Step State
const currentStep = ref(1) // 1: Graph Building, 2: Environment Setup, 3: Run Simulation, 4: Report Generation, 5: Deep Interaction
const stepNames = ['Graph Building', 'Environment Setup', 'Run Simulation', 'Report Generation', 'Deep Interaction']

// Data State
const currentProjectId = ref(route.params.projectId)
const loading = ref(false)
const graphLoading = ref(false)
const error = ref('')
const projectData = ref(null)
const graphData = ref(null)
const ontologyProgress = ref(null)
const buildProgress = ref(null)
const currentPhase = ref(-1) // -1: Before upload, 0: Ontology, 1: Building Graph, 2: Graph Complete
const systemLogs = ref([])
const clarificationModal = ref({
  visible: false,
  missingContext: [],
  questions: [],
  answers: []
})
const submittingClarification = ref(false)
let pollTimer = null
let graphPollTimer = null

const clarificationPlaceholders = [
  'Example: Focus on the next 3 months, starting from April 20, 2026.',
  'Example: I am a junior developer with 4 months of Python practice and no production job yet.',
  'Example: I want to know my likely job path, risks, and what skill gaps matter most.'
]

// --- Computed Layout Styles ---
const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0, transform: 'translateX(-20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, transform: 'translateX(20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

// --- Status Computed ---
const statusClass = computed(() => {
  if (error.value) return 'error'
  if (currentPhase.value >= 2) return 'completed'
  if (currentPhase.value >= 0) return 'processing'
  return ''
})

const statusText = computed(() => {
  if (error.value) return 'Error'
  if (currentPhase.value >= 2) return 'Ready'
  if (currentPhase.value >= 0) return 'Processing'
  return 'Idle'
})

const hasClarificationAnswer = computed(() =>
  clarificationModal.value.answers.some(answer => (answer || '').trim())
)

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 200) {
    systemLogs.value.shift()
  }

  // Broadcast state for Playground overlay
  window.dispatchEvent(new CustomEvent('univerra-log', { detail: { time, msg } }))
}

const buildOntologyFormData = (pending) => {
  const formData = new FormData()
  pending.files.forEach(f => formData.append('files', f))
  formData.append('simulation_requirement', pending.simulationRequirement)
  formData.append('source_text', pending.simulationRequirement)

  if (pending.additionalContext?.trim()) {
    formData.append('additional_context', pending.additionalContext.trim())
  }

  return formData
}

const openClarificationModal = (data = {}) => {
  clarificationModal.value = {
    visible: true,
    missingContext: Array.isArray(data.missing_context) ? data.missing_context : [],
    questions: Array.isArray(data.questions) && data.questions.length
      ? data.questions
      : ['What extra detail should Univerra know before continuing?'],
    answers: Array.isArray(data.questions) && data.questions.length
      ? data.questions.map(() => '')
      : ['']
  }

  window.dispatchEvent(new CustomEvent('univerra-action-required', {
    detail: {
      type: 'clarification',
      title: 'Custom Simulation Details',
      message: 'The backend needs a few more grounded details before it can continue the simulation.',
      missingContext: clarificationModal.value.missingContext,
      questions: clarificationModal.value.questions,
      allowContinueWithout: true,
      actionLabel: 'Submit Details'
    }
  }))
}

const closeClarificationModal = () => {
  clarificationModal.value = {
    visible: false,
    missingContext: [],
    questions: [],
    answers: []
  }
}

// --- Layout Methods ---
const toggleMaximize = (target) => {
  if (viewMode.value === target) {
    viewMode.value = 'split'
  } else {
    viewMode.value = target
  }
}

const handleNextStep = (params = {}) => {
  if (currentStep.value < 5) {
    currentStep.value++
    addLog(`Entering Step ${currentStep.value}: ${stepNames[currentStep.value - 1]}`)

    // If entering Step 3 from Step 2, log simulation round config
    if (currentStep.value === 3 && params.maxRounds) {
      addLog(`Custom simulation rounds: ${params.maxRounds}`)
    }
  }
}

const handleGoBack = () => {
  if (currentStep.value > 1) {
    currentStep.value--
    addLog(`Returning to Step ${currentStep.value}: ${stepNames[currentStep.value - 1]}`)
  }
}

// --- Data Logic ---
const initProject = async () => {
  if (currentProjectId.value === 'new') {
    await handleNewProject()
  } else {
    await loadProject()
  }
}

const handleNewProject = async () => {
  const pending = getPendingUpload()
  if (!pending.isPending || !pending.simulationRequirement?.trim()) {
    error.value = 'No pending simulation details found.'
    addLog('Error: No pending simulation details found for new project.')
    return
  }

  if (pending.requiresFileReselection && pending.pendingFileNames?.length) {
    addLog(`File attachments need to be reselected after reload: ${pending.pendingFileNames.join(', ')}`)
  }

  try {
    loading.value = true
    error.value = ''
    currentPhase.value = 0
    ontologyProgress.value = { message: 'Uploading and analyzing docs...' }
    addLog('Starting ontology generation...')

    const formData = buildOntologyFormData(pending)
    const res = await generateOntology(formData)
    if (res.needs_clarification || res.data?.status === 'needs_clarification') {
      loading.value = false
      ontologyProgress.value = { message: 'Waiting for your custom simulation details...' }
      addLog('Backend requested additional detail before continuing.')
      openClarificationModal(res.data || {})
      return
    }

    if (res.success) {
      clearPendingUpload()
      currentProjectId.value = res.data.project_id
      projectData.value = res.data

      router.replace({ name: 'Process', params: { projectId: res.data.project_id } })
      ontologyProgress.value = null
      addLog(`Ontology generated successfully for project ${res.data.project_id}`)
      await startBuildGraph()
    } else {
      error.value = res.error || 'Ontology generation failed'
      addLog(`Error generating ontology: ${error.value}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception in handleNewProject: ${err.message}`)
  } finally {
    loading.value = false
  }
}

const submitClarification = async () => {
  if (!hasClarificationAnswer.value) return

  const pending = getPendingUpload()
  const contextLines = clarificationModal.value.questions
    .map((question, index) => {
      const answer = clarificationModal.value.answers[index]?.trim()
      if (!answer) return ''
      return `${question}\n${answer}`
    })
    .filter(Boolean)

  const mergedContext = [pending.additionalContext?.trim(), ...contextLines]
    .filter(Boolean)
    .join('\n\n')

  submittingClarification.value = true
  setPendingUpload(pending.files, pending.simulationRequirement, mergedContext)
  closeClarificationModal()
  addLog('Received custom simulation details from the user. Resuming ontology generation...')

  try {
    await handleNewProject()
  } finally {
    submittingClarification.value = false
  }
}

const continueWithoutClarification = async () => {
  const pending = getPendingUpload()
  const mergedContext = [pending.additionalContext?.trim(), 'Proceed with the currently supplied information only.']
    .filter(Boolean)
    .join('\n\n')

  submittingClarification.value = true
  setPendingUpload(pending.files, pending.simulationRequirement, mergedContext)
  closeClarificationModal()
  addLog('Continuing with the currently supplied prompt only.')

  try {
    await handleNewProject()
  } finally {
    submittingClarification.value = false
  }
}

const handleFrontendAuthorizeAction = async (event) => {
  const detail = event?.detail || {}

  if (detail.type === 'clarification') {
    if (!clarificationModal.value.visible) return

    clarificationModal.value.answers = clarificationModal.value.questions.map((_, index) =>
      detail.answers?.[index] || ''
    )

    if (detail.continueWithout) {
      await continueWithoutClarification()
      return
    }

    if (clarificationModal.value.answers.some(answer => (answer || '').trim())) {
      await submitClarification()
    }
    return
  }
}

const loadProject = async () => {
  try {
    loading.value = true
    addLog(`Loading project ${currentProjectId.value}...`)
    const res = await getProject(currentProjectId.value)
    if (res.success) {
      projectData.value = res.data
      updatePhaseByStatus(res.data.status)
      addLog(`Project loaded. Status: ${res.data.status}`)

      if (res.data.status === 'ontology_generated' && !res.data.graph_id) {
        await startBuildGraph()
      } else if (res.data.status === 'graph_building' && res.data.graph_build_task_id) {
        currentPhase.value = 1
        startPollingTask(res.data.graph_build_task_id)
        startGraphPolling()
      } else if (res.data.status === 'graph_completed' && res.data.graph_id) {
        currentPhase.value = 2
        await loadGraph(res.data.graph_id)
      }
    } else {
      error.value = res.error
      addLog(`Error loading project: ${res.error}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception in loadProject: ${err.message}`)
  } finally {
    loading.value = false
  }
}

const updatePhaseByStatus = (status) => {
  switch (status) {
    case 'created':
    case 'ontology_generated': currentPhase.value = 0; break;
    case 'graph_building': currentPhase.value = 1; break;
    case 'graph_completed': currentPhase.value = 2; break;
    case 'failed': error.value = 'Project failed'; break;
  }
}

const startBuildGraph = async () => {
  try {
    currentPhase.value = 1
    buildProgress.value = { progress: 0, message: 'Starting build...' }
    addLog('Initiating graph build...')

    const res = await buildGraph({ project_id: currentProjectId.value })
    if (res.success) {
      addLog(`Graph build task started. Task ID: ${res.data.task_id}`)
      startGraphPolling()
      startPollingTask(res.data.task_id)
    } else {
      error.value = res.error
      addLog(`Error starting build: ${res.error}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception in startBuildGraph: ${err.message}`)
  }
}

const startGraphPolling = () => {
  addLog('Started polling for graph data...')
  fetchGraphData()
  graphPollTimer = setInterval(fetchGraphData, 10000)
}

const fetchGraphData = async () => {
  try {
    // Refresh project info to check for graph_id
    const projRes = await getProject(currentProjectId.value)
    if (projRes.success && projRes.data.graph_id) {
      const gRes = await getGraphData(projRes.data.graph_id)
      if (gRes.success) {
        graphData.value = gRes.data
        const nodeCount = gRes.data.node_count || gRes.data.nodes?.length || 0
        const edgeCount = gRes.data.edge_count || gRes.data.edges?.length || 0
        addLog(`Graph data refreshed. Nodes: ${nodeCount}, Edges: ${edgeCount}`)
      }
    }
  } catch (err) {
    console.warn('Graph fetch error:', err)
  }
}

const startPollingTask = (taskId) => {
  pollTaskStatus(taskId)
  pollTimer = setInterval(() => pollTaskStatus(taskId), 2000)
}

const pollTaskStatus = async (taskId) => {
  try {
    const res = await getTaskStatus(taskId)
    if (res.success) {
      const task = res.data

      // Log progress message if it changed
      if (task.message && task.message !== buildProgress.value?.message) {
        addLog(task.message)
      }

      buildProgress.value = { progress: task.progress || 0, message: task.message }

      if (task.status === 'completed') {
        addLog('Graph build task completed.')
        stopPolling()
        stopGraphPolling() // Stop polling, do final load
        currentPhase.value = 2

        // Final load
        const projRes = await getProject(currentProjectId.value)
        if (projRes.success && projRes.data.graph_id) {
            projectData.value = projRes.data
            await loadGraph(projRes.data.graph_id)
        }
      } else if (task.status === 'failed') {
        stopPolling()
        error.value = task.error
        addLog(`Graph build task failed: ${task.error}`)
      }
    }
  } catch (e) {
    console.error(e)
  }
}

const loadGraph = async (graphId) => {
  graphLoading.value = true
  addLog(`Loading full graph data: ${graphId}`)
  try {
    const res = await getGraphData(graphId)
    if (res.success) {
      graphData.value = res.data
      addLog('Graph data loaded successfully.')
    } else {
      addLog(`Failed to load graph data: ${res.error}`)
    }
  } catch (e) {
    addLog(`Exception loading graph: ${e.message}`)
  } finally {
    graphLoading.value = false
  }
}

const refreshGraph = () => {
  if (projectData.value?.graph_id) {
    addLog('Manual graph refresh triggered.')
    loadGraph(projectData.value.graph_id)
  }
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const stopGraphPolling = () => {
  if (graphPollTimer) {
    clearInterval(graphPollTimer)
    graphPollTimer = null
    addLog('Graph polling stopped.')
  }
}

onMounted(() => {
  window.addEventListener('frontend-authorize-action', handleFrontendAuthorizeAction)
  initProject()
})

onUnmounted(() => {
  window.removeEventListener('frontend-authorize-action', handleFrontendAuthorizeAction)
  stopPolling()
  stopGraphPolling()
})
</script>

<style scoped>
.main-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  overflow: hidden;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* Header */
.app-header {
  height: 60px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: var(--bg-primary);
  z-index: 100;
  position: relative;
}

.header-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 18px;
  letter-spacing: 1px;
  cursor: pointer;
}

.view-switcher {
  display: flex;
  background: rgba(255, 255, 255, 0.05);
  padding: 4px;
  border-radius: 6px;
  gap: 4px;
}

.switch-btn {
  border: none;
  background: transparent;
  padding: 6px 16px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.switch-btn.active {
  background: var(--bg-primary);
  color: var(--text-main);
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.workflow-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: var(--text-muted);
}

.step-name {
  font-weight: 700;
  color: var(--text-main);
}

.step-divider {
  width: 1px;
  height: 14px;
  background-color: var(--border-color);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(255,255,255,0.2);
}

.status-indicator.processing .dot { background: #FF5722; animation: pulse 1s infinite; }
.status-indicator.completed .dot { background: #4CAF50; }
.status-indicator.error .dot { background: #F44336; }

@keyframes pulse { 50% { opacity: 0.5; } }

/* Content */
.content-area {
  flex: 1;
  display: flex;
  position: relative;
  overflow: hidden;
}

.panel-wrapper {
  height: 100%;
  overflow: hidden;
  transition: width 0.4s cubic-bezier(0.25, 0.8, 0.25, 1), opacity 0.3s ease, transform 0.3s ease;
  will-change: width, opacity, transform;
}

.panel-wrapper.left {
  border-right: 1px solid var(--border-color);
}

.clarification-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(5, 5, 5, 0.72);
  backdrop-filter: blur(12px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 400;
}

.clarification-modal {
  width: min(720px, 100%);
  background: #0d0d0d;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.45);
  overflow: hidden;
}

.clarification-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 24px 24px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.clarification-kicker {
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #e8f5a2;
  margin-bottom: 8px;
}

.clarification-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-main);
}

.clarification-close {
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 28px;
  line-height: 1;
  cursor: pointer;
}

.clarification-body {
  padding: 20px 24px 0;
}

.clarification-copy {
  margin: 0 0 16px;
  color: var(--text-muted);
  line-height: 1.6;
}

.clarification-hints {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 18px;
}

.hint-chip {
  padding: 8px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: var(--text-muted);
  font-size: 12px;
}

.clarification-question {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
}

.clarification-label {
  color: var(--text-main);
  font-size: 13px;
  font-weight: 600;
}

.clarification-input {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-main);
  border-radius: 12px;
  padding: 14px 16px;
  resize: vertical;
  min-height: 92px;
  font: inherit;
}

.clarification-input:focus {
  outline: none;
  border-color: rgba(232, 245, 162, 0.45);
  box-shadow: 0 0 0 3px rgba(232, 245, 162, 0.08);
}

.clarification-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 24px 24px;
}

.modal-btn {
  min-width: 150px;
  padding: 12px 16px;
  border-radius: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.modal-btn.secondary {
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--text-muted);
}

.modal-btn.primary {
  background: #e8f5a2;
  border: 1px solid #e8f5a2;
  color: #111;
}

.modal-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
</style>
