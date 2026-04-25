import { Activity, Clock, FlaskConical, Cpu } from 'lucide-react'

const NAV = [
  { id: 'runner',  label: 'Scenario Runner', icon: FlaskConical },
  { id: 'history', label: 'Run History',     icon: Clock },
]

export default function Sidebar({ current, onNav }) {
  return (
    <aside style={{
      width: 220,
      background: 'var(--bg2)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{ padding: '24px 20px 20px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'linear-gradient(135deg, var(--accent), var(--accent2))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Activity size={16} color="#000" strokeWidth={2.5} />
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.04em', color: 'var(--text)' }}>MEDDEVICE</div>
            <div style={{ fontSize: 10, color: 'var(--text3)', fontFamily: 'var(--mono)', marginTop: 1 }}>digital twin</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: '12px 0' }}>
        {NAV.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => onNav(id)} style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '10px 20px',
            background: current === id ? 'rgba(0,212,168,0.08)' : 'transparent',
            borderLeft: current === id ? '2px solid var(--accent)' : '2px solid transparent',
            color: current === id ? 'var(--accent)' : 'var(--text2)',
            fontSize: 13,
            fontWeight: current === id ? 500 : 400,
            transition: 'all 0.15s',
          }}>
            <Icon size={15} />
            {label}
          </button>
        ))}
      </nav>

      {/* Status */}
      <div style={{ padding: '16px 20px', borderTop: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)' }} />
          <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--mono)' }}>API connected</span>
        </div>
        <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 4 }}>v0.1.0-mvp</div>
      </div>
    </aside>
  )
}
