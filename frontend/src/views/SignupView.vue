<template>
  <main class="signup-page">
    <div class="grid-backdrop"></div>
    <router-link to="/" class="brand-link">UNIVERRA</router-link>

    <section class="intro">
      <p class="eyebrow">Personal forecast memory</p>
      <h1>Create your simulation identity</h1>
      <p class="copy-text">
        Add a goal now and every relevant forecast can use it to shape assumptions, risks, and roadmaps.
      </p>
    </section>

    <section class="signup-panel">
      <div class="panel-head">
        <span>Sign up</span>
        <router-link to="/login">I already have an account</router-link>
      </div>

      <form @submit.prevent="submitSignup" class="signup-form">
        <div class="two-col">
          <label>
            <span>Name</span>
            <input v-model.trim="form.name" autocomplete="name" required />
          </label>
          <label>
            <span>Email</span>
            <input v-model.trim="form.email" type="email" autocomplete="email" required />
          </label>
        </div>

        <label>
          <span>Password</span>
          <input v-model="form.password" type="password" autocomplete="new-password" minlength="8" required />
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
          <textarea
            v-model.trim="form.goal"
            rows="3"
            placeholder="Example: Become an IAS officer, senior developer, founder, researcher..."
            required
          ></textarea>
        </label>

        <label>
          <span>Personal details for better simulation</span>
          <textarea
            v-model.trim="form.personal_details"
            rows="4"
            placeholder="Current education, skills, city, schedule, strengths, weak areas, resources..."
          ></textarea>
        </label>

        <div class="two-col">
          <label>
            <span>Current level</span>
            <input v-model.trim="form.experience_level" placeholder="Beginner, college student, 2 years exp..." />
          </label>

          <label>
            <span>Constraints</span>
            <input v-model.trim="form.constraints" placeholder="Budget, time, family, job, exam attempts..." />
          </label>
        </div>

        <p v-if="error" class="error-text">{{ error }}</p>

        <button class="primary-btn" type="submit" :disabled="loading">
          {{ loading ? 'Creating account...' : 'Create account' }}
        </button>
      </form>
    </section>
  </main>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { signup } from '../api/auth'
import { setAuthSession } from '../store/auth'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const error = ref('')

const form = reactive({
  name: '',
  email: '',
  password: '',
  goal_category: 'career',
  goal: '',
  personal_details: '',
  experience_level: '',
  target_timeline: '',
  constraints: '',
  preferred_language: 'English'
})

const submitSignup = async () => {
  if (loading.value) return
  loading.value = true
  error.value = ''

  try {
    const response = await signup(form)
    setAuthSession({
      token: response.data.token,
      user: response.data.user
    })
    router.push(route.query.redirect || { name: 'Home' })
  } catch (err) {
    error.value = err.message || 'Signup failed'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.signup-page {
  min-height: 100vh;
  position: relative;
  display: grid;
  grid-template-columns: minmax(300px, 0.85fr) minmax(420px, 680px);
  gap: 48px;
  align-items: start;
  padding: 88px clamp(22px, 6vw, 96px) 56px;
  background:
    linear-gradient(135deg, rgba(255, 69, 0, 0.15), transparent 28%),
    linear-gradient(315deg, rgba(232, 245, 162, 0.1), transparent 32%),
    #050505;
}

.grid-backdrop {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px);
  background-size: 44px 44px;
  pointer-events: none;
  mask-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.7), transparent 88%);
}

.brand-link {
  position: fixed;
  top: 28px;
  left: 36px;
  color: #fafafa;
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.16em;
  z-index: 2;
}

.intro,
.signup-panel {
  position: relative;
  z-index: 1;
}

.intro {
  padding-top: 56px;
  position: sticky;
  top: 42px;
}

.eyebrow {
  color: #e8f5a2;
  font-family: var(--font-mono);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  margin-bottom: 18px;
}

h1 {
  color: #ffffff;
  font-size: clamp(42px, 6vw, 78px);
  line-height: 0.98;
  letter-spacing: 0;
  margin-bottom: 24px;
}

.copy-text {
  max-width: 520px;
  color: rgba(255, 255, 255, 0.68);
  font-size: 17px;
  line-height: 1.65;
}

.signup-panel {
  width: 100%;
  padding: 30px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(12, 12, 12, 0.84);
  backdrop-filter: blur(18px);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.42);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
  color: #ffffff;
  font-size: 22px;
  font-weight: 700;
}

.panel-head a {
  color: #e8f5a2;
  font-size: 13px;
  text-decoration: none;
  font-family: var(--font-mono);
  text-align: right;
}

.signup-form {
  display: grid;
  gap: 16px;
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

select {
  height: 46px;
}

textarea {
  resize: vertical;
  min-height: 88px;
}

input:focus,
textarea:focus,
select:focus {
  border-color: #e8f5a2;
  box-shadow: 0 0 0 3px rgba(232, 245, 162, 0.12);
}

option {
  background: #111111;
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

.primary-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.error-text {
  color: #ff9f7d;
  font-size: 13px;
  line-height: 1.5;
}

@media (max-width: 920px) {
  .signup-page {
    grid-template-columns: 1fr;
    padding: 96px 22px 42px;
  }

  .intro {
    position: static;
    padding-top: 0;
  }
}

@media (max-width: 620px) {
  .two-col {
    grid-template-columns: 1fr;
  }

  .signup-panel {
    padding: 22px;
  }
}
</style>
