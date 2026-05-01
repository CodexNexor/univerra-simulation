<template>
  <main class="profile-page">
    <header class="topbar">
      <router-link to="/app" class="brand">UNIVERRA</router-link>
      <div class="top-actions">
        <router-link to="/app" class="text-link">New simulation</router-link>
        <button class="ghost-btn" @click="signOut">Sign out</button>
      </div>
    </header>

    <section class="profile-hero">
      <div>
        <p class="eyebrow">Account memory</p>
        <h1>{{ authState.user?.name || 'Your profile' }}</h1>
        <p class="hero-copy">
          This goal profile is quietly added to relevant simulations so reports can produce a more personal roadmap.
        </p>
      </div>
      <div class="metric-strip">
        <div>
          <span class="metric-value">{{ simulations.length }}</span>
          <span class="metric-label">Simulations</span>
        </div>
        <div>
          <span class="metric-value">{{ completedCount }}</span>
          <span class="metric-label">Ready reports</span>
        </div>
      </div>
    </section>

    <section class="content-grid">
      <form class="profile-panel" @submit.prevent="saveProfile">
        <div class="panel-title">
          <span>Goal profile</span>
          <span v-if="saved" class="saved-badge">Saved</span>
        </div>

        <label>
          <span>Name</span>
          <input v-model.trim="form.name" />
        </label>

        <div class="two-col">
          <label>
            <span>Goal type</span>
            <select v-model="form.goal_category">
              <option value="career">Career</option>
              <option value="exam">Exam preparation</option>
              <option value="business">Business</option>
              <option value="research">Research</option>
              <option value="personal">Personal growth</option>
            </select>
          </label>

          <label>
            <span>Target timeline</span>
            <input v-model.trim="form.target_timeline" placeholder="12 months, 2027, 5 years" />
          </label>
        </div>

        <label>
          <span>Main goal</span>
          <textarea v-model.trim="form.goal" rows="3"></textarea>
        </label>

        <label>
          <span>Personal details</span>
          <textarea v-model.trim="form.personal_details" rows="4"></textarea>
        </label>

        <div class="two-col">
          <label>
            <span>Current level</span>
            <input v-model.trim="form.experience_level" />
          </label>
          <label>
            <span>Constraints</span>
            <input v-model.trim="form.constraints" />
          </label>
        </div>

        <p v-if="error" class="error-text">{{ error }}</p>

        <button class="primary-btn" type="submit" :disabled="saving">
          {{ saving ? 'Saving...' : 'Save goal profile' }}
        </button>
      </form>

      <section class="history-panel">
        <div class="panel-title">
          <span>Previous simulations</span>
          <button class="refresh-btn" @click="loadSimulations" :disabled="loadingHistory">Refresh</button>
        </div>

        <div v-if="loadingHistory" class="empty-state">Loading simulations...</div>
        <div v-else-if="simulations.length === 0" class="empty-state">
          No saved simulations yet.
        </div>

        <div v-else class="history-list">
          <article
            v-for="item in simulations"
            :key="item.simulation_id"
            class="history-row"
            @click="openSimulation(item)"
          >
            <div>
              <div class="row-title">{{ simulationTitle(item) }}</div>
              <div class="row-meta">
                {{ formatDate(item.created_at) }} · {{ item.status }} · {{ item.profiles_count || 0 }} agents
              </div>
            </div>
            <div class="row-actions">
              <button v-if="item.report_id" @click.stop="openReport(item)">Report</button>
              <button @click.stop="openSimulation(item)">Open</button>
            </div>
          </article>
        </div>
      </section>
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getMySimulations, updateProfile } from '../api/auth'
import { authState, initAuth, logout, setAuthSession } from '../store/auth'

const router = useRouter()
const saving = ref(false)
const saved = ref(false)
const error = ref('')
const loadingHistory = ref(false)
const simulations = ref([])

const form = reactive({
  name: '',
  goal_category: 'career',
  goal: '',
  personal_details: '',
  experience_level: '',
  target_timeline: '',
  constraints: '',
  preferred_language: 'English'
})

const completedCount = computed(() => simulations.value.filter(item => item.report_id).length)

const hydrateForm = () => {
  const user = authState.user || {}
  const profile = user.profile || {}
  form.name = user.name || ''
  form.goal_category = profile.goal_category || 'career'
  form.goal = profile.goal || ''
  form.personal_details = profile.personal_details || ''
  form.experience_level = profile.experience_level || ''
  form.target_timeline = profile.target_timeline || ''
  form.constraints = profile.constraints || ''
  form.preferred_language = profile.preferred_language || 'English'
}

const saveProfile = async () => {
  saving.value = true
  saved.value = false
  error.value = ''

  try {
    const response = await updateProfile(form)
    setAuthSession({
      token: authState.token,
      user: response.data.user
    })
    saved.value = true
    setTimeout(() => {
      saved.value = false
    }, 2200)
  } catch (err) {
    error.value = err.message || 'Could not save profile'
  } finally {
    saving.value = false
  }
}

const loadSimulations = async () => {
  loadingHistory.value = true
  try {
    const response = await getMySimulations(50)
    simulations.value = response.data || []
  } catch (err) {
    console.warn('Failed to load user simulations:', err)
    simulations.value = []
  } finally {
    loadingHistory.value = false
  }
}

const simulationTitle = (item) => {
  const text = item.simulation_requirement || item.project_name || item.simulation_id
  return text.length > 80 ? `${text.slice(0, 80)}...` : text
}

const formatDate = (value) => {
  if (!value) return 'Unknown date'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

const openSimulation = (item) => {
  router.push({ name: 'Simulation', params: { simulationId: item.simulation_id } })
}

const openReport = (item) => {
  router.push({ name: 'Report', params: { reportId: item.report_id } })
}

const signOut = async () => {
  await logout()
  router.push({ name: 'Login' })
}

onMounted(async () => {
  await initAuth(true)
  hydrateForm()
  await loadSimulations()
})
</script>

<style scoped>
.profile-page {
  min-height: 100vh;
  background:
    linear-gradient(135deg, rgba(255, 69, 0, 0.13), transparent 28%),
    linear-gradient(315deg, rgba(232, 245, 162, 0.09), transparent 34%),
    #050505;
  color: #ffffff;
  padding: 94px clamp(22px, 5vw, 76px) 54px;
}

.topbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 68px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 clamp(22px, 5vw, 76px);
  background: rgba(5, 5, 5, 0.72);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(18px);
  z-index: 10;
}

.brand,
.text-link {
  color: #ffffff;
  text-decoration: none;
}

.brand {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.top-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.text-link {
  color: rgba(255, 255, 255, 0.68);
  font-size: 14px;
}

.ghost-btn,
.refresh-btn,
.row-actions button {
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  color: #ffffff;
  padding: 9px 12px;
  cursor: pointer;
}

.profile-hero {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 32px;
  margin-bottom: 34px;
}

.eyebrow {
  color: #e8f5a2;
  font-family: var(--font-mono);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  margin-bottom: 16px;
}

h1 {
  font-size: clamp(42px, 6vw, 78px);
  line-height: 0.95;
  letter-spacing: 0;
  margin-bottom: 18px;
}

.hero-copy {
  max-width: 650px;
  color: rgba(255, 255, 255, 0.68);
  line-height: 1.65;
  font-size: 17px;
}

.metric-strip {
  min-width: 260px;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
}

.metric-strip > div {
  padding: 20px;
  display: grid;
  gap: 6px;
}

.metric-strip > div + div {
  border-left: 1px solid rgba(255, 255, 255, 0.1);
}

.metric-value {
  font-size: 30px;
  font-weight: 800;
}

.metric-label {
  color: rgba(255, 255, 255, 0.58);
  font-size: 12px;
  font-family: var(--font-mono);
  text-transform: uppercase;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(320px, 520px) minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

.profile-panel,
.history-panel {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(12, 12, 12, 0.82);
  backdrop-filter: blur(18px);
  padding: 24px;
}

.profile-panel {
  display: grid;
  gap: 16px;
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  color: #ffffff;
  font-size: 20px;
  font-weight: 800;
  margin-bottom: 8px;
}

.saved-badge {
  color: #050505;
  background: #e8f5a2;
  border-radius: 999px;
  padding: 5px 9px;
  font-size: 11px;
  font-family: var(--font-mono);
}

.two-col {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

label {
  display: grid;
  gap: 8px;
  color: rgba(255, 255, 255, 0.76);
  font-size: 13px;
  font-weight: 600;
}

input,
textarea,
select {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  color: #ffffff;
  padding: 12px 14px;
  font: inherit;
  outline: none;
}

textarea {
  resize: vertical;
  min-height: 92px;
}

select {
  height: 46px;
}

option {
  background: #111111;
}

input:focus,
textarea:focus,
select:focus {
  border-color: #e8f5a2;
  box-shadow: 0 0 0 3px rgba(232, 245, 162, 0.12);
}

.primary-btn {
  height: 50px;
  border: none;
  border-radius: 6px;
  background: #e8f5a2;
  color: #050505;
  font-weight: 800;
  cursor: pointer;
}

.primary-btn:disabled,
.refresh-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.error-text {
  color: #ff9f7d;
  font-size: 13px;
  line-height: 1.5;
}

.empty-state {
  padding: 28px 0;
  color: rgba(255, 255, 255, 0.58);
}

.history-list {
  display: grid;
  gap: 12px;
}

.history-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: center;
  padding: 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  cursor: pointer;
}

.history-row:hover {
  border-color: rgba(232, 245, 162, 0.55);
}

.row-title {
  color: #ffffff;
  font-weight: 700;
  line-height: 1.4;
}

.row-meta {
  margin-top: 6px;
  color: rgba(255, 255, 255, 0.52);
  font-family: var(--font-mono);
  font-size: 12px;
}

.row-actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 980px) {
  .profile-hero,
  .content-grid {
    grid-template-columns: 1fr;
  }

  .profile-hero {
    display: grid;
  }

  .metric-strip {
    min-width: 0;
  }
}

@media (max-width: 640px) {
  .two-col,
  .history-row {
    grid-template-columns: 1fr;
  }

  .topbar {
    height: auto;
    min-height: 68px;
    padding-top: 12px;
    padding-bottom: 12px;
    align-items: flex-start;
  }

  .top-actions {
    align-items: flex-end;
    flex-direction: column;
    gap: 8px;
  }
}
</style>
