import { useState } from 'react'
import { Play, Loader, CheckCircle, XCircle, ChevronRight, Plus, X } from 'lucide-react'
import { api } from '../lib/api.js'

// ── Option definitions ──────────────────────────────────────────────────────

const WEAR_DURATIONS = [
  { id: '1m',   label: '1 minute',    seconds: 60 },
  { id: '5m',   label: '5 minutes',   seconds: 300 },
  { id: '15m',  label: '15 minutes',  seconds: 900 },
  { id: '30m',  label: '30 minutes',  seconds: 1800 },
  { id: '1h',   label: '1 hour',      seconds: 3600 },
  { id: '2h',   label: '2 hours',     seconds: 7200 },
  { id: '8h',   label: '8 hours',     seconds: 28800 },
  { id: '24h',  label: '24 hours',    seconds: 86400 },
  { id: '3d',   label: '3 days',      seconds: 259200 },
  { id: '7d',   label: '7 days',      seconds: 604800 },
  { id: '16d',  label: '16 days',     seconds: 1382400 },
  { id: '30d',  label: '30 days',     seconds: 2592000 },
  { id: 'custom', label: 'Custom',    seconds: null },
]

const ACTIVITY_PROFILES = [
  { id: 'resting',       label: 'Resting',                    color: '#00d4a8' },
  { id: 'walking',       label: 'Walking',                    color: '#0096ff' },
  { id: 'sleeping',      label: 'Sleeping',                   color: '#a78bfa' },
  { id: 'high_motion',   label: 'High Motion',                color: '#f5a623' },
  { id: 'mixed_daily',   label: 'Mixed Daily Activity',       color: '#ff6b81' },
  { id: 'clinical_rest', label: 'Low-Motion Clinical Setting',color: '#00d4a8' },
]

const WEAR_CONDITIONS = [
  { id: 'normal',        label: 'Normal Contact',             color: '#00d4a8' },
  { id: 'low_adhesion',  label: 'Low Adhesion',               color: '#f5a623' },
  { id: 'intermittent',  label: 'Intermittent Contact',       color: '#ff4757' },
  { id: 'perspiration',  label: 'High Perspiration',          color: '#0096ff' },
  { id: 'poor_placement',label: 'Poor Placement',             color: '#f5a623' },
  { id: 'high_motion_artifact', label: 'High Motion Artifact',color: '#ff4757' },
  { id: 'low_amplitude', label: 'Low Signal Amplitude',       color: '#a78bfa' },
  { id: 'noisy_signal',  label: 'Noisy Signal',               color: '#ff6b81' },
]

const SIGNAL_PROFILES = [
  { id: 'stable',         label: 'Stable HR/RR' },
  { id: 'hr_increase',    label: 'Gradual HR Increase' },
  { id: 'temp_increase',  label: 'Gradual Temp Increase' },
  { id: 'rr_spike',       label: 'Respiratory-Rate Spike' },
  { id: 'low_confidence', label: 'Low-Confidence Vitals' },
  { id: 'missing_vitals', label: 'Missing Vitals' },
  { id: 'out_of_range',   label: 'Out-of-Range Vitals' },
]

const NETWORK_CONDITIONS = [
  { id: 'normal_sync',      label: 'Normal Sync' },
  { id: 'gateway_offline',  label: 'Gateway Offline' },
  { id: 'wifi_outage',      label: 'Wi-Fi Outage' },
  { id: 'ble_failure',      label: 'BLE Connection Failure' },
  { id: 'delayed_upload',   label: 'Delayed Upload' },
  { id: 'duplicate_retry',  label: 'Duplicate Upload Retry' },
  { id: 'out_of_order',     label: 'Out-of-Order Arrival' },
  { id: 'auth_failure',     label: 'Authentication Failure' },
  { id: 'cloud_delay',      label: 'Cloud Ingestion Delay' },
]

const BEHAVIOR_CHECKS = [
  { id: 'timestamps_preserved',      label: 'Timestamps preserved' },
  { id: 'no_duplicates',             label: 'No duplicate samples' },
  { id: 'late_data_backfilled',      label: 'Late data backfilled correctly' },
  { id: 'stale_data_flagged',        label: 'Dashboard marks stale data' },
  { id: 'low_confidence_handled',    label: 'Low-confidence vitals handled correctly' },
  { id: 'no_false_alert_stale',      label: 'No false alert from stale data' },
  { id: 'failure_logged',            label: 'Failure logged correctly' },
]

const FIRMWARE_OPTS = [
  { v: '1.0.0', label: 'v1.0.0 — baseline' },
  { v: '1.2.0', label: 'v1.2.0 — BLE retry' },
  { v: '2.0.0', label: 'v2.0.0 — compression + CRC' },
]

// ── Component ───────────────────────────────────────────────────────────────

export default function ScenarioRunner({ onRunComplete }) {
  // Selections (multi-select where applicable)
  const [duration,       setDuration]       = useState('2h')
  const [customSeconds,  setCustomSeconds]  = useState(3600)
  const [activities,     setActivities]     = useState(['resting'])
  const [wearConds,      setWearConds]      = useState(['normal'])
  const [signalProfiles, setSignalProfiles] = useState(['stable'])
  const [networkConds,   setNetworkConds]   = useState(['normal_sync'])
  const [behaviorChecks, setBehaviorChecks] = useState(['timestamps_preserved', 'no_duplicates'])
  const [firmware,       setFirmware]       = useState('1.2.0')

  const [running, setRunning] = useState(false)
  const [result,  setResult]  = useState(null)
  const [error,   setError]   = useState(null)

  function toggle(list, setList, id, multi = true) {
    if (!multi) { setList([id]); return }
    setList(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  const durObj  = WEAR_DURATIONS.find(d => d.id === duration)
  const durSecs = duration === 'custom' ? customSeconds : durObj?.seconds

  async function handleRun() {
    setRunning(true)
    setResult(null)
    setError(null)
    try {
      const body = {
        scenario_id:      'CUSTOM',
        firmware_version: firmware,
        duration_seconds: durSecs,
        activity_profiles:  activities,
        wear_conditions:    wearConds,
        signal_profiles:    signalProfiles,
        network_conditions: networkConds,
        behavior_checks:    behaviorChecks,
        // legacy compat
        initial_battery_pct: 95,
        ambient_temp_c:      22,
        fault_profile:       networkConds.includes('wifi_outage') ? 'outage_20min'
                           : networkConds.includes('ble_failure') ? 'flaky'
                           : networkConds.includes('auth_failure') ? 'tls_failure'
                           : 'clean',
        outage_start_min: networkConds.includes('wifi_outage') ? 40 : null,
        outage_end_min:   networkConds.includes('wifi_outage') ? 60 : null,
      }
      const data = await api.runScenario(body)

      if (!data || data.status === 'error') {
        setError(data?.error || 'Unknown backend error')
        return
      }
      if (!data.validation || typeof data.validation.passed === 'undefined') {
        setError(`Unexpected response shape: ${JSON.stringify(data).slice(0, 300)}`)
        return
      }
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div style={{ padding: '28px 36px', maxWidth: 1100, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--accent)', letterSpacing: '0.12em', marginBottom: 6 }}>
          SCENARIO BUILDER
        </div>
        <h1 style={{ fontSize: 24, fontWeight: 300, letterSpacing: '-0.02em' }}>Scenario Runner</h1>
        <p style={{ color: 'var(--text2)', fontSize: 13, marginTop: 4 }}>
          Select condition ranges → simulator generates scenario → validation engine checks system invariants
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 24, alignItems: 'start' }}>

        {/* ── Left: builder ── */}
        <div style={{ display: 'grid', gap: 16 }}>

          {/* 1. Wear duration */}
          <Section title="1. Wear Duration">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {WEAR_DURATIONS.map(d => (
                <Chip key={d.id} active={duration === d.id}
                  onClick={() => setDuration(d.id)}>{d.label}</Chip>
              ))}
            </div>
            {duration === 'custom' && (
              <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 10 }}>
                <input type="number" min={60} value={customSeconds}
                  onChange={e => setCustomSeconds(+e.target.value)}
                  style={{ ...inputStyle, width: 120 }} />
                <span style={{ fontSize: 12, color: 'var(--text3)' }}>seconds
                  ({(customSeconds/3600).toFixed(1)} hrs)</span>
              </div>
            )}
          </Section>

          {/* 2. Activity profile */}
          <Section title="2. Activity Profile" hint="multi-select">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {ACTIVITY_PROFILES.map(a => (
                <Chip key={a.id} active={activities.includes(a.id)} color={a.color}
                  onClick={() => toggle(activities, setActivities, a.id)}>
                  {a.label}
                </Chip>
              ))}
            </div>
          </Section>

          {/* 3. Wear/contact condition */}
          <Section title="3. Wear / Contact Condition" hint="multi-select">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {WEAR_CONDITIONS.map(w => (
                <Chip key={w.id} active={wearConds.includes(w.id)} color={w.color}
                  onClick={() => toggle(wearConds, setWearConds, w.id)}>
                  {w.label}
                </Chip>
              ))}
            </div>
          </Section>

          {/* 4. Signal profile */}
          <Section title="4. Physiological Signal Profile" hint="multi-select">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {SIGNAL_PROFILES.map(s => (
                <Chip key={s.id} active={signalProfiles.includes(s.id)}
                  onClick={() => toggle(signalProfiles, setSignalProfiles, s.id)}>
                  {s.label}
                </Chip>
              ))}
            </div>
          </Section>

          {/* 5. Gateway/network condition */}
          <Section title="5. Gateway / Network Condition" hint="multi-select">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {NETWORK_CONDITIONS.map(n => (
                <Chip key={n.id} active={networkConds.includes(n.id)}
                  color={n.id === 'normal_sync' ? '#00d4a8' : '#f5a623'}
                  onClick={() => toggle(networkConds, setNetworkConds, n.id)}>
                  {n.label}
                </Chip>
              ))}
            </div>
          </Section>

          {/* 6. Expected behavior checks */}
          <Section title="6. Expected Behavior Checks" hint="select checks to validate">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              {BEHAVIOR_CHECKS.map(b => (
                <label key={b.id} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '8px 10px', borderRadius: 7, cursor: 'pointer',
                  background: behaviorChecks.includes(b.id) ? 'rgba(0,212,168,0.06)' : 'var(--bg3)',
                  border: `1px solid ${behaviorChecks.includes(b.id) ? 'rgba(0,212,168,0.3)' : 'var(--border)'}`,
                  fontSize: 12, color: behaviorChecks.includes(b.id) ? 'var(--text)' : 'var(--text2)',
                  transition: 'all 0.1s',
                }}>
                  <input type="checkbox" checked={behaviorChecks.includes(b.id)}
                    onChange={() => toggle(behaviorChecks, setBehaviorChecks, b.id)}
                    style={{ accentColor: 'var(--accent)', flexShrink: 0 }} />
                  {b.label}
                </label>
              ))}
            </div>
          </Section>

          {/* Firmware */}
          <Section title="Device Firmware">
            <div style={{ display: 'flex', gap: 8 }}>
              {FIRMWARE_OPTS.map(f => (
                <Chip key={f.v} active={firmware === f.v}
                  onClick={() => setFirmware(f.v)}>{f.label}</Chip>
              ))}
            </div>
          </Section>
        </div>

        {/* ── Right: summary + run ── */}
        <div style={{ position: 'sticky', top: 28 }}>
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: 20 }}>
            <div style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text3)', marginBottom: 14 }}>
              SCENARIO SUMMARY
            </div>

            <SummaryRow label="Duration"  value={duration === 'custom' ? `${(customSeconds/3600).toFixed(1)} hrs` : durObj?.label} />
            <SummaryRow label="Firmware"  value={`v${firmware}`} />
            <SummaryRow label="Activity"  value={activities.map(id => ACTIVITY_PROFILES.find(a=>a.id===id)?.label).join(', ')} />
            <SummaryRow label="Wear"      value={wearConds.map(id => WEAR_CONDITIONS.find(w=>w.id===id)?.label).join(', ')} />
            <SummaryRow label="Signal"    value={signalProfiles.map(id => SIGNAL_PROFILES.find(s=>s.id===id)?.label).join(', ')} />
            <SummaryRow label="Network"   value={networkConds.map(id => NETWORK_CONDITIONS.find(n=>n.id===id)?.label).join(', ')} />
            <SummaryRow label="Checks"    value={`${behaviorChecks.length} selected`} />

            <button onClick={handleRun} disabled={running} style={{
              width: '100%', marginTop: 18, padding: '12px 0', borderRadius: 8,
              background: running ? 'var(--bg3)' : 'var(--accent)',
              color: running ? 'var(--text2)' : '#000',
              fontWeight: 600, fontSize: 13, border: 'none',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              cursor: running ? 'not-allowed' : 'pointer', transition: 'all 0.15s',
            }}>
              {running
                ? <><Loader size={14} style={{ animation: 'spin 1s linear infinite' }} /> Simulating...</>
                : <><Play size={14} /> Run Simulation</>}
            </button>

            {error && (
              <div style={{
                marginTop: 14, padding: 12, borderRadius: 8, fontSize: 11,
                background: 'rgba(255,71,87,0.08)', border: '1px solid rgba(255,71,87,0.3)',
                color: 'var(--danger)', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                maxHeight: 180, overflowY: 'auto',
              }}>{error}</div>
            )}

            {result && result.validation && (
              <div style={{ marginTop: 14 }}>
                <div style={{
                  padding: 12, borderRadius: 8, marginBottom: 10,
                  background: result.validation.passed ? 'rgba(0,212,168,0.06)' : 'rgba(255,71,87,0.06)',
                  border: `1px solid ${result.validation.passed ? 'rgba(0,212,168,0.25)' : 'rgba(255,71,87,0.25)'}`,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    {result.validation.passed
                      ? <CheckCircle size={15} color="var(--accent)" />
                      : <XCircle size={15} color="var(--danger)" />}
                    <span style={{ fontWeight: 600, fontSize: 13,
                      color: result.validation.passed ? 'var(--accent)' : 'var(--danger)' }}>
                      {result.validation.passed ? 'ALL CHECKS PASSED' : 'CHECKS FAILED'}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text2)' }}>
                    {result.validation.pass_count}/{(result.validation.pass_count||0) + (result.validation.fail_count||0)} passed
                    · {result.total_uploaded} packets
                  </div>
                </div>

                {(result.validation.results || []).map(r => (
                  <div key={r.check_id} style={{
                    display: 'flex', alignItems: 'center', gap: 7,
                    padding: '5px 0', borderBottom: '1px solid var(--border)', fontSize: 11,
                  }}>
                    {r.passed
                      ? <CheckCircle size={11} color="var(--accent)" />
                      : <XCircle size={11} color="var(--danger)" />}
                    <span style={{ color: 'var(--text2)', flex: 1, lineHeight: 1.4 }}>
                      {r.description}
                    </span>
                  </div>
                ))}

                <button onClick={() => onRunComplete(result.run_id)} style={{
                  width: '100%', marginTop: 10, padding: '8px 0', borderRadius: 6,
                  background: 'var(--bg3)', border: '1px solid var(--border2)',
                  color: 'var(--text2)', fontSize: 12, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                }}>
                  View full report <ChevronRight size={12} />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

// ── Sub-components ──────────────────────────────────────────────────────────

function Section({ title, hint, children }) {
  return (
    <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 12 }}>
        <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)' }}>{title}</span>
        {hint && <span style={{ fontSize: 10, color: 'var(--text3)', fontFamily: 'var(--mono)' }}>{hint}</span>}
      </div>
      {children}
    </div>
  )
}

function Chip({ active, color, onClick, children }) {
  const c = color || 'var(--accent)'
  return (
    <button onClick={onClick} style={{
      padding: '5px 12px', borderRadius: 20, fontSize: 11, cursor: 'pointer',
      background: active ? c + '18' : 'var(--bg3)',
      border: `1px solid ${active ? c : 'var(--border)'}`,
      color: active ? c : 'var(--text2)',
      transition: 'all 0.12s', fontFamily: 'var(--sans)',
    }}>{children}</button>
  )
}

function SummaryRow({ label, value }) {
  return (
    <div style={{ display: 'flex', gap: 8, padding: '5px 0', borderBottom: '1px solid var(--border)', alignItems: 'flex-start' }}>
      <span style={{ fontSize: 11, color: 'var(--text3)', minWidth: 64, flexShrink: 0 }}>{label}</span>
      <span style={{ fontSize: 11, color: 'var(--text)', fontFamily: 'var(--mono)', lineHeight: 1.5 }}>{value}</span>
    </div>
  )
}

const inputStyle = {
  background: 'var(--bg3)', border: '1px solid var(--border)', borderRadius: 6,
  color: 'var(--text)', padding: '6px 10px', fontSize: 12, fontFamily: 'var(--sans)', outline: 'none',
}
