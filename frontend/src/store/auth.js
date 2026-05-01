import { computed, reactive } from 'vue'
import { getMe, logout as apiLogout } from '../api/auth'

export const AUTH_TOKEN_KEY = 'univerra_auth_token'

export const authState = reactive({
  token: window.localStorage?.getItem(AUTH_TOKEN_KEY) || '',
  user: null,
  initialized: false,
  loading: false
})

export const isAuthenticated = computed(() => Boolean(authState.token && authState.user))

export const setAuthSession = ({ token, user }) => {
  authState.token = token || ''
  authState.user = user || null

  if (authState.token) {
    window.localStorage?.setItem(AUTH_TOKEN_KEY, authState.token)
  } else {
    window.localStorage?.removeItem(AUTH_TOKEN_KEY)
  }
  authState.initialized = true
}

export const clearAuthSession = () => {
  setAuthSession({ token: '', user: null })
}

export const initAuth = async (force = false) => {
  if (authState.initialized && !force) {
    return authState.user
  }

  authState.token = window.localStorage?.getItem(AUTH_TOKEN_KEY) || ''
  if (!authState.token) {
    authState.user = null
    authState.initialized = true
    return null
  }

  authState.loading = true
  try {
    const response = await getMe()
    authState.user = response.data?.user || null
    return authState.user
  } catch (error) {
    clearAuthSession()
    return null
  } finally {
    authState.loading = false
    authState.initialized = true
  }
}

export const logout = async () => {
  try {
    if (authState.token) {
      await apiLogout()
    }
  } catch (error) {
    console.warn('Logout request failed:', error)
  } finally {
    clearAuthSession()
    authState.initialized = true
  }
}
