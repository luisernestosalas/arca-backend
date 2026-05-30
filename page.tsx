'use client'

import { useState, useEffect } from 'react'
import { Shield, TrendingUp, TrendingDown, AlertTriangle, CheckCircle, ArrowRight, BarChart3, Plus, Bell, Search, Loader2, RefreshCw } from 'lucide-react'
import Link from 'next/link'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface PortfolioCompany {
  id: string
  name: string
  industry: string
  stage: string | null
  country_code: string | null
  created_at: string
  cert_id: string | null
  cert_level: string | null
  cert_score: number | null
  cert_p_survival: number | null
  cert_valid_until: string | null
  cert_issued_at: string | null
  score_by_dimension: { id: string; name: string; score: number }[] | null
  prev_score: number | null
}

const CERT_CONFIG: Record<string, { color: string; bg: string; border: string }> = {
  PLATINUM: { color: '#1D9E75', bg: '#1D9E7515', border: '#1D9E7540' },
  GOLD:     { color: '#EF9F27', bg: '#EF9F2715', border: '#EF9F2740' },
  SILVER:   { color: '#888780', bg: '#88878015', border: '#88878040' },
  BRONZE:   { color: '#BA7517', bg: '#BA751715', border: '#BA751740' },
  NO_CERT:  { color: '#E24B4A', bg: '#E24B4A15', border: '#E24B4A40' },
  PENDING:  { color: '#6B7280', bg: '#6B728015', border: '#6B728040' },
}

const DIMS: Record<string, string> = {
  D1: 'Liquidez', D2: 'Concentración', D3: 'Dependencia',
  D4: 'Exposición', D5: 'Legal', D6: 'Adaptativa', D7: 'Gobernanza',
}

function scoreColor(v: number) {
  return v >= 70 ? '#1D9E75' : v >= 50 ? '#EF9F27' : '#E24B4A'
}

function getTrend(company: PortfolioCompany): 'up' | 'down' | 'stable' | 'none' {
  if (!company.cert_score || !company.prev_score) return 'none'
  const diff = company.cert_score - company.prev_score
  if (diff > 2) return 'up'
  if (diff < -2) return 'down'
  return 'stable'
}

function getAlert(company: PortfolioCompany): string | null {
  if (!company.cert_level) return null
  if (company.cert_level === 'BRONZE') return 'Resiliencia básica — requiere plan de mejora'
  if (company.cert_level === 'NO_CERT') return 'Fragilidad estructural detectada — acción urgente'
  if (company.cert_score && company.prev_score && company.cert_score - company.prev_score < -5)
    return `Score cayó ${(company.cert_score - company.prev_score).toFixed(1)} pts vs certificación anterior`
  const d1 = company.score_by_dimension?.find(d => d.id === 'D1')
  if (d1 && d1.score < 40) return `D1 Liquidez crítica — score ${d1.score}`
  return null
}

export default function FondoDashboard() {
  const [portfolio, setPortfolio] = useState<PortfolioCompany[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  async function fetchPortfolio() {
    setLoading(true)
    try {
      const res = await fetch(`${API_URL}/api/v1/subjects/portfolio`)
      if (res.ok) {
        const data = await res.json()
        setPortfolio(data)
        setLastUpdated(new Date())
      }
    } catch (e) {
      console.error('Error fetching portfolio:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchPortfolio() }, [])

  const enriched = portfolio.map(p => ({ ...p, alert: getAlert(p), trend: getTrend(p) }))

  const filtered = enriched.filter(p => {
    const matchSearch = p.name.toLowerCase().includes(search.toLowerCase()) ||
      (p.industry || '').toLowerCase().includes(search.toLowerCase())
    const level = p.cert_level || 'PENDING'
    const matchFilter = filter === 'all' || level === filter ||
      (filter === 'alerts' && p.alert)
    return matchSearch && matchFilter
  })

  const selectedCompany = enriched.find(p => p.id === selected)

  const avgScore = portfolio.filter(p => p.cert_score).reduce((a, p) => a + (p.cert_score || 0), 0) /
    (portfolio.filter(p => p.cert_score).length || 1)
  const alerts = enriched.filter(p => p.alert).length
  const platinum = portfolio.filter(p => p.cert_level === 'PLATINUM').length
  const atRisk = portfolio.filter(p => p.cert_level === 'BRONZE' || p.cert_level === 'NO_CERT').length

  return (
    <main className="min-h-screen bg-[#0D1117]">
      <nav className="border-b border-[#21262D] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-[#1D9E75] rounded-lg flex items-center justify-center">
            <Shield size={16} className="text-white" />
          </div>
          <div>
            <div className="font-bold text-sm">ARCA</div>
            <div className="text-[10px] text-[#6B7280] tracking-widest">PANEL DEL FONDO</div>
          </div>
          <div className="ml-4 px-3 py-1 bg-[#161B22] border border-[#21262D] rounded-lg text-xs text-[#6B7280]">
            {portfolio.length} empresa{portfolio.length !== 1 ? 's' : ''} en portafolio
          </div>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-[#6B7280]">
              Actualizado {lastUpdated.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button onClick={fetchPortfolio} disabled={loading}
            className="p-2 border border-[#21262D] rounded-lg hover:border-[#1D9E75]/50 transition-colors">
            <RefreshCw size={14} className={`text-[#6B7280] ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button className="relative p-2 border border-[#21262D] rounded-lg hover:border-[#1D9E75]/50 transition-colors">
            <Bell size={16} className="text-[#6B7280]" />
            {alerts > 0 && (
              <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full text-[10px] flex items-center justify-center">
                {alerts}
              </span>
            )}
          </button>
          <Link href="/certificar"
            className="flex items-center gap-2 bg-[#1D9E75] hover:bg-[#0F6E56] text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
            <Plus size={14} />Solicitar ARCA
          </Link>
        </div>
      </nav>

      <div className="flex h-[calc(100vh-57px)]">
        {/* Panel izquierdo */}
        <div className="w-96 border-r border-[#21262D] flex flex-col">
          <div className="p-4 border-b border-[#21262D] grid grid-cols-4 gap-2">
            {[
              { label: 'Score promedio', value: portfolio.filter(p => p.cert_score).length > 0 ? avgScore.toFixed(1) : '—', color: scoreColor(avgScore) },
              { label: 'Alertas', value: String(alerts), color: alerts > 0 ? '#E24B4A' : '#1D9E75' },
              { label: 'Platinum', value: String(platinum), color: '#1D9E75' },
              { label: 'En riesgo', value: String(atRisk), color: atRisk > 0 ? '#EF9F27' : '#1D9E75' },
            ].map(m => (
              <div key={m.label} className="text-center">
                <div className="text-lg font-bold" style={{ color: m.color }}>{m.value}</div>
                <div className="text-[10px] text-[#6B7280] leading-tight">{m.label}</div>
              </div>
            ))}
          </div>

          <div className="p-3 border-b border-[#21262D] space-y-2">
            <div className="relative">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#6B7280]" />
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Buscar empresa..."
                className="w-full bg-[#161B22] border border-[#21262D] rounded-lg pl-8 pr-3 py-2 text-sm text-white placeholder-[#6B7280] focus:outline-none focus:border-[#1D9E75]" />
            </div>
            <div className="flex gap-1 flex-wrap">
              {['all', 'PLATINUM', 'GOLD', 'SILVER', 'BRONZE', 'alerts'].map(f => (
                <button key={f} onClick={() => setFilter(f)}
                  className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${filter === f ? 'bg-[#1D9E75] text-white' : 'bg-[#161B22] text-[#6B7280] hover:text-white border border-[#21262D]'}`}>
                  {f === 'all' ? 'Todos' : f === 'alerts' ? '⚠ Alertas' : f}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-20 text-[#6B7280]">
                <Loader2 size={20} className="animate-spin mr-2" />Cargando portafolio...
              </div>
            ) : filtered.length === 0 ? (
              <div className="text-center py-16 text-[#6B7280]">
                <Shield size={32} className="mx-auto mb-3 opacity-20" />
                <p className="text-sm">
                  {portfolio.length === 0 ? 'Sin empresas certificadas aún' : 'Sin resultados'}
                </p>
                {portfolio.length === 0 && (
                  <Link href="/certificar" className="mt-3 inline-flex items-center gap-1 text-xs text-[#1D9E75]">
                    <Plus size={12} />Certificar primera startup
                  </Link>
                )}
              </div>
            ) : (
              filtered.map(company => {
                const level = company.cert_level || 'PENDING'
                const cert = CERT_CONFIG[level] || CERT_CONFIG['PENDING']
                const isSelected = selected === company.id
                return (
                  <button key={company.id} onClick={() => setSelected(isSelected ? null : company.id)}
                    className={`w-full text-left p-4 border-b border-[#21262D] transition-all ${isSelected ? 'bg-[#161B22]' : 'hover:bg-[#161B22]/50'}`}>
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <div className="font-medium text-sm">{company.name}</div>
                        <div className="text-xs text-[#6B7280]">
                          {company.industry}{company.stage ? ` · ${company.stage}` : ''}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {company.trend === 'up' && <TrendingUp size={12} className="text-[#1D9E75]" />}
                        {company.trend === 'down' && <TrendingDown size={12} className="text-red-400" />}
                        <span className="text-sm font-bold" style={{ color: cert.color }}>
                          {company.cert_score ? company.cert_score.toFixed(1) : '—'}
                        </span>
                      </div>
                    </div>
                    <div className="h-1 bg-[#21262D] rounded-full overflow-hidden mb-2">
                      <div className="h-full rounded-full transition-all"
                        style={{ width: `${company.cert_score || 0}%`, background: cert.color }} />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] px-2 py-0.5 rounded-full font-medium"
                        style={{ background: cert.bg, color: cert.color, border: `1px solid ${cert.border}` }}>
                        {level === 'PENDING' ? 'SIN AVAL' : level}
                      </span>
                      {company.alert && (
                        <div className="flex items-center gap-1 text-[10px] text-amber-400">
                          <AlertTriangle size={10} />Alerta
                        </div>
                      )}
                    </div>
                  </button>
                )
              })
            )}
          </div>
        </div>

        {/* Panel derecho */}
        <div className="flex-1 overflow-y-auto p-6">
          {selectedCompany ? (
            <CompanyDetail company={selectedCompany} />
          ) : (
            <PortfolioOverview portfolio={enriched} />
          )}
        </div>
      </div>
    </main>
  )
}

function PortfolioOverview({ portfolio }: { portfolio: (PortfolioCompany & { alert: string | null; trend: string })[] }) {
  const levelCounts = portfolio.reduce((acc, p) => {
    const level = p.cert_level || 'PENDING'
    acc[level] = (acc[level] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div className="space-y-6 animate-fade-up">
      <div>
        <h1 className="text-2xl font-bold mb-1">Visión del portafolio</h1>
        <p className="text-[#6B7280] text-sm">Selecciona una empresa para ver el detalle</p>
      </div>

      <div className="border border-[#21262D] rounded-2xl p-5">
        <h3 className="text-sm font-semibold text-[#6B7280] uppercase tracking-widest mb-4">
          Distribución por nivel ARCA
        </h3>
        <div className="grid grid-cols-5 gap-3">
          {['PLATINUM', 'GOLD', 'SILVER', 'BRONZE', 'NO_CERT'].map(level => {
            const cert = CERT_CONFIG[level]
            const count = levelCounts[level] || 0
            const pct = portfolio.length > 0 ? (count / portfolio.length) * 100 : 0
            return (
              <div key={level} className="text-center border border-[#21262D] rounded-xl p-3"
                style={{ borderColor: count > 0 ? cert.border : undefined }}>
                <div className="text-2xl font-bold mb-1" style={{ color: cert.color }}>{count}</div>
                <div className="text-[10px] font-medium mb-2" style={{ color: cert.color }}>{level}</div>
                <div className="h-1 bg-[#21262D] rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${pct}%`, background: cert.color }} />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {portfolio.filter(p => p.alert).length > 0 && (
        <div className="border border-amber-500/30 bg-amber-500/5 rounded-2xl p-5">
          <h3 className="text-sm font-semibold text-amber-400 uppercase tracking-widest mb-4 flex items-center gap-2">
            <AlertTriangle size={14} />Alertas activas
          </h3>
          <div className="space-y-3">
            {portfolio.filter(p => p.alert).map(p => {
              const cert = CERT_CONFIG[p.cert_level || 'PENDING']
              return (
                <div key={p.id} className="flex items-center justify-between py-2 border-b border-[#21262D] last:border-0">
                  <div>
                    <div className="font-medium text-sm">{p.name}</div>
                    <div className="text-xs text-amber-400 mt-0.5">{p.alert}</div>
                  </div>
                  <span className="text-xs px-2 py-1 rounded-full font-medium"
                    style={{ background: cert.bg, color: cert.color }}>
                    {p.cert_level || 'SIN AVAL'}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {portfolio.filter(p => p.cert_score).length > 0 && (
        <div className="border border-[#21262D] rounded-2xl overflow-hidden">
          <div className="p-4 border-b border-[#21262D]">
            <h3 className="text-sm font-semibold text-[#6B7280] uppercase tracking-widest">
              Comparativa de dimensiones
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[#21262D]">
                  <th className="text-left p-3 text-[#6B7280] font-medium">Empresa</th>
                  {Object.keys(DIMS).map(d => (
                    <th key={d} className="text-center p-3 text-[#6B7280] font-medium">{d}</th>
                  ))}
                  <th className="text-center p-3 text-[#6B7280] font-medium">Global</th>
                </tr>
              </thead>
              <tbody>
                {portfolio.filter(p => p.cert_score).sort((a, b) => (b.cert_score || 0) - (a.cert_score || 0)).map((p, i) => (
                  <tr key={p.id} className={`border-b border-[#21262D] ${i % 2 === 0 ? '' : 'bg-[#161B22]/30'}`}>
                    <td className="p-3 font-medium">{p.name}</td>
                    {Object.keys(DIMS).map(d => {
                      const dim = p.score_by_dimension?.find(s => s.id === d)
                      const val = dim?.score
                      return (
                        <td key={d} className="text-center p-3 font-mono font-bold"
                          style={{ color: val !== undefined ? scoreColor(val) : '#6B7280' }}>
                          {val !== undefined ? val : '—'}
                        </td>
                      )
                    })}
                    <td className="text-center p-3 font-mono font-bold"
                      style={{ color: scoreColor(p.cert_score || 0) }}>
                      {p.cert_score?.toFixed(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {portfolio.length === 0 && (
        <div className="text-center py-20 border border-[#21262D] rounded-2xl">
          <Shield size={48} className="mx-auto mb-4 opacity-20" />
          <h2 className="text-lg font-medium mb-2">Portafolio vacío</h2>
          <p className="text-[#6B7280] text-sm mb-6">Certifica tu primera startup para empezar</p>
          <Link href="/certificar"
            className="inline-flex items-center gap-2 bg-[#1D9E75] hover:bg-[#0F6E56] text-white px-6 py-3 rounded-xl font-medium transition-colors">
            <Plus size={16} />Certificar startup
          </Link>
        </div>
      )}
    </div>
  )
}

function CompanyDetail({ company }: { company: PortfolioCompany & { alert: string | null; trend: string } }) {
  const level = company.cert_level || 'PENDING'
  const cert = CERT_CONFIG[level] || CERT_CONFIG['PENDING']
  const scoreDiff = company.cert_score && company.prev_score
    ? company.cert_score - company.prev_score : null

  return (
    <div className="space-y-5 animate-fade-up">
      <div className="border border-[#21262D] rounded-2xl p-5"
        style={{ background: cert.bg, borderColor: cert.border }}>
        <div className="flex items-start justify-between">
          <div>
            <div className="text-sm text-[#6B7280] mb-1">
              {company.industry}{company.stage ? ` · ${company.stage}` : ''}
            </div>
            <h2 className="text-xl font-bold mb-2">{company.name}</h2>
            <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-bold"
              style={{ background: `${cert.color}25`, color: cert.color }}>
              <Shield size={13} />{level === 'PENDING' ? 'SIN AVAL' : level}
            </span>
          </div>
          <div className="text-right">
            <div className="text-4xl font-bold" style={{ color: cert.color }}>
              {company.cert_score ? company.cert_score.toFixed(1) : '—'}
            </div>
            <div className="text-xs text-[#6B7280]">/ 100</div>
            {scoreDiff !== null && (
              <div className={`text-xs mt-1 flex items-center gap-1 justify-end ${scoreDiff >= 0 ? 'text-[#1D9E75]' : 'text-red-400'}`}>
                {scoreDiff >= 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
                {scoreDiff >= 0 ? '+' : ''}{scoreDiff.toFixed(1)} vs anterior
              </div>
            )}
          </div>
        </div>
      </div>

      {company.alert && (
        <div className="flex items-center gap-3 bg-amber-500/10 border border-amber-500/30 rounded-xl p-4">
          <AlertTriangle size={16} className="text-amber-400 flex-shrink-0" />
          <div>
            <div className="text-sm font-medium text-amber-400">Alerta de resiliencia</div>
            <div className="text-xs text-[#6B7280] mt-0.5">{company.alert}</div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'P(supervivencia)', value: company.cert_p_survival ? `${(company.cert_p_survival * 100).toFixed(0)}%` : '—' },
          { label: 'Válido hasta', value: company.cert_valid_until ? new Date(company.cert_valid_until).toLocaleDateString('es-CO', { month: 'short', year: 'numeric' }) : '—' },
          { label: 'Tendencia', value: company.trend === 'up' ? '↑ Mejorando' : company.trend === 'down' ? '↓ Deteriorando' : company.trend === 'stable' ? '→ Estable' : '— Sin historial' },
        ].map(m => (
          <div key={m.label} className="border border-[#21262D] rounded-xl p-3 text-center bg-[#161B22]">
            <div className="text-xs text-[#6B7280] mb-1">{m.label}</div>
            <div className="text-sm font-bold">{m.value}</div>
          </div>
        ))}
      </div>

      {company.score_by_dimension && company.score_by_dimension.length > 0 && (
        <div className="border border-[#21262D] rounded-2xl p-5">
          <h3 className="text-xs font-semibold text-[#6B7280] uppercase tracking-widest mb-4">
            Score por dimensión
          </h3>
          <div className="space-y-3">
            {company.score_by_dimension.map(d => (
              <div key={d.id} className="grid grid-cols-[90px_1fr_36px] items-center gap-3">
                <div className="text-xs text-[#6B7280]">{d.id} · {DIMS[d.id] || d.name}</div>
                <div className="h-1.5 bg-[#21262D] rounded-full overflow-hidden">
                  <div className="h-full rounded-full transition-all"
                    style={{ width: `${d.score}%`, background: scoreColor(d.score) }} />
                </div>
                <div className="text-xs font-bold font-mono text-right"
                  style={{ color: scoreColor(d.score) }}>{d.score}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Link href={`/verificar?id=${company.cert_id}`}
          className={`border border-[#21262D] hover:border-[#1D9E75]/50 rounded-xl p-3 text-sm font-medium text-left transition-all ${!company.cert_id ? 'opacity-40 pointer-events-none' : ''}`}>
          <div className="text-[#1D9E75] mb-1"><CheckCircle size={14} /></div>
          <div>Ver certificado</div>
          <div className="text-xs text-[#6B7280]">Verificar autenticidad</div>
        </Link>
        <Link href="/certificar"
          className="border border-[#21262D] hover:border-[#1D9E75]/50 rounded-xl p-3 text-sm font-medium text-left transition-all">
          <div className="text-[#1D9E75] mb-1"><ArrowRight size={14} /></div>
          <div>{company.cert_id ? 'Recertificar' : 'Solicitar ARCA'}</div>
          <div className="text-xs text-[#6B7280]">Nueva evaluación</div>
        </Link>
      </div>
    </div>
  )
}