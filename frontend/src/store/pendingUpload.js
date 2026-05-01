/**
 * Temporary storage for files and requirements pending upload
 * Used for immediate navigation after clicking start engine on homepage; API calls happen on the Process page
 */
import { reactive } from 'vue'

const STORAGE_KEY = 'univerra.pendingUpload'

const loadInitialState = () => {
  if (typeof window === 'undefined') {
    return {
      files: [],
      pendingFileNames: [],
      requiresFileReselection: false,
      simulationRequirement: '',
      additionalContext: '',
      isPending: false
    }
  }

  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return {
        files: [],
        pendingFileNames: [],
        requiresFileReselection: false,
        simulationRequirement: '',
        additionalContext: '',
        isPending: false
      }
    }

    const parsed = JSON.parse(raw)
    return {
      files: [],
      pendingFileNames: Array.isArray(parsed.pendingFileNames) ? parsed.pendingFileNames : [],
      requiresFileReselection: Boolean(parsed.requiresFileReselection),
      simulationRequirement: typeof parsed.simulationRequirement === 'string' ? parsed.simulationRequirement : '',
      additionalContext: typeof parsed.additionalContext === 'string' ? parsed.additionalContext : '',
      isPending: Boolean(parsed.isPending)
    }
  } catch {
    return {
      files: [],
      pendingFileNames: [],
      requiresFileReselection: false,
      simulationRequirement: '',
      additionalContext: '',
      isPending: false
    }
  }
}

const persistState = () => {
  if (typeof window === 'undefined') return

  try {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        pendingFileNames: state.pendingFileNames,
        requiresFileReselection: state.pendingFileNames.length > 0,
        simulationRequirement: state.simulationRequirement,
        additionalContext: state.additionalContext,
        isPending: state.isPending
      })
    )
  } catch {
    // Ignore storage errors and keep in-memory state working.
  }
}

const initialState = loadInitialState()

const state = reactive({
  files: initialState.files,
  pendingFileNames: initialState.pendingFileNames,
  requiresFileReselection: initialState.requiresFileReselection,
  simulationRequirement: initialState.simulationRequirement,
  additionalContext: initialState.additionalContext,
  isPending: initialState.isPending
})

export function setPendingUpload(files, requirement, additionalContext = '') {
  state.files = files
  state.pendingFileNames = Array.isArray(files) ? files.map(file => file?.name).filter(Boolean) : []
  state.requiresFileReselection = false
  state.simulationRequirement = requirement
  state.additionalContext = additionalContext
  state.isPending = true
  persistState()
}

export function getPendingUpload() {
  return {
    files: state.files,
    pendingFileNames: state.pendingFileNames,
    requiresFileReselection: state.requiresFileReselection,
    simulationRequirement: state.simulationRequirement,
    additionalContext: state.additionalContext,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.files = []
  state.pendingFileNames = []
  state.requiresFileReselection = false
  state.simulationRequirement = ''
  state.additionalContext = ''
  state.isPending = false
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(STORAGE_KEY)
  }
}

export default state
