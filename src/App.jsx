import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  Bot,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronRight,
  Clock3,
  Copy,
  Download,
  Eye,
  FileText,
  Flame,
  Gauge,
  Headphones,
  Home,
  Info,
  Lightbulb,
  LineChart,
  LoaderCircle,
  Menu,
  MoreHorizontal,
  PanelLeftClose,
  Play,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  UploadCloud,
  UsersRound,
  Video,
  WandSparkles,
  X,
  Zap,
} from 'lucide-react'
import {
  accountStats,
  api,
  apiDownload,
  bootstrapSession,
  clearSession,
  getApiUrl,
  lastAnalysis,
  loadSession,
  saveAccountStats,
  saveLastAnalysis,
} from './api'

const navItems = [
  { id: 'overview', label: 'Bosh sahifa', icon: Home },
  { id: 'analyze', label: 'Videoni tahlil qilish', icon: Video, badge: 'AI' },
  { id: 'idea', label: "G'oyani tekshirish", icon: Lightbulb },
  { id: 'plan', label: 'Kontent-reja', icon: CalendarDays },
  { id: 'competitors', label: 'Raqobatchilar', icon: UsersRound },
  { id: 'results', label: 'Natijalarim', icon: BarChart3 },
  { id: 'insights', label: 'AI tavsiyalar', icon: Sparkles },
  { id: 'admin', label: 'Admin', icon: ShieldCheck },
]

const WEEKDAYS = ['Yak', 'Du', 'Se', 'Cha', 'Pa', 'Ju', 'Sh']
const MONTHS = ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentyabr', 'oktabr', 'noyabr', 'dekabr']
const CURRENT_MONTH = new Date().toISOString().slice(0, 7)
const SCORE_COLORS = { Hook: '#8b7cff', Retention: '#eab64e', Vizual: '#33c8a3', Audio: '#58a7ff', Ulashish: '#f17e9a', Saqlash: '#ba78f2' }

function timeCode(seconds) {
  const s = Math.max(0, Math.round(seconds || 0))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

function formatViews(value) {
  if (value === null || value === undefined) return '—'
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`
  return String(value)
}

function formatDay(iso) {
  if (!iso) return null
  const date = new Date(iso)
  return { day: String(date.getDate()), week: WEEKDAYS[date.getDay()], month: MONTHS[date.getMonth()] }
}

function timelinePoints(timeline) {
  if (!timeline?.length) return null
  const last = timeline.length - 1
  return timeline
    .map((entry, index) => {
      const x = last === 0 ? 330 : (index / last) * 660
      const y = 126 - (entry.retention_probability / 100) * 114
      return `${Math.round(x)},${Math.round(y)}`
    })
    .join(' ')
}

function viewsChartData(videos) {
  const rows = videos
    .filter((video) => video.prediction?.predicted_views !== null && video.prediction?.predicted_views !== undefined)
    .slice(0, 8)
  if (!rows.length) return null
  const maxViews = Math.max(1, ...rows.map((row) => Math.max(row.prediction.predicted_views, row.prediction.actual_views ?? 0)))
  const point = (index, value) => `${rows.length === 1 ? 335 : (index / (rows.length - 1)) * 670},${196 - (value / maxViews) * 176}`
  const predicted = rows.map((row, index) => point(index, row.prediction.predicted_views)).join(' ')
  const actual = rows.map((row, index) => (row.prediction.actual_views !== null && row.prediction.actual_views !== undefined ? point(index, row.prediction.actual_views) : null)).filter(Boolean).join(' ')
  return { predicted, actual: actual || null, maxViews, rows }
}

function ScoreRing({ score = 0, size = 122, stroke = 10, label = 'Viral Score', light = false }) {
  const radius = (size - stroke) / 2
  const circumference = radius * 2 * Math.PI
  const offset = circumference - (score / 100) * circumference
  return (
    <div className={`score-ring ${light ? 'score-ring-light' : ''}`} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle className="score-ring-track" cx={size / 2} cy={size / 2} r={radius} strokeWidth={stroke} fill="none" />
        <circle
          className="score-ring-progress"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="score-ring-value">
        <strong>{score}</strong>
        <span>{label}</span>
      </div>
    </div>
  )
}

function Brand() {
  return (
    <div className="brand" aria-label="Viral Video AI">
      <span className="brand-mark"><Flame size={17} strokeWidth={2.6} /></span>
      <span>viral<span>ai</span></span>
    </div>
  )
}

function Avatar({ small = false }) {
  return <span className={`avatar ${small ? 'avatar-small' : ''}`}>MU</span>
}

function MetricCard({ icon: Icon, label, value, delta, positive = true, suffix, tone = 'violet', caption }) {
  return (
    <div className="metric-card card">
      <div className={`metric-icon metric-${tone}`}><Icon size={18} /></div>
      <div className="metric-heading">
        <span>{label}</span>
        <button className="icon-button subtle" aria-label={`${label} haqida ma'lumot`} tabIndex={-1}><Info size={15} /></button>
      </div>
      <div className="metric-bottom">
        <strong>{value}{suffix && <small>{suffix}</small>}</strong>
        {delta && (
          <span className={`delta ${positive ? 'delta-positive' : 'delta-negative'}`}>
            {positive ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
            {delta}
          </span>
        )}
      </div>
      <div className="metric-caption">{caption || 'oldingi 30 kunga nisbatan'}</div>
    </div>
  )
}

function VideoCover({ muted = false, mini = false }) {
  return (
    <div className={`video-cover ${mini ? 'video-mini' : ''} ${muted ? 'video-muted' : ''}`}>
      <div className="cover-noise" />
      <div className="cover-grid" />
      <div className="cover-chip">VIRAL AI</div>
      <div className="cover-person">
        <span className="person-hair" />
        <span className="person-face" />
        <span className="person-neck" />
        <span className="person-shirt" />
      </div>
      <div className="cover-copy">
        <span>VIDEOINGIZ</span>
        <strong>TAHLILGA<br />TAYYOR</strong>
      </div>
      {!muted && <button className="video-play" aria-label="Videoni ko‘rish" tabIndex={-1}><Play size={18} fill="currentColor" /></button>}
      <div className="cover-duration">00:00</div>
    </div>
  )
}

function EmptyState({ icon: Icon, title, text, action, onAction }) {
  return (
    <div className="empty-state card">
      <div className="empty-icon"><Icon size={26} /></div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action && <button className="button button-primary" onClick={onAction}>{action}<ArrowRight size={16} /></button>}
    </div>
  )
}

function WorkspacePicker({ workspace, plan }) {
  return (
    <button className="workspace-picker">
      <span className="workspace-logo">{(workspace || 'M')[0].toUpperCase()}</span>
      <span><strong>{workspace || 'Ish maydoni'}</strong><small>{plan ? `${plan} tarif` : 'Asosiy ish maydoni'}</small></span>
      <ChevronDown size={15} />
    </button>
  )
}

function Header({ title, description, children, onMenu }) {
  return (
    <header className="topbar">
      <button className="mobile-menu icon-button" onClick={onMenu} aria-label="Menyuni ochish"><Menu size={20} /></button>
      <div className="topbar-title">
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      <div className="topbar-actions">{children}</div>
    </header>
  )
}

function LoadingCard({ label = 'Ma\'lumotlar yuklanmoqda…' }) {
  return (
    <div className="empty-state card">
      <div className="empty-icon"><LoaderCircle size={26} className="spin" /></div>
      <h3>{label}</h3>
    </div>
  )
}

function useVideos(workspaceId) {
  const [videos, setVideos] = useState(null)
  const [error, setError] = useState('')
  const refresh = () =>
    api(`/v1/workspaces/${workspaceId}/videos`).then(setVideos).catch((cause) => {
      setVideos([])
      setError(cause.message)
    })
  useEffect(() => {
    setVideos(null)
    setError('')
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId])
  return { videos, error, refresh }
}

function Overview({ session, goTo }) {
  const { videos } = useVideos(session.workspace_id)
  const [plans, setPlans] = useState([])
  const [latestReport, setLatestReport] = useState(null)

  useEffect(() => {
    api(`/v1/workspaces/${session.workspace_id}/content-plans`)
      .then(setPlans)
      .catch(() => setPlans([]))
  }, [session.workspace_id])

  useEffect(() => {
    const latest = (videos || []).find((video) => video.analysis?.status === 'completed')
    if (!latest?.analysis?.id) {
      setLatestReport(null)
      return
    }
    let live = true
    api(`/v1/analyses/persisted/${latest.analysis.id}`)
      .then((analysis) => { if (live) setLatestReport(analysis.report || null) })
      .catch(() => { if (live) setLatestReport(null) })
    return () => { live = false }
  }, [videos])

  if (videos === null) return <LoadingCard label="Ish maydoni ma'lumotlari yuklanmoqda…" />

  const completed = videos.filter((video) => video.analysis?.status === 'completed' && video.analysis.viral_score != null)
  const latest = completed[0] || null
  const averageScore = completed.length ? Math.round(completed.reduce((sum, video) => sum + video.analysis.viral_score, 0) / completed.length) : null
  const accuracies = videos.map((video) => video.prediction?.accuracy).filter((value) => value != null)
  const averageAccuracy = accuracies.length ? Math.round(accuracies.reduce((sum, value) => sum + value, 0) / accuracies.length) : null

  const now = new Date()
  const thisMonth = videos.filter((video) => {
    const date = new Date(video.created_at)
    return date.getMonth() === now.getMonth() && date.getFullYear() === now.getFullYear()
  }).length
  const lastMonth = videos.filter((video) => {
    const date = new Date(video.created_at)
    const previous = new Date(now.getFullYear(), now.getMonth() - 1, 1)
    return date.getMonth() === previous.getMonth() && date.getFullYear() === previous.getFullYear()
  }).length
  const videoDelta = lastMonth > 0 ? `${Math.round(((thisMonth - lastMonth) / lastMonth) * 100)}%` : null
  const report = latestReport

  return (
    <>
      <div className="welcome-row">
        <div>
          <div className="eyebrow"><span className="status-dot" /> Akkauntingiz tahlil uchun tayyor</div>
          <h2>Xayrli kun, Madina <span>✦</span></h2>
          <p>Bugun videoingizni joylashdan oldin uning kuchli nuqtalarini tekshirib oling.</p>
        </div>
        <button className="button button-primary analyze-cta" onClick={() => goTo('analyze')}><Sparkles size={17} /> Yangi video tahlili</button>
      </div>

      <section className="metrics-grid">
        <MetricCard icon={Video} label="Videolar" value={videos.length} delta={videoDelta} tone="violet" caption={videoDelta ? 'oldingi oyga nisbatan' : 'shu ish maydonida'} />
        <MetricCard icon={Gauge} label="O‘rtacha Viral Score" value={averageScore ?? '—'} suffix={averageScore != null ? '/100' : ''} tone="mint" caption={`${completed.length} ta tayyor hisobot`} />
        <MetricCard icon={Check} label="Tayyor hisobotlar" value={completed.length} tone="blue" caption={`${videos.length - completed.length} ta navbatda`} />
        <MetricCard icon={TrendingUp} label="Prognoz aniqligi" value={averageAccuracy ?? '—'} suffix={averageAccuracy != null ? '%' : ''} tone="orange" caption="AI o‘rganish tsikli" />
      </section>

      <section className="dashboard-grid">
        <div className="analysis-highlight card">
          <div className="section-heading">
            <div>
              <div className="eyebrow eyebrow-violet"><Sparkles size={13} /> SO‘NGGI AI TAHLIL</div>
              <h3>{latest ? 'Hisobot tayyor' : 'Videoingiz tahlilga tayyor'}</h3>
            </div>
            {latest && <button className="text-button" onClick={() => goTo('report')}>To‘liq hisobot <ArrowRight size={15} /></button>}
          </div>
          {latest ? (
            <div className="analysis-content">
              <VideoCover mini />
              <div className="analysis-summary">
                <div className="video-meta"><span>Reels</span><i /> {Math.round(latest.duration_seconds || 0)} soniya <i /> {formatDay(latest.created_at)?.day} {formatDay(latest.created_at)?.month}</div>
                <h4>“{latest.original_name.replace(/\.[^.]+$/, '')}”</h4>
                <div className="analysis-tags"><span className="tag tag-mint"><Check size={12} /> Viral score {latest.analysis.viral_score}</span><span className="tag tag-amber">{latest.analysis.provider_mode === 'demo' ? 'Demo rejim' : 'Real model'}</span></div>
                <button className="link-button" onClick={() => goTo('report')}>Hisobotni ochish <ChevronRight size={15} /></button>
              </div>
              <ScoreRing score={latest.analysis.viral_score} size={112} stroke={9} />
            </div>
          ) : (
            <div className="analysis-summary" style={{ padding: '18px 6px' }}>
              <h4 style={{ margin: '0 0 8px' }}>Hozircha tahlil qilingan video yo‘q</h4>
              <p style={{ margin: '0 0 14px' }}>Birinchi videoni yuklang — AI hook, retention, ssenariy va audio signalini o‘lchab, sekundma-sekund hisobot beradi.</p>
              <button className="button button-primary" onClick={() => goTo('analyze')}><WandSparkles size={16} /> Tahlilni boshlash</button>
            </div>
          )}
          <div className="analysis-footnote"><Info size={14} /> Bu prognoz kafolat emas. U video, auditoriya va tarixiy natijalarga asoslangan AI bahosidir.</div>
        </div>

        <div className="performance-card card">
          <div className="section-heading">
            <div><h3>Tahlil oqimi</h3><p>Platforma holati</p></div>
            <button className="text-button" onClick={() => goTo('results')}>Natijalar <ArrowRight size={14} /></button>
          </div>
          <div className="plan-kpis">
            <span><b>{videos.length}</b> video</span><i />
            <span><b>{completed.length}</b> hisobot</span><i />
            <span><b>{plans.length}</b> kontent-reja</span><i />
            <span><b>{averageAccuracy ?? '—'}{averageAccuracy != null ? '%' : ''}</b> aniqlik</span>
          </div>
          <div className="performance-note"><span className="note-icon"><ShieldCheck size={14} /></span><span>Videolar yopiq saqlanadi, har bir hisobotda <strong>evidence belgilari</strong> bor — fakt va AI xulosasi aralashmaydi.</span></div>
        </div>
      </section>

      <section className="lower-grid">
        <div className="retention-card card">
          <div className="section-heading">
            <div><h3>AI tavsiyalar</h3><p>So‘nggi hisobotdagi eng muhim o‘zgarishlar</p></div>
            {report && <button className="text-button" onClick={() => goTo('insights')}>Barchasi <ArrowRight size={15} /></button>}
          </div>
          {report?.required_changes?.length ? (
            <div className="recommendation-list">
              {report.required_changes.slice(0, 3).map((change, index) => (
                <button className="recommendation-row" key={change} onClick={() => goTo('insights')}>
                  <span className={`recommendation-icon rec-${['violet', 'mint', 'orange'][index % 3]}`}>
                    {index % 3 === 0 ? <TrendingUp size={16} /> : index % 3 === 1 ? <Target size={16} /> : <Zap size={16} />}
                  </span>
                  <span><small>Hisobot tavsiyasi</small><strong>{change}</strong></span>
                  <ChevronRight size={16} />
                </button>
              ))}
            </div>
          ) : (
            <p style={{ padding: '8px 0' }}>{latest ? 'Hisobotda aniq o‘zgarishlar ro‘yxati mavjud bo‘ldi.' : 'Birinchi hisobotdan keyin shu yerdagi tavsiyalar paydo bo‘ladi.'}</p>
          )}
        </div>

        <div className="recommendations card">
          <div className="section-heading">
            <div><h3>Kontent rejasi</h3><p>Rejalashtirilgan videolar</p></div>
            <button className="text-button" onClick={() => goTo('plan')}>Reja <ArrowRight size={15} /></button>
          </div>
          {plans.length ? (
            <div className="recommendation-list">
              {plans.slice(0, 3).map((plan) => (
                <button className="recommendation-row" key={plan.id} onClick={() => goTo('plan')}>
                  <span className="recommendation-icon rec-violet"><CalendarDays size={16} /></span>
                  <span><small>{plan.month}</small><strong>{plan.title}</strong></span>
                  <ChevronRight size={16} />
                </button>
              ))}
            </div>
          ) : (
            <p style={{ padding: '8px 0' }}>Hali kontent-reja yo‘q. Birinchi oylik rejani tuzing — har bir kun uchun g‘oya va hook bilan.</p>
          )}
        </div>
      </section>

      <section className="plan-strip card">
        <div className="plan-strip-icon"><CalendarDays size={20} /></div>
        <div>
          <strong>{plans.length ? 'Kontent rejasi ishlayapti' : 'Bu oyning kontent rejasi hali tuzilmagan'}</strong>
          <span>{plans.length ? `${plans.length} ta reja · rejada bo‘lgan har bir video g‘oyasi hook va ssenariy bilan saqlanadi.` : 'Reja tuzish bir daqiqa — g‘oya, hook va sanani kiriting.'}</span>
        </div>
        <button className="button button-secondary" onClick={() => goTo('plan')}>Rejani ko‘rish <ArrowRight size={16} /></button>
      </section>
    </>
  )
}

function UploadPage({ session, goTo, toast }) {
  const inputRef = useRef(null)
  const [fileName, setFileName] = useState('')
  const [selectedFile, setSelectedFile] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('idle')
  const [topic, setTopic] = useState('Instagramda Reels retentionini oshirish')
  const [objective, setObjective] = useState('save')
  const [audience, setAudience] = useState('SMM mutaxassislari va kichik biznes egalari')

  const resetUpload = () => {
    setFileName('')
    setSelectedFile(null)
    setStage('idle')
    setProgress(0)
  }

  const selectFile = (file) => {
    if (!file) return
    const valid = ['video/mp4', 'video/quicktime', 'video/x-msvideo', '']
    if (file.type && !valid.includes(file.type)) {
      toast('MP4, MOV yoki AVI formatini tanlang', 'warning')
      return
    }
    setSelectedFile(file)
    setFileName(file.name)
    setStage('ready')
  }

  const loadDemoClip = async () => {
    try {
      const response = await fetch('/demo-clip.mp4')
      if (!response.ok) throw new Error('demo clip missing')
      const blob = await response.blob()
      const file = new File([blob], 'demo-clip.mp4', { type: 'video/mp4' })
      setSelectedFile(file)
      setFileName('demo-clip.mp4')
      setStage('ready')
      toast('Demo video yuklandi — AI tahlilni boshlashingiz mumkin', 'success')
    } catch {
      toast('Demo video yuklanmadi', 'warning')
    }
  }

  const startAnalysis = async () => {
    if (!selectedFile) return
    setStage('processing')
    setProgress(8)
    try {
      const stats = accountStats()
      const context = {
        title: fileName.replace(/\.[^.]+$/, ''),
        topic,
        objective,
        audience,
        language: 'uz',
        account: {
          account_type: 'expert',
          niche: 'Marketing va SMM',
          language: 'uz',
          average_views: stats.average_views || null,
          best_views: stats.best_views || null,
        },
      }
      const form = new FormData()
      form.append('file', selectedFile)
      form.append('context', JSON.stringify(context))
      const created = await api(`/v1/workspaces/${session.workspace_id}/videos/upload`, {
        method: 'POST',
        form,
        headers: { 'Idempotency-Key': crypto.randomUUID() },
      })
      saveLastAnalysis({ video_id: created.video_id, analysis_id: created.analysis_id })
      setProgress(32)

      const poll = async () => {
        const state = await api(`/v1/analyses/${created.analysis_id}/progress`)
        if (state.status === 'completed') {
          setProgress(100)
          setStage('done')
          toast('Tahlil tayyor — hisobotni ko‘rishingiz mumkin', 'success')
          return
        }
        if (state.status === 'failed' || state.status === 'cancelled') throw new Error(state.error || 'Tahlil muvaffaqiyatsiz tugadi')
        setProgress(Math.max(10, state.progress || 10))
        window.setTimeout(() => poll().catch(handleApiError), 700)
      }
      const handleApiError = (error) => {
        setStage('ready')
        setProgress(0)
        toast(error.message || 'Tahlil xatosi bilan tugadi', 'warning')
      }
      await poll()
    } catch (error) {
      setStage('ready')
      setProgress(0)
      toast(error.message || 'Video yuklanmadi', 'warning')
    }
  }

  return (
    <div className="analyze-page">
      <div className="page-hero compact-hero">
        <div className="eyebrow eyebrow-violet"><Bot size={13} /> VIDEO INTELLIGENCE</div>
        <h2>Videoni joylashdan oldin <em>ko‘rib chiqing.</em></h2>
        <p>AI hook, retention, ssenariy, vizual va audio signalini tahlil qiladi. Natija — aniq sekundlar va amaliy montaj briefi.</p>
      </div>

      <div className="upload-layout">
        <div className="upload-primary">
          <div
            className={`dropzone card ${isDragging ? 'dragging' : ''} ${fileName ? 'file-selected' : ''}`}
            onDragOver={(event) => { event.preventDefault(); setIsDragging(true) }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(event) => { event.preventDefault(); setIsDragging(false); selectFile(event.dataTransfer.files[0]) }}
          >
            <input
              ref={inputRef}
              type="file"
              accept="video/mp4,video/quicktime,video/x-msvideo"
              onChange={(event) => selectFile(event.target.files[0])}
              hidden
            />
            {!fileName ? (
              <>
                <div className="upload-orb"><UploadCloud size={27} /></div>
                <h3>Videoni shu yerga tashlang</h3>
                <p>yoki qurilmangizdan tanlang</p>
                <div className="upload-actions">
                  <button className="button button-primary" onClick={() => inputRef.current?.click()}>Faylni tanlash</button>
                  <button className="button button-tertiary" onClick={loadDemoClip}><Sparkles size={16} /> Demo bilan sinash</button>
                </div>
                <span className="upload-note">MP4, MOV yoki AVI · 500 MB gacha · 180 soniyagacha</span>
              </>
            ) : (
              <>
                <div className="selected-video-icon"><Video size={24} /></div>
                <h3>{fileName}</h3>
                <p>{Math.round((selectedFile?.size || 0) / 1024)} KB · Tahlil uchun tayyor</p>
                <div className="file-progress"><span><i style={{ width: stage === 'processing' ? `${progress}%` : '100%' }} /></span><b>{stage === 'processing' ? `${progress}%` : 'Yuklandi'}</b></div>
                {stage === 'ready' && (
                  <div className="upload-actions">
                    <button className="button button-primary" onClick={startAnalysis}><WandSparkles size={17} /> AI tahlilni boshlash</button>
                    <button className="button button-tertiary" onClick={resetUpload}>Almashtirish</button>
                  </div>
                )}
                {stage === 'processing' && (
                  <div className="processing-label"><LoaderCircle size={16} className="spin" /> {progress < 44 ? 'Video saqlanmoqda va media signal o‘lchanmoqda…' : progress < 83 ? 'AI signal va ssenariy tahlil qilinmoqda…' : 'Shaxsiy hisobot tuzilmoqda…'}</div>
                )}
                {stage === 'done' && (
                  <div className="upload-actions">
                    <button className="button button-primary" onClick={() => goTo('report')}>Hisobotni ochish <ArrowRight size={16} /></button>
                    <button className="button button-tertiary" onClick={resetUpload}>Yangi video</button>
                  </div>
                )}
              </>
            )}
          </div>

          <div className="upload-form card">
            <div className="section-heading"><div><h3>Kontekst qo‘shing <span className="optional">ixtiyoriy</span></h3><p>AI tavsiyalari aniqroq bo‘ladi</p></div></div>
            <div className="form-row">
              <label>Mavzu<input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Video nima haqida?" /></label>
              <label>Video maqsadi<select value={objective} onChange={(event) => setObjective(event.target.value)}><option value="save">Saqlash va ulashish</option><option value="reach">Ko‘rishlarni oshirish</option><option value="lead">Lead olish</option><option value="sales">Sotuv</option></select></label>
            </div>
            <label className="full-label">Kim uchun?<input value={audience} onChange={(event) => setAudience(event.target.value)} placeholder="Maqsadli auditoriya" /></label>
            <p style={{ fontSize: 12, opacity: 0.75, margin: '10px 0 0' }}><ShieldCheck size={12} style={{ verticalAlign: '-2px' }} /> Akkaunt o‘rtacha ko‘rishlari Sozlamalardagi qiymatlar bilan birga yuboriladi — prognoz shu tarixga asosan hisoblanadi.</p>
          </div>
        </div>

        <aside className="upload-aside">
          <div className="quality-card card">
            <div className="quality-top"><span className="quality-icon"><ShieldCheck size={18} /></span><div><h3>AI tahlilda nimalar bor?</h3><p>Har bir tavsiya sabab va vaqt kodi bilan beriladi.</p></div></div>
            <ul className="check-list">
              <li><span><Check size={13} /></span> 1–3 soniyalik hook bahosi</li>
              <li><span><Check size={13} /></span> Sekundma-sekund retention xaritasi</li>
              <li><span><Check size={13} /></span> Ssenariy va subtitr tahriri</li>
              <li><span><Check size={13} /></span> Montajchi uchun aniq brief</li>
              <li><span><Check size={13} /></span> Caption, CTA va cover g‘oyasi</li>
            </ul>
          </div>
          <div className="quota-card">
            <div><span>{session.workspace.plan} tarif</span><strong>{session.limits?.videos_per_month ?? '—'} tahlil/oy</strong></div>
            <div className="quota-progress"><i /></div>
            <button onClick={() => goTo('settings')}>Tarifni boshqarish <ArrowUpRight size={14} /></button>
          </div>
          <div className="privacy-line"><ShieldCheck size={15} /> Videolaringiz yopiq saqlanadi va faqat tahlil uchun ishlatiladi.</div>
        </aside>
      </div>
    </div>
  )
}

function ReportPage({ session, toast, goTo }) {
  const [state, setState] = useState({ loading: true, data: null, error: '' })
  const [tab, setTab] = useState('overview')
  const [selectedSegment, setSelectedSegment] = useState(0)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let live = true
    setState({ loading: true, data: null, error: '' })
    ;(async () => {
      try {
        const videos = await api(`/v1/workspaces/${session.workspace_id}/videos`)
        const stored = lastAnalysis()
        let video = stored?.video_id ? videos.find((item) => item.id === stored.video_id) : null
        let analysisId = stored?.analysis_id
        if (!video?.analysis?.id && (!analysisId || !video)) {
          video = videos.find((item) => item.analysis?.status === 'completed') || videos.find((item) => item.analysis?.id) || null
          analysisId = video?.analysis?.id
        }
        if (!video || !analysisId) {
          if (live) setState({ loading: false, data: null, error: 'empty' })
          return
        }
        const analysis = await api(`/v1/analyses/persisted/${analysisId}`)
        let sourceUrl = null
        try {
          const signed = await api(`/v1/videos/${video.id}/source-url`)
          // Local storage returns API-relative signed URLs; S3 returns absolute ones.
          sourceUrl = signed.url?.startsWith('http') ? signed.url : `${getApiUrl()}${signed.url}`
        } catch {
          sourceUrl = null
        }
        if (live) setState({ loading: false, data: { video, analysis, sourceUrl } })
      } catch (cause) {
        if (live) setState({ loading: false, data: null, error: cause.message })
      }
    })()
    return () => { live = false }
  }, [session.workspace_id])

  const { data } = state
  const report = data?.analysis?.report || null

  if (state.loading) return <LoadingCard label="Hisobot yuklanmoqda…" />
  if (state.error === 'empty' || !data) {
    return (
      <EmptyState
        icon={Sparkles}
        title={state.error && state.error !== 'empty' ? 'Hisobotni olib bo‘lmadi' : 'Hozircha tayyor hisobot yo‘q'}
        text={state.error && state.error !== 'empty' ? state.error : 'Videoni yuklab, AI tahlilni boshlang — hisobot shu yerda ochiladi.'}
        action={state.error && state.error !== 'empty' ? 'Qayta urinish' : 'Videoni tahlil qilish'}
        onAction={() => (state.error && state.error !== 'empty' ? window.location.reload() : goTo('analyze'))}
      />
    )
  }

  const { video, analysis } = data
  const scores = report?.scores
  const breakdown = scores ? [
    ['Hook', scores.hook_score],
    ['Retention', scores.retention_score],
    ['Vizual', scores.visual_score],
    ['Audio', scores.audio_score],
    ['Ulashish', scores.share_score],
    ['Saqlash', scores.save_score],
  ] : []
  const segments = report?.segments || []
  const timeline = report?.timeline || []
  const selected = segments[selectedSegment] || null
  const prediction = report?.prediction
  const media = report?.media

  const exportReport = async (format) => {
    try {
      await apiDownload(`/v1/videos/${video.id}/reports/${format}`, `report-${video.id}.${format}`)
      toast(`${format.toUpperCase()} hisobot yuklandi`, 'success')
    } catch (cause) {
      toast(cause.message || 'Eksport xatosi', 'warning')
    }
  }

  const copyText = (text, message) => {
    window.navigator.clipboard?.writeText(text).then(
      () => { setCopied(true); toast(message, 'success'); window.setTimeout(() => setCopied(false), 1800) },
      () => toast('Nusxalash imkoni bo‘lmadi', 'warning')
    )
  }

  if (analysis.status !== 'completed' || !report) {
    return (
      <EmptyState
        icon={Clock3}
        title={analysis.status === 'failed' ? 'Tahlil muvaffaqiyatsiz tugadi' : 'Tahlil hali davom etmoqda'}
        text={analysis.error || `Holat: ${analysis.status}`}
        action="Qayta urinish"
        onAction={async () => {
          try {
            await api(`/v1/analyses/${analysis.id}/retry`, { method: 'POST' })
            toast('Tahlil qayta navbatga olindi', 'success')
            window.location.reload()
          } catch (cause) {
            toast(cause.message || 'Retry imkoni bo‘lmadi', 'warning')
          }
        }}
      />
    )
  }

  return (
    <div className="report-page">
      <div className="report-heading">
        <div>
          <div className="eyebrow eyebrow-violet"><Sparkles size={13} /> AI VIDEO HISOBOTI {report.provider_mode === 'demo' && <span className="tag tag-amber" style={{ marginLeft: 8 }}>DEMO REJIM</span>}</div>
          <h2>{video.original_name.replace(/\.[^.]+$/, '')}</h2>
          <p>{Math.round(video.duration_seconds || 0)} soniya · {(report.language || 'uz').toUpperCase()} · {video.width ? `${video.width}×${video.height}` : '—'} · Tahlil qilingan: {formatDay(video.created_at)?.day} {formatDay(video.created_at)?.month}</p>
        </div>
        <div className="report-actions">
          <button className="button button-secondary" onClick={() => exportReport('pdf')}><Download size={16} /> PDF</button>
          <button className="button button-primary" onClick={() => exportReport('json')}><Download size={16} /> JSON</button>
        </div>
      </div>

      <div className="score-panel card">
        <div className="overall-score">
          <ScoreRing score={scores.viral_score} size={132} stroke={11} />
          <div><span className="score-label">UMUMIY BAHO</span><h3>{scores.viral_score >= 75 ? 'Yuqori potensial' : scores.viral_score >= 55 ? 'Yaxshi, lekin ishlash kerak' : 'Katta o‘sish imkoni'}</h3><p>{report.short_summary}</p></div>
        </div>
        <div className="score-breakdown">{breakdown.map(([label, value]) => <div className="score-line" key={label}><span>{label}</span><i><b style={{ width: `${value}%`, background: SCORE_COLORS[label] }} /></i><strong>{value}</strong></div>)}</div>
        <div className="score-disclaimer"><Info size={14} /> Viral Score — kafolat emas. Bu sizning video signallaringiz va mavjud kontekstga asoslangan ehtimoliy baho.</div>
      </div>

      <div className="report-tabs">
        {[
          ['overview', 'Umumiy xulosa'],
          ['timeline', 'Timeline'],
          ['script', 'Ssenariy'],
          ['editor', 'Montajchi uchun'],
        ].map(([id, label]) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{label}</button>)}
      </div>

      {tab === 'overview' && (
        <div className="report-content-grid">
          <div className="report-main">
            <div className="report-summary card">
              <div className="section-heading"><div><h3>Qisqa xulosa</h3><p>Hisobot asosida</p></div><span className="confidence-badge"><Gauge size={14} /> {scores.confidence}% ishonch</span></div>
              <p className="summary-copy">{report.short_summary}</p>
              <div className="summary-signals"><span><Check size={13} /> {report.evidence.filter((item) => item.kind === 'verified_fact').length} ta o‘lchangan fakt</span><span><Zap size={13} /> {report.required_changes.length} ta tuzatish</span></div>
            </div>
            <div className="issues-card card">
              <div className="section-heading"><div><h3>Majburiy o‘zgarishlar</h3><p>Eng katta ta’sir beradigan nuqtalar</p></div><span className="count-badge">{report.required_changes.length}</span></div>
              <ol className="issues-list">
                {report.required_changes.map((change, index) => (
                  <li key={change}>
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <div><strong>{change}</strong></div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
          <aside className="report-side">
            <div className="video-side-card card">
              {data.sourceUrl ? (
                <video src={data.sourceUrl} controls muted playsInline style={{ width: '100%', display: 'block', borderRadius: 12 }} />
              ) : (
                <VideoCover />
              )}
              <div className="video-side-meta">
                <span><Eye size={14} /> {prediction?.basis === 'account_history' ? `${formatViews(prediction.low_views)}–${formatViews(prediction.high_views)}` : 'Prognoz yetarli tarixsiz'}</span>
                <span><TrendingUp size={14} /> {scores.confidence}% ishonch</span>
              </div>
            </div>
            <div className="forecast-card">
              <div className="forecast-stars"><Sparkles size={17} /></div>
              <span>ORGANIK KO‘RISH PROGNOZI</span>
              {prediction?.basis === 'account_history' ? (
                <>
                  <strong>{formatViews(prediction.low_views)} — {formatViews(prediction.high_views)}</strong>
                  <p>O‘rtacha kutilgan: <b>{formatViews(prediction.expected_views)}</b></p>
                  <small>{prediction.note}</small>
                </>
              ) : (
                <>
                  <strong>Tarix yetarli emas</strong>
                  <small>Sozlamalardagi o‘rtacha ko‘rishlarni kiriting — keyingi hisobotda real prognoz chiqadi.</small>
                </>
              )}
            </div>
            <div className="video-side-card card" style={{ padding: 16 }}>
              <div className="section-heading"><div><h3 style={{ fontSize: 15 }}>Dalillar (evidence)</h3><p>Har bir signal qaydan olingan</p></div></div>
              <ul className="check-list">
                {report.evidence.map((item) => (
                  <li key={item.label}><span><Check size={13} /></span> <b>{item.label}:</b> {item.detail}</li>
                ))}
              </ul>
            </div>
          </aside>
        </div>
      )}

      {tab === 'timeline' && (
        <div className="timeline-report-grid">
          <div className="timeline-visual card">
            <div className="section-heading"><div><h3>Retention prognozi</h3><p>{timeline.length ? 'Har bir soniya uchun model bahosi (o‘lchangan flaglar bilan)' : 'FFmpeg mavjud emas — timeline o‘lchovlarsiz'}</p></div><span className="chart-chip"><i /> AI prognozi</span></div>
            {timeline.length ? (
              <div className="retention-chart">
                <div className="chart-grid"><span style={{ top: '8%' }} /><span style={{ top: '35%' }} /><span style={{ top: '62%' }} /><span style={{ top: '89%' }} /></div>
                <svg viewBox="0 0 660 132" preserveAspectRatio="none" aria-label="Retention prognozi">
                  <defs>
                    <linearGradient id="retentionFill" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stopColor="#8b7cff" stopOpacity="0.24" />
                      <stop offset="100%" stopColor="#8b7cff" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <polygon points={`${timelinePoints(timeline)} 660,132 0,132`} fill="url(#retentionFill)" />
                  <polyline points={timelinePoints(timeline)} fill="none" stroke="#765eff" strokeWidth="3" vectorEffect="non-scaling-stroke" />
                </svg>
                <div className="chart-axis chart-y"><span>100%</span><span>75%</span><span>50%</span><span>25%</span></div>
                <div className="chart-axis chart-x"><span>{timeCode(0)}</span><span>{timeCode((video.duration_seconds || 0) / 3)}</span><span>{timeCode(((video.duration_seconds || 0) * 2) / 3)}</span><span>{timeCode(video.duration_seconds || 0)}</span></div>
              </div>
            ) : (
              <p style={{ padding: '20px 0' }}>Bu muhitda FFmpeg o‘rnatilmagani uchun sekundma-sekund xarita bo‘sh. Production muhitida har bir soniya uchun o‘lchangan jimlik, sahna o‘zgarishi va nutq flaglari beriladi.</p>
            )}
            <div className="timeline-video-strip">
              <VideoCover muted />
              <div className="timeline-markers">
                {segments.map((item, index) => (
                  <button key={item.title} onClick={() => setSelectedSegment(index)} className={index === selectedSegment ? 'selected' : ''} style={{ left: `${(index / Math.max(1, segments.length - 1)) * 88 + 6}%` }} aria-label={item.title} />
                ))}
              </div>
            </div>
          </div>
          <div className="timeline-detail card">
            {selected ? (
              <>
                <div className={`timeline-state state-${selected.state}`}>{selected.state === 'risk' ? <TrendingDown size={16} /> : <TrendingUp size={16} />}{selected.state === 'risk' ? 'E’tibor nuqtasi' : 'Kuchli signal'}</div>
                <span className="detail-time">{timeCode(selected.start_time)}–{timeCode(selected.end_time)}</span>
                <h3>{selected.title}</h3>
                <div className="detail-score"><span>Retention ehtimoli</span><strong>{selected.retention_probability}%</strong></div>
                <div className="detail-bar"><i style={{ width: `${selected.retention_probability}%` }} /></div>
                <p>{selected.issue}</p>
                <div className="detail-action"><WandSparkles size={16} /><span><b>Tavsiya:</b> {selected.recommendation}</span></div>
              </>
            ) : (
              <p>Segmentlar yo‘q — timeline bo‘sh.</p>
            )}
          </div>
          <div className="timeline-list card">
            <div className="section-heading"><div><h3>Segmentlar</h3><p>Muammo ustiga bosing</p></div></div>
            {segments.map((item, index) => (
              <button className={`timeline-list-item ${index === selectedSegment ? 'active' : ''}`} key={item.title} onClick={() => setSelectedSegment(index)}>
                <span className={`state-dot ${item.state}`} />
                <span><small>{timeCode(item.start_time)}–{timeCode(item.end_time)}</small><strong>{item.title}</strong></span>
                <ChevronRight size={16} />
              </button>
            ))}
          </div>
        </div>
      )}

      {tab === 'script' && (
        <div className="script-grid">
          {report.improved_hooks.length > 0 && (
            <div className="script-card card">
              <div className="section-heading"><div><div className="eyebrow eyebrow-violet">QAYTA YOZILGAN HOOK</div><h3>0–3 soniya</h3></div><button className="icon-button subtle" onClick={() => copyText(report.improved_hooks[0], 'Hook nusxalandi')}><Copy size={16} /></button></div>
              <blockquote>“{report.improved_hooks[0]}”</blockquote>
              <div className="script-tags"><span>Hook</span><span>{report.improved_hooks.length} ta variant hisobotda</span></div>
            </div>
          )}
          {report.improved_cta && (
            <div className="script-card card">
              <div className="section-heading"><div><div className="eyebrow eyebrow-mint">YANGI CTA</div><h3>Oxirgi soniyalar</h3></div><button className="icon-button subtle" onClick={() => copyText(report.improved_cta, 'CTA nusxalandi')}><Copy size={16} /></button></div>
              <blockquote>“{report.improved_cta}”</blockquote>
              <div className="script-tags"><span>CTA</span><span>Bitta aniq harakat</span></div>
            </div>
          )}
          <div className="full-script card">
            <div className="section-heading"><div><h3>Yaxshilangan ssenariy</h3><p>{report.improved_script.length ? 'Har bir qator — tayyor subtitr/og‘zaki matn' : 'Demo rejimda ssenariy bosqichlari'}</p></div><button className="button button-secondary" onClick={() => copyText(report.improved_script.join('\n'), 'Ssenariy nusxalandi')}>{copied ? <Check size={16} /> : <Copy size={16} />}{copied ? 'Nusxalandi' : 'Nusxalash'}</button></div>
            <div className="script-lines">
              {report.improved_script.length ? (
                report.improved_script.map((line) => <p key={line}><span>●</span><b>{line}</b></p>)
              ) : (
                <p>Hisobotda ssenariy matni yo‘q.</p>
              )}
            </div>
          </div>
          {report.improved_hooks.length > 1 && (
            <div className="full-script card">
              <div className="section-heading"><div><h3>Boshqa hook variantlari</h3><p>Har birini A/B sinab ko‘ring</p></div></div>
              {report.improved_hooks.slice(1).map((hook, index) => (
                <button className="hook-row" key={hook} onClick={() => copyText(hook, 'Hook nusxalandi')}><span>{String(index + 2).padStart(2, '0')}</span><strong>{hook}</strong><Copy size={15} /></button>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'editor' && (
        <div className="editor-layout">
          <div className="editor-brief card">
            <div className="section-heading"><div><div className="eyebrow eyebrow-violet">MONTAJCHI UCHUN TAYYOR</div><h3>Texnik topshiriq</h3><p>{report.editor_brief.length} ta o‘zgarish</p></div><button className="button button-secondary" onClick={() => copyText(report.editor_brief.join('\n'), 'Montajchi brieﬁ nusxalandi')}><Copy size={16} /> Briefni nusxalash</button></div>
            <div className="editor-items">
              {report.editor_brief.map((line, index) => {
                const match = line.match(/^(\d{1,2}:\d{2}(?:–|-)\d{1,2}:\d{2})\s*[:.]?\s*(.*)$/)
                return (
                  <div className="editor-item" key={line}>
                    <span className="editor-index">{String(index + 1).padStart(2, '0')}</span>
                    <div>
                      <div className="editor-item-heading"><small>{match ? match[1] : 'Bosqich'}</small><i>{match ? match[2].slice(0, 40) : line.slice(0, 48)}</i></div>
                      <p>{match ? match[2] : line}</p>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
          <aside className="editor-side">
            <div className="cover-recommendation card">
              <span className="label-with-icon"><FileText size={15} /> MEDIA O‘LCHOVlARI</span>
              <p>
                {media?.analysed ? (
                  <>
                    <b>{Math.round(media.duration_seconds || 0)}s</b> · {media.width}×{media.height} · {media.aspect_ratio || '—'} · {media.video_codec || '—'}
                    <br />Sahna o‘zgarishlari: <b>{media.scene_change_count}</b> · jimlik: <b>{media.silence_seconds.toFixed(1)}s</b>
                    <br />Thumbnail nomzodlar: <b>{media.thumbnails.length}</b>
                  </>
                ) : (
                  'Bu muhitda FFmpeg o‘rnatilmagani uchun media o‘lchovlari olinmadi. Production muhitida bu yerdagi raqamlar haqiqiy FFprobe/FFmpeg o‘lchovidir.'
                )}
              </p>
            </div>
            <div className="audio-recommendation">
              <Headphones size={18} />
              <div>
                <span>AUDIO SIGNAL</span>
                <strong>{media?.analysed ? (media.has_audio ? `Nutq ulushi: ${media.speech_ratio != null ? `${Math.round(media.speech_ratio * 100)}%` : '—'} · ${media.audio_codec || 'audio bor'}` : 'Audio oqim yo‘q') : 'Audio o‘lchovlari mavjud emas'}</strong>
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}

function IdeaPage({ toast }) {
  const [idea, setIdea] = useState('2026-yilda O‘zbekistonda qaysi reklama kanallari ishlaydi?')
  const [checked, setChecked] = useState(false)
  const [isChecking, setIsChecking] = useState(false)
  const [format, setFormat] = useState('Ekspert Reels')
  const [objective, setObjective] = useState('save')
  const [apiResult, setApiResult] = useState(null)

  const validateIdea = async () => {
    if (idea.trim().length < 8) {
      toast('G‘oyani biroz batafsilroq yozing', 'warning')
      return
    }
    setIsChecking(true)
    try {
      const response = await api('/v1/ideas/check', {
        method: 'POST',
        body: { idea, objective, format: format.toLowerCase().replaceAll(' ', '_') },
      })
      setApiResult(response)
      setChecked(true)
      toast('G‘oya API orqali tahlil qilindi', 'success')
    } catch (error) {
      setChecked(false)
      setApiResult(null)
      toast(error.message || 'G‘oyani tekshirib bo‘lmadi', 'warning')
    } finally {
      setIsChecking(false)
    }
  }

  return (
    <div className="idea-page">
      <div className="page-hero">
        <div className="eyebrow eyebrow-violet"><Lightbulb size={13} /> IDEA VALIDATOR</div>
        <h2>G‘oyangizni video olishdan <em>oldin sinab ko‘ring.</em></h2>
        <p>Auditoriya mosligi, yangilik, raqobat, share/save signallari va kuchli formatni bir joyda aniqlang.</p>
      </div>
      <div className="idea-grid">
        <div className="idea-form card">
          <label className="idea-textarea-label">Video g‘oyasi
            <textarea value={idea} onChange={(event) => { setIdea(event.target.value); setChecked(false) }} placeholder="Masalan: 2026-yilda O‘zbekistonda qaysi reklama kanallari ishlaydi?" />
          </label>
          <div className="idea-options">
            <label>Format<select value={format} onChange={(event) => { setFormat(event.target.value); setChecked(false) }}><option>Ekspert Reels</option><option>Storytelling</option><option>Case study</option><option>Trend format</option></select></label>
            <label>Maqsad<select value={objective} onChange={(event) => { setObjective(event.target.value); setChecked(false) }}><option value="save">Saqlash</option><option value="reach">Reach</option><option value="lead">Lead</option></select></label>
          </div>
          <button className="button button-primary idea-submit" onClick={validateIdea} disabled={isChecking}>
            {isChecking ? <LoaderCircle size={17} className="spin" /> : <WandSparkles size={17} />}
            {isChecking ? 'AI tekshirmoqda…' : 'G‘oyani tekshirish'}
          </button>
          <div className="fact-note"><ShieldCheck size={15} /> Fakt talab qiladigan joylar alohida belgilanadi. AI xulosasi fakt o‘rnini bosmaydi.</div>
        </div>
        {checked && apiResult ? <IdeaResult result={apiResult} toast={toast} /> : (
          <EmptyState icon={Search} title="Tahlilni yangilang" text="G‘oyadagi o‘zgarishlar uchun qaytadan AI xulosasini oling." action="G‘oyani tekshirish" onAction={validateIdea} />
        )}
      </div>
      {checked && apiResult && (
        <div className="idea-bottom">
          <div className="hooks-card card">
            <div className="section-heading"><div><h3>Siz uchun hooklar</h3><p>Tanlangan format: {format}</p></div><button className="text-button" onClick={validateIdea}>Yana yaratish <RefreshCw size={14} /></button></div>
            {(apiResult.hooks || []).map((hook, index) => (
              <button className="hook-row" key={hook} onClick={() => window.navigator.clipboard?.writeText(hook).then(() => toast(`Hook ${index + 1} nusxalandi`, 'success'))}>
                <span>{String(index + 1).padStart(2, '0')}</span><strong>{hook}</strong><Copy size={15} />
              </button>
            ))}
          </div>
          <div className="idea-structures card">
            <div className="section-heading"><div><h3>Tekshiruv signallari</h3><p>Optimal davomiylik va ehtiyot bo‘lish kerak bo‘lgan faktlar</p></div></div>
            <div className="structure-row"><span className="structure-number n1">1</span><div><strong>Optimal davomiylik</strong><p>{apiResult.optimal_duration_seconds[0]}–{apiResult.optimal_duration_seconds[1]} soniya</p></div></div>
            <div className="structure-row"><span className="structure-number n2">2</span><div><strong>Fakt bilan tasdiqlash kerak</strong><p>{(apiResult.fact_check_needed || []).join(' · ') || 'Fakt talab qilmaydi'}</p></div></div>
            <div className="structure-row"><span className="structure-number n3">3</span><div><strong>Eslatma</strong><p>{apiResult.disclaimer}</p></div></div>
          </div>
        </div>
      )}
    </div>
  )
}

function IdeaResult({ result, toast }) {
  const score = result?.potential_score || 0
  const audienceFit = result?.audience_fit || 0
  const savePotential = result?.save_potential || 0
  const novelty = result?.novelty || 0
  const competition = result?.competition === 'low' ? 'Past' : result?.competition === 'high' ? 'Yuqori' : 'O‘rta'
  return (
    <div className="idea-result card">
      <div className="idea-result-top">
        <div><div className="eyebrow eyebrow-mint"><Check size={13} /> TAHLIL TAYYOR</div><h3>{score >= 80 ? 'Yuqori potensial' : 'Sinab ko‘rishga arziydi'}</h3><p>Backend scoring va idea signaliga ko‘ra</p></div>
        <ScoreRing score={score} label="Idea Score" size={108} stroke={9} />
      </div>
      <div className="idea-ratings">
        <div><span>Auditoriya mosligi</span><b>{audienceFit}</b><i><em style={{ width: `${audienceFit}%` }} /></i></div>
        <div><span>Save potensiali</span><b>{savePotential}</b><i><em style={{ width: `${savePotential}%` }} /></i></div>
        <div><span>Yangilik</span><b>{novelty}</b><i><em style={{ width: `${novelty}%` }} /></i></div>
        <div><span>Raqobat</span><b>{competition}</b><i><em style={{ width: `${competition === 'Yuqori' ? 80 : competition === 'Past' ? 35 : 58}%` }} /></i></div>
      </div>
      <div className="idea-takeaway"><Sparkles size={16} /><p><b>AI xulosasi:</b> {result?.improved_angle}</p></div>
      <button className="link-button" onClick={() => toast('Batafsil tavsiyalar ochildi', 'info')}>Batafsil tavsiyalar <ArrowRight size={15} /></button>
    </div>
  )
}

function PlanPage({ session, toast }) {
  const [plans, setPlans] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [creating, setCreating] = useState(false)
  const [newPlan, setNewPlan] = useState({ month: CURRENT_MONTH, title: '' })
  const [newItem, setNewItem] = useState({ topic: '', hook: '', scheduled_for: '' })
  const [newScript, setNewScript] = useState('')

  const loadPlans = () =>
    api(`/v1/workspaces/${session.workspace_id}/content-plans`)
      .then((list) => {
        setPlans(list)
        const next = selectedId && list.some((plan) => plan.id === selectedId) ? selectedId : (list[0]?.id ?? null)
        setSelectedId(next)
        setDetail(null)
      })
      .catch((cause) => { setPlans([]); toast(cause.message, 'warning') })

  useEffect(() => {
    setPlans(null)
    loadPlans()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.workspace_id])

  useEffect(() => {
    if (!selectedId) return
    api(`/v1/content-plans/${selectedId}`)
      .then(setDetail)
      .catch((cause) => toast(cause.message, 'warning'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId])

  const createPlan = async () => {
    if (!newPlan.title.trim()) { toast('Reja nomini kiriting', 'warning'); return }
    setCreating(true)
    try {
      const created = await api(`/v1/workspaces/${session.workspace_id}/content-plans`, { method: 'POST', body: { month: newPlan.month, title: newPlan.title.trim() } })
      setNewPlan({ month: CURRENT_MONTH, title: '' })
      toast('Kontent-reja yaratildi', 'success')
      await loadPlans()
      setSelectedId(created.id)
    } catch (cause) {
      toast(cause.message || 'Reja yaratilmadi', 'warning')
    } finally {
      setCreating(false)
    }
  }

  const addItem = async () => {
    if (!selectedId || !newItem.topic.trim()) { toast('Mavzuni kiriting', 'warning'); return }
    try {
      await api(`/v1/content-plans/${selectedId}/items`, {
        method: 'POST',
        body: {
          topic: newItem.topic.trim(),
          hook: newItem.hook.trim() || null,
          scheduled_for: newItem.scheduled_for ? `${newItem.scheduled_for}T19:30:00` : null,
        },
      })
      setNewItem({ topic: '', hook: '', scheduled_for: '' })
      toast('Rejaga qo‘shildi', 'success')
      await api(`/v1/content-plans/${selectedId}`).then(setDetail)
    } catch (cause) {
      toast(cause.message || 'Element qo‘shilmadi', 'warning')
    }
  }

  const updateScript = async (item) => {
    if (!newScript.trim()) return
    try {
      await api(`/v1/content-plans/${selectedId}/items/${item.id}`, { method: 'PATCH', body: { script: newScript.trim() } })
      setNewScript('')
      toast('Ssenariy saqlandi', 'success')
      await api(`/v1/content-plans/${selectedId}`).then(setDetail)
    } catch (cause) {
      toast(cause.message || 'Saqlanmadi', 'warning')
    }
  }

  return (
    <div className="plan-page">
      <div className="page-title-row">
        <div>
          <div className="eyebrow eyebrow-violet"><CalendarDays size={13} /> KONTENT STRATEGIYASI</div>
          <h2>Kontent-reja</h2>
          <p>{session.workspace.name} · Har bir element g‘oya, hook va sana bilan saqlanadi</p>
        </div>
        <div className="report-actions">
          <button className="button button-secondary" onClick={() => setCreating(!creating)}><Plus size={17} /> Yangi reja</button>
        </div>
      </div>

      {creating && (
        <div className="card" style={{ marginBottom: 16, padding: 16 }}>
          <div className="form-row">
            <label>Oy<input type="month" value={newPlan.month} onChange={(event) => setNewPlan({ ...newPlan, month: event.target.value })} /></label>
            <label>Reja nomi<input value={newPlan.title} onChange={(event) => setNewPlan({ ...newPlan, title: event.target.value })} placeholder="Masalan: Oktabr — ekspertlik seriyasi" /></label>
          </div>
          <div className="upload-actions"><button className="button button-primary" onClick={createPlan} disabled={creating}>Yaratish</button><button className="button button-tertiary" onClick={() => setCreating(false)}>Bekor qilish</button></div>
        </div>
      )}

      {plans === null ? (
        <LoadingCard label="Rejalar yuklanmoqda…" />
      ) : plans.length === 0 ? (
        <EmptyState icon={CalendarDays} title="Hali kontent-reja yo‘q" text="Birinchi oylik rejani yarating — g‘oya, hook va sanani saqlaymiz." action="Reja yaratish" onAction={() => setCreating(true)} />
      ) : (
        <>
          <div className="plan-kpis">
            <span><b>{plans.length}</b> reja</span><i />
            <span><b>{detail?.items?.length ?? 0}</b> element tanlangan rejada</span><i />
            <span><b>{detail?.items?.filter((item) => item.hook).length ?? 0}</b> hook bilan</span>
          </div>
          <div className="plan-layout">
            <div className="calendar-card card">
              <div className="calendar-head">
                <div>
                  <h3>{detail ? `${detail.month} · ${detail.title}` : 'Reja tanlang'}</h3>
                  <p>{plans.map((plan, index) => <button key={plan.id} className={plan.id === selectedId ? 'active' : ''} style={{ background: 'none', border: 'none', cursor: 'pointer', color: plan.id === selectedId ? '#8b7cff' : 'inherit', fontWeight: plan.id === selectedId ? 700 : 400, marginRight: 8 }} onClick={() => setSelectedId(plan.id)}>{plan.month}{index < plans.length - 1 ? ' · ' : ''}</button>)}</p>
                </div>
              </div>
              <div className="calendar-days">
                {(detail?.items || []).map((item, index) => {
                  const day = formatDay(item.scheduled_for)
                  return (
                    <button key={item.id} className={`calendar-entry ${index === 0 ? 'active' : ''}`}>
                      <div className="calendar-date"><span>{day ? day.week : '—'}</span><b>{day ? day.day : '•'}</b></div>
                      <div className={`calendar-type ${['violet', 'mint', 'orange', 'blue'][index % 4]}`}>{item.status === 'idea' ? 'G‘oya' : item.status}</div>
                      <strong>{item.topic}</strong>
                      <span className="calendar-time"><Clock3 size={13} /> {item.hook ? 'hook tayyor' : 'hook kiritilishi kerak'}</span>
                    </button>
                  )
                })}
                {!detail?.items?.length && <p style={{ padding: '12px 0' }}>Bu rejada hali elementlar yo‘q — pastdan qo‘shing.</p>}
              </div>
              <div className="card" style={{ marginTop: 12, padding: 14, background: 'rgba(139,124,255,0.05)' }}>
                <label style={{ display: 'block', marginBottom: 8 }}><b>Mavzu</b><input value={newItem.topic} onChange={(event) => setNewItem({ ...newItem, topic: event.target.value })} placeholder="Video g‘oyasi" style={{ marginTop: 4 }} /></label>
                <div className="form-row">
                  <label>Hook<input value={newItem.hook} onChange={(event) => setNewItem({ ...newItem, hook: event.target.value })} placeholder="Birinchi 3 soniya" /></label>
                  <label>Sana<input type="date" value={newItem.scheduled_for} onChange={(event) => setNewItem({ ...newItem, scheduled_for: event.target.value })} /></label>
                </div>
                <button className="button button-primary" onClick={addItem}><Plus size={16} /> Qo‘shish</button>
              </div>
            </div>
            <div className="plan-detail card">
              {(detail?.items || []).map((item, index) => (
                <div key={item.id} style={{ borderBottom: index < detail.items.length - 1 ? '1px solid rgba(255,255,255,0.06)' : 'none' }}>
                  <div className="detail-color-bar" />
                  <div className="section-heading"><div><span className={`type-pill ${['violet', 'mint', 'orange', 'blue'][index % 4]}`}>{item.status}</span><h3>{item.topic}</h3><p>{formatDay(item.scheduled_for) ? `${formatDay(item.scheduled_for).day} ${formatDay(item.scheduled_for).month} · 19:30` : 'Sana belgilanmagan'} · Reels</p></div><button className="icon-button subtle"><MoreHorizontal size={19} /></button></div>
                  <div className="plan-detail-block"><small>HOOK</small><p>{item.hook ? `“${item.hook}”` : '—'}</p></div>
                  <div className="plan-detail-block"><small>SSENARIY</small><p>{item.script || '—'}</p></div>
                  {!item.script && (
                    <div style={{ display: 'flex', gap: 8, margin: '10px 0' }}>
                      <input value={newScript} onChange={(event) => setNewScript(event.target.value)} placeholder="Ssenariy matnini kiriting…" />
                      <button className="button button-secondary" onClick={() => updateScript(item)}><WandSparkles size={15} /> Saqlash</button>
                    </div>
                  )}
                  <div className="plan-detail-meta"><span><Target size={14} /> {item.hook ? 'Hook tayyor' : 'Hook kiriting'}</span><span><Flame size={14} /> {item.script ? 'Ssenariy bor' : 'Ssenariy yo‘q'}</span></div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function CompetitorsPage({ session, toast }) {
  const [competitors, setCompetitors] = useState(null)
  const [form, setForm] = useState({ username: '', notes: '' })

  const load = () =>
    api(`/v1/workspaces/${session.workspace_id}/competitors`).then(setCompetitors).catch((cause) => { setCompetitors([]); toast(cause.message, 'warning') })

  useEffect(() => {
    setCompetitors(null)
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.workspace_id])

  const add = async () => {
    if (!form.username.trim()) { toast('Akkaunt nomini kiriting', 'warning'); return }
    try {
      await api(`/v1/workspaces/${session.workspace_id}/competitors`, {
        method: 'POST',
        body: { username: form.username.trim(), notes: form.notes.trim() || null },
      })
      setForm({ username: '', notes: '' })
      toast('Raqobatchi qo‘shildi', 'success')
      await load()
    } catch (cause) {
      toast(cause.message || 'Qo‘shilmadi', 'warning')
    }
  }

  return (
    <div className="competitors-page">
      <div className="page-title-row">
        <div>
          <div className="eyebrow eyebrow-violet"><UsersRound size={13} /> MARKET SIGNALS</div>
          <h2>Raqobatchilar tahlili</h2>
          <p>{competitors?.length ?? 0} ta kuzatilayotgan akkaunt · limit: {session.limits?.competitors ?? '—'}/oy tarifda</p>
        </div>
      </div>

      <div className="competitor-hero card">
        <div className="competitor-hero-copy">
          <span className="eyebrow eyebrow-mint"><Plus size={13} /> YANGI RAQOBATCHI</span>
          <h3>Kuzatish ro‘yxatiga akkaunt qo‘shing.</h3>
          <p>Raqobatchi profilini, izoh va strategiya eslatmalarini saqlang; keyin uning kontent signalini o‘zingiznikiga solishtiring.</p>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', margin: '14px 0' }}>
            <input value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} placeholder="@username" style={{ flex: '1 1 220px' }} />
            <input value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} placeholder="Izoh (ixtiyoriy)" style={{ flex: '2 1 280px' }} />
          </div>
          <button className="button button-dark" onClick={add}><Plus size={16} /> Qo‘shish</button>
        </div>
      </div>

      {competitors === null ? (
        <LoadingCard label="Raqobatchilar yuklanmoqda…" />
      ) : (
        <div className="competitor-table card">
          <div className="table-top">
            <div><h3>Akkauntlar</h3><p>Kuzatish ro‘yxati va izohlar</p></div>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Akkaunt</th><th>Izoh</th><th>Qo‘shilgan</th><th /></tr></thead>
              <tbody>
                {competitors.map((item) => (
                  <tr key={item.id}>
                    <td><span className={`competitor-avatar ${['purple', 'peach', 'sky'][item.username.length % 3]}`}>{item.username.slice(0, 2).toUpperCase()}</span><b>@{item.username}</b></td>
                    <td>{item.notes || '—'}</td>
                    <td>{formatDay(item.created_at) ? `${formatDay(item.created_at).day} ${formatDay(item.created_at).month}` : '—'}</td>
                    <td />
                  </tr>
                ))}
                {!competitors.length && <tr><td colSpan={4} style={{ padding: 24, opacity: 0.7 }}>Raqobatchi hali yo‘q — birinchi akkauntini qo‘shing.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function ResultsPage({ session, toast }) {
  const { videos, refresh } = useVideos(session.workspace_id)
  const [recordViews, setRecordViews] = useState({})

  if (videos === null) return <LoadingCard label="Natijalar yuklanmoqda…" />

  const completed = videos.filter((video) => video.analysis?.status === 'completed' && video.analysis.viral_score != null)
  const scores = completed.map((video) => video.analysis.viral_score)
  const medianScore = scores.length ? Math.round(scores.sort((a, b) => a - b)[Math.floor(scores.length / 2)]) : null
  const accuracies = videos.map((video) => video.prediction?.accuracy).filter((value) => value != null)
  const averageAccuracy = accuracies.length ? Math.round(accuracies.reduce((sum, value) => sum + value, 0) / accuracies.length) : null
  const totalViews = videos.reduce((sum, video) => sum + (video.latest_metric?.views || video.prediction?.actual_views || 0), 0)
  const chart = viewsChartData([...videos].reverse())

  const record = async (video) => {
    const value = Number(recordViews[video.id])
    if (!Number.isFinite(value) || value < 0) { toast('Ko‘rishlar sonini kiriting', 'warning'); return }
    try {
      const result = await api(`/v1/videos/${video.id}/metrics`, { method: 'POST', body: { views: value } })
      toast(result.prediction_accuracy != null ? `Natija o‘rganish tsikliga qo‘shildi — aniqlik ${Math.round(result.prediction_accuracy)}%` : 'Natija saqlandi', 'success')
      setRecordViews({ ...recordViews, [video.id]: '' })
      await refresh()
    } catch (cause) {
      toast(cause.message || 'Saqlanmadi', 'warning')
    }
  }

  return (
    <div className="results-page">
      <div className="page-title-row">
        <div>
          <div className="eyebrow eyebrow-violet"><LineChart size={13} /> LEARNING LOOP</div>
          <h2>Natijalarim</h2>
          <p>AI prognozlari va real Instagram natijalari taqqoslanmoqda</p>
        </div>
      </div>
      <div className="results-summary-grid">
        <MetricCard icon={Gauge} label="Prognoz aniqligi" value={averageAccuracy ?? '—'} suffix={averageAccuracy != null ? '%' : ''} tone="violet" caption="real natijalardan" />
        <MetricCard icon={Eye} label="Real ko‘rishlar" value={formatViews(totalViews)} tone="mint" caption="barcha videolar" />
        <MetricCard icon={TrendingUp} label="Median Viral Score" value={medianScore ?? '—'} suffix={medianScore != null ? '/100' : ''} tone="blue" caption={`${completed.length} ta tahlil`} />
        <MetricCard icon={Check} label="Natija kiritilgan" value={videos.filter((video) => video.latest_metric || video.prediction?.actual_views != null).length} tone="orange" caption={`/ ${videos.length} video`} />
      </div>
      <div className="prediction-card card">
        <div className="section-heading">
          <div><h3>Prognoz va real natija</h3><p>Soniyasiz: har bir video uchun AI prognozi va kiritilgan real ko‘rishlar</p></div>
          <div className="chart-key"><span><i className="actual" /> Real</span><span><i className="predicted" /> AI prognozi</span></div>
        </div>
        {chart ? (
          <div className="prediction-chart">
            <div className="prediction-y"><span>{formatViews(chart.maxViews)}</span><span>{formatViews(chart.maxViews * 0.75)}</span><span>{formatViews(chart.maxViews * 0.5)}</span><span>{formatViews(chart.maxViews * 0.25)}</span><span>0</span></div>
            <div className="prediction-lines">
              <span /><span /><span /><span />
              <svg viewBox="0 0 670 205" preserveAspectRatio="none">
                <polyline points={chart.predicted} fill="none" stroke="#b8adff" strokeWidth="3" strokeDasharray="8 8" vectorEffect="non-scaling-stroke" />
                {chart.actual && <polyline points={chart.actual} fill="none" stroke="#7965ff" strokeWidth="3" vectorEffect="non-scaling-stroke" />}
                {chart.rows.map((row, index) => (
                  row.prediction.actual_views != null ? (
                    <circle key={row.id} cx={chart.rows.length === 1 ? 335 : (index / (chart.rows.length - 1)) * 670} cy={196 - (row.prediction.actual_views / chart.maxViews) * 176} r="4.5" fill="#fff" stroke="#7965ff" strokeWidth="3" />
                  ) : null
                ))}
              </svg>
            </div>
            <div className="prediction-x">{chart.rows.map((row) => <span key={row.id}>{(row.original_name || '').slice(0, 6)}</span>)}</div>
          </div>
        ) : (
          <p style={{ padding: '18px 0' }}>Prognoz chizig‘i uchun kamida bitta video hisobotga ega bo‘lishi kerak. Akkaunt o‘rtacha ko‘rishlari Sozlamalarga kiritilganda har bir tahlilda prognoz oralig‘i paydo bo‘ladi.</p>
        )}
        <div className="prediction-insight"><span><Sparkles size={15} /></span><p><b>AI o‘rganmoqda:</b> Har bir kiritilgan real natija prognoz aniqligini yangilaydi — keyingi tahlillarda baho aniqroq bo‘ladi.</p></div>
      </div>
      <div className="published-videos card">
        <div className="section-heading"><div><h3>Joylangan videolar</h3><p>Har bir video bo‘yicha o‘rganilgan signal</p></div></div>
        <div className="published-list">
          {videos.map((video) => {
            const actualViews = video.latest_metric?.views ?? video.prediction?.actual_views
            const viewsLabel = actualViews != null
              ? formatViews(actualViews)
              : video.prediction?.predicted_views != null ? `prognoz ${formatViews(video.prediction.predicted_views)}` : '—'
            const delta = video.prediction?.predicted_views && video.prediction.actual_views != null
              ? Math.round(((video.prediction.actual_views - video.prediction.predicted_views) / Math.max(1, video.prediction.predicted_views)) * 100)
              : null
            return (
              <div className="published-row" key={video.id}>
                <VideoCover muted mini />
                <div className="published-title"><strong>{video.original_name.replace(/\.[^.]+$/, '')}</strong><span>{formatDay(video.created_at)?.day} {formatDay(video.created_at)?.month} · {Math.round(video.duration_seconds || 0)} soniya · Reels</span></div>
                <span className={`tiny-score ${video.analysis?.viral_score >= 70 ? 'mint' : video.analysis?.viral_score != null ? 'orange' : ''}`}>{video.analysis?.viral_score ?? '—'}</span>
                <span className="published-views"><Eye size={14} /> {viewsLabel}</span>
                <span className={`published-delta ${delta === null ? '' : delta >= 0 ? 'up' : 'down'}`}>
                  {delta === null ? (video.prediction?.predicted_views != null ? 'natija kutilmoqda' : '—') : `${delta >= 0 ? '+' : ''}${delta}% prognozga`}
                </span>
                {video.prediction?.predicted_views != null && (
                  <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <input type="number" min="0" placeholder="real ko‘rishlar" value={recordViews[video.id] ?? ''} onChange={(event) => setRecordViews({ ...recordViews, [video.id]: event.target.value })} style={{ width: 130 }} />
                    <button className="button button-secondary" onClick={() => record(video)} style={{ padding: '8px 12px' }}><Check size={14} /></button>
                  </span>
                )}
              </div>
            )
          })}
          {!videos.length && <p style={{ padding: 24, opacity: 0.7 }}>Hali video yo‘q — birinchisini tahlil qiling.</p>}
        </div>
      </div>
    </div>
  )
}

function InsightsPage({ session, toast, goTo }) {
  const [state, setState] = useState({ loading: true, report: null, providerMode: null, videoName: null, error: '' })

  useEffect(() => {
    let live = true
    setState({ loading: true, report: null, providerMode: null, videoName: null, error: '' })
    ;(async () => {
      try {
        const videos = await api(`/v1/workspaces/${session.workspace_id}/videos`)
        const video = videos.find((item) => item.analysis?.status === 'completed') || null
        if (!video?.analysis?.id) {
          if (live) setState({ loading: false, report: null, error: 'empty' })
          return
        }
        const analysis = await api(`/v1/analyses/persisted/${video.analysis.id}`)
        if (live) setState({ loading: false, report: analysis.report, providerMode: analysis.provider_mode, videoName: video.original_name, error: '' })
      } catch (cause) {
        if (live) setState({ loading: false, report: null, error: cause.message })
      }
    })()
    return () => { live = false }
  }, [session.workspace_id])

  if (state.loading) return <LoadingCard label="Tavsiyalar yuklanmoqda…" />
  if (state.error === 'empty' || !state.report) {
    return (
      <EmptyState
        icon={Sparkles}
        title={state.error && state.error !== 'empty' ? 'Tavsiyalarni olib bo‘lmadi' : 'Tavsiyalar hali yo‘q'}
        text={state.error && state.error !== 'empty' ? state.error : 'Birinchi video hisoboti tayyor bo‘lganda, shu yerda amaliy tavsiyalar to‘planadi.'}
        action="Videoni tahlil qilish"
        onAction={() => goTo('analyze')}
      />
    )
  }

  const { report } = state
  const changes = (report.required_changes || []).map((title, index) => ({ icon: [TrendingUp, Target, Zap][index % 3], tag: 'Video sifati', title, body: 'So‘nggi hisobotdagi majburiy o‘zgarish ro‘yxatidan.', tone: 'violet' }))
  const hooks = (report.improved_hooks || []).slice(0, 3).map((title, index) => ({ icon: [Sparkles, Lightbulb, Target][index % 3], tag: 'Strategiya', title, body: 'Yaxshilangan hook variantlari — har birini A/B sinab ko‘ring.', tone: 'mint' }))
  const cta = report.improved_cta ? [{ icon: Zap, tag: 'O‘sish', title: report.improved_cta, body: 'Yaxshilangan CTA — bitta aniq harakat.', tone: 'orange' }] : []
  const cards = [...changes, ...hooks, ...cta]

  return (
    <div className="insights-page">
      <div className="page-title-row">
        <div>
          <div className="eyebrow eyebrow-violet"><Sparkles size={13} /> PERSONALIZED INTELLIGENCE</div>
          <h2>AI tavsiyalar</h2>
          <p>So‘nggi hisobot: {state.videoName?.replace(/\.[^.]+$/, '')} · tavsiyalar hisobot ma’lumotlaridan olinadi</p>
        </div>
        <button className="button button-secondary" onClick={() => window.location.reload()}><RefreshCw size={16} /> Yangilash</button>
      </div>
      <div className="insights-filter"><button className="active">Barchasi <span>{cards.length}</span></button><button>Video sifati <span>{changes.length}</span></button><button>Strategiya <span>{hooks.length}</span></button><button>O‘sish <span>{cta.length}</span></button></div>
      <div className="insight-cards">
        {cards.map(({ icon: Icon, tag, title, body, tone }) => (
          <article className={`insight-card card insight-${tone}`} key={`${tag}-${title}`}>
            <div className="insight-card-top"><span className={`recommendation-icon rec-${tone}`}><Icon size={18} /></span><span className="insight-category">{tag}</span><button className="icon-button subtle"><MoreHorizontal size={17} /></button></div>
            <h3>{title}</h3>
            <p>{body}</p>
            <div className="insight-evidence"><span><BarChart3 size={14} /> Ma’lumot signali</span><strong>so‘nggi hisobot</strong></div>
            <button className="link-button" onClick={() => toast('Tavsiya amaliy rejaga qo‘shildi', 'success')}>Amalga oshirish <ArrowRight size={15} /></button>
          </article>
        ))}
      </div>
      <div className="fact-legend card">
        <div><ShieldCheck size={19} /><span><strong>Ma’lumot shaffofligi</strong><small>Har bir xulosa qaysi turdagi signalga tayanganini hisobotda ko‘ring.</small></span></div>
        <span className="legend-label verified">Tekshirilgan ma’lumot</span>
        <span className="legend-label ai">AI xulosasi</span>
        <span className="legend-label context">Akkaunt tarixi</span>
        {state.providerMode === 'demo' && <span className="tag tag-amber" style={{ alignSelf: 'center' }}>Demo rejim — production’da LLM matnlari beriladi</span>}
      </div>
    </div>
  )
}

function SettingsPage({ session, toast }) {
  const [name, setName] = useState(session.workspace.name || '')
  const [industry, setIndustry] = useState(session.workspace.industry || '')
  const [plan, setPlan] = useState(session.workspace.plan || 'free')
  const [stats, setStats] = useState(() => accountStats())
  const [deleting, setDeleting] = useState(false)

  const saveProfile = async () => {
    try {
      await api(`/v1/workspaces/${session.workspace_id}/secure`, { method: 'PATCH', body: { name: name.trim() || null, industry: industry.trim() || null } })
      toast('Profil saqlandi', 'success')
    } catch (cause) {
      toast(cause.message || 'Saqlanmadi', 'warning')
    }
  }

  const changePlan = async () => {
    try {
      await api(`/v1/workspaces/${session.workspace_id}/plan`, { method: 'PATCH', body: { plan } })
      const fresh = await bootstrapSession({})
      toast(`${plan} tarif faollashtirildi`, 'success')
      window.dispatchEvent(new CustomEvent('viralai:session', { detail: fresh }))
    } catch (cause) {
      toast(cause.message || 'Tarif o‘zgartirilmadi', 'warning')
    }
  }

  const saveStats = async () => {
    saveAccountStats({
      average_views: stats.average_views === '' ? null : Number(stats.average_views),
      best_views: stats.best_views === '' ? null : Number(stats.best_views),
    })
    toast('Akkaunt statistikasi saqlandi — keyingi tahlillarda prognoz shunga asosan hisoblanadi', 'success')
  }

  const erase = async () => {
    if (!window.confirm("Barcha ma'lumotlaringiz (videolar, hisobotlar, profil) butunlay o'chiriladi. Davom etasizmi?")) return
    setDeleting(true)
    try {
      await api(`/v1/users/${session.user_id}`, { method: 'DELETE' })
      clearSession()
      window.location.reload()
    } catch (cause) {
      toast(cause.message || 'O‘chirilmadi', 'warning')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="settings-page">
      <div className="page-title-row">
        <div>
          <div className="eyebrow eyebrow-violet"><Settings2 size={13} /> ISH MAYDONI</div>
          <h2>Profil va sozlamalar</h2>
          <p>Kontent tavsiyalaringiz uchun asosiy kontekst</p>
        </div>
        <button className="button button-primary" onClick={saveProfile}><Check size={16} /> Saqlash</button>
      </div>
      <div className="settings-layout">
        <div className="settings-main">
          <section className="setting-section card">
            <div className="section-heading"><div><h3>Akkaunt profili</h3><p>AI baholashni sizning biznesingizga moslashtiradi</p></div></div>
            <div className="profile-setting"><Avatar /><div><strong>Madina Abdullayeva</strong><span>@{session.workspace.name.toLowerCase().replaceAll(' ', '')} · {session.workspace.plan} tarif</span></div><button className="button button-secondary" onClick={() => toast('Profil rasmi sozlamasi demo muhitda o‘chirilgan', 'info')}>O‘zgartirish</button></div>
            <div className="settings-fields">
              <label>Ish maydoni nomi<input value={name} onChange={(event) => setName(event.target.value)} /></label>
              <label>Faoliyat sohasi<input value={industry} onChange={(event) => setIndustry(event.target.value)} /></label>
            </div>
          </section>
          <section className="setting-section card">
            <div className="section-heading"><div><h3>Akkaunt statistikasi</h3><p>Prognoz oralig‘i shu tarixiy o‘rtachaga asosan hisoblanadi</p></div></div>
            <div className="settings-fields">
              <label>O‘rtacha ko‘rishlar<input type="number" min="0" value={stats.average_views ?? ''} onChange={(event) => setStats({ ...stats, average_views: event.target.value })} placeholder="masalan: 1200" /></label>
              <label>Eng yaxshi ko‘rishlar<input type="number" min="0" value={stats.best_views ?? ''} onChange={(event) => setStats({ ...stats, best_views: event.target.value })} placeholder="masalan: 8600" /></label>
            </div>
            <div className="upload-actions" style={{ marginTop: 10 }}><button className="button button-secondary" onClick={saveStats}>Statistikani saqlash</button></div>
          </section>
          <section className="setting-section card">
            <div className="section-heading"><div><h3>Tarif</h3><p>Har bir tarif oylik tahlil va raqobatchilar limitini belgilaydi</p></div></div>
            <div className="goal-options">
              {['free', 'creator', 'pro', 'agency'].map((option) => (
                <button key={option} className={option === plan ? 'selected' : ''} onClick={() => setPlan(option)}>
                  <span><TrendingUp size={18} /></span>
                  <div><strong>{option}</strong><small>{option === 'free' ? '3 tahlil/oy' : option === 'creator' ? '30 tahlil/oy' : option === 'pro' ? '150 tahlil/oy' : '1000 tahlil/oy'}</small></div>
                  {option === plan && <Check size={17} />}
                </button>
              ))}
            </div>
            {plan !== session.workspace.plan && <button className="button button-primary" onClick={changePlan} style={{ marginTop: 10 }}>{plan} tarifga o‘tish</button>}
          </section>
        </div>
        <aside className="settings-side">
          <div className="telegram-card">
            <span className="telegram-icon"><Send size={20} /></span>
            <h3>Telegram boti</h3>
            <p>Production muhitida video va hisobotlarni bevosita Telegram’da olasiz (bot token sozlanganda).</p>
          </div>
          <div className="danger-card card">
            <h3>Ma’lumotlar va maxfiylik</h3>
            <p style={{ fontSize: 13, opacity: 0.8, margin: '8px 0 12px' }}>Ish maydonini o‘chirish — GDPR-uslubidagi to‘liq erasure: profil anonimlashtiriladi va yopiq saqlangan barcha media o‘chiriladi.</p>
            <button className="danger" onClick={erase} disabled={deleting}>{deleting ? 'O‘chirilmoqda…' : 'Ish maydonini o‘chirish'} <ArrowRight size={14} /></button>
          </div>
        </aside>
      </div>
    </div>
  )
}

function AdminPage() {
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api('/v1/admin/summary').then(setSummary).catch((cause) => setError(cause.message))
  }, [])
  return (
    <section className="card report-summary">
      <div className="section-heading"><div><h3>Admin dashboard</h3><p>Platforma operatsion hisoboti (API /v1/admin/summary)</p></div></div>
      {error && <p>{error}</p>}
      {!summary && !error && <p>Yuklanmoqda…</p>}
      {summary && (
        <div className="plan-kpis">
          <span><b>{summary.users}</b> foydalanuvchi</span><i />
          <span><b>{summary.workspaces}</b> ish maydoni</span><i />
          <span><b>{summary.videos}</b> video</span><i />
          <span><b>{summary.analyses}</b> tahlil</span><i />
          <span><b>{summary.failed_analyses}</b> xato</span>
        </div>
      )}
    </section>
  )
}

function Sidebar({ active, onNavigate, collapsed, onToggle, mobileOpen, onClose, workspace, plan }) {
  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}>
      <div className="sidebar-top"><Brand /><button className="desktop-collapse icon-button subtle" onClick={onToggle} aria-label="Panelni yig‘ish"><PanelLeftClose size={18} /></button><button className="sidebar-close icon-button subtle" onClick={onClose} aria-label="Menyuni yopish"><X size={19} /></button></div>
      <div className="sidebar-workspace"><WorkspacePicker workspace={workspace} plan={plan} /></div>
      <nav className="side-nav" aria-label="Asosiy navigatsiya">{navItems.map(({ id, label, icon: Icon, badge }) => <button className={`nav-item ${active === id || (id === 'analyze' && active === 'report') ? 'active' : ''}`} key={id} onClick={() => { onNavigate(id); onClose() }}><Icon size={19} /><span>{label}</span>{badge && <b>{badge}</b>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="usage-card"><div><span>{plan} tarif</span><strong>oylik limit</strong></div><div className="usage-bar"><i /></div><small>Videolar yopiq saqlanadi</small><button onClick={() => onNavigate('settings')}>Tarifni boshqarish <ArrowUpRight size={13} /></button></div><button className="user-nav" onClick={() => onNavigate('settings')}><Avatar small /><span><strong>Madina A.</strong><small>Sozlamalar</small></span><ChevronRight size={15} /></button></div>
    </aside>
  )
}

function Toast({ data, onClose }) {
  if (!data) return null
  const Icon = data.type === 'success' ? Check : data.type === 'warning' ? Info : Sparkles
  return <div className={`toast toast-${data.type || 'info'}`}><span><Icon size={16} /></span><p>{data.message}</p><button onClick={onClose} aria-label="Yopish"><X size={15} /></button></div>
}

function BootScreen({ error, onRetry }) {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0b0a12', color: '#fff' }}>
      <div style={{ textAlign: 'center', maxWidth: 420, padding: 24 }}>
        <Brand />
        <h2 style={{ margin: '18px 0 8px' }}>{error ? 'API bilan ulanib bo‘lmadi' : 'Sessiya yaratilmoqda…'}</h2>
        <p style={{ opacity: 0.75 }}>{error || 'Ish maydoni va token tayyorlanmoqda.'}</p>
        {error && <button className="button button-primary" onClick={onRetry}><RefreshCw size={16} /> Qayta urinish</button>}
        {!error && <div style={{ marginTop: 16 }}><LoaderCircle size={22} className="spin" /></div>}
      </div>
    </div>
  )
}

function App() {
  const [session, setSession] = useState(() => loadSession())
  const [bootError, setBootError] = useState('')
  const [page, setPage] = useState('overview')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileMenu, setMobileMenu] = useState(false)
  const [toastData, setToastData] = useState(null)
  const titleMap = useMemo(() => ({
    overview: 'Bosh sahifa',
    analyze: 'Videoni tahlil qilish',
    report: 'Video hisoboti',
    idea: "G'oyani tekshirish",
    plan: 'Kontent-reja',
    competitors: 'Raqobatchilar',
    results: 'Natijalarim',
    insights: 'AI tavsiyalar',
    admin: 'Admin dashboard',
    settings: 'Sozlamalar',
  }), [])

  const boot = () => {
    setBootError('')
    bootstrapSession({ name: 'Marketing Ustasi', instagram_username: 'marketingustasi', industry: 'Marketing va SMM' })
      .then(setSession)
      .catch((cause) => setBootError(cause.message || 'APIga ulanib bo‘lmadi. Backendni ishga tushirib, sahifani yangilang.'))
  }

  useEffect(() => {
    if (!loadSession()) boot()
  }, [])

  useEffect(() => {
    const handler = (event) => setSession(event.detail)
    window.addEventListener('viralai:session', handler)
    return () => window.removeEventListener('viralai:session', handler)
  }, [])

  const toast = (message, type = 'info') => {
    setToastData({ message, type })
    window.clearTimeout(window.__viralToastTimeout)
    window.__viralToastTimeout = window.setTimeout(() => setToastData(null), 3200)
  }

  const navigate = (next) => {
    setPage(next)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  if (!session) {
    return <BootScreen error={bootError} onRetry={boot} />
  }

  const headerDescription = page === 'overview' ? 'Akkauntingizdagi kontent signallari — real API ma’lumotlari' : undefined
  return (
    <div className={`app-shell ${sidebarCollapsed ? 'sidebar-is-collapsed' : ''}`}>
      <Sidebar active={page} onNavigate={navigate} collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} mobileOpen={mobileMenu} onClose={() => setMobileMenu(false)} workspace={session.workspace.name} plan={session.workspace.plan} />
      {mobileMenu && <button className="mobile-backdrop" onClick={() => setMobileMenu(false)} aria-label="Menyuni yopish" />}
      <main className="main-area">
        <Header title={titleMap[page]} description={headerDescription} onMenu={() => setMobileMenu(true)}>
          <button className="header-search" onClick={() => toast('Qidiruv tez orada qo‘shiladi', 'info')}><Search size={17} /><span>Qidirish</span><kbd>⌘ K</kbd></button>
          <button className="icon-button notification-button" onClick={() => toast('Yangi bildirishnomalar yo‘q', 'info')} aria-label="Bildirishnomalar"><Bell size={19} /><i /></button>
          <Avatar small />
        </Header>
        <div className="page-content">
          {page === 'overview' && <Overview session={session} goTo={navigate} />}
          {page === 'analyze' && <UploadPage session={session} goTo={navigate} toast={toast} />}
          {page === 'report' && <ReportPage session={session} toast={toast} goTo={navigate} />}
          {page === 'idea' && <IdeaPage toast={toast} />}
          {page === 'plan' && <PlanPage session={session} toast={toast} />}
          {page === 'competitors' && <CompetitorsPage session={session} toast={toast} />}
          {page === 'results' && <ResultsPage session={session} toast={toast} />}
          {page === 'insights' && <InsightsPage session={session} toast={toast} goTo={navigate} />}
          {page === 'admin' && <AdminPage />}
          {page === 'settings' && <SettingsPage session={session} toast={toast} />}
        </div>
      </main>
      <Toast data={toastData} onClose={() => setToastData(null)} />
    </div>
  )
}

export default App
