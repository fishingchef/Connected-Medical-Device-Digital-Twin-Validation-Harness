import { useState, useEffect } from 'react'
import { Play, Loader, CheckCircle, XCircle, ChevronRight, Wifi, WifiOff, Battery, Thermometer, Activity } from 'lucide-react'
import { api } from '../lib/api.js'

const SCENARIOS = [
  { id: 'GW_WIFI_OUTAGE_01', name: 'Gateway Wi-Fi Outage', tag: 'Data Integrity', color: '#0096ff',
    desc: '2-hr rest session. Gateway offline min 40–60. Tests buffering + timestamp preservation.' },
  { id: 'HIGH_MOTION_01', name: 'High Motion / Degraded Signal', tag: 'Alert Safety', color: '#f5a623',
    desc: '30 min vigorous activity → low-confidence HR/RR. Tests alert suppression logic.' },
  { id: 'FEVER_TREND_01', name: 'Fever Trend', tag: 'Alert Trigger', color: '#ff4757',
    desc: 'Gradual temp rise over 60 min. Tests threshold-crossing alert generation.' },
  { id: 'POOR_CONTACT_01', name: 'Poor Sensor Contact', tag: 'Data Quality', color: '#a78bfa',
    desc: '30 min poor adhesion. Tests low-confidence annotation and dashboard flagging.' },
]

const FIRMWARE_OPTS = [
  { v: '1.0.0', label: 'v1.0.0 — baseline (no retry logic)' },
  { v: '1.2.0', label: 'v1.2.0 — BLE retry on disconnect' },
  { v: '2.0.0', label: 'v2.0.0 — compression + CRC check' },
]

const FAULT_OPTS = [
  { id: 'clean',        label: 'Clean — no faults' },
  { id: 'flaky',        label: 'Flaky — intermittent latency + 5% loss' },
  { id: 'lossy',        label: 'Lossy — 15% packet loss' },
  { id: 'tls_failure',  label: 'TLS failures — 30% auth error rate' },
]

export default function ScenarioRunner({ onRunComplete }) {
  const [selected, setSelected] = useState('GW_WIFI_OUTAGE_01')
  const [fw, setFw]             = useState('1.2.0')
  const [battery, setBattery]   = useState(95)
  const [ambient, setAmbient]   = useState(22)
  const [fault, setFault]       = useState('clean')
  const [outageStart, setOutageStart] = useState(40)
  const [outageEnd, setOutageEnd]     = useState(60)
  const [useOutage, setUseOutage]     = useState(false)
  const [running, setRunning]   = useState(false)
  const [result, setResult]     = useState(null)
  const [error, setError]       = useState(null)

  async function handleRun() {
    setRunning(true)
    setResult(null)
    setError(null)
    try {
      const body = {
        scenario_id: selected,
        firmware_version: fw,
        initial_battery_pct: battery,
        ambient_temp_c: ambient,
        fault_profile: fault,
        outage_start_min: useOutage ? outageStart : null,
        outage_end_min:   useOutage ? outageEnd   : null,
      }
      const data = await api.runScenario(body)
      if (data.status === 'error') {
        setError(`Backend error: ${data.error}`)
      } else {
        setResult(data)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  const scenario = SCENARIOS.find(s => s.id === selected)

  return (
    <div style={{ padding: '32px 40px', maxWidth: 960, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--accent)', letterSpacing: '0.12em', marginBottom: 8 }}>
          SIMULATION CONTROL
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 300, color: 'var(--text)', letterSpacing: '-0.02em' }}>
          Scenario Runner
        </h1>
        <p style={{ color: 'var(--text2)', marginTop: 6, fontSize: 13 }}>
          Configure and execute end-to-end device simulation. Each run produces a validation report with pass/fail evidence.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 24 }}>
        {/* Left: Scenario selection */}
        <div>
          <Label>Select scenario</Label>
          <div style={{ display: 'grid', gap: 8, marginBottom: 24 }}>
            {SCENARIOS.map(s => (
              <button key={s.id} onClick={() => setSelected(s.id)} style={{
                background: selected === s.id ? 'var(--bg3)' : 'var(--bg2)',
                border: `1px solid ${selected === s.id ? s.color + '60' : 'var(--border)'}`,
                borderRadius: 10,
                padding: '14px 16px',
                textAlign: 'left',
                transition: 'all 0.15s',
                cursor: 'pointer',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                  <div style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: selected === s.id ? s.color : 'var(--text3)',
                    flexShrink: 0,
                  }} />
                  <span style={{ fontSize: 13, fontWeight: 500, color: selected === s.id ? 'var(--text)' : 'var(--text2)' }}>
                    {s.name}
                  </span>
                  <span style={{
                    marginLeft: 'auto',
                    fontSize: 10,
                    fontFamily: 'var(--mono)',
                    color: s.color,
                    background: s.color + '18',
                    padding: '2px 8px',
                    borderRadius: 4,
                  }}>{s.tag}</span>
                </div>
                <p style={{ fontSize: 12, color: 'var(--text3)', marginLeft: 16, lineHeight: 1.5 }}>{s.desc}</p>
              </button>
            ))}
          </div>

          {/* Device + network config */}
          <Label>Device configuration</Label>
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: 16, marginBottom: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
              <Field label="Firmware version">
                <select value={fw} onChange={e => setFw(e.target.value)} style={selectStyle}>
                  {FIRMWARE_OPTS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
                </select>
              </Field>
              <Field label={`Battery (${battery}%)`}>
                <input type="range" min={10} max={100} value={battery}
                  onChange={e => setBattery(+e.target.value)}
                  style={{ width: '100%', accentColor: 'var(--accent)' }} />
              </Field>
            </div>
            <Field label={`Ambient temperature (${ambient}°C)`}>
              <input type="range" min={5} max={40} value={ambient}
                onChange={e => setAmbient(+e.target.value)}
                style={{ width: '100%', accentColor: 'var(--accent)' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text3)', marginTop: 2 }}>
                <span>5°C (cold)</span><span>22°C (normal)</span><span>40°C (hot)</span>
              </div>
            </Field>
          </div>

          <Label>Network fault injection</Label>
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
              {FAULT_OPTS.map(o => (
                <button key={o.id} onClick={() => setFault(o.id)} style={{
                  padding: '8px 12px',
                  borderRadius: 6,
                  fontSize: 12,
                  background: fault === o.id ? 'rgba(0,212,168,0.1)' : 'var(--bg3)',
                  border: `1px solid ${fault === o.id ? 'var(--accent)' : 'var(--border)'}`,
                  color: fault === o.id ? 'var(--accent)' : 'var(--text2)',
                  textAlign: 'left',
                  cursor: 'pointer',
                  transition: 'all 0.1s',
                }}>{o.label}</button>
              ))}
            </div>

            {/* Custom outage window */}
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text2)', cursor: 'pointer', marginBottom: 10 }}>
              <input type="checkbox" checked={useOutage} onChange={e => setUseOutage(e.target.checked)}
                style={{ accentColor: 'var(--accent)' }} />
              Set custom gateway outage window
            </label>
            {useOutage && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <Field label={`Outage start (min ${outageStart})`}>
                  <input type="range" min={1} max={100} value={outageStart}
                    onChange={e => setOutageStart(+e.target.value)}
                    style={{ width: '100%', accentColor: 'var(--warn)' }} />
                </Field>
                <Field label={`Outage end (min ${outageEnd})`}>
                  <input type="range" min={2} max={110} value={outageEnd}
                    onChange={e => setOutageEnd(+e.target.value)}
                    style={{ width: '100%', accentColor: 'var(--warn)' }} />
                </Field>
              </div>
            )}
          </div>
        </div>

        {/* Right: Run panel + results */}
        <div>
          <div style={{
            background: 'var(--bg2)',
            border: '1px solid var(--border)',
            borderRadius: 12,
            padding: 20,
            position: 'sticky',
            top: 32,
          }}>
            <div style={{ fontSize: 12, color: 'var(--text3)', fontFamily: 'var(--mono)', marginBottom: 12 }}>RUN CONFIGURATION</div>

            <ConfigRow icon={<Activity size={13} />} label="Scenario" value={scenario?.name} />
            <ConfigRow icon={<Battery size={13} />} label="Firmware" value={`v${fw}`} />
            <ConfigRow icon={<Battery size={13} />} label="Battery" value={`${battery}%`} />
            <ConfigRow icon={<Thermometer size={13} />} label="Ambient" value={`${ambient}°C`} />
            <ConfigRow icon={<WifiOff size={13} />} label="Network" value={fault} />
            {useOutage && (
              <ConfigRow icon={<WifiOff size={13} />} label="Outage" value={`min ${outageStart}–${outageEnd}`} color="var(--warn)" />
            )}

            <button onClick={handleRun} disabled={running} style={{
              width: '100%',
              marginTop: 20,
              padding: '12px 0',
              borderRadius: 8,
              background: running ? 'var(--bg3)' : 'var(--accent)',
              color: running ? 'var(--text2)' : '#000',
              fontWeight: 600,
              fontSize: 13,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              transition: 'all 0.15s',
              cursor: running ? 'not-allowed' : 'pointer',
            }}>
              {running ? <><Loader size={14} style={{ animation: 'spin 1s linear infinite' }} /> Simulating...</> : <><Play size={14} /> Run Simulation</>}
            </button>

            {/* Result summary */}
            {error && (
              <div style={{ marginTop: 16, padding: 12, background: 'rgba(255,71,87,0.08)', border: '1px solid rgba(255,71,87,0.3)', borderRadius: 8, fontSize: 12, color: 'var(--danger)' }}>
                {error}
              </div>
            )}

            {result && (
              <div style={{ marginTop: 16 }}>
                <div style={{
                  padding: 14,
                  background: result.validation.passed ? 'rgba(0,212,168,0.06)' : 'rgba(255,71,87,0.06)',
                  border: `1px solid ${result.validation.passed ? 'rgba(0,212,168,0.3)' : 'rgba(255,71,87,0.3)'}`,
                  borderRadius: 8,
                  marginBottom: 10,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    {result.validation.passed
                      ? <CheckCircle size={16} color="var(--accent)" />
                      : <XCircle size={16} color="var(--danger)" />}
                    <span style={{ fontWeight: 600, fontSize: 13, color: result.validation.passed ? 'var(--accent)' : 'var(--danger)' }}>
                      {result.validation.passed ? 'ALL CHECKS PASSED' : 'CHECKS FAILED'}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text2)' }}>
                    {result.validation.pass_count}/{result.validation.pass_count + result.validation.fail_count} validations passed
                    · {result.total_uploaded} packets ingested
                  </div>
                </div>

                {result.validation.results.map(r => (
                  <div key={r.check_id} style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '6px 0',
                    borderBottom: '1px solid var(--border)',
                    fontSize: 11,
                  }}>
                    {r.passed
                      ? <CheckCircle size={12} color="var(--accent)" />
                      : <XCircle size={12} color="var(--danger)" />}
                    <span style={{ color: 'var(--text2)', flex: 1 }}>{r.description}</span>
                  </div>
                ))}

                <button onClick={() => onRunComplete(result.run_id)} style={{
                  width: '100%',
                  marginTop: 12,
                  padding: '8px 0',
                  borderRadius: 6,
                  background: 'var(--bg3)',
                  border: '1px solid var(--border2)',
                  color: 'var(--text2)',
                  fontSize: 12,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                  cursor: 'pointer',
                }}>
                  View full report <ChevronRight size={12} />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); }}`}</style>
    </div>
  )
}

function Label({ children }) {
  return <div style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text3)', letterSpacing: '0.08em', marginBottom: 8, marginTop: 4 }}>{children.toUpperCase()}</div>
}

function Field({ label, children }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  )
}

function ConfigRow({ icon, label, value, color }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ color: 'var(--text3)' }}>{icon}</span>
      <span style={{ fontSize: 12, color: 'var(--text3)', flex: 1 }}>{label}</span>
      <span style={{ fontSize: 12, fontFamily: 'var(--mono)', color: color || 'var(--text)' }}>{value}</span>
    </div>
  )
}

const selectStyle = {
  width: '100%',
  background: 'var(--bg3)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  color: 'var(--text)',
  padding: '7px 10px',
  fontSize: 12,
  fontFamily: 'var(--sans)',
  outline: 'none',
}
