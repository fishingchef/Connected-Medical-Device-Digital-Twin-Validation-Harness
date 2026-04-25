import { useState, useEffect } from 'react'
import { ArrowLeft, CheckCircle, XCircle, Activity, Thermometer, Wind } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend, ScatterChart, Scatter
} from 'recharts'
import { api } from '../lib/api.js'

const COLORS = { hr: '#ff4757', rr: '#0096ff', temp: '#f5a623', conf: '#00d4a8' }

export default function RunDetail({ runId, onBack }) {
  const [run,     setRun]     = useState(null)
  const [packets, setPackets] = useState([])
  const [report,  setReport]  = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!runId) return
    Promise.all([api.run(runId), api.packets(runId), api.report(runId)])
      .then(([r, p, rep]) => { setRun(r); setPackets(p.packets || []); setReport(rep) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [runId])

  if (loading) return <div style={{ padding: 40, color: 'var(--text3)', fontFamily: 'var(--mono)' }}>Loading run data...</div>
  if (!run)    return <div style={{ padding: 40, color: 'var(--danger)' }}>Run not found.</div>

  const chartData = packets.map(p => ({
    min:  Math.round(p.elapsed_sec / 60),
    hr:   p.hr_bpm,
    rr:   p.rr_rpm,
    temp: p.temp_c,
    conf: +(p.signal_confidence * 100).toFixed(1),
    bat:  p.battery_pct,
    buf:  p.buffered ? 1 : 0,
    state: p.firmware_state,
  }))

  // Find outage window from buffered packets
  const bufferedMins = chartData.filter(d => d.buf).map(d => d.min)
  const outageStart  = bufferedMins.length ? Math.min(...bufferedMins) : null
  const outageEnd    = bufferedMins.length ? Math.max(...bufferedMins) : null

  const passed = report?.passed

  return (
    <div style={{ padding: '32px 40px', maxWidth: 1100, margin: '0 auto' }}>
      {/* Header */}
      <button onClick={onBack} style={{
        display: 'flex', alignItems: 'center', gap: 6,
        background: 'none', color: 'var(--text3)', fontSize: 12,
        marginBottom: 24, cursor: 'pointer', padding: 0,
      }}>
        <ArrowLeft size={13} /> Back to history
      </button>

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--accent)', letterSpacing: '0.12em', marginBottom: 6 }}>
            RUN DETAIL
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 300, letterSpacing: '-0.02em' }}>{run.scenario_id}</h1>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>{runId}</div>
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '10px 16px', borderRadius: 8,
          background: passed ? 'rgba(0,212,168,0.08)' : 'rgba(255,71,87,0.08)',
          border: `1px solid ${passed ? 'rgba(0,212,168,0.3)' : 'rgba(255,71,87,0.3)'}`,
        }}>
          {passed ? <CheckCircle size={18} color="var(--accent)" /> : <XCircle size={18} color="var(--danger)" />}
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: passed ? 'var(--accent)' : 'var(--danger)' }}>
              {passed ? 'ALL PASSED' : 'CHECKS FAILED'}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text3)' }}>
              {report?.results?.filter(r => r.passed).length}/{report?.results?.length} checks · {packets.length} packets
            </div>
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 28 }}>
        {[
          { label: 'Total packets', value: packets.length, color: 'var(--text)' },
          { label: 'Buffered (offline)', value: packets.filter(p => p.buffered).length, color: 'var(--warn)' },
          { label: 'Low confidence', value: packets.filter(p => p.signal_confidence < 0.4).length, color: 'var(--danger)' },
          { label: 'Avg HR', value: packets.length ? (packets.reduce((a,p)=>a+p.hr_bpm,0)/packets.length).toFixed(1)+' bpm' : '—', color: COLORS.hr },
        ].map(c => (
          <div key={c.label} style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 6 }}>{c.label}</div>
            <div style={{ fontSize: 22, fontWeight: 500, color: c.color, fontFamily: 'var(--mono)' }}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* HR + RR chart */}
      <ChartCard title="Heart Rate & Respiratory Rate" icon={<Activity size={14} color="var(--accent)" />}>
        {outageStart !== null && (
          <div style={{ fontSize: 11, color: 'var(--warn)', fontFamily: 'var(--mono)', marginBottom: 8 }}>
            ⚠ Gateway offline min {outageStart}–{outageEnd} — packets buffered on device
          </div>
        )}
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
            <XAxis dataKey="min" tick={{ fill: 'var(--text3)', fontSize: 10 }} label={{ value: 'min', position: 'insideRight', fill: 'var(--text3)', fontSize: 10 }} />
            <YAxis tick={{ fill: 'var(--text3)', fontSize: 10 }} />
            <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {outageStart !== null && <ReferenceLine x={outageStart} stroke="var(--warn)" strokeDasharray="3 3" label={{ value: 'outage↓', fill: 'var(--warn)', fontSize: 10 }} />}
            {outageEnd   !== null && <ReferenceLine x={outageEnd}   stroke="var(--accent)" strokeDasharray="3 3" label={{ value: 'reconnect↑', fill: 'var(--accent)', fontSize: 10 }} />}
            <Line type="monotone" dataKey="hr" stroke={COLORS.hr} dot={false} strokeWidth={1.5} name="HR (bpm)" />
            <Line type="monotone" dataKey="rr" stroke={COLORS.rr} dot={false} strokeWidth={1.5} name="RR (rpm)" />
          </LineChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Temp + confidence */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <ChartCard title="Temperature (°C)" icon={<Thermometer size={14} color={COLORS.temp} />}>
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
              <XAxis dataKey="min" tick={{ fill: 'var(--text3)', fontSize: 10 }} />
              <YAxis tick={{ fill: 'var(--text3)', fontSize: 10 }} domain={['auto','auto']} />
              <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }} />
              <Line type="monotone" dataKey="temp" stroke={COLORS.temp} dot={false} strokeWidth={1.5} name="Temp °C" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Signal Confidence (%)" icon={<Wind size={14} color={COLORS.conf} />}>
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
              <XAxis dataKey="min" tick={{ fill: 'var(--text3)', fontSize: 10 }} />
              <YAxis domain={[0, 100]} tick={{ fill: 'var(--text3)', fontSize: 10 }} />
              <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }} />
              <ReferenceLine y={40} stroke="var(--danger)" strokeDasharray="3 3" label={{ value: 'low threshold', fill: 'var(--danger)', fontSize: 10 }} />
              <Line type="monotone" dataKey="conf" stroke={COLORS.conf} dot={false} strokeWidth={1.5} name="Confidence %" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Validation checks */}
      {report && (
        <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: 20, marginBottom: 24 }}>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text3)', letterSpacing: '0.08em', marginBottom: 14 }}>
            VALIDATION REPORT
          </div>
          <div style={{ display: 'grid', gap: 8 }}>
            {report.results.map(r => (
              <div key={r.check_name} style={{
                display: 'grid',
                gridTemplateColumns: '20px 1fr auto',
                gap: 12,
                padding: '10px 14px',
                background: r.passed ? 'rgba(0,212,168,0.04)' : 'rgba(255,71,87,0.04)',
                border: `1px solid ${r.passed ? 'rgba(0,212,168,0.15)' : 'rgba(255,71,87,0.15)'}`,
                borderRadius: 8,
                alignItems: 'start',
              }}>
                <div style={{ paddingTop: 2 }}>
                  {r.passed ? <CheckCircle size={14} color="var(--accent)" /> : <XCircle size={14} color="var(--danger)" />}
                </div>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)', marginBottom: 2 }}>{r.description}</div>
                  <div style={{ fontSize: 11, color: 'var(--text3)' }}>
                    Expected: {r.expected}
                  </div>
                  <div style={{ fontSize: 11, color: r.passed ? 'var(--text3)' : 'var(--danger)' }}>
                    Actual: {r.actual}
                  </div>
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

      {/* Raw packet table (first 30) */}
      <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: 20 }}>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text3)', letterSpacing: '0.08em', marginBottom: 14 }}>
          INGESTED PACKETS (first {Math.min(packets.length, 30)})
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, fontFamily: 'var(--mono)' }}>
            <thead>
              <tr>
                {['Min','HR','RR','Temp','Conf%','Battery','Buffered','State'].map(h => (
                  <th key={h} style={{ padding: '6px 10px', textAlign: 'left', color: 'var(--text3)', borderBottom: '1px solid var(--border)', fontWeight: 400 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {packets.slice(0, 30).map((p, i) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--border)', background: p.buffered ? 'rgba(245,166,35,0.04)' : 'transparent' }}>
                  <td style={td}>{Math.round(p.elapsed_sec/60)}</td>
                  <td style={td}>{p.hr_bpm?.toFixed(1)}</td>
                  <td style={td}>{p.rr_rpm?.toFixed(1)}</td>
                  <td style={td}>{p.temp_c?.toFixed(2)}</td>
                  <td style={{ ...td, color: p.signal_confidence < 0.4 ? 'var(--danger)' : 'var(--text)' }}>
                    {(p.signal_confidence*100).toFixed(0)}
                  </td>
                  <td style={{ ...td, color: p.battery_pct < 30 ? 'var(--warn)' : 'var(--text)' }}>{p.battery_pct?.toFixed(0)}%</td>
                  <td style={{ ...td, color: p.buffered ? 'var(--warn)' : 'var(--text3)' }}>{p.buffered ? '⚠ yes' : 'no'}</td>
                  <td style={{ ...td, color: 'var(--text3)' }}>{p.firmware_state}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function ChartCard({ title, icon, children }) {
  return (
    <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: '16px 18px', marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 12 }}>
        {icon}
        <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text2)' }}>{title}</span>
      </div>
      {children}
    </div>
  )
}

const td = { padding: '6px 10px', color: 'var(--text)' }
