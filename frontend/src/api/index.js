import axios from 'axios'

// Create axios instance
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001',
  timeout: 300000, // 5-minute timeout (ontology generation may take a long time)
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor
service.interceptors.request.use(
  config => {
    const token = window.localStorage?.getItem('univerra_auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

// Response interceptor (with retry mechanism)
service.interceptors.response.use(
  response => {
    const res = response.data

    // If the returned status is not success, throw an error
    if (!res.success && res.success !== undefined) {
      console.error('API Error:', res.error || res.message || 'Unknown error')
      return Promise.reject(new Error(res.error || res.message || 'Error'))
    }

    return res
  },
  error => {
    console.error('Response error:', error)
    const backendMessage = error.response?.data?.error || error.response?.data?.message
    const statusCode = error.response?.status

    // Handle timeout
    if (error.code === 'ECONNABORTED' && error.message.includes('timeout')) {
      console.error('Request timeout')
    }

    // Handle network error
    if (error.message === 'Network Error') {
      console.error('Network error - please check your connection')
    }

    if (backendMessage) {
      if (statusCode === 401) {
        window.localStorage?.removeItem('univerra_auth_token')
        window.dispatchEvent(new CustomEvent('univerra-auth-expired'))
      }
      const wrappedError = new Error(backendMessage)
      wrappedError.response = error.response
      wrappedError.status = statusCode
      return Promise.reject(wrappedError)
    }

    return Promise.reject(error)
  }
)

// Request function with retry
export const requestWithRetry = async (requestFn, maxRetries = 3, delay = 1000) => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn()
    } catch (error) {
      const status = error.status || error.response?.status
      const retryable = !status || status === 408 || status === 429 || status >= 500
      if (!retryable) {
        throw error
      }

      if (i === maxRetries - 1) throw error

      console.warn(`Request failed, retrying (${i + 1}/${maxRetries})...`)
      await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, i)))
    }
  }
}

export default service
