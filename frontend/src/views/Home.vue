<template>
  <div class="home-container" v-reveal>
    <!-- Background ambiance -->
    <div class="ambient-glow orb-left"></div>
    <div class="ambient-glow orb-right"></div>
    <div class="mesh-grid"></div>

    <!-- Top navigation bar -->
    <nav class="navbar" v-reveal>
      <div class="nav-brand">
        <span class="brand-sub">UNIVERRA</span>
        <span class="brand-version">v0.1-preview</span>
      </div>
      <div class="nav-links">
        <router-link to="/profile" class="github-link">Profile</router-link>
        <button class="nav-button" @click="handleLogout">Sign out</button>
      </div>
    </nav>

    <div class="main-content">
      <!-- Centered Cinematic Hero -->
      <section class="hero-section center-layout delay-100" v-reveal>
        <div class="tag-row centered">
          <span class="orange-tag">Advanced Universal Swarm Engine</span>
        </div>

        <h1 class="main-title cinematic-title">
          Initiate Simulation<br />
          <span class="gradient-text pulse-glow">Forecast Reality.</span>
        </h1>

        <p class="hero-desc centered">
          Deploy a <span class="highlight-bold">million-agent parallel world</span> generated instantly from your report. Inject diverse variables and observe dynamic complex group interactions. Find the optimal solution before acting in the real world.
        </p>
      </section>

      <!-- Floating Glass Console -->
      <section class="console-section center-layout delay-200" v-reveal>
        <div class="glass-console">

          <div class="console-grid">
            <!-- Left: Reality Seeds -->
            <div class="console-column">
              <div class="console-header">
                <span class="step-badge">1</span>
                <span class="console-label">Inject Reality Seeds (PDF, MD, TXT)</span>
              </div>
              <div
                class="upload-zone"
                :class="{ 'drag-over': isDragOver, 'has-files': files.length > 0 }"
                @dragover.prevent="handleDragOver"
                @dragleave.prevent="handleDragLeave"
                @drop.prevent="handleDrop"
                @click="triggerFileInput"
              >
                <input
                  ref="fileInput"
                  type="file"
                  multiple
                  accept=".pdf,.md,.txt"
                  @change="handleFileSelect"
                  style="display: none"
                  :disabled="loading"
                />
                <div v-if="files.length === 0" class="upload-placeholder">
                  <div class="upload-icon">↑</div>
                  <div class="upload-title">Drop files or click</div>
                </div>
                <div v-else class="file-list">
                  <div v-for="(file, index) in files" :key="index" class="file-item">
                    <span class="file-icon">📄</span>
                    <span class="file-name">{{ file.name }}</span>
                    <button @click.stop="removeFile(index)" class="remove-btn">×</button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Right: Simulation Prompt -->
            <div class="console-column">
              <div class="console-header">
                <span class="step-badge">2</span>
                <span class="console-label">Configure Parameters</span>
              </div>
              <div class="input-wrapper">
                <textarea
                  v-model="formData.simulationRequirement"
                  class="code-input"
                  placeholder="e.g., What would happen to public opinion if a controversial disciplinary decision is reversed?"
                  rows="5"
                  :disabled="loading"
                ></textarea>
                <div class="model-badge">Univerra-V1.0</div>
              </div>
            </div>
          </div>

          <div class="console-action">
            <button
              class="start-engine-btn action-glow"
              @click="startSimulation"
              :disabled="!canSubmit || loading"
            >
              <div class="btn-content">
                <span class="btn-text" v-if="!loading">Initialize Sequence</span>
                <span class="btn-text" v-else>Initializing Engine...</span>
              </div>
              <span class="btn-arrow">→</span >
            </button>
          </div>
        </div>
      </section>

      <!-- Flow Metrics & Steps (Horizontal) -->
      <section class="workflow-dashboard delay-300" v-reveal>
        <div class="status-ribbon">
          <span class="status-dot"></span>
          <span class="status-text">Prediction Engine Standing By  —  $5 Avg Cost  —  Uncapped Concurrency</span>
        </div>

        <div class="steps-grid">
          <div class="step-card">
            <div class="step-num">01</div>
            <div>
               <h4>Build Graph</h4>
               <p>Reality seed extraction.</p>
            </div>
          </div>
          <div class="step-card">
            <div class="step-num">02</div>
            <div>
               <h4>Set Limits</h4>
               <p>Agent parameter logic.</p>
            </div>
          </div>
          <div class="step-card">
            <div class="step-num">03</div>
            <div>
               <h4>Simulate</h4>
               <p>Dual-platform engine.</p>
            </div>
          </div>
          <div class="step-card">
            <div class="step-num">04</div>
            <div>
               <h4>Evaluate</h4>
               <p>Deep Rich toolset generation.</p>
            </div>
          </div>
        </div>
      </section>

      <!-- History project database -->
      <section class="history-section delay-400" v-reveal>
        <HistoryDatabase />
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import HistoryDatabase from '../components/HistoryDatabase.vue'
import { logout } from '../store/auth'

const router = useRouter()

// Form data
const formData = ref({
  simulationRequirement: ''
})

// File list
const files = ref([])

// State
const loading = ref(false)
const error = ref('')
const isDragOver = ref(false)

// File input ref
const fileInput = ref(null)

// Computed: can submit
const canSubmit = computed(() => {
  return formData.value.simulationRequirement.trim() !== ''
})

// Trigger file selection
const triggerFileInput = () => {
  if (!loading.value) {
    fileInput.value?.click()
  }
}

// Handle file selection
const handleFileSelect = (event) => {
  const selectedFiles = Array.from(event.target.files)
  addFiles(selectedFiles)
}

// Handle drag events
const handleDragOver = (e) => {
  if (!loading.value) {
    isDragOver.value = true
  }
}

const handleDragLeave = (e) => {
  isDragOver.value = false
}

const handleDrop = (e) => {
  isDragOver.value = false
  if (loading.value) return

  const droppedFiles = Array.from(e.dataTransfer.files)
  addFiles(droppedFiles)
}

// Add files
const addFiles = (newFiles) => {
  const validFiles = newFiles.filter(file => {
    const ext = file.name.split('.').pop().toLowerCase()
    return ['pdf', 'md', 'txt'].includes(ext)
  })
  files.value.push(...validFiles)
}

// Remove file
const removeFile = (index) => {
  files.value.splice(index, 1)
}

// Scroll to bottom
const scrollToBottom = () => {
  window.scrollTo({
    top: document.body.scrollHeight,
    behavior: 'smooth'
  })
}

// Start simulation - navigate immediately, API calls happen on Process page
const startSimulation = () => {
  if (!canSubmit.value || loading.value) return

  // Store pending upload data
  import('../store/pendingUpload.js').then(({ setPendingUpload }) => {
    setPendingUpload(files.value, formData.value.simulationRequirement)

    // Navigate to Process page immediately (using special identifier for new project)
    router.push({
      name: 'Process',
      params: { projectId: 'new' }
    })
  })
}

const handleLogout = async () => {
  await logout()
  router.push({ name: 'Login' })
}
</script>

<style scoped>
/* Scoped Variables using Global dark configuration */
:root {
  --black: var(--bg-primary);
  --white: var(--text-main);
  --orange: var(--accent-primary);
  --border: var(--border-color);
}

.home-container {
  min-height: 100vh;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Base Aesthetics */
.ambient-glow {
  position: absolute;
  width: 60vw;
  height: 60vw;
  border-radius: 50%;
  filter: blur(100px);
  z-index: 0;
  opacity: 0.15;
  pointer-events: none;
}
.orb-left {
  top: -20vh;
  left: -20vw;
  background: radial-gradient(circle, var(--accent-primary), transparent 60%);
}
.orb-right {
  bottom: -20vh;
  right: -20vw;
  background: radial-gradient(circle, rgba(255,255,255,1), transparent 60%);
}
.mesh-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
  background-size: 50px 50px;
  z-index: 0;
  pointer-events: none;
}

/* Navbar */
.navbar {
  height: 70px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 5vw;
  position: fixed;
  top: 0; left: 0; right: 0;
  background: rgba(5, 5, 5, 0.5);
  backdrop-filter: blur(20px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  z-index: 100;
}
.nav-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.brand-sub {
  font-family: var(--font-mono);
  font-weight: 800;
  letter-spacing: 2px;
  font-size: 1.2rem;
  color: var(--text-main);
}
.brand-version {
  font-size: 0.75rem;
  color: var(--text-muted);
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 2px 8px;
  border-radius: 12px;
  font-family: var(--font-mono);
}
.github-link {
  color: var(--text-muted);
  text-decoration: none;
  font-size: 0.9rem;
  font-weight: 500;
  transition: color 0.3s ease;
}
.github-link:hover {
  color: var(--text-main);
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 16px;
}

.nav-button {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-muted);
  padding: 8px 12px;
  cursor: pointer;
}

.nav-button:hover {
  color: var(--text-main);
  border-color: rgba(255, 255, 255, 0.24);
}

/* Main Flow */
.main-content {
  position: relative;
  z-index: 10;
  padding-top: 15vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6vh;
  width: 100%;
}

/* Hero Section */
.hero-section {
  text-align: center;
  max-width: 900px;
  padding: 0 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}
.orange-tag {
  background: rgba(255, 69, 0, 0.1);
  color: var(--accent-primary);
  border: 1px solid rgba(255, 69, 0, 0.3);
  padding: 8px 16px;
  border-radius: 20px;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 1px;
}
.main-title {
  font-size: clamp(3rem, 6vw, 5.5rem);
  line-height: 1.1;
  font-weight: 600;
  letter-spacing: -2px;
}
.gradient-text {
  background: var(--gradient-text);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.pulse-glow {
  text-shadow: 0 0 40px rgba(255, 255, 255, 0.2);
}
.hero-desc {
  font-size: 1.15rem;
  line-height: 1.7;
  color: var(--text-muted);
  max-width: 750px;
}
.highlight-bold {
  color: var(--text-main);
  font-weight: 600;
}
.highlight-orange {
  color: var(--accent-primary);
}

/* Floating Glass Console */
.console-section {
  width: 100%;
  max-width: 1100px;
  padding: 0 20px;
}
.glass-console {
  background: rgba(25, 25, 25, 0.4);
  backdrop-filter: blur(30px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 24px;
  padding: 30px;
  box-shadow: 0 30px 60px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.05) inset;
  display: flex;
  flex-direction: column;
  gap: 30px;
}
.console-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 30px;
}
@media (max-width: 800px) {
  .console-grid {
    grid-template-columns: 1fr;
  }
}
.console-column {
  display: flex;
  flex-direction: column;
  gap: 15px;
}
.console-header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.step-badge {
  background: rgba(255, 255, 255, 0.1);
  width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: bold;
}
.console-label {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: var(--text-muted);
}

/* Inputs & Uploads */
.upload-zone {
  flex: 1;
  border: 1px dashed rgba(255, 255, 255, 0.2);
  border-radius: 16px;
  background: rgba(0, 0, 0, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
  cursor: pointer;
  min-height: 160px;
}
.upload-zone:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.4);
}
.upload-icon {
  width: 48px; height: 48px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  margin: 0 auto 10px;
  color: var(--text-muted);
  font-size: 1.2rem;
}
.upload-placeholder {
  text-align: center;
}
.upload-title {
  font-weight: 500;
  font-size: 0.9rem;
  color: var(--text-main);
}
.file-list {
  width: 100%;
  padding: 15px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.file-item {
  display: flex;
  align-items: center;
  background: rgba(255, 255, 255, 0.05);
  padding: 10px 15px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  font-family: var(--font-mono);
  font-size: 0.8rem;
}
.file-name {
  flex: 1; margin: 0 10px;
}
.remove-btn {
  background: none; border: none; cursor: pointer; color: var(--text-muted); font-size: 1.2rem;
}

.input-wrapper {
  position: relative;
  flex: 1;
  display: flex;
}
.code-input {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.02);
  border-radius: 16px;
  padding: 20px;
  color: var(--text-main);
  font-family: var(--font-sans);
  font-size: 0.95rem;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  transition: border-color 0.3s;
}
.code-input:focus {
  border-color: var(--accent-primary);
  background: rgba(255, 255, 255, 0.05);
}
.model-badge {
  position: absolute;
  bottom: 15px; right: 15px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: rgba(255,255,255,0.3);
}

.console-action {
  display: flex;
  justify-content: flex-end;
}
.start-engine-btn {
  width: 100%;
  background: var(--text-main);
  color: var(--bg-primary);
  border: none;
  padding: 20px;
  border-radius: 14px;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 1.1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}
.start-engine-btn:not(:disabled):hover {
  background: var(--accent-primary);
  color: var(--text-main);
  transform: translateY(-2px);
  box-shadow: 0 8px 25px var(--accent-glow);
}
.start-engine-btn:disabled {
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.2);
  cursor: not-allowed;
}

/* Steps Dashboard */
.workflow-dashboard {
  width: 100%;
  max-width: 1100px;
  padding: 0 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.status-ribbon {
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 15px 25px;
}
.status-dot {
  width: 8px; height: 8px;
  background: #1A936F;
  border-radius: 50%;
  box-shadow: 0 0 10px #1A936F;
}
.status-text {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: var(--text-muted);
}
.steps-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 15px;
}
.step-card {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 16px;
  padding: 20px;
  display: flex;
  gap: 15px;
  transition: background 0.3s;
}
.step-card:hover {
  background: rgba(255, 255, 255, 0.05);
}
.step-num {
  font-family: var(--font-mono);
  font-size: 1.2rem;
  color: rgba(255,255,255,0.1);
  font-weight: bold;
}
.step-card h4 {
  font-size: 0.95rem;
  margin-bottom: 5px;
  color: var(--text-main);
}
.step-card p {
  font-size: 0.8rem;
  color: var(--text-muted);
  line-height: 1.4;
}

.history-section {
  width: 100%;
}
</style>
