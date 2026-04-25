import { useState } from 'react'
import { Play, Loader, CheckCircle, XCircle, ChevronRight, User, Activity } from 'lucide-react'
import { api } from '../lib/api.js'

// ── Option definitions ────────────────────────────────────────────────────────

const SUBJECT_PROFILES = [
  { id: 'healthy_adult_m',  label: 'Healthy Adult Male',    detail: '35yr, moderate fitness, HR rest 65',  color: '#00d4a8' },
  { id: 'healthy_adult_f',  label: 'Healthy Adult Female',  detail: '32yr, moderate fitness, HR rest 68',  color: '#00d4a8' },
  { id: 'athletic_m',       label: 'Athletic Male',         detail: '28yr, high fitness, HR rest 52',      color: '#0096ff' },
  { id: 'elderly_f',        label: 'Elderly Female',        detail: '72yr, sedentary, HR rest 74',         color: '#a78bfa' },
  { id: 'clinical_patient', label: 'Clinical Patient',      detail: '58yr, sedentary, elevated baseline',  color: '#f5a623' },
  { id: 'fever_patient',    label: 'Fever Patient',         detail: '34yr, HR 90, Temp 38.4°C baseline',  color: '#ff4757' },
]

const DAY_SCHEDULES = [
  { id: 'typical_day',         label: 'Typical Day',              detail: 'Sleep → work → exercise → evening (16h)',     icon: '🌅', recommended: 'healthy_adult_m' },
  { id: 'sleep_study',         label: 'Sleep Study',              detail: 'Full 8h sleep architecture with REM cycles',   icon: '😴', recommended: 'healthy_adult_m' },
  { id: 'exercise_session',    label: 'Exercise Session',         detail: 'Warmup → run → cooldown (60 min)',             icon: '🏃', recommended: 'athletic_m' },
  { id: 'clinical_monitoring', label: 'Clinical Monitoring',      detail: 'Hospital bed, minimal activity (24h)',         icon: '🏥', recommended: 'clinical_patient' },
  { id: 'fever_progression',   label: 'Fever Progression',        detail: 'Gradual fever onset over 5h',                  icon: '🌡️', recommended: 'fever_patient' },
  { id: 'high_motion_wear',    label: 'High Motion Wear Test',    detail: 'Walk → stairs → run → recovery (55 min)',      icon: '⚡', recommended: 'athletic_m' },
]

const WEAR_CONDITIONS = [
  { id: 'normal',               label: 'Normal Contact',       color: '#00d4a8' },
  { id: 'low_adhesion',         label: 'Low Adhesion',         color: '#f5a623' },
  { id: 'intermittent',         label: 'Intermittent Contact', color: '#ff4757' },
  { id: 'perspiration',         label: 'High Perspiration',    color: '#0096ff' },
  { id: 'poor_placement',       label: 'Poor Placement',       color: '#f5a623' },
  { id: 'high_motion_artifact', label: 'High Motion Artifact', color: '#ff4757' },
  { id: 'low_amplitude',        label: 'Low Signal Amplitude', color: '#a78bfa' },
  { id: 'noisy_signal',         label: 'Noisy Signal',         color: '#ff6b81' },
]

const NETWORK_CONDITIONS = [
  { id: 'normal_sync',     label: 'Normal Sync',             color: '#00d4a8' },
  { id: 'gateway_offline', label: 'Gateway Offline',         color: '#f5a623' },
  { id: 'wifi_outage',     label: 'Wi-Fi Outage',            color: '#f5a623' },
  { id: 'ble_failure',     label: 'BLE Connection Failure',  color: '#ff4757' },
  { id: 'delayed_upload',  label: 'Delayed Upload',          color: '#f5a623' },
  { id: 'duplicate_retry', label: 'Duplicate Upload Retry',  color: '#a78bfa' },
  { id: 'out_of_order',    label: 'Out-of-Order Arrival',    color: '#a78bfa' },
  { id: 'auth_failure',    label: 'Authentication Failure',  color: '#ff4757' },
  { id: 'cloud_delay',     label: 'Cloud Ingestion Delay',   color: '#f5a623' },
]

const BEHAVIOR_CHECKS = [
  { id: 'timestamps_preserved',   label: 'Timestamps preserved' },
  { id: 'no_duplicates',          label: 'No duplicate samples' },
  { id: 'late_data_backfilled',   label: 'Late data backfilled correctly' },
  { id: 'stale_data_flagged',     label: 'Dashboard marks stale data' },
  { id: 'low_confidence_handled', label: 'Low-confidence vitals handled' },
  { id: 'no_false_alert_stale',   label: 'No false alert from stale data' },
  { id: 'failure_logged',         label: 'Failure logged correctly' },
]

const FIRMWARE_OPTS = [
  { v: '1.0.0', label: 'v1.0.0 — baseline' },
  { v: '1.2.0', label: 'v1.2.0 — BLE retry' },
  { v: '2.0.0', label: 'v2.0.0 — compression + CRC' },
]

// ── Component ─────────────────────────────────────────────────────────────────

export default function ScenarioRunner({ onRunComplete }) {
  const [subject,        setSubject]        = useState('healthy_adult_m')
  const [schedule,       setSchedule]       = useState('typical_day')
  const [wearConds,      setWearConds]      = useState(['normal'])
  const [networkConds,   setNetworkConds]   = useState(['normal_sync'])
  const [behaviorChecks, setBehaviorChecks] = useState(['timestamps_preserved', 'no_duplicates'])
  const [firmware,       setFirmware]       = useState('1.2.0')
  const [running,        setRunning]        = useState(false)
  const [result,         setResult]         = useState(null)
  const [error,          setError]          = useState(null)

  function toggle(list, setList, id) {
    setList(prev => prev.includes(id)
      ? (prev.length > 1 ? prev.filter(x => x !== id) : prev)  // keep at least 1
      : [...prev, id]
    )
  }

  const subjectObj   = SUBJECT_PROFILES.find(s => s.id === subject)
  const scheduleObj  = DAY_SCHEDULES.find(s => s.id === schedule)
  const recommended  = scheduleObj?.recommended
  const mismatch     = recommended && subject !== recommended
  const recommendedLabel = SUBJECT_PROFILES.find(s => s.id === recommended)?.label
  const scheduleObj = DAY_SCHEDULES.find(s => s.id === schedule)

  async function handleRun() {
    setRunning(true)
    setResult(null)
    setError(null)
    try {
      const body = {
        scenario_id:        'CUSTOM',
        subject_profile:    subject,
        day_schedule:       schedule,
        firmware_version:   firmware,
        initial_battery_pct: 95,
        ambient_temp_c:     22,
        wear_conditions:    wearConds,
        network_conditions: networkConds,
        behavior_checks:    behaviorChecks,
        fault_profile:      networkConds.includes('wifi_outage')    ? 'outage_20min'
                          : networkConds.includes('ble_failure')    ? 'flaky'
                          : networkConds.includes('auth_failure')   ? 'tls_failure'
                          : networkConds.includes('out_of_order')   ? 'lossy'
                          : 'clean',
      }
      const data = await api.runScenario(body)

      if (!data || data.status === 'error') {
        setError(data?.error || 'Unknown backend error')
        return
      }
      if (!data.validation || typeof data.validation.passed === 'undefined') {
        setError(`Unexpected response: ${JSON.stringify(data).slice(0, 300)}`)
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
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--accent)', letterSpacing: '0.12em', marginBottom: 6 }}>
          SCENARIO BUILDER
        </div>
        <h1 style={{ fontSize: 24, fontWeight: 300, letterSpacing: '-0.02em' }}>Scenario Runner</h1>
        <p style={{ color: 'var(--text2)', fontSize: 13, marginTop: 4 }}>
          Select a subject + activity schedule, then layer wear conditions and network faults to test system behavior.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 24, alignItems: 'start' }}>

        {/* ── Left builder ── */}
        <div style={{ display: 'grid', gap: 14 }}>

          {/* 1. Subject profile */}
          <Section number="1" title="Subject Profile" hint="select one">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {SUBJECT_PROFILES.map(s => (
                <button key={s.id} onClick={() => setSubject(s.id)} style={{
                  padding: '10px 12px', borderRadius: 8, textAlign: 'left', cursor: 'pointer',
                  background: subject === s.id ? s.color + '12' : 'var(--bg3)',
                  border: `1px solid ${subject === s.id ? s.color + '60' : 'var(--border)'}`,
                  transition: 'all 0.12s',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                    <User size={11} color={subject === s.id ? s.color : 'var(--text3)'} />
                    <span style={{ fontSize: 12, fontWeight: 500, color: subject === s.id ? s.color : 'var(--text)' }}>
                      {s.label}
                    </span>
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text3)', marginLeft: 17 }}>{s.detail}</div>
                </button>
              ))}
            </div>
          </Section>

          {/* 2. Day schedule */}
          <Section number="2" title="Activity Schedule" hint="select one">
            <div style={{ display: 'grid', gap: 6 }}>
              {DAY_SCHEDULES.map(s => (
                <button key={s.id} onClick={() => setSchedule(s.id)} style={{
                  padding: '10px 14px', borderRadius: 8, textAlign: 'left', cursor: 'pointer',
                  background: schedule === s.id ? 'rgba(0,212,168,0.08)' : 'var(--bg3)',
                  border: `1px solid ${schedule === s.id ? 'var(--accent)' : 'var(--border)'}`,
                  display: 'flex', alignItems: 'center', gap: 12,
                  transition: 'all 0.12s',
                }}>
                  <span style={{ fontSize: 18, lineHeight: 1 }}>{s.icon}</span>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 500, color: schedule === s.id ? 'var(--accent)' : 'var(--text)', marginBottom: 2 }}>
                      {s.label}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text3)' }}>{s.detail}</div>
                  </div>
                  {schedule === s.id && (
                    <CheckCircle size={14} color="var(--accent)" style={{ marginLeft: 'auto', flexShrink: 0 }} />
                  )}
                </button>
              ))}
            </div>
          </Section>

          {/* Mismatch warning */}
          {mismatch && (
            <div style={{
              padding: '10px 14px', borderRadius: 8, fontSize: 12,
              background: 'rgba(245,166,35,0.08)', border: '1px solid rgba(245,166,35,0.3)',
              color: 'var(--warn)', display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <span>⚠</span>
              <span>
                <strong>{scheduleObj?.label}</strong> is designed for <strong>{recommendedLabel}</strong>.
                Your selection will still run — subject physiology will be applied to the schedule.
              </span>
            </div>
          )}

          {/* 3. Wear condition */}
          <Section number="3" title="Wear / Contact Condition" hint="multi-select">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {WEAR_CONDITIONS.map(w => (
                <Chip key={w.id} active={wearConds.includes(w.id)} color={w.color}
                  onClick={() => toggle(wearConds, setWearConds, w.id)}>
                  {w.label}
                </Chip>
              ))}
            </div>
          </Section>

          {/* 4. Network condition */}
          <Section number="4" title="Gateway / Network Condition" hint="multi-select">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {NETWORK_CONDITIONS.map(n => (
                <Chip key={n.id} active={networkConds.includes(n.id)} color={n.color}
                  onClick={() => toggle(networkConds, setNetworkConds, n.id)}>
                  {n.label}
                </Chip>
              ))}
            </div>
          </Section>

          {/* 5. Behavior checks */}
          <Section number="5" title="Expected Behavior Checks" hint="select checks to validate">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              {BEHAVIOR_CHECKS.map(b => (
                <label key={b.id} style={{
                  display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px',
                  borderRadius: 7, cursor: 'pointer', fontSize: 12,
                  background: behaviorChecks.includes(b.id) ? 'rgba(0,212,168,0.06)' : 'var(--bg3)',
                  border: `1px solid ${behaviorChecks.includes(b.id) ? 'rgba(0,212,168,0.3)' : 'var(--border)'}`,
                  color: behaviorChecks.includes(b.id) ? 'var(--text)' : 'var(--text2)',
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

          {/* 6. Firmware */}
          <Section number="6" title="Device Firmware">
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

            <SummaryRow label="Subject"  value={subjectObj?.label} />
            <SummaryRow label="Schedule" value={`${scheduleObj?.icon} ${scheduleObj?.label}`} />
            <SummaryRow label="Firmware" value={`v${firmware}`} />
            <SummaryRow label="Wear"     value={wearConds.map(id => WEAR_CONDITIONS.find(w => w.id === id)?.label).join(', ')} />
            <SummaryRow label="Network"  value={networkConds.map(id => NETWORK_CONDITIONS.find(n => n.id === id)?.label).join(', ')} />
            <SummaryRow label="Checks"   value={`${behaviorChecks.length} selected`} />

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
                maxHeight: 200, overflowY: 'auto',
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
                      : <XCircle    size={15} color="var(--danger)" />}
                    <span style={{ fontWeight: 600, fontSize: 13,
                      color: result.validation.passed ? 'var(--accent)' : 'var(--danger)' }}>
                      {result.validation.passed ? 'ALL CHECKS PASSED' : 'CHECKS FAILED'}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text2)' }}>
                    {result.validation.pass_count}/{(result.validation.pass_count || 0) + (result.validation.fail_count || 0)} passed
                    · {result.total_uploaded} packets
                  </div>
                </div>

                {(result.validation.results || []).map(r => (
                  <div key={r.check_id} style={{
                    display: 'flex', alignItems: 'flex-start', gap: 7,
                    padding: '5px 0', borderBottom: '1px solid var(--border)', fontSize: 11,
                  }}>
                    {r.passed
                      ? <CheckCircle size={11} color="var(--accent)" style={{ flexShrink: 0, marginTop: 1 }} />
                      : <XCircle    size={11} color="var(--danger)"  style={{ flexShrink: 0, marginTop: 1 }} />}
                    <span style={{ color: 'var(--text2)', lineHeight: 1.4 }}>{r.description}</span>
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

// ── Sub-components ────────────────────────────────────────────────────────────

function Section({ number, title, hint, children }) {
  return (
    <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 12 }}>
        <span style={{
          fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--accent)',
          background: 'rgba(0,212,168,0.1)', padding: '2px 7px', borderRadius: 4,
        }}>{number}</span>
        <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>{title}</span>
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
      <span style={{ fontSize: 11, color: 'var(--text3)', minWidth: 60, flexShrink: 0 }}>{label}</span>
      <span style={{ fontSize: 11, color: 'var(--text)', fontFamily: 'var(--mono)', lineHeight: 1.5 }}>{value}</span>
    </div>
  )
}
