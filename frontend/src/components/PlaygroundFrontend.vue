<template>
  <div class="playground-frontend">
    <!-- Chat History / Output Area -->
    <div class="chat-container">
      <div v-for="(msg, index) in chatHistory" :key="index" class="chat-message" :class="msg.role">
        <div class="avatar">{{ msg.role === 'user' ? 'U' : 'AI' }}</div>
        <div class="message-content">
          <p v-if="msg.text">{{ msg.text }}</p>

          <!-- System Monitor / To-Do List injected if it's the active system running state -->
          <div v-if="msg.type === 'system-monitor'" class="system-monitor" v-reveal>
            <div class="monitor-header clickable" @click="monitorCollapsed = !monitorCollapsed">
              <span class="monitor-title">Universal Swarm Engine</span>
              <div class="monitor-header-right">
                <span class="monitor-status" :class="{ 'done': systemState.answerReady || systemState.step >= 4 }">
                  {{ systemState.answerReady ? 'Answer Ready' : systemState.step >= 4 ? 'Analysis Complete' : 'Calculating...' }}
                </span>
                <span class="monitor-toggle">{{ monitorCollapsed ? '+' : '−' }}</span>
              </div>
            </div>
            <div v-if="monitorCollapsed" class="monitor-collapsed">
              <span>{{ completedCount }}/5 steps completed</span>
              <span class="collapsed-hint">Tap to view details</span>
            </div>
            <ul v-else class="monitor-steps">
              <li :class="{ 'done': systemState.phase > 0 }">
                <span class="check">{{ systemState.phase > 0 ? '✓' : '⟳' }}</span>
                Extracting Reality Seeds (Ontology)
              </li>
              <li :class="{ 'done': systemState.phase >= 2 }">
                <span class="check">{{ systemState.phase >= 2 ? '✓' : '⟳' }}</span>
                Building Memory Graph
              </li>
              <li :class="{ 'done': systemState.step >= 2 }">
                <span class="check">{{ systemState.step >= 2 ? '✓' : '⟳' }}</span>
                Initializing Agent Personas
              </li>
              <li :class="{ 'done': systemState.step >= 3 }">
                <span class="check">{{ systemState.step >= 3 ? '✓' : '⟳' }}</span>
                Executing Dual Simulation Rounds
              </li>
              <li :class="{ 'done': systemState.step >= 4 }">
                <span class="check">{{ systemState.step >= 4 ? '✓' : '⟳' }}</span>
                Compiling Advanced Evaluation
              </li>
            </ul>
          </div>

          <div v-if="msg.type === 'final-answer'" class="assistant-answer" v-reveal>
            <div class="assistant-answer-header">
              <span class="assistant-chip">Univerra</span>
              <span class="assistant-title">{{ msg.title || 'Final Answer' }}</span>
            </div>
            <div class="assistant-answer-body" v-html="msg.html || fallbackHtml(msg.content)"></div>
          </div>

          <!-- Final Summarized Generation block -->
          <div v-if="msg.type === 'summary'" class="summary-module" v-reveal>
            <div class="summary-aesthetic">
              <div class="summary-stat">
                <span class="stat-label">AGENTS</span>
                <span class="stat-value">{{ systemState.projectData?.total_agents || '10,000' }}</span>
              </div>
              <div class="summary-stat">
                <span class="stat-label">HOURS SIMULATED</span>
                <span class="stat-value">720</span>
              </div>
              <div class="summary-stat">
                <span class="stat-label">ROUNDS</span>
                <span class="stat-value">3</span>
              </div>
            </div>
            <div class="summary-text">{{ msg.reportText || "The simulation has firmly predicted short-term destabilization followed by median adoption. Full interaction reports are securely mapped." }}</div>
          </div>
        </div>
      </div>

      <!-- Input requirement aesthetic popup -->
      <div v-if="actionState" class="action-popup" v-reveal>
        <div class="action-kicker">Backend Action Required</div>
        <h4>{{ actionState.title || 'System Action Required' }}</h4>
        <p>{{ actionState.message || 'The backend paused. Would you like to continue?' }}</p>

        <div
          v-if="actionState.type === 'start-dual' && actionState.allowCustomRounds"
          class="action-rounds"
        >
          <div class="action-rounds-header">
            <span>Use Custom Rounds</span>
            <label class="popup-switch">
              <input type="checkbox" v-model="useCustomRounds" />
              <span class="popup-switch-track"></span>
            </label>
          </div>

          <div class="round-values">
            <span class="round-pill">Auto {{ actionState.autoRounds || '-' }} rounds</span>
            <span v-if="useCustomRounds" class="round-pill active">{{ popupRounds }} rounds</span>
          </div>

          <div v-if="useCustomRounds" class="round-numeric-row">
            <label>Rounds</label>
            <input
              v-model.number="popupRounds"
              class="round-number-input"
              type="number"
              min="10"
              :max="actionState.autoRounds || 72"
              step="1"
            />
          </div>

          <p v-if="useCustomRounds" class="round-helper">
            Recommended preview: {{ actionState.recommendedRounds || 40 }} rounds
          </p>
        </div>

        <div
          v-if="actionState.type === 'clarification' && actionState.questions?.length"
          class="action-clarification"
        >
          <div
            v-for="(question, index) in actionState.questions"
            :key="`${index}-${question}`"
            class="clarification-field"
          >
            <label>{{ question }}</label>
            <textarea
              v-model="clarificationAnswers[index]"
              rows="3"
              :placeholder="clarificationPlaceholders[index] || 'Add the missing detail here...'"
            ></textarea>
          </div>
        </div>

        <div class="action-buttons">
          <button class="ghost-btn" @click="dismissAction">
            {{ actionState.type === 'clarification' ? 'Continue With Current Input' : 'Not Now' }}
          </button>
          <button @click="submitAction">
            {{ actionState.actionLabel || 'Authorize Simulation' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Fixed Prompt Bar -->
    <div class="prompt-bar-wrapper">
      <div class="prompt-bar">
        <button class="attach-btn">+</button>
        <textarea
          v-model="promptInput"
          placeholder="Send a proposal, text, or query to begin..."
          rows="1"
          @keydown.enter.prevent="submitPrompt"
        ></textarea>
        <button class="send-btn" @click="submitPrompt" :disabled="!promptInput.trim()">↑</button>
      </div>
      <div class="prompt-footer">Univerra generates probability fields. Verify outputs in backend.</div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  chatHistory: {
    type: Array,
    default: () => []
  },
  systemState: {
    type: Object,
    default: () => ({ step: 1, phase: -1, projectData: null })
  },
  actionRequired: {
    type: [Boolean, Object],
    default: false
  }
})

const emit = defineEmits(['submit-prompt', 'submit-action'])

const promptInput = ref('')
const useCustomRounds = ref(false)
const popupRounds = ref(40)
const clarificationAnswers = ref([])
const monitorCollapsed = ref(false)
const clarificationPlaceholders = [
  'Example: I am choosing between studying tonight and going to a 4-hour party.',
  'Example: The deadline is April 21, 2026 at 9:00 AM.',
  'Example: I want the most realistic short-term outcome and risk tradeoff.'
]

const actionState = computed(() => {
  if (!props.actionRequired) return null
  if (props.actionRequired === true) {
    return {
      type: 'start-dual',
      title: 'System Action Required',
      message: 'The backend paused. Would you like to launch the customized Dual Simulation protocol?',
      actionLabel: 'Authorize Simulation'
    }
  }
  return props.actionRequired
})

const completedCount = computed(() => {
  let count = 0
  if (props.systemState.phase > 0) count++
  if (props.systemState.phase >= 2) count++
  if (props.systemState.step >= 2) count++
  if (props.systemState.step >= 3) count++
  if (props.systemState.step >= 4) count++
  return count
})

watch(actionState, (nextValue) => {
  if (!nextValue) return
  useCustomRounds.value = false
  popupRounds.value = nextValue.recommendedRounds || Math.min(nextValue.autoRounds || 40, 40)
  clarificationAnswers.value = Array.isArray(nextValue.questions) ? nextValue.questions.map(() => '') : []
}, { immediate: true })

watch(() => props.systemState.answerReady, (ready) => {
  if (ready) {
    monitorCollapsed.value = true
  }
}, { immediate: true })

const fallbackHtml = (content = '') => {
  const escaped = String(content)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return escaped.replace(/\n/g, '<br>')
}

const submitPrompt = () => {
  if (!promptInput.value.trim()) return
  emit('submit-prompt', promptInput.value)
  promptInput.value = ''
}

const dismissAction = () => {
  emit('submit-action', {
    type: actionState.value?.type || 'dismiss-action',
    continueWithout: actionState.value?.type === 'clarification',
    dismissed: actionState.value?.type !== 'clarification'
  })
}

const submitAction = () => {
  if (!actionState.value) return
  emit('submit-action', {
    type: actionState.value.type || 'start-dual',
    useCustomRounds: useCustomRounds.value,
    maxRounds: useCustomRounds.value ? popupRounds.value : undefined,
    answers: clarificationAnswers.value
  })
}
</script>

<style scoped>
.playground-frontend {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background-color: #0d0d0d;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 80px 20% 120px 20%; /* Space for top header and bottom prompt */
  display: flex;
  flex-direction: column;
  gap: 30px;
}

@media (max-width: 1024px) {
  .chat-container { padding: 80px 5% 120px 5%; }
}

.chat-message {
  display: flex;
  gap: 20px;
  max-width: 800px;
  width: 100%;
  margin: 0 auto;
}

.chat-message.user .avatar {
  background: #E8F5A2;
  color: #000;
}

.chat-message.system .avatar {
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #fff;
}

.avatar {
  width: 30px;
  height: 30px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono), monospace;
  font-size: 12px;
  flex-shrink: 0;
}

.message-content {
  flex: 1;
  color: #E2E2E2;
  font-size: 16px;
  line-height: 1.6;
}

/* System Monitor */
.system-monitor {
  margin-top: 10px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 20px;
  font-family: var(--font-mono), monospace;
}

.monitor-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;
  border-bottom: 1px dashed rgba(255, 255, 255, 0.1);
  padding-bottom: 10px;
}

.monitor-header.clickable {
  cursor: pointer;
}

.monitor-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.monitor-title { color: #fff; font-size: 12px; }
.monitor-status { color: #888; font-size: 12px; }
.monitor-status.done { color: #E8F5A2; }
.monitor-toggle {
  color: rgba(255, 255, 255, 0.6);
  font-size: 16px;
  line-height: 1;
}

.monitor-collapsed {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.68);
}

.collapsed-hint {
  color: rgba(232, 245, 162, 0.76);
}

.monitor-steps {
  list-style: none;
  padding: 0; margin: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.monitor-steps li {
  font-size: 12px;
  color: #666;
  display: flex;
  align-items: center;
  gap: 10px;
  transition: color 0.3s;
}

.monitor-steps li.done {
  color: #4CAF50; /* Green aesthetic requested by user */
  text-decoration: line-through; /* Single line cut through */
}

.assistant-answer {
  margin-top: 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 22px;
}

.assistant-answer-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.assistant-chip {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(232, 245, 162, 0.12);
  color: #E8F5A2;
  font-size: 11px;
  font-family: var(--font-mono), monospace;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.assistant-title {
  color: #fff;
  font-size: 18px;
  font-weight: 600;
}

.assistant-answer-body {
  color: #e2e2e2;
  line-height: 1.75;
}

.assistant-answer-body :deep(h1),
.assistant-answer-body :deep(h2),
.assistant-answer-body :deep(h3) {
  color: #fff;
  margin: 1.2em 0 0.6em;
  font-size: 1.05em;
}

.assistant-answer-body :deep(p) {
  margin: 0 0 1em;
}

.assistant-answer-body :deep(ul) {
  padding-left: 1.2em;
  margin: 0 0 1em;
}

.assistant-answer-body :deep(li) {
  margin: 0.35em 0;
}

.assistant-answer-body :deep(code) {
  font-family: var(--font-mono), monospace;
  background: rgba(255,255,255,0.06);
  padding: 0.1em 0.35em;
  border-radius: 6px;
}

/* Summary Aesthetic Module */
.summary-module {
  margin-top: 20px;
  padding: 0;
}

.summary-aesthetic {
  display: flex;
  gap: 20px;
  background: rgba(232, 245, 162, 0.05);
  border: 1px solid rgba(232, 245, 162, 0.2);
  padding: 20px;
  border-radius: 12px;
  margin-bottom: 16px;
}

.summary-stat {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.stat-label {
  font-family: var(--font-mono), monospace;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.4);
  letter-spacing: 0.1em;
  margin-bottom: 4px;
}

.stat-value {
  font-family: 'Times New Roman', Times, serif; /* Different font requested by user */
  font-size: 24px;
  color: #fff;
}

.summary-text {
  font-family: 'Times New Roman', Times, serif;
  font-size: 17px;
  color: #ccc;
  line-height: 1.6;
}

/* Auth popup */
.action-popup {
  background: rgba(20, 20, 20, 0.9);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(232, 245, 162, 0.28);
  padding: 30px;
  border-radius: 16px;
  color: #fff;
  max-width: 500px;
  margin: 20px auto;
  text-align: left;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}

.action-kicker {
  font-family: var(--font-mono), monospace;
  font-size: 11px;
  color: #E8F5A2;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-bottom: 10px;
}

.action-popup h4 {
  margin-top: 0;
  margin-bottom: 10px;
  font-size: 22px;
}

.action-popup p {
  color: rgba(255, 255, 255, 0.72);
  line-height: 1.6;
}

.action-rounds {
  margin-top: 18px;
  padding: 16px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  background: rgba(255, 255, 255, 0.03);
}

.action-rounds-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  font-family: var(--font-mono), monospace;
  font-size: 12px;
}

.round-values {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.round-pill {
  border-radius: 999px;
  padding: 7px 12px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.68);
  background: rgba(255, 255, 255, 0.04);
}

.round-pill.active {
  color: #111;
  background: #E8F5A2;
}

.round-numeric-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.round-numeric-row label {
  font-family: var(--font-mono), monospace;
  font-size: 12px;
  color: rgba(255,255,255,0.72);
}

.round-number-input {
  width: 120px;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.04);
  color: #fff;
  padding: 10px 12px;
  font: inherit;
  text-align: right;
}

.round-number-input:focus {
  outline: none;
  border-color: rgba(232, 245, 162, 0.35);
  box-shadow: 0 0 0 3px rgba(232, 245, 162, 0.08);
}

.round-helper {
  margin-top: 10px;
  margin-bottom: 0;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.55);
}

.action-clarification {
  margin-top: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.clarification-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.clarification-field label {
  font-family: var(--font-mono), monospace;
  font-size: 12px;
  color: #f5f5f5;
}

.clarification-field textarea {
  width: 100%;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: #f5f5f5;
  padding: 12px 14px;
  resize: vertical;
  min-height: 90px;
  font: inherit;
}

.clarification-field textarea:focus {
  outline: none;
  border-color: rgba(232, 245, 162, 0.35);
  box-shadow: 0 0 0 3px rgba(232, 245, 162, 0.08);
}

.popup-switch {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.popup-switch input {
  display: none;
}

.popup-switch-track {
  width: 44px;
  height: 26px;
  background: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  position: relative;
  transition: background 0.2s ease;
}

.popup-switch-track::after {
  content: '';
  position: absolute;
  top: 3px;
  left: 3px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s ease;
}

.popup-switch input:checked + .popup-switch-track {
  background: rgba(232, 245, 162, 0.35);
}

.popup-switch input:checked + .popup-switch-track::after {
  transform: translateX(18px);
  background: #E8F5A2;
}

.action-buttons button {
  margin-top: 20px;
  background: #E8F5A2;
  color: #000;
  border: none;
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: bold;
  cursor: pointer;
}

.action-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.ghost-btn {
  background: transparent !important;
  color: rgba(255, 255, 255, 0.74) !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
}

/* Prompt Bar */
.prompt-bar-wrapper {
  position: fixed;
  bottom: 0; left: 0; right: 0;
  background: linear-gradient(to top, #0d0d0d 60%, transparent);
  padding: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.prompt-bar {
  max-width: 800px;
  width: 100%;
  display: flex;
  align-items: flex-end;
  background: #252525;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 24px;
  padding: 10px 16px;
  gap: 12px;
}

.prompt-bar:focus-within {
  border-color: rgba(255,255,255,0.3);
}

.attach-btn {
  background: transparent;
  border: none;
  color: #888;
  font-size: 24px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}

.prompt-bar textarea {
  flex: 1;
  background: transparent;
  border: none;
  color: #fff;
  font-family: var(--font-sans);
  font-size: 16px;
  resize: none;
  outline: none;
  padding: 8px 0;
  max-height: 200px;
}

.send-btn {
  background: #E8F5A2;
  color: #000;
  border: none;
  width: 32px; height: 32px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-weight: bold;
  cursor: pointer;
  transition: opacity 0.2s;
}

.send-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.prompt-footer {
  font-size: 11px;
  color: #555;
  margin-top: 12px;
}
</style>
