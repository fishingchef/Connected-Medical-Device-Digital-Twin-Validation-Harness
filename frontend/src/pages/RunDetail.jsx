import { useState, useEffect } from 'react'
import { ArrowLeft, CheckCircle, XCircle, Activity, Thermometer, Wind, Footprints } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend, BarChart, Bar
} from 'recharts'
import { api } from '../lib/api.js'

const COLORS = { hr:'#ff4757', rr:'#0096ff', temp:'#f5a623', conf:'#00d4a8', steps:'#a78bfa', cadence:'#ff6b81' }

const SLEEP_COLORS = {
  AWAKE: '#f5a623', LIGHT: '#0096ff', DEEP: '#a78bfa', REM: '#00d4a8'
}

export default function RunDetail({ runId, onBack }) {
  const [run,     setRun]     = useState(null)
  const [packets, setPackets] = useState([])
  const [report,  setReport]  = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab,     setTab]     = useState('vitals')

  useEffect(() => {
    if (!runId) return
    Promise.all([api.run(runId), api.packets(runId), api.report(runId)])
      .then(([r, p, rep]) => { setRun(r); setPackets(p.packets || []); setReport(rep) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [runId])

  if (loading) return <div style={{ padding: 40, color: 'var(--text3)', fontFamily: 'var(--mono)' }}>Loading...</div>
  if (!run)    return <div style={{ padding: 40, color: 'var(--danger)' }}>Run not found.</div>

  const chartData = packets.map(p => ({
    min:     Math.round(p.elapsed_sec / 60),
    hr:      p.hr_bpm,
    rr:      p.rr_rpm,
    temp:    p.temp_c,
    conf:    +(p.signal_confidence * 100).toFixed(1),
    bat:     p.battery_pct,
    buf:     p.buffered ? 1 : 0,
    steps:   p.step_count,
    cadence: p.gait_cadence || 0,
    sleep:   p.sleep_stage,
    activity:p.activity_label,
    alert:   p.alert_triggered ? 1 : 0,
    hour:    p.hour_of_day,
  }))

  const bufferedMins = chartData.filter(d => d.buf).map(d => d.min)
  const outageStart  = bufferedMins.length ? Math.min(...bufferedMins) : null
  const outageEnd    = bufferedMins.length ? Math.max(...bufferedMins) : null
  const passed       = report?.passed
  const totalSteps   = packets.length ? (packets[packets.length - 1].step_count || 0) : 0
  const lowConfCount = packets.filter(p => p.signal_confidence < 0.4).length
  const alertCount   = packets.filter(p => p.alert_triggered).length

  const TABS = ['vitals', 'motion', 'sleep', 'validation', 'raw']

  return (
    <div style={{ padding: '28px 36px', maxWidth: 1100, margin: '0 auto' }}>

      {/* Header */}
      <button onClick={onBack} style={{
        display: 'flex', alignItems: 'center', gap: 6, background: 'none',
        color: 'var(--text3)', fontSize: 12, marginBottom: 20, cursor: 'pointer', padding: 0, border: 'none',
      }}>
        <ArrowLeft size={13} /> Back to history
      </button>

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--accent)', letterSpacing: '0.12em', marginBottom: 4 }}>
            RUN DETAIL
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 300, letterSpacing: '-0.02em' }}>{run.scenario_id}</h1>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text3)', marginTop: 3 }}>{runId}</div>
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '10px 16px', borderRadius: 8,
          background: passed ? 'rgba(0,212,168,0.08)' : 'rgba(255,71,87,0.08)',
          border: `1px solid ${passed ? 'rgba(0,212,168,0.3)' : 'rgba(255,71,87,0.3)'}`,
        }}>
          {passed ? <CheckCircle size={18} color="var(--accent)" /> : <XCircle size={18} color="var(--danger)" />}
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: passed ? 'var(--accent)' : 'var(--danger)' }}>
              {passed ? 'ALL PASSED' : 'CHECKS FAILED'}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text3)' }}>
              {report?.results?.filter(r => r.passed).length}/{report?.results?.length} · {packets.length} packets
            </div>
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, marginBottom: 24 }}>
        {[
          { label: 'Packets',      value: packets.length,    color: 'var(--text)' },
          { label: 'Buffered',     value: packets.filter(p => p.buffered).length, color: 'var(--warn)' },
          { label: 'Low Conf',     value: lowConfCount,      color: 'var(--danger)' },
          { label: 'Device Alerts',value: alertCount,        color: alertCount > 0 ? 'var(--danger)' : 'var(--accent)' },
          { label: 'Total Steps',  value: totalSteps.toLocaleString(), color: COLORS.steps },
        ].map(c => (
          <div key={c.label} style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '12px 14px' }}>
            <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 4 }}>{c.label}</div>
            <div style={{ fontSize: 20, fontWeight: 500, color: c.color, fontFamily: 'var(--mono)' }}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16, borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: '8px 16px', fontSize: 12, cursor: 'pointer', background: 'none',
            border: 'none', borderBottom: `2px solid ${tab === t ? 'var(--accent)' : 'transparent'}`,
            color: tab === t ? 'var(--accent)' : 'var(--text3)',
            fontWeight: tab === t ? 500 : 400, marginBottom: -1,
            textTransform: 'capitalize', transition: 'all 0.1s',
          }}>{t}</button>
        ))}
      </div>

      {/* ── Vitals tab ── */}
      {tab === 'vitals' && (
        <div>
          <ChartCard title="Heart Rate & Respiratory Rate" icon={<Activity size={14} color="var(--accent)" />}>
            {outageStart !== null && (
              <div style={{ fontSize: 11, color: 'var(--warn)', fontFamily: 'var(--mono)', marginBottom: 8 }}>
                ⚠ Gateway offline min {outageStart}–{outageEnd}
              </div>
            )}
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
                <XAxis dataKey="min" tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                <YAxis tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {outageStart !== null && <ReferenceLine x={outageStart} stroke="var(--warn)" strokeDasharray="3 3" />}
                {outageEnd   !== null && <ReferenceLine x={outageEnd}   stroke="var(--accent)" strokeDasharray="3 3" />}
                <Line type="monotone" dataKey="hr" stroke={COLORS.hr} dot={false} strokeWidth={1.5} name="HR (bpm)" />
                <Line type="monotone" dataKey="rr" stroke={COLORS.rr} dot={false} strokeWidth={1.5} name="RR (rpm)" />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <ChartCard title="Temperature (°C)" icon={<Thermometer size={14} color={COLORS.temp} />}>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
                  <XAxis dataKey="min" tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                  <YAxis tick={{ fill: 'var(--text3)', fontSize: 10 }} domain={['auto', 'auto']} />
                  <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }} />
                  <Line type="monotone" dataKey="temp" stroke={COLORS.temp} dot={false} strokeWidth={1.5} name="Temp °C" />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Signal Confidence (%)" icon={<Wind size={14} color={COLORS.conf} />}>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
                  <XAxis dataKey="min" tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                  <YAxis domain={[0, 100]} tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                  <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }} />
                  <ReferenceLine y={40} stroke="var(--danger)" strokeDasharray="3 3" label={{ value: 'alert threshold', fill: 'var(--danger)', fontSize: 9 }} />
                  <Line type="monotone" dataKey="conf" stroke={COLORS.conf} dot={false} strokeWidth={1.5} name="Confidence %" />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
        </div>
      )}

      {/* ── Motion tab ── */}
      {tab === 'motion' && (
        <div>
          <ChartCard title="Gait Cadence (steps/min)" icon={<Activity size={14} color={COLORS.cadence} />}>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
                <XAxis dataKey="min" tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                <YAxis tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }} />
                <Line type="monotone" dataKey="cadence" stroke={COLORS.cadence} dot={false} strokeWidth={1.5} name="Cadence (spm)" />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Cumulative Step Count" icon={<Activity size={14} color={COLORS.steps} />}>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
                <XAxis dataKey="min" tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                <YAxis tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }} />
                <Line type="monotone" dataKey="steps" stroke={COLORS.steps} dot={false} strokeWidth={1.5} name="Steps" />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>

          {/* Activity timeline */}
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: '16px 18px' }}>
            <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text2)', marginBottom: 12 }}>Activity Timeline</div>
            <div style={{ display: 'flex', height: 32, borderRadius: 6, overflow: 'hidden', gap: 1 }}>
              {chartData.filter((_, i) => i % 3 === 0).map((d, i) => {
                const actColor =
                  d.activity?.includes('running') ? '#ff4757' :
                  d.activity?.includes('jogging') ? '#f5a623' :
                  d.activity?.includes('walking') ? '#0096ff' :
                  d.activity?.includes('climbing')? '#a78bfa' :
                  d.activity?.includes('sleep')   ? '#4d5870' :
                  'var(--bg3)'
                return (
                  <div key={i} title={`${d.min}min: ${d.activity}`} style={{
                    flex: 1, background: actColor, minWidth: 1,
                  }} />
                )
              })}
            </div>
            <div style={{ display: 'flex', gap: 12, marginTop: 10, flexWrap: 'wrap' }}>
              {[
                { label: 'Running',  color: '#ff4757' },
                { label: 'Jogging',  color: '#f5a623' },
                { label: 'Walking',  color: '#0096ff' },
                { label: 'Stairs',   color: '#a78bfa' },
                { label: 'Sleep',    color: '#4d5870' },
                { label: 'Rest',     color: 'var(--bg3)' },
              ].map(l => (
                <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10, color: 'var(--text3)' }}>
                  <div style={{ width: 8, height: 8, borderRadius: 2, background: l.color, border: '1px solid var(--border)' }} />
                  {l.label}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Sleep tab ── */}
      {tab === 'sleep' && (
        <div>
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: '16px 18px', marginBottom: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text2)', marginBottom: 12 }}>Sleep Stage Hypnogram</div>
            <div style={{ display: 'flex', height: 60, borderRadius: 6, overflow: 'hidden', gap: 1 }}>
              {chartData.filter((_, i) => i % 2 === 0).map((d, i) => (
                <div key={i} title={`${d.min}min: ${d.sleep}`}
                  style={{ flex: 1, background: SLEEP_COLORS[d.sleep] || 'var(--bg3)', minWidth: 1, opacity: 0.85 }} />
              ))}
            </div>
            <div style={{ display: 'flex', gap: 16, marginTop: 10 }}>
              {Object.entries(SLEEP_COLORS).map(([stage, color]) => {
                const count = chartData.filter(d => d.sleep === stage).length
                const pct   = packets.length ? Math.round(count / packets.length * 100) : 0
                return (
                  <div key={stage} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ width: 10, height: 10, borderRadius: 2, background: color }} />
                    <span style={{ fontSize: 11, color: 'var(--text2)' }}>{stage}</span>
                    <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--mono)' }}>{pct}%</span>
                  </div>
                )
              })}
            </div>
          </div>

          <ChartCard title="HR During Sleep Stages" icon={<Activity size={14} color={COLORS.hr} />}>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
                <XAxis dataKey="min" tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                <YAxis tick={{ fill: 'var(--text3)', fontSize: 10 }} />
                <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }} />
                <Line type="monotone" dataKey="hr" stroke={COLORS.hr} dot={false} strokeWidth={1.5} name="HR" />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      )}

      {/* ── Validation tab ── */}
      {tab === 'validation' && report && (
        <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: 20 }}>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text3)', letterSpacing: '0.08em', marginBottom: 14 }}>
            VALIDATION REPORT
          </div>
          <div style={{ display: 'grid', gap: 8 }}>
            {report.results.map(r => (
              <div key={r.check_name} style={{
                display: 'grid', gridTemplateColumns: '20px 1fr auto',
                gap: 12, padding: '10px 14px', alignItems: 'start', borderRadius: 8,
                background: r.passed ? 'rgba(0,212,168,0.04)' : 'rgba(255,71,87,0.04)',
                border: `1px solid ${r.passed ? 'rgba(0,212,168,0.15)' : 'rgba(255,71,87,0.15)'}`,
              }}>
                <div style={{ paddingTop: 2 }}>
                  {r.passed ? <CheckCircle size={14} color="var(--accent)" /> : <XCircle size={14} color="var(--danger)" />}
                </div>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)', marginBottom: 3 }}>
                    {r.check_name}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text3)' }}>Expected: {r.expected}</div>
                  <div style={{ fontSize: 11, color: r.passed ? 'var(--text3)' : 'var(--danger)' }}>Actual: {r.actual}</div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3 }}>
                  <span style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--text3)' }}>{r.requirement_id}</span>
                  <span style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--text3)' }}>{r.risk_id}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Raw tab ── */}
      {tab === 'raw' && (
        <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: 20 }}>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text3)', marginBottom: 14 }}>
            INGESTED PACKETS (first {Math.min(packets.length, 50)})
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, fontFamily: 'var(--mono)' }}>
              <thead>
                <tr>
                  {['Min','HR','RR','Temp','Conf%','Steps','Cadence','Sleep','Activity','Buffered','Alert'].map(h => (
                    <th key={h} style={{ padding: '6px 10px', textAlign: 'left', color: 'var(--text3)', borderBottom: '1px solid var(--border)', fontWeight: 400, whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {packets.slice(0, 50).map((p, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)', background: p.buffered ? 'rgba(245,166,35,0.04)' : 'transparent' }}>
                    <td style={td}>{Math.round(p.elapsed_sec/60)}</td>
                    <td style={td}>{p.hr_bpm?.toFixed(1)}</td>
                    <td style={td}>{p.rr_rpm?.toFixed(1)}</td>
                    <td style={td}>{p.temp_c?.toFixed(2)}</td>
                    <td style={{ ...td, color: p.signal_confidence < 0.4 ? 'var(--danger)' : 'var(--text)' }}>
                      {(p.signal_confidence * 100).toFixed(0)}
                    </td>
                    <td style={td}>{p.step_count ?? '—'}</td>
                    <td style={td}>{p.gait_cadence?.toFixed(0) ?? '—'}</td>
                    <td style={{ ...td, color: SLEEP_COLORS[p.sleep_stage] || 'var(--text3)' }}>{p.sleep_stage ?? '—'}</td>
                    <td style={{ ...td, color: 'var(--text3)', fontSize: 10 }}>{p.activity_label}</td>
                    <td style={{ ...td, color: p.buffered ? 'var(--warn)' : 'var(--text3)' }}>{p.buffered ? '⚠' : '—'}</td>
                    <td style={{ ...td, color: p.alert_triggered ? 'var(--danger)' : 'var(--text3)' }}>
                      {p.alert_triggered ? p.alert_type : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function ChartCard({ title, icon, children }) {
  return (
    <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: '14px 16px', marginBottom: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 12 }}>
        {icon}
        <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text2)' }}>{title}</span>
      </div>
      {children}
    </div>
  )
}

const td = { padding: '5px 10px', color: 'var(--text)' }
