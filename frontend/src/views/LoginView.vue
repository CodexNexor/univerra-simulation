<template>
  <main class="auth-page">
    <div class="grid-backdrop"></div>

    <router-link to="/" class="brand-link">UNIVERRA</router-link>

    <section class="auth-copy">
      <p class="eyebrow">Secure simulation workspace</p>
      <h1>Welcome back</h1>
      <p class="copy-text">
        Your saved goals, profile context, and previous simulations stay attached to your account.
      </p>
    </section>

    <section class="auth-panel">
      <div class="panel-head">
        <span>Login</span>
        <router-link to="/signup">Create account</router-link>
      </div>

      <form @submit.prevent="submitLogin" class="auth-form">
        <label>
          <span>Email</span>
          <input v-model.trim="form.email" type="email" autocomplete="email" required />
        </label>

        <label>
          <span>Password</span>
          <input v-model="form.password" type="password" autocomplete="current-password" required />
        </label>

        <p v-if="error" class="error-text">{{ error }}</p>

        <button class="primary-btn" type="submit" :disabled="loading">
          {{ loading ? 'Signing in...' : 'Sign in' }}
        </button>
      </form>
    </section>
  </main>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../api/auth'
import { setAuthSession } from '../store/auth'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const error = ref('')

const form = reactive({
  email: '',
  password: ''
})

const submitLogin = async () => {
  if (loading.value) return
  loading.value = true
  error.value = ''

  try {
    const response = await login(form)
    setAuthSession({
      token: response.data.token,
      user: response.data.user
    })
    router.push(route.query.redirect || { name: 'Home' })
  } catch (err) {
    error.value = err.message || 'Login failed'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  position: relative;
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(320px, 460px);
  gap: 56px;
  align-items: center;
  padding: 80px clamp(24px, 7vw, 110px);
  background:
    linear-gradient(135deg, rgba(255, 69, 0, 0.16), transparent 28%),
    linear-gradient(315deg, rgba(232, 245, 162, 0.1), transparent 30%),
    #050505;
  overflow: hidden;
}

.grid-backdrop {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.7), transparent 85%);
  pointer-events: none;
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

.auth-copy,
.auth-panel {
  position: relative;
  z-index: 1;
}

.eyebrow {
  color: #e8f5a2;
  font-family: var(--font-mono);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  margin-bottom: 20px;
}

h1 {
  font-size: clamp(44px, 7vw, 92px);
  line-height: 0.94;
  letter-spacing: 0;
  color: #ffffff;
  margin-bottom: 24px;
}

.copy-text {
  max-width: 560px;
  color: rgba(255, 255, 255, 0.68);
  font-size: 18px;
  line-height: 1.65;
}

.auth-panel {
  width: 100%;
  padding: 32px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(12, 12, 12, 0.82);
  backdrop-filter: blur(18px);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.42);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 28px;
  color: #ffffff;
  font-size: 22px;
  font-weight: 700;
}

.panel-head a {
  color: #e8f5a2;
  font-size: 13px;
  text-decoration: none;
  font-family: var(--font-mono);
}

.auth-form {
  display: grid;
  gap: 18px;
}

label {
  display: grid;
  gap: 8px;
  color: rgba(255, 255, 255, 0.76);
  font-size: 13px;
  font-weight: 600;
}

input {
  width: 100%;
  height: 48px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  color: #ffffff;
  padding: 0 14px;
  font: inherit;
  outline: none;
}

input:focus {
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

.primary-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.error-text {
  color: #ff9f7d;
  font-size: 13px;
  line-height: 1.5;
}

@media (max-width: 860px) {
  .auth-page {
    grid-template-columns: 1fr;
    gap: 32px;
    padding: 96px 22px 40px;
  }

  .auth-copy {
    max-width: 560px;
  }

  .copy-text {
    font-size: 16px;
  }
}
</style>
