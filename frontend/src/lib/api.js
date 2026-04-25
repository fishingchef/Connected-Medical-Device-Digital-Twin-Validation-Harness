const BASE = import.meta.env.VITE_API_URL || ''

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

export const api = {
  scenarios: ()            => req('/api/scenarios'),
  runs:      ()            => req('/api/runs'),
  run:       (id)          => req(`/api/runs/${id}`),
  packets:   (id)          => req(`/api/runs/${id}/packets`),
  report:    (id)          => req(`/api/runs/${id}/report`),
  runScenario: (body)      => req('/api/scenarios/run', {
    method: 'POST',
    body: JSON.stringify(body),
  }),
}
