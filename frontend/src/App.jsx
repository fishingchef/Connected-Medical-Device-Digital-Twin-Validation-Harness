import { useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import ScenarioRunner from './pages/ScenarioRunner.jsx'
import RunHistory from './pages/RunHistory.jsx'
import RunDetail from './pages/RunDetail.jsx'

export default function App() {
  const [page, setPage] = useState('runner')
  const [selectedRun, setSelectedRun] = useState(null)

  function openRun(runId) {
    setSelectedRun(runId)
    setPage('detail')
  }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar current={page} onNav={setPage} />
      <main style={{ flex: 1, overflow: 'auto', background: 'var(--bg)' }}>
        {page === 'runner' && <ScenarioRunner onRunComplete={openRun} />}
        {page === 'history' && <RunHistory onSelectRun={openRun} />}
        {page === 'detail' && <RunDetail runId={selectedRun} onBack={() => setPage('history')} />}
      </main>
    </div>
  )
}
