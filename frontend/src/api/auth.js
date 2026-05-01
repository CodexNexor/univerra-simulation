import service from './index'

export const signup = (data) => {
  return service.post('/api/auth/signup', data)
}

export const login = (data) => {
  return service.post('/api/auth/login', data)
}

export const getMe = () => {
  return service.get('/api/auth/me')
}

export const updateProfile = (data) => {
  return service.patch('/api/auth/profile', data)
}

export const getMySimulations = (limit = 50) => {
  return service.get('/api/auth/simulations', { params: { limit } })
}

export const logout = () => {
  return service.post('/api/auth/logout')
}
