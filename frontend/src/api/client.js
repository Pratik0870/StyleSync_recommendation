/**
 * The only place this app talks to the backend.
 *
 * No recommendation logic lives on the client: it does not score, rank, filter
 * or re-order anything. It sends intent and renders what FastAPI returns.
 */

const BASE = import.meta.env.VITE_API_BASE ?? ''

/** Resolve a relative image path from the API against the API origin. */
export function imageUrl(path) {
  if (!path) return null
  if (/^https?:\/\//i.test(path)) return path
  return `${BASE}${path}`
}

export class ApiError extends Error {
  constructor(message, { status, code, detail } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.detail = detail
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch (cause) {
    // Network-level failure: the backend is not running or unreachable.
    throw new ApiError('Could not reach the recommendation service.', {
      code: 'network_error',
      detail:
        'The backend is not responding. Start it with `python scripts/run_api.py` and try again.',
    })
  }

  let body = null
  let parseFailed = false
  try {
    body = await response.json()
  } catch {
    body = null
    parseFailed = true
  }

  // A 200 that is not JSON means the request never reached the API — usually a
  // dev-proxy gap serving the SPA shell. Surfacing it beats rendering an empty
  // page that looks like "no results".
  if (response.ok && parseFailed) {
    throw new ApiError('The service returned an unexpected response.', {
      status: response.status,
      code: 'bad_response',
      detail: `${path} did not return JSON. If this is the dev server, check the Vite proxy covers this route.`,
    })
  }

  if (!response.ok) {
    throw new ApiError(body?.error ?? 'The request failed.', {
      status: response.status,
      code: body?.code ?? 'unknown_error',
      detail: body?.detail ?? `The service replied with status ${response.status}.`,
    })
  }
  return body
}

export function getHealth() {
  return request('/health')
}

export function getProduct(productId) {
  return request(`/products/${productId}`)
}

export function getBrowse({ category, domain, colour, gender, anchorsOnly, limit, offset } = {}) {
  const params = new URLSearchParams()
  if (category) params.set('category', category)
  if (domain) params.set('domain', domain)
  if (colour) params.set('colour', colour)
  if (gender) params.set('gender', gender)
  if (anchorsOnly) params.set('anchors_only', 'true')
  if (limit) params.set('limit', String(limit))
  if (offset) params.set('offset', String(offset))
  return request(`/catalog/browse?${params}`)
}

export function getCategories({ anchorCategory, occasion } = {}) {
  const params = new URLSearchParams()
  if (anchorCategory) params.set('anchor_category', anchorCategory)
  if (occasion) params.set('occasion', occasion)
  const suffix = params.toString() ? `?${params}` : ''
  return request(`/categories${suffix}`)
}

/**
 * Build the POST body. Only fields the backend actually accepts are sent -
 * it rejects unknown fields, and empty values are omitted so a blank control
 * never overrides something the parser extracted.
 */
export function buildRecommendPayload(input) {
  const payload = {}
  const text = (key, value) => {
    if (typeof value === 'string' && value.trim()) payload[key] = value.trim()
  }
  const list = (key, value) => {
    if (Array.isArray(value) && value.length) payload[key] = value
  }

  text('query', input.query)
  text('anchor_type', input.anchorType)
  text('colour', input.colour)
  text('occasion', input.occasion)
  text('style', input.style)
  if (input.gender) payload.gender = input.gender
  if (Number.isInteger(input.productId)) payload.product_id = input.productId
  if (input.anchorType) payload.anchor_type = input.anchorType
  list('preferred_colours', input.preferredColours)
  list('include_categories', input.includeCategories)
  list('exclude_categories', input.excludeCategories)
  if (input.limit) payload.limit = input.limit
  if (input.maxPerCategory) payload.max_per_category = input.maxPerCategory
  if (input.includeScoreBreakdown) payload.include_score_breakdown = true
  if (input.useLlm === false) payload.use_llm = false
  return payload
}

export function postRecommend(input) {
  return request('/recommend', {
    method: 'POST',
    body: JSON.stringify(buildRecommendPayload(input)),
  })
}
