import { expandInserts, computeEntityBounds } from '../utils/geometry.js'

self.onmessage = (ev) => {
  const { jobId, entities, blockDefinitions } = ev.data
  try {
    const { drawn } = expandInserts(entities, blockDefinitions || {})
    for (const entity of drawn) {
      entity._bbox = computeEntityBounds(entity)
    }
    self.postMessage({ jobId, drawn })
  } catch (err) {
    self.postMessage({ jobId, error: String(err) })
  }
}
