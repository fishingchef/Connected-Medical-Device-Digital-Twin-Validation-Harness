import { useState, useEffect } from 'react'
import { CheckCircle, XCircle, ChevronRight, RefreshCw } from 'lucide-react'
import { api } from '../lib/api.js'

export default function RunHistory({ onSelectRun }) {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      const data = await api.runs()
      setRuns(data.runs || [])
    } catch {}
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  return (
    <div style={{ padding: '32px 40px', maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--accent)', letterSpacing: '0.12em', marginBottom: 8 }}>
            SIMULATION HISTORY
          </div>
          <h1 style={{ fontSize: 26, fontWeight: 300, color: 'var(--text)', letterSpacing: '-0.02em' }}>Run History</h1>
        </div>
        <button onClick={load} style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '8px 14px', borderRadius: 7,
          background: 'var(--bg2)', border: '1px solid var(--border)',
          color: 'var(--text2)', fontSize: 12, cursor: 'pointer',
        }}>
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {loading ? (
        <div style={{ color: 'var(--text3)', fontFamily: 'var(--mono)', fontSize: 12 }}>Loading...</div>
      ) : runs.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '60px 0',
          color: 'var(--text3)', borderRadius: 12,
          border: '1px dashed var(--border)',
        }}>
          <div style={{ fontSize: 13 }}>No simulation runs yet.</div>
          <div style={{ fontSize: 12, marginTop: 6 }}>Go to Scenario Runner to launch your first simulation.</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 8 }}>
          {runs.map(run => (
            <button key={run.run_id} onClick={() => onSelectRun(run.run_id)} style={{
              display: 'flex', alignItems: 'center', gap: 14,
              padding: '14px 18px',
              background: 'var(--bg2)', border: '1px solid var(--border)',
              borderRadius: 10, cursor: 'pointer', width: '100%', textAlign: 'left',
              transition: 'border-color 0.15s',
            }}>
              {run.passed === true
                ? <CheckCircle size={16} color="var(--accent)" />
                : run.passed === false
                ? <XCircle size={16} color="var(--danger)" />
                : <div style={{ width: 16, height: 16, borderRadius: '50%', background: 'var(--text3)' }} />}

              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, color: 'var(--text)', marginBottom: 2 }}>
                  {run.scenario_id}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--mono)' }}>
                  {run.run_id} · {run.created_at ? new Date(run.created_at).toLocaleString() : ''}
                </div>
              </div>

              <div style={{
                fontSize: 11, fontFamily: 'var(--mono)', padding: '3px 8px',
                borderRadius: 4,
                background: run.passed === true ? 'rgba(0,212,168,0.1)'
                          : run.passed === false ? 'rgba(255,71,87,0.1)' : 'var(--bg3)',
                color: run.passed === true ? 'var(--accent)'
                     : run.passed === false ? 'var(--danger)' : 'var(--text3)',
              }}>
                {run.passed === true ? 'PASS' : run.passed === false ? 'FAIL' : 'RUNNING'}
              </div>

              <ChevronRight size={14} color="var(--text3)" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
