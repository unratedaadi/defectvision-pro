const key = 'defectvision.reduceMotion'

export function reducedMotion() {
  try {
    return localStorage.getItem(key) === 'true'
  } catch {
    return false
  }
}

export function applyMotionPreference(value: boolean) {
  document.documentElement.dataset.reduceMotion = String(value)
}

export function saveMotionPreference(value: boolean) {
  applyMotionPreference(value)
  try {
    localStorage.setItem(key, String(value))
    return true
  } catch {
    return false
  }
}
