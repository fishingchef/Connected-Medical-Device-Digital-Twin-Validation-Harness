import { useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import ScenarioRunner from './pages/ScenarioRunner.jsx'
import RunHistory from './pages/RunHistory.jsx'
import RunDetail from './pages/RunDetail.jsx'

const DEFAULT_SCENARIO = {
  subject:        'healthy_adult_m',
  schedule:       'typical_day',
  wearConds:      ['normal'],
  networkConds:   ['normal_sync'],
  behaviorChecks: ['timestamps_preserved', 'no_duplicates'],
  firmware:       '1.2.0',
  syncInterval:   null,   // null = default 30s
}

export default function App() {
  const [page,         setPage]         = useState('runner')
  const [selectedRun,  setSelectedRun]  = useState(null)
  const [prevPage,     setPrevPage]     = useState(null)
  // Persisted scenario selections
  const [scenario,     setScenario]     = useState(DEFAULT_SCENARIO)

  function openRun(runId, fromPage = page) {
    setPrevPage(fromPage)
    setSelectedRun(runId)
    setPage('detail')
  }

  function goBack() {
    setPage(prevPage || 'runner')
    setPrevPage(null)
  }

  function resetScenario() {
    setScenario({ ...DEFAULT_SCENARIO })
  }

  function navTo(p) {
    setPrevPage(null)
    setPage(p)
  }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar current={page} onNav={navTo} />
      <main style={{ flex: 1, overflow: 'auto', background: 'var(--bg)' }}>
        {page === 'runner' && (
          <ScenarioRunner
            scenario={scenario}
            onScenarioChange={setScenario}
            onReset={resetScenario}
            onRunComplete={(id) => openRun(id, 'runner')}
          />
        )}
        {page === 'history' && (
          <RunHistory onSelectRun={(id) => openRun(id, 'history')} />
        )}
        {page === 'detail' && (
          <RunDetail
            runId={selectedRun}
            prevPage={prevPage}
            onBack={goBack}
            onBackToRunner={() => { setPrevPage(null); setPage('runner') }}
          />
        )}
      </main>
    </div>
  )
}
