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
  Image as ImageIcon,
  Info,
  Lightbulb,
  LineChart,
  LoaderCircle,
  Menu,
  MessageCircle,
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

const navItems = [
  { id: 'overview', label: 'Bosh sahifa', icon: Home },
  { id: 'analyze', label: 'Videoni tahlil qilish', icon: Video, badge: 'AI' },
  { id: 'idea', label: "G‘oyani tekshirish", icon: Lightbulb },
  { id: 'plan', label: 'Kontent-reja', icon: CalendarDays },
  { id: 'competitors', label: 'Raqobatchilar', icon: UsersRound },
  { id: 'results', label: 'Natijalarim', icon: BarChart3 },
  { id: 'insights', label: 'AI tavsiyalar', icon: Sparkles },
  { id: 'admin', label: 'Admin', icon: ShieldCheck },
]

const reportScores = [
  { label: 'Hook', score: 85, color: '#8b7cff' },
  { label: 'Retention', score: 68, color: '#eab64e' },
  { label: 'Vizual', score: 74, color: '#33c8a3' },
  { label: 'Audio', score: 81, color: '#58a7ff' },
  { label: 'Ulashish', score: 72, color: '#f17e9a' },
  { label: 'Saqlash', score: 88, color: '#ba78f2' },
]

const timelineItems = [
  {
    time: '00:00—00:02',
    title: 'Hook kuchli',
    state: 'strong',
    score: 91,
    detail: 'Muammo birinchi jumladanoq aniq aytilgan. Katta matn foydalanuvchi e’tiborini ushlaydi.',
    action: 'Natija raqamini 12% kattalashtiring.',
  },
  {
    time: '00:03—00:05',
    title: 'Mavzu tushunarli',
    state: 'good',
    score: 84,
    detail: 'Kimga foyda berishi aniq. Ssenariy hook va va’da bilan mos keladi.',
    action: 'Bu qismni o‘zgartirmang.',
  },
  {
    time: '00:06—00:09',
    title: 'Drop-off xavfi',
    state: 'risk',
    score: 58,
    detail: 'Ikki soniyalik pauza va bir xil kadr retentionni pasaytirishi mumkin.',
    action: 'Pauzani kesing, ekran yozuvi yoki B-roll qo‘shing.',
  },
  {
    time: '00:10—00:16',
    title: 'Foydali qism',
    state: 'good',
    score: 76,
    detail: 'Amaliy qadam tomoshabinni davom ettirishga undaydi.',
    action: 'Asosiy iboralarni subtitrda ajrating.',
  },
  {
    time: '00:17—00:21',
    title: 'Vizual yangilanish kerak',
    state: 'risk',
    score: 61,
    detail: 'Kadr uzoq vaqt statik qoladi, ammo nutqdagi misol kuchli.',
    action: 'Mijoz natijasi yoki grafik B-rollini qo‘shing.',
  },
  {
    time: '00:22—00:29',
    title: 'Kuchli dalil',
    state: 'strong',
    score: 86,
    detail: 'Aniq misol ishonch va saqlab qo‘yish ehtimolini oshiradi.',
    action: 'Dalilni cover matnida ham ishlating.',
  },
  {
    time: '00:30—00:34',
    title: 'CTA kuchsiz',
    state: 'risk',
    score: 52,
    detail: '“Kuzatib boring” juda umumiy va foyda sababini bermaydi.',
    action: 'Bitta aniq harakatni so‘rang: saqlash yoki izoh yozish.',
  },
]

const contentPlan = [
  {
    day: '12',
    week: 'Du',
    type: 'Ekspertlik',
    title: 'Reels 1 000 ko‘rishda to‘xtashining 3 sababi',
    hook: 'Sizning Reels’ingiz yomon emas. U noto‘g‘ri joyda sekinlashadi.',
    score: 82,
    color: 'violet',
  },
  {
    day: '13',
    week: 'Se',
    type: 'Case',
    title: '42 soniyalik videoni 29 soniyaga tushirdik',
    hook: 'Mana shu 13 soniya mijozimizga +64% retention olib keldi.',
    score: 88,
    color: 'mint',
  },
  {
    day: '15',
    week: 'Pa',
    type: 'Muammo',
    title: 'Kontentingiz foydali bo‘lsa ham nega saqlashmaydi?',
    hook: 'Maslahat emas, foydalanishga tayyor formula bering.',
    score: 76,
    color: 'orange',
  },
  {
    day: '17',
    week: 'Sh',
    type: 'Behind the scenes',
    title: 'Bir video tahlili ichida nimalar bo‘ladi?',
    hook: 'Bu 34 soniya — videoingizdagi yashirin xatolar xaritasi.',
    score: 71,
    color: 'blue',
  },
]

const competitors = [
  {
    username: '@marketinglab.uz',
    initials: 'ML',
    gradient: 'purple',
    followers: '118K',
    frequency: '4.8 / hafta',
    best: '“3 ta reklama xatosi”',
    format: 'Face cam + katta subtitr',
    opportunity: 'Yuqori',
  },
  {
    username: '@reels.school',
    initials: 'RS',
    gradient: 'peach',
    followers: '87K',
    frequency: '3.1 / hafta',
    best: '“Reels hook formulasi”',
    format: 'Screen record + B-roll',
    opportunity: 'O‘rta',
  },
  {
    username: '@digital.suhbat',
    initials: 'DS',
    gradient: 'sky',
    followers: '52K',
    frequency: '5.0 / hafta',
    best: '“Mijoz topishning yangi yo‘li”',
    format: 'Storytelling',
    opportunity: 'Yuqori',
  },
]

const recommendationItems = [
  {
    tag: 'Bugun sinab ko‘ring',
    title: '“Natijani boshida aytish” formati sizning auditoriyangizda ishlaydi',
    body: 'Oxirgi 8 videoda natija 3-soniyagacha berilganda o‘rtacha ko‘rish davomiyligi 19% yuqori bo‘lgan.',
    icon: TrendingUp,
    tone: 'violet',
  },
  {
    tag: 'Kontent bo‘shlig‘i',
    title: 'Raqobatchilarda “montaj briefi” mavzusi kam',
    body: 'Sizning ekspertlik yo‘nalishingiz bilan mos, save potensiali esa yuqori.',
    icon: Target,
    tone: 'mint',
  },
  {
    tag: 'E’tibor',
    title: 'CTA’lar haddan tashqari umumiy bo‘lib qolgan',
    body: 'Keyingi 3 Reels’da faqat “saqlab qo‘ying” CTA’sini A/B sinab ko‘ring.',
    icon: Zap,
    tone: 'orange',
  },
]

function ScoreRing({ score = 78, size = 122, stroke = 10, label = 'Viral Score', light = false }) {
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
  return <span className={`avatar ${small ? 'avatar-small' : ''}`}>MA</span>
}

function MetricCard({ icon: Icon, label, value, delta, positive = true, suffix, tone = 'violet' }) {
  return (
    <div className="metric-card card">
      <div className={`metric-icon metric-${tone}`}><Icon size={18} /></div>
      <div className="metric-heading">
        <span>{label}</span>
        <button className="icon-button subtle" aria-label={`${label} haqida ma'lumot`}><Info size={15} /></button>
      </div>
      <div className="metric-bottom">
        <strong>{value}{suffix && <small>{suffix}</small>}</strong>
        <span className={`delta ${positive ? 'delta-positive' : 'delta-negative'}`}>
          {positive ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
          {delta}
        </span>
      </div>
      <div className="metric-caption">oldingi 30 kunga nisbatan</div>
    </div>
  )
}

function TinyBarChart() {
  const bars = [42, 58, 47, 70, 61, 89, 74, 95, 62, 78, 85, 72]
  return (
    <div className="tiny-bars" aria-label="So‘nggi 12 video natijasi">
      {bars.map((height, i) => <span key={i} className={i === 7 ? 'active' : ''} style={{ height: `${height}%` }} />)}
    </div>
  )
}

function RetentionChart({ compact = false }) {
  const points = compact
    ? '0,39 25,42 50,46 75,49 100,53 125,55 150,61 175,61 200,66 225,70 250,74 275,75 300,78 325,81 350,83'
    : '0,42 44,46 88,50 132,55 176,59 220,62 264,69 308,69 352,75 396,80 440,83 484,89 528,92 572,99 616,105 660,112'
  return (
    <div className={`retention-chart ${compact ? 'retention-compact' : ''}`}>
      <div className="chart-grid">
        <span style={{ top: '8%' }} />
        <span style={{ top: '35%' }} />
        <span style={{ top: '62%' }} />
        <span style={{ top: '89%' }} />
      </div>
      <svg viewBox={compact ? '0 0 350 115' : '0 0 660 132'} preserveAspectRatio="none" aria-label="Retention prognozi">
        <defs>
          <linearGradient id={compact ? 'retentionFillSmall' : 'retentionFill'} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#8b7cff" stopOpacity="0.24" />
            <stop offset="100%" stopColor="#8b7cff" stopOpacity="0" />
          </linearGradient>
          <linearGradient id={compact ? 'retentionStrokeSmall' : 'retentionStroke'} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#baacff" />
            <stop offset="100%" stopColor="#765eff" />
          </linearGradient>
        </defs>
        <polygon points={`${points} ${compact ? '350,115 0,115' : '660,132 0,132'}`} fill={`url(#${compact ? 'retentionFillSmall' : 'retentionFill'})`} />
        <polyline points={points} fill="none" stroke={`url(#${compact ? 'retentionStrokeSmall' : 'retentionStroke'})`} strokeWidth="3" vectorEffect="non-scaling-stroke" />
        {!compact && <>
          <circle cx="132" cy="55" r="5" fill="#f4b640" stroke="#fff" strokeWidth="2" />
          <circle cx="440" cy="83" r="5" fill="#f4b640" stroke="#fff" strokeWidth="2" />
        </>}
      </svg>
      {!compact && <>
        <div className="chart-axis chart-y"><span>100%</span><span>75%</span><span>50%</span><span>25%</span></div>
        <div className="chart-axis chart-x"><span>0:00</span><span>0:08</span><span>0:16</span><span>0:24</span><span>0:34</span></div>
        <div className="chart-callout callout-one"><span>6–9 s</span> pauza</div>
        <div className="chart-callout callout-two"><span>17–21 s</span> statik kadr</div>
      </>}
    </div>
  )
}

function VideoCover({ muted = false, mini = false }) {
  return (
    <div className={`video-cover ${mini ? 'video-mini' : ''} ${muted ? 'video-muted' : ''}`}>
      <div className="cover-noise" />
      <div className="cover-grid" />
      <div className="cover-chip">REELS TIPS</div>
      <div className="cover-person">
        <span className="person-hair" />
        <span className="person-face" />
        <span className="person-neck" />
        <span className="person-shirt" />
      </div>
      <div className="cover-copy">
        <span>VIDEONGIZ</span>
        <strong>1 000’da<br />TO‘XTAYDIMI?</strong>
      </div>
      {!muted && <button className="video-play" aria-label="Videoni ko‘rish"><Play size={18} fill="currentColor" /></button>}
      <div className="cover-duration">00:34</div>
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

function WorkspacePicker() {
  return (
    <button className="workspace-picker">
      <span className="workspace-logo">M</span>
      <span><strong>Marketing Ustasi</strong><small>Asosiy ish maydoni</small></span>
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

function Overview({ goTo }) {
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
        <MetricCard icon={Eye} label="Jami ko‘rishlar" value="284.6K" delta="18.4%" tone="violet" />
        <MetricCard icon={Clock3} label="O‘rtacha retention" value="61" suffix="%" delta="6.1%" tone="mint" />
        <MetricCard icon={Send} label="Ulashishlar" value="3,842" delta="11.8%" tone="blue" />
        <MetricCard icon={UsersRound} label="Yangi obunachilar" value="1,284" delta="4.3%" tone="orange" />
      </section>

      <section className="dashboard-grid">
        <div className="analysis-highlight card">
          <div className="section-heading">
            <div>
              <div className="eyebrow eyebrow-violet"><Sparkles size={13} /> SO‘NGGI AI TAHLIL</div>
              <h3>Videoingiz tahlilga tayyor</h3>
            </div>
            <button className="text-button" onClick={() => goTo('report')}>To‘liq hisobot <ArrowRight size={15} /></button>
          </div>
          <div className="analysis-content">
            <VideoCover mini />
            <div className="analysis-summary">
              <div className="video-meta"><span>Reels</span><i /> 34 soniya <i /> Bugun, 10:42</div>
              <h4>“Reels 1 000 ko‘rishda to‘xtashining sababi”</h4>
              <div className="analysis-tags"><span className="tag tag-mint"><Check size={12} /> Hook kuchli</span><span className="tag tag-amber">3 ta tuzatish</span></div>
              <button className="link-button" onClick={() => goTo('report')}>Hisobotni ochish <ChevronRight size={15} /></button>
            </div>
            <ScoreRing score={78} size={112} stroke={9} />
          </div>
          <div className="analysis-footnote"><Info size={14} /> Bu prognoz kafolat emas. U video, auditoriya va tarixiy natijalarga asoslangan AI bahosidir.</div>
        </div>

        <div className="performance-card card">
          <div className="section-heading">
            <div><h3>Kontent samaradorligi</h3><p>So‘nggi 12 video</p></div>
            <button className="period-select">30 kun <ChevronDown size={14} /></button>
          </div>
          <TinyBarChart />
          <div className="performance-scale"><span>20 apr</span><span>26 apr</span><span>2 may</span><span>8 may</span></div>
          <div className="performance-note"><span className="note-icon"><TrendingUp size={14} /></span><span><strong>+24%</strong> — videolaringiz o‘tgan oyga nisbatan ko‘proq ulashilmoqda.</span></div>
        </div>
      </section>

      <section className="lower-grid">
        <div className="retention-card card">
          <div className="section-heading">
            <div><h3>Retention xaritasi</h3><p>Oxirgi tahlil qilingan video bo‘yicha prognoz</p></div>
            <button className="icon-button subtle" aria-label="Ko‘proq"><MoreHorizontal size={19} /></button>
          </div>
          <RetentionChart />
          <div className="retention-legend"><span><i className="legend-dot violet" /> Davom ettirish ehtimoli</span><span><i className="legend-dot amber" /> E’tibor nuqtasi</span></div>
        </div>

        <div className="recommendations card">
          <div className="section-heading">
            <div><h3>Siz uchun AI tavsiyalar</h3><p>Akkauntingiz ma’lumotlari asosida</p></div>
            <button className="text-button" onClick={() => goTo('insights')}>Barchasi <ArrowRight size={15} /></button>
          </div>
          <div className="recommendation-list">
            {recommendationItems.slice(0, 3).map(({ icon: Icon, tag, title, tone }) => (
              <button className="recommendation-row" key={title} onClick={() => goTo('insights')}>
                <span className={`recommendation-icon rec-${tone}`}><Icon size={16} /></span>
                <span><small>{tag}</small><strong>{title}</strong></span>
                <ChevronRight size={16} />
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="plan-strip card">
        <div className="plan-strip-icon"><CalendarDays size={20} /></div>
        <div><strong>Bu haftaning kontent rejasi tayyor</strong><span>4 ta video g‘oyasi sizning maqsadingiz va auditoriyangizga moslab tuzildi.</span></div>
        <div className="plan-progress"><span><i style={{ width: '50%' }} /></span><small>2 / 4 tayyor</small></div>
        <button className="button button-secondary" onClick={() => goTo('plan')}>Rejani ko‘rish <ArrowRight size={16} /></button>
      </section>
    </>
  )
}

function UploadPage({ goTo, toast }) {
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
    const valid = ['video/mp4', 'video/quicktime', 'video/x-msvideo']
    if (file.type && !valid.includes(file.type)) {
      toast('MP4, MOV yoki AVI formatini tanlang', 'warning')
      return
    }
    setSelectedFile(file)
    setFileName(file.name)
    setStage('ready')
  }

  const completeDemoAnalysis = () => {
    const milestones = [[22, 350], [44, 850], [66, 1400], [83, 1900], [100, 2500]]
    milestones.forEach(([value, timeout]) => {
      window.setTimeout(() => {
        setProgress(value)
        if (value === 100) {
          setStage('done')
          toast('Tahlil tayyor — hisobotni ko‘rishingiz mumkin', 'success')
        }
      }, timeout)
    })
  }

  const startAnalysis = async () => {
    setStage('processing')
    setProgress(8)
    const apiUrl = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')
    if (!selectedFile) {
      completeDemoAnalysis()
      return
    }

    try {
      const context = {
        title: fileName.replace(/\.[^.]+$/, ''),
        topic,
        objective,
        audience,
        account: { account_type: 'expert', niche: 'Marketing va SMM', language: 'uz' },
      }
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('context', JSON.stringify(context))
      const created = await fetch(`${apiUrl}/v1/analyses/upload`, { method: 'POST', body: formData })
      if (!created.ok) throw new Error((await created.json()).detail || 'Upload bajarilmadi')
      const job = await created.json()
      setProgress(32)
      const poll = async () => {
        const response = await fetch(`${apiUrl}/v1/analyses/${job.id}`)
        if (!response.ok) throw new Error('Tahlil holatini olish imkoni bo‘lmadi')
        const status = await response.json()
        const progressByStatus = { queued: 12, processing: 22, transcribing: 43, visual_analysis: 65, scoring: 82, report_generation: 92 }
        setProgress(progressByStatus[status.status] || 100)
        if (status.status === 'completed') {
          setStage('done')
          toast('API tahlili tayyor — hisobotni ko‘rishingiz mumkin', 'success')
          return
        }
        if (status.status === 'failed') throw new Error(status.error || 'Tahlil muvaffaqiyatsiz tugadi')
        window.setTimeout(() => poll().catch(handleApiError), 550)
      }
      const handleApiError = (error) => {
        setStage('ready')
        setProgress(0)
        toast(error.message || 'API bilan ulanishda xato', 'warning')
      }
      poll().catch(handleApiError)
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
            {!fileName ? <>
              <div className="upload-orb"><UploadCloud size={27} /></div>
              <h3>Videoni shu yerga tashlang</h3>
              <p>yoki qurilmangizdan tanlang</p>
              <div className="upload-actions"><button className="button button-primary" onClick={() => inputRef.current?.click()}>Faylni tanlash</button><button className="button button-tertiary" onClick={() => { setSelectedFile(null); setFileName('reels_retention_demo.mp4'); setStage('ready') }}><Sparkles size={16} /> Demo bilan sinash</button></div>
              <span className="upload-note">MP4, MOV yoki AVI · 500 MB gacha · 180 soniyagacha</span>
            </> : <>
              <div className="selected-video-icon"><Video size={24} /></div>
              <h3>{fileName}</h3>
              <p>34 soniya · 1080 × 1920 · Tahlil uchun tayyor</p>
              <div className="file-progress"><span><i style={{ width: stage === 'processing' ? `${progress}%` : '100%' }} /></span><b>{stage === 'processing' ? `${progress}%` : 'Yuklandi'}</b></div>
              {stage === 'ready' && <div className="upload-actions"><button className="button button-primary" onClick={startAnalysis}><WandSparkles size={17} /> AI tahlilni boshlash</button><button className="button button-tertiary" onClick={resetUpload}>Almashtirish</button></div>}
              {stage === 'processing' && <div className="processing-label"><LoaderCircle size={16} className="spin" /> {progress < 44 ? 'Audio va kadrlar ajratilmoqda...' : progress < 83 ? 'AI signal va ssenariyni o‘qimoqda...' : 'Shaxsiy hisobot tuzilmoqda...'}</div>}
              {stage === 'done' && <div className="upload-actions"><button className="button button-primary" onClick={() => goTo('report')}>Hisobotni ochish <ArrowRight size={16} /></button><button className="button button-tertiary" onClick={resetUpload}>Yangi video</button></div>}
            </>}
          </div>

          <div className="upload-form card">
            <div className="section-heading"><div><h3>Kontekst qo‘shing <span className="optional">ixtiyoriy</span></h3><p>AI tavsiyalari aniqroq bo‘ladi</p></div></div>
            <div className="form-row">
              <label>Mavzu<input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Video nima haqida?" /></label>
              <label>Video maqsadi<select value={objective} onChange={(event) => setObjective(event.target.value)}><option value="save">Saqlash va ulashish</option><option value="reach">Ko‘rishlarni oshirish</option><option value="lead">Lead olish</option><option value="sales">Sotuv</option></select></label>
            </div>
            <label className="full-label">Kim uchun?<input value={audience} onChange={(event) => setAudience(event.target.value)} placeholder="Maqsadli auditoriya" /></label>
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
            <div><span>Creator tarif</span><strong>12 / 30 tahlil</strong></div>
            <div className="quota-progress"><i /></div>
            <button onClick={() => toast('Tariflar tez orada ochiladi', 'info')}>Tarifni boshqarish <ArrowUpRight size={14} /></button>
          </div>
          <div className="privacy-line"><ShieldCheck size={15} /> Videolaringiz yopiq saqlanadi va faqat tahlil uchun ishlatiladi.</div>
        </aside>
      </div>
    </div>
  )
}

function ReportPage({ toast }) {
  const [tab, setTab] = useState('overview')
  const [selectedTimeline, setSelectedTimeline] = useState(2)
  const selected = timelineItems[selectedTimeline]
  return (
    <div className="report-page">
      <div className="report-heading">
        <div><div className="eyebrow eyebrow-violet"><Sparkles size={13} /> AI VIDEO HISOBOTI</div><h2>Reels 1 000 ko‘rishda to‘xtashining sababi</h2><p>34 soniya · O‘zbekcha · Tahlil qilingan: bugun, 10:44</p></div>
        <div className="report-actions"><button className="button button-secondary" onClick={() => toast('PDF hisoboti yuklashga tayyorlandi', 'success')}><Download size={16} /> PDF</button><button className="button button-primary" onClick={() => toast('Hisobot havolasi nusxalandi', 'success')}><Copy size={16} /> Ulashish</button></div>
      </div>

      <div className="score-panel card">
        <div className="overall-score"><ScoreRing score={78} size={132} stroke={11} /><div><span className="score-label">UMUMIY BAHO</span><h3>Yuqori potensial</h3><p>Videoda kuchli foydali va saqlashga undovchi signal bor. Retention xavfini bartaraf qilsangiz, prognoz +9 ballga o‘sadi.</p></div></div>
        <div className="score-breakdown">{reportScores.map(({ label, score, color }) => <div className="score-line" key={label}><span>{label}</span><i><b style={{ width: `${score}%`, background: color }} /></i><strong>{score}</strong></div>)}</div>
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

      {tab === 'overview' && <div className="report-content-grid">
        <div className="report-main">
          <div className="report-summary card">
            <div className="section-heading"><div><h3>Qisqa xulosa</h3><p>AI xulosasi · video, ssenariy va akkaunt benchmarki asosida</p></div><span className="confidence-badge"><Gauge size={14} /> 82% ishonch</span></div>
            <p className="summary-copy">Video foydali va <b>saqlab olishga mos</b>. Biroq 5–9 soniya orasidagi tushuntirish cho‘zilib ketgani sababli retention pasayishi mumkin. Birinchi natijani kadr boshidayoq ko‘rsating va CTA’ni bitta aniq harakatga almashtiring.</p>
            <div className="summary-signals"><span><Check size={13} /> Kuchli: hook, foyda, dalil</span><span><Zap size={13} /> Tuzatish: tempo, B-roll, CTA</span></div>
          </div>
          <div className="issues-card card">
            <div className="section-heading"><div><h3>Majburiy o‘zgarishlar</h3><p>Eng katta ta’sir beradigan 4 nuqta</p></div><span className="count-badge">4</span></div>
            <ol className="issues-list">
              <li><span>01</span><div><strong>Birinchi kadrga natijani chiqaring</strong><p>Hozirgi kadr chiroyli, ammo va’da 1.2 soniya kechikadi.</p></div><button aria-label="Batafsil"><ChevronRight size={17} /></button></li>
              <li><span>02</span><div><strong>05–08 soniyani 3 soniyaga qisqartiring</strong><p>Pauza va takror jumla tomoshabinning keyingi qismga o‘tishiga sabab bo‘ladi.</p></div><button aria-label="Batafsil"><ChevronRight size={17} /></button></li>
              <li><span>03</span><div><strong>17-soniyaga dalil B-roll qo‘shing</strong><p>Statik talking-head o‘rniga Insights grafik yoki oldin-keyin kadrini ishlating.</p></div><button aria-label="Batafsil"><ChevronRight size={17} /></button></li>
              <li><span>04</span><div><strong>CTA’ni “saqlab qo‘ying”ga o‘zgartiring</strong><p>Mazmun cheklistga o‘xshaydi; follow CTA’si tabiiy yakun bermayapti.</p></div><button aria-label="Batafsil"><ChevronRight size={17} /></button></li>
            </ol>
          </div>
        </div>
        <aside className="report-side">
          <div className="video-side-card card"><VideoCover /><div className="video-side-meta"><span><Eye size={14} /> 40K–100K</span><span><TrendingUp size={14} /> 78% ehtimol</span></div></div>
          <div className="forecast-card"><div className="forecast-stars"><Sparkles size={17} /></div><span>ORGANIK KO‘RISH PROGNOZI</span><strong>40K — 100K</strong><p>Optimistik ssenariy: <b>300K+</b></p><small>Retention va share rate benchmarkga yetganda.</small></div>
        </aside>
      </div>}

      {tab === 'timeline' && <div className="timeline-report-grid">
        <div className="timeline-visual card"><div className="section-heading"><div><h3>Retention prognozi</h3><p>Tomoshabin e’tiborining ehtimoliy xaritasi</p></div><span className="chart-chip"><i /> AI prognozi</span></div><RetentionChart /><div className="timeline-video-strip"><VideoCover muted /><div className="playhead" style={{ left: `${(selectedTimeline / (timelineItems.length - 1)) * 88 + 6}%` }} /><div className="timeline-markers">{timelineItems.map((item, index) => <button key={item.time} onClick={() => setSelectedTimeline(index)} className={index === selectedTimeline ? 'selected' : ''} style={{ left: `${(index / (timelineItems.length - 1)) * 88 + 6}%` }} aria-label={item.time} />)}</div></div></div>
        <div className="timeline-detail card"><div className={`timeline-state state-${selected.state}`}>{selected.state === 'risk' ? <TrendingDown size={16} /> : <TrendingUp size={16} />}{selected.state === 'risk' ? 'E’tibor nuqtasi' : 'Kuchli signal'}</div><span className="detail-time">{selected.time}</span><h3>{selected.title}</h3><div className="detail-score"><span>Retention ehtimoli</span><strong>{selected.score}%</strong></div><div className="detail-bar"><i style={{ width: `${selected.score}%` }} /></div><p>{selected.detail}</p><div className="detail-action"><WandSparkles size={16} /><span><b>Tavsiya:</b> {selected.action}</span></div></div>
        <div className="timeline-list card"><div className="section-heading"><div><h3>Segmentlar</h3><p>Muammo ustiga bosing</p></div></div>{timelineItems.map((item, index) => <button className={`timeline-list-item ${index === selectedTimeline ? 'active' : ''}`} key={item.time} onClick={() => setSelectedTimeline(index)}><span className={`state-dot ${item.state}`} /><span><small>{item.time}</small><strong>{item.title}</strong></span><ChevronRight size={16} /></button>)}</div>
      </div>}

      {tab === 'script' && <ScriptTab toast={toast} />}
      {tab === 'editor' && <EditorTab toast={toast} />}
    </div>
  )
}

function ScriptTab({ toast }) {
  const [copied, setCopied] = useState(false)
  const copyScript = () => {
    setCopied(true)
    toast('Yaxshilangan ssenariy nusxalandi', 'success')
    window.setTimeout(() => setCopied(false), 1800)
  }
  return <div className="script-grid">
    <div className="script-card card"><div className="section-heading"><div><div className="eyebrow eyebrow-violet">QAYTA YOZILGAN HOOK</div><h3>0–3 soniya</h3></div><button className="icon-button subtle" onClick={() => toast('Hook nusxalandi', 'success')}><Copy size={16} /></button></div><blockquote>“Instagramda videolaringiz 1 000 ko‘rishdan o‘tmayaptimi? Asosiy sabab kontentda emas.”</blockquote><p>Muammo + qarama-qarshilik formulasi sizning auditoriyangizdagi eng yaxshi 5 videoga mos keladi.</p><div className="script-tags"><span>Muammo</span><span>Qarama-qarshilik</span><span>1.8 soniya</span></div></div>
    <div className="script-card card"><div className="section-heading"><div><div className="eyebrow eyebrow-mint">YANGI CTA</div><h3>30–34 soniya</h3></div><button className="icon-button subtle" onClick={() => toast('CTA nusxalandi', 'success')}><Copy size={16} /></button></div><blockquote>“Keyingi videongizni joylashdan oldin shu cheklist bo‘yicha tekshirib chiqing va saqlab qo‘ying.”</blockquote><p>Bitta harakat, aniq foyda. Bu format save maqsadiga to‘g‘ri keladi.</p><div className="script-tags"><span>Save CTA</span><span>Foyda berilgan</span></div></div>
    <div className="full-script card"><div className="section-heading"><div><h3>Yaxshilangan ssenariy</h3><p>Taxminiy davomiylik: 29–31 soniya · originaldan 5 soniya qisqa</p></div><button className="button button-secondary" onClick={copyScript}>{copied ? <Check size={16} /> : <Copy size={16} />}{copied ? 'Nusxalandi' : 'Nusxalash'}</button></div><div className="script-lines"><p><span>00:00</span><b>Hook</b> Instagramda videolaringiz 1 000 ko‘rishdan o‘tmayaptimi? Asosiy sabab kontentda emas.</p><p><span>00:03</span><b>Muammo</b> Ko‘pchilik birinchi 5 soniyada tomoshabinga sabab bermaydi.</p><p><span>00:07</span><b>Qiymat</b> Mana retentionni pasaytiradigan uchta signal: uzun intro, natijaning kechikishi va bir xil kadr.</p><p><span>00:13</span><b>Dalil</b> Biz 42 soniyalik Reels’ni 29 soniyaga qisqartirdik — o‘rtacha ko‘rish davomiyligi 64 foizga oshdi.</p><p><span>00:21</span><b>Yechim</b> Birinchi kadrda natijani ko‘rsating, har 2–3 soniyada vizual o‘zgartiring va subtitrda asosiy so‘zni ajrating.</p><p><span>00:29</span><b>CTA</b> Keyingi videongizni joylashdan oldin shu cheklist bo‘yicha tekshirib chiqing va saqlab qo‘ying.</p></div></div>
  </div>
}

function EditorTab({ toast }) {
  const items = [
    ['00:00–00:02', 'Birinchi kadr', 'Videodagi “1 000” matnini 15% kattalashtiring va natija oldidan yengil zoom qo‘shing.', 'Yuqori'],
    ['00:05–00:08', 'Keraksiz pauza', '“Ya’ni...” so‘zidan keyingi 1.8 soniyani kesing. Keyingi punktni to‘g‘ridan-to‘g‘ri olib kiring.', 'Yuqori'],
    ['00:10–00:16', 'Subtitr urg‘usi', '“3 ta signal” va “uzun intro” so‘zlarini #8B7CFF rangida, 120% o‘lchamda ko‘rsating.', 'O‘rta'],
    ['00:17–00:21', 'B-roll qo‘shing', 'Insights grafik + watch-time screenshot yoki oldin/keyin diagrammasidan foydalaning.', 'Yuqori'],
    ['00:30–00:34', 'Yangi CTA', 'Eski “kuzatib boring” subtitrini yangi save CTA bilan almashtiring.', 'Yuqori'],
  ]
  return <div className="editor-layout"><div className="editor-brief card"><div className="section-heading"><div><div className="eyebrow eyebrow-violet">MONTАJCHI UCHUN TAYYOR</div><h3>Texnik topshiriq</h3><p>5 ta o‘zgarish · Taxminiy montaj vaqti: 25 daqiqa</p></div><button className="button button-secondary" onClick={() => toast('Montajchi brieﬁ nusxalandi', 'success')}><Copy size={16} /> Briefni nusxalash</button></div><div className="editor-items">{items.map(([time, title, detail, priority], index) => <div className="editor-item" key={title}><span className="editor-index">{String(index + 1).padStart(2, '0')}</span><div><div className="editor-item-heading"><small>{time}</small><i className={priority === 'Yuqori' ? 'priority-high' : ''}>{priority}</i></div><h4>{title}</h4><p>{detail}</p></div><button aria-label="Tahrirlash" className="icon-button subtle"><MoreHorizontal size={18} /></button></div>)}</div></div><aside className="editor-side"><div className="cover-recommendation card"><span className="label-with-icon"><ImageIcon size={15} /> COVER TAVSIYASI</span><div className="suggested-cover"><span>REELS NIMA UCHUN<br /><b>1 000’DA TO‘XTAYDI?</b></span></div><p>Yuqori kontrast, 4–5 so‘z va muammo markazda. Yuz ifodasi — hayrat yoki frustratsiya.</p><button className="link-button" onClick={() => toast('Cover matni nusxalandi', 'success')}>Matnni nusxalash <Copy size={14} /></button></div><div className="audio-recommendation"><Headphones size={18} /><div><span>AUDIO SIGNAL</span><strong>Nutq aniq, fon musiqa 2 dB baland</strong><p>Musiqani -16 LUFS ga tushiring.</p></div></div></aside></div>
}

function IdeaPage({ toast }) {
  const [idea, setIdea] = useState('2026-yilda O‘zbekistonda qaysi reklama kanallari ishlaydi?')
  const [checked, setChecked] = useState(true)
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
    const apiUrl = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')
    try {
      const response = await fetch(`${apiUrl}/v1/ideas/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea, objective, format: format.toLowerCase().replaceAll(' ', '_') }),
      })
      if (!response.ok) throw new Error((await response.json()).detail || 'G‘oyani tekshirib bo‘lmadi')
      setApiResult(await response.json())
      setChecked(true)
      toast('G‘oya API orqali tahlil qilindi', 'success')
    } catch (error) {
      // The dashboard remains useful as a standalone demo when no API is running.
      setApiResult(null)
      setChecked(true)
      toast(error.message || 'Demo tahlil ko‘rsatildi', 'info')
    } finally {
      setIsChecking(false)
    }
  }

  return <div className="idea-page">
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
          {isChecking ? 'AI tekshirmoqda...' : 'G‘oyani tekshirish'}
        </button>
        <div className="fact-note"><ShieldCheck size={15} /> Fakt talab qiladigan joylar alohida belgilanadi. AI xulosasi fakt o‘rnini bosmaydi.</div>
      </div>
      {checked ? <IdeaResult result={apiResult} toast={toast} /> : <EmptyState icon={Search} title="Tahlilni yangilang" text="G‘oyadagi o‘zgarishlar uchun qaytadan AI xulosasini oling." action="G‘oyani tekshirish" onAction={validateIdea} />}
    </div>
    {checked && <div className="idea-bottom">
      <div className="hooks-card card">
        <div className="section-heading"><div><h3>Siz uchun 5 ta hook</h3><p>Tanlangan format: {format}</p></div><button className="text-button" onClick={validateIdea}>Yana yaratish <RefreshCw size={14} /></button></div>
        {(apiResult?.hooks || [
          '“2026’da reklama budgetini shu 3 kanalda sarflamasangiz, kech qolishingiz mumkin.”',
          '“Hamma Instagram reklamasi o‘ldi deyapti. Raqamlar boshqa narsani ko‘rsatmoqda.”',
          '“O‘zbekistonda kichik biznes uchun eng foydali reklama kanali — bu emas.”',
          '“$100 budget bilan qaysi kanal real mijoz olib keladi?”',
          '“Reklama kanallarini tanlashda ko‘pchilik bitta xatoga yo‘l qo‘yadi.”',
        ]).map((hook, index) => <button className="hook-row" key={hook} onClick={() => toast(`Hook ${index + 1} nusxalandi`, 'success')}><span>{String(index + 1).padStart(2, '0')}</span><strong>{hook}</strong><Copy size={15} /></button>)}
      </div>
      <div className="idea-structures card">
        <div className="section-heading"><div><h3>3 ta ssenariy strukturasi</h3><p>Har biri 30–45 soniyaga mo‘ljallangan</p></div></div>
        {[
          ['Qarama-qarshilik', 'Mif → raqamlar → 3 kanal → tanlash mezoni → save CTA'],
          ['Cheklist', 'Savol → 3 mezon → kanallar taqqoslanishi → mini xulosa → comment CTA'],
          ['Case storytelling', 'Budget muammosi → oldingi xato → test → natija → follow CTA'],
        ].map(([type, structure], index) => <div className="structure-row" key={type}><span className={`structure-number n${index + 1}`}>{index + 1}</span><div><strong>{type}</strong><p>{structure}</p></div><ChevronRight size={17} /></div>)}
      </div>
    </div>}
  </div>
}

function IdeaResult({ result, toast }) {
  const score = result?.potential_score || 84
  const audienceFit = result?.audience_fit || 92
  const savePotential = result?.save_potential || 89
  const novelty = result?.novelty || 70
  const competition = result?.competition === 'low' ? 'Past' : result?.competition === 'high' ? 'Yuqori' : 'O‘rta'
  const improvedAngle = result?.improved_angle || 'Mavzu keng auditoriyaga mos, ammo “kanallar” juda umumiy. Amaliy budget yoki niche misoli bilan farqlaning.'
  return <div className="idea-result card">
    <div className="idea-result-top"><div><div className="eyebrow eyebrow-mint"><Check size={13} /> TAHLIL TAYYOR</div><h3>{score >= 80 ? 'Yuqori potensial' : 'Sinab ko‘rishga arziydi'}</h3><p>{result ? 'Backend scoring va idea signaliga ko‘ra' : 'Akkauntingiz va mavzu signallariga ko‘ra'}</p></div><ScoreRing score={score} label="Idea Score" size={108} stroke={9} /></div>
    <div className="idea-ratings">
      <div><span>Auditoriya mosligi</span><b>{audienceFit}</b><i><em style={{ width: `${audienceFit}%` }} /></i></div>
      <div><span>Save potensiali</span><b>{savePotential}</b><i><em style={{ width: `${savePotential}%` }} /></i></div>
      <div><span>Yangilik</span><b>{novelty}</b><i><em style={{ width: `${novelty}%` }} /></i></div>
      <div><span>Raqobat</span><b>{competition}</b><i><em style={{ width: `${competition === 'Yuqori' ? 80 : competition === 'Past' ? 35 : 58}%` }} /></i></div>
    </div>
    <div className="idea-takeaway"><Sparkles size={16} /><p><b>AI xulosasi:</b> {improvedAngle}</p></div>
    <button className="link-button" onClick={() => toast('Batafsil tavsiyalar ochildi', 'info')}>Batafsil tavsiyalar <ArrowRight size={15} /></button>
  </div>
}

function PlanPage({ toast }) {
  const [selected, setSelected] = useState(0)
  const item = contentPlan[selected]
  return <div className="plan-page"><div className="page-title-row"><div><div className="eyebrow eyebrow-violet"><CalendarDays size={13} /> 4 HAFTALIK STRATEGIYA</div><h2>May uchun kontent-reja</h2><p>Marketing Ustasi · Maqsad: ekspertlik va organik reach</p></div><div className="report-actions"><button className="button button-secondary" onClick={() => toast('Google Sheets eksporti tayyorlandi', 'success')}><FileText size={16} /> Eksport</button><button className="button button-primary" onClick={() => toast('Yangi kontent g‘oyasi qo‘shildi', 'success')}><Plus size={17} /> G‘oya qo‘shish</button></div></div><div className="plan-kpis"><span><b>4</b> kontent ustuni</span><i /><span><b>16</b> rejalashtirilgan Reels</span><i /><span><b>67%</b> qiymatli kontent</span><i /><span><b>3.8x</b> haftalik chastota</span></div><div className="plan-layout"><div className="calendar-card card"><div className="calendar-head"><div><h3>1-hafta · 12–18 may</h3><p>Har bir kun uchun optimallashtirilgan posting vaqti</p></div><button className="period-select">Haftalik <ChevronDown size={14} /></button></div><div className="calendar-days">{contentPlan.map((entry, index) => <button key={entry.day} onClick={() => setSelected(index)} className={`calendar-entry ${index === selected ? 'active' : ''}`}><div className="calendar-date"><span>{entry.week}</span><b>{entry.day}</b></div><div className={`calendar-type ${entry.color}`}>{entry.type}</div><strong>{entry.title}</strong><span className="calendar-time"><Clock3 size={13} /> {index % 2 ? '19:30' : '12:30'}</span><span className="calendar-score"><Sparkles size={13} /> {entry.score}</span></button>)}</div><button className="add-plan-item" onClick={() => toast('Yangi reja elementi qo‘shildi', 'success')}><Plus size={17} /> 18 mayga video qo‘shish</button></div><div className="plan-detail card"><div className={`detail-color-bar ${item.color}`} /><div className="section-heading"><div><span className={`type-pill ${item.color}`}>{item.type}</span><h3>{item.title}</h3><p>13 may, seshanba · 19:30 · 30–35 soniya</p></div><button className="icon-button subtle"><MoreHorizontal size={19} /></button></div><div className="plan-detail-block"><small>HOOK</small><p>“{item.hook}”</p></div><div className="plan-detail-block"><small>ASOSIY FIKR</small><p>Reels retentionini oshirish uchun qisqa, o‘lchanadigan va darhol qo‘llash mumkin bo‘lgan o‘zgarishlarni bering.</p></div><div className="plan-detail-meta"><span><Target size={14} /> Save + reach</span><span><Flame size={14} /> {item.score} viral potensial</span></div><div className="plan-detail-actions"><button className="button button-primary" onClick={() => toast('Ssenariy yaratildi', 'success')}><WandSparkles size={16} /> Ssenariy yaratish</button><button className="button button-secondary" onClick={() => toast('Tahrirlash rejimi ochildi', 'info')}>Tahrirlash</button></div></div></div><div className="content-pillars card"><div className="section-heading"><div><h3>Kontent ustunlari balansi</h3><p>May oyi uchun tavsiya etilgan nisbat</p></div></div><div className="pillar-bars">{[['Ekspertlik', '43%', 'violet'], ['Case va dalil', '25%', 'mint'], ['Muammo va xato', '19%', 'orange'], ['Shaxsiy brend', '13%', 'blue']].map(([name, value, tone]) => <div key={name}><span>{name}<b>{value}</b></span><i><em className={tone} style={{ width: value }} /></i></div>)}</div></div></div>
}

function CompetitorsPage({ toast }) {
  return <div className="competitors-page"><div className="page-title-row"><div><div className="eyebrow eyebrow-violet"><UsersRound size={13} /> MARKET SIGNALS</div><h2>Raqobatchilar tahlili</h2><p>3 ta kuzatilayotgan akkaunt · Oxirgi yangilanish: bugun, 08:20</p></div><button className="button button-primary" onClick={() => toast('Raqobatchi qo‘shish oynasi tez orada', 'info')}><Plus size={17} /> Raqobatchi qo‘shish</button></div><div className="competitor-hero card"><div className="competitor-hero-copy"><span className="eyebrow eyebrow-mint"><Sparkles size={13} /> AI TOPILMASI</span><h3>Bozorda “real montaj briefi” mavzusida bo‘shliq bor.</h3><p>Raqobatchilar hook va Reels g‘oyasini ko‘p tushuntiradi, ammo montajchi uchun sekundli texnik topshiriq formatini deyarli ishlatmaydi.</p><button className="button button-dark" onClick={() => toast('8 ta bo‘shliq g‘oyasi yaratildi', 'success')}>8 ta g‘oya yaratish <ArrowRight size={16} /></button></div><div className="opportunity-graphic"><div className="opportunity-rings"><i /><i /><i /><span><Sparkles size={21} /></span></div><div><b>83</b><span>Bo‘shliq skori</span></div></div></div><div className="competitor-table card"><div className="table-top"><div><h3>Akkauntlar solishtiruvi</h3><p>Kontent mexanikasi, frequency va imkoniyatlar</p></div><button className="period-select"><Clock3 size={14} /> So‘nggi 30 kun <ChevronDown size={14} /></button></div><div className="table-wrap"><table><thead><tr><th>Akkaunt</th><th>Auditoriya</th><th>Chastota</th><th>Eng yaxshi mavzu</th><th>Asosiy format</th><th>Imkoniyat</th><th /></tr></thead><tbody>{competitors.map((item) => <tr key={item.username}><td><span className={`competitor-avatar ${item.gradient}`}>{item.initials}</span><b>{item.username}</b></td><td>{item.followers}</td><td>{item.frequency}</td><td>{item.best}</td><td>{item.format}</td><td><span className={`opportunity-tag ${item.opportunity === 'Yuqori' ? 'high' : 'medium'}`}><i /> {item.opportunity}</span></td><td><button className="icon-button subtle" onClick={() => toast(`${item.username} profili ochildi`, 'info')}><ChevronRight size={17} /></button></td></tr>)}</tbody></table></div></div><div className="competitor-bottom-grid"><div className="format-card card"><div className="section-heading"><div><h3>Ishlayotgan formatlar</h3><p>Raqobatchilardagi umumiy signal</p></div></div>{[['Face cam + katta subtitr', '81%', 'violet'], ['Natija → qadamlar', '74%', 'mint'], ['Screen record + izoh', '63%', 'blue']].map(([name, percentage, color]) => <div className="format-row" key={name}><span>{name}</span><i><b className={color} style={{ width: percentage }} /></i><strong>{percentage}</strong></div>)}</div><div className="gap-card"><div className="gap-icon"><Target size={18} /></div><div><span>DIFFERENSIATSIYA</span><h3>“Kontentni tahrirlashdan oldin diagnostika qilish” pozitsiyasini egallang.</h3><p>Bu sizning mahsulotingiz va ekspertligingiz bilan tabiiy bog‘lanadi.</p><button className="link-button" onClick={() => toast('Pozitsiyalash briefi ochildi', 'info')}>Strategiyani ko‘rish <ArrowRight size={15} /></button></div></div></div></div>
}

function ResultsPage({ toast }) {
  const [range, setRange] = useState('30 kun')
  return <div className="results-page"><div className="page-title-row"><div><div className="eyebrow eyebrow-violet"><LineChart size={13} /> LEARNING LOOP</div><h2>Natijalarim</h2><p>AI prognozlari va real Instagram natijalari taqqoslanmoqda</p></div><button className="period-select range-large" onClick={() => setRange(range === '30 kun' ? '90 kun' : '30 kun')}><CalendarDays size={15} /> {range} <ChevronDown size={14} /></button></div><div className="results-summary-grid"><MetricCard icon={Gauge} label="Prognoz aniqligi" value="82" suffix="%" delta="5.6%" tone="violet" /><MetricCard icon={Eye} label="Real ko‘rishlar" value="284.6K" delta="18.4%" tone="mint" /><MetricCard icon={TrendingUp} label="Median Viral Score" value="73" suffix="/100" delta="8 ball" tone="blue" /><MetricCard icon={Check} label="Tavsiya bajarilgan" value="68" suffix="%" delta="12%" tone="orange" /></div><div className="prediction-card card"><div className="section-heading"><div><h3>Prognoz va real natija</h3><p>Oxirgi 8 ta joylangan video · Ko‘rishlar</p></div><div className="chart-key"><span><i className="actual" /> Real</span><span><i className="predicted" /> AI prognozi</span></div></div><PredictionChart /><div className="prediction-insight"><span><Sparkles size={15} /></span><p><b>AI o‘rganmoqda:</b> Sizning auditoriyangiz case-video formatiga prognozdan 14% yaxshiroq javob bermoqda. Keyingi kontent rejada ushbu format ulushi oshirildi.</p><button onClick={() => toast('O‘rganish modeli yangilandi', 'success')}>Batafsil <ArrowRight size={14} /></button></div></div><div className="published-videos card"><div className="section-heading"><div><h3>Joylangan videolar</h3><p>Har bir video bo‘yicha o‘rganilgan signal</p></div><button className="text-button" onClick={() => toast('Barcha natijalar yuklandi', 'info')}>Barchasini ko‘rish <ArrowRight size={15} /></button></div><div className="published-list">{[['42 soniyalik Reels’ni 29 soniyaga tushirdik', '85', '92.4K', '+18%', 'mint'], ['Reels hook formulasini copy qilmang', '74', '51.8K', '-4%', 'orange'], ['3 ta retention xatosi', '79', '64.7K', '+7%', 'violet']].map(([title, score, views, delta, tone]) => <div className="published-row" key={title}><VideoCover muted mini /><div className="published-title"><strong>{title}</strong><span>7 may · 34 soniya · Reels</span></div><span className={`tiny-score ${tone}`}>{score}</span><span className="published-views"><Eye size={14} /> {views}</span><span className={`published-delta ${delta.startsWith('+') ? 'up' : 'down'}`}>{delta} prognozga</span><button className="icon-button subtle" onClick={() => toast(`${title} natijasi ochildi`, 'info')}><ChevronRight size={17} /></button></div>)}</div></div></div>
}

function PredictionChart() {
  return <div className="prediction-chart"><div className="prediction-y"><span>100K</span><span>75K</span><span>50K</span><span>25K</span><span>0</span></div><div className="prediction-lines"><span /><span /><span /><span /><svg viewBox="0 0 670 205" preserveAspectRatio="none"><polyline points="0,167 95,131 190,148 285,92 380,129 475,74 570,104 670,48" fill="none" stroke="#b8adff" strokeWidth="3" strokeDasharray="8 8" vectorEffect="non-scaling-stroke"/><polyline points="0,170 95,139 190,156 285,64 380,141 475,52 570,111 670,29" fill="none" stroke="#7965ff" strokeWidth="3" vectorEffect="non-scaling-stroke"/>{[[0,170],[95,139],[190,156],[285,64],[380,141],[475,52],[570,111],[670,29]].map(([cx, cy]) => <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="4.5" fill="#fff" stroke="#7965ff" strokeWidth="3" />)}</svg></div><div className="prediction-x"><span>15 apr</span><span>19 apr</span><span>23 apr</span><span>27 apr</span><span>1 may</span><span>5 may</span><span>9 may</span><span>13 may</span></div></div>
}

function InsightsPage({ toast }) {
  return <div className="insights-page"><div className="page-title-row"><div><div className="eyebrow eyebrow-violet"><Sparkles size={13} /> PERSONALIZED INTELLIGENCE</div><h2>AI tavsiyalar</h2><p>Akkauntingizning oxirgi kontenti, benchmarki va bozor signallari asosida</p></div><button className="button button-secondary" onClick={() => toast('AI tavsiyalar yangilandi', 'success')}><RefreshCw size={16} /> Yangilash</button></div><div className="insights-filter"><button className="active">Barchasi <span>6</span></button><button>Video sifati <span>2</span></button><button>Strategiya <span>2</span></button><button>O‘sish <span>2</span></button></div><div className="insight-cards">{recommendationItems.map(({ icon: Icon, tag, title, body, tone }, index) => <article className={`insight-card card insight-${tone}`} key={title}><div className="insight-card-top"><span className={`recommendation-icon rec-${tone}`}><Icon size={18} /></span><span className="insight-category">{tag}</span><button className="icon-button subtle"><MoreHorizontal size={17} /></button></div><h3>{title}</h3><p>{body}</p><div className="insight-evidence"><span><BarChart3 size={14} /> Ma’lumot signali</span><strong>{index === 0 ? '8 ta video' : index === 1 ? '3 raqobatchi' : '12 ta CTA'}</strong></div><button className="link-button" onClick={() => toast('Tavsiya amaliy rejaga qo‘shildi', 'success')}>Amalga oshirish <ArrowRight size={15} /></button></article>)}<article className="insight-card card insight-blue"><div className="insight-card-top"><span className="recommendation-icon rec-blue"><Clock3 size={18} /></span><span className="insight-category">Posting vaqti</span><button className="icon-button subtle"><MoreHorizontal size={17} /></button></div><h3>Seshanba 19:00–20:00 oralig‘i eng yaxshi oynangiz</h3><p>Bu vaqtda dastlabki 30 daqiqadagi ulashish tezligi odatdagidan 1.7x yuqori.</p><div className="insight-evidence"><span><BarChart3 size={14} /> Tarixiy ma’lumot</span><strong>12 hafta</strong></div><button className="link-button" onClick={() => toast('Posting vaqti rejalashtirildi', 'success')}>Rejaga qo‘shish <ArrowRight size={15} /></button></article></div><div className="fact-legend card"><div><ShieldCheck size={19} /><span><strong>Ma’lumot shaffofligi</strong><small>Har bir xulosa qaysi turdagi signalga tayanganini ko‘ring.</small></span></div><span className="legend-label verified">Tekshirilgan ma’lumot</span><span className="legend-label ai">AI xulosasi</span><span className="legend-label context">Akkaunt tarixi</span><button className="link-button" onClick={() => toast('Ma’lumot siyosati ochildi', 'info')}>Batafsil <ArrowRight size={14} /></button></div></div>
}

function SettingsPage({ toast }) {
  const [language, setLanguage] = useState('O‘zbekcha')
  return <div className="settings-page"><div className="page-title-row"><div><div className="eyebrow eyebrow-violet"><Settings2 size={13} /> ISH MAYDONI</div><h2>Profil va sozlamalar</h2><p>Kontent tavsiyalaringiz uchun asosiy kontekst</p></div><button className="button button-primary" onClick={() => toast('O‘zgarishlar saqlandi', 'success')}><Check size={16} /> Saqlash</button></div><div className="settings-layout"><div className="settings-main"><section className="setting-section card"><div className="section-heading"><div><h3>Akkaunt profili</h3><p>AI baholashni sizning biznesingizga moslashtiradi</p></div></div><div className="profile-setting"><Avatar /><div><strong>Madina Abdullayeva</strong><span>@marketingustasi · Creator tarif</span></div><button className="button button-secondary" onClick={() => toast('Profil rasmi yangilash oynasi ochildi', 'info')}>O‘zgartirish</button></div><div className="settings-fields"><label>Faoliyat sohasi<select defaultValue="marketing"><option value="marketing">Marketing va SMM</option><option>Ta’lim</option><option>E-commerce</option><option>Xizmat</option></select></label><label>Akkaunt turi<select defaultValue="expert"><option value="expert">Ekspert blog</option><option>Shaxsiy brend</option><option>Biznes</option></select></label><label>Asosiy til<select value={language} onChange={(e) => setLanguage(e.target.value)}><option>O‘zbekcha</option><option>Русский</option><option>English</option></select></label><label>Asosiy hudud<select defaultValue="uz"><option value="uz">O‘zbekiston</option><option>Markaziy Osiyo</option><option>Global</option></select></label></div></section><section className="setting-section card"><div className="section-heading"><div><h3>Kontent maqsadi</h3><p>Reja, score va CTA tavsiyalari shu maqsadga moslashadi</p></div></div><div className="goal-options"><button className="selected"><span><TrendingUp size={18} /></span><div><strong>Organik o‘sish</strong><small>Reach, follower va brand tanilishi</small></div><Check size={17} /></button><button><span><Target size={18} /></span><div><strong>Lead va sotuv</strong><small>Direct, link click va konsultatsiya</small></div></button><button><span><MessageCircle size={18} /></span><div><strong>Hamjamiyat</strong><small>Izoh va ishonchni oshirish</small></div></button></div></section></div><aside className="settings-side"><div className="telegram-card"><span className="telegram-icon"><Send size={20} /></span><h3>Telegram boti ulangan</h3><p>Video va hisobotlarni bevosita Telegram’da oling.</p><button className="button button-dark" onClick={() => toast('Telegram bot sozlamalari ochildi', 'info')}>Botni ochish <ArrowUpRight size={15} /></button></div><div className="danger-card card"><h3>Ma’lumotlar va maxfiylik</h3><button onClick={() => toast('Ma’lumotlarni eksport qilish so‘rovi yaratildi', 'success')}>Ma’lumotlarni eksport qilish <ArrowRight size={14} /></button><button onClick={() => toast('Instagram ulash oynasi ochildi', 'info')}>Instagram akkauntini ulash <ArrowRight size={14} /></button><button className="danger" onClick={() => toast('Bu demo muhitida o‘chirish mavjud emas', 'warning')}>Ish maydonini o‘chirish <ArrowRight size={14} /></button></div></aside></div></div>
}

function Sidebar({ active, onNavigate, collapsed, onToggle, mobileOpen, onClose }) {
  return <aside className={`sidebar ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}>
    <div className="sidebar-top"><Brand /><button className="desktop-collapse icon-button subtle" onClick={onToggle} aria-label="Panelni yig‘ish"><PanelLeftClose size={18} /></button><button className="sidebar-close icon-button subtle" onClick={onClose} aria-label="Menyuni yopish"><X size={19} /></button></div>
    <div className="sidebar-workspace"><WorkspacePicker /></div>
    <nav className="side-nav" aria-label="Asosiy navigatsiya">{navItems.map(({ id, label, icon: Icon, badge }) => <button className={`nav-item ${active === id || (id === 'analyze' && active === 'report') ? 'active' : ''}`} key={id} onClick={() => { onNavigate(id); onClose() }}><Icon size={19} /><span>{label}</span>{badge && <b>{badge}</b>}</button>)}</nav>
    <div className="sidebar-bottom"><div className="usage-card"><div><span>Creator tarif</span><strong>12 / 30</strong></div><div className="usage-bar"><i /></div><small>Bu oyda 18 ta tahlil qoldi</small><button onClick={() => onNavigate('settings')}>Tarifni boshqarish <ArrowUpRight size={13} /></button></div><button className="user-nav" onClick={() => onNavigate('settings')}><Avatar small /><span><strong>Madina A.</strong><small>Sozlamalar</small></span><ChevronRight size={15} /></button></div>
  </aside>
}

function Toast({ data, onClose }) {
  if (!data) return null
  const Icon = data.type === 'success' ? Check : data.type === 'warning' ? Info : Sparkles
  return <div className={`toast toast-${data.type || 'info'}`}><span><Icon size={16} /></span><p>{data.message}</p><button onClick={onClose} aria-label="Yopish"><X size={15} /></button></div>
}

function AdminPage() {
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_URL || '/api'}/v1/admin/summary`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('Admin API unavailable')))
      .then(setSummary).catch((cause) => setError(cause.message))
  }, [])
  return <section className="card report-summary"><div className="section-heading"><div><h3>Admin dashboard</h3><p>Persisted platform health summary from the API.</p></div></div>{error && <p>{error}</p>}{!summary && !error && <p>Yuklanmoqda…</p>}{summary && <div className="plan-kpis"><span><b>{summary.users}</b> users</span><i /><span><b>{summary.workspaces}</b> workspaces</span><i /><span><b>{summary.videos}</b> videos</span><i /><span><b>{summary.analyses}</b> analyses</span><i /><span><b>{summary.failed_analyses}</b> failed</span></div>}</section>
}

function App() {
  const [page, setPage] = useState('overview')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileMenu, setMobileMenu] = useState(false)
  const [toastData, setToastData] = useState(null)
  const titleMap = useMemo(() => ({
    overview: 'Bosh sahifa',
    analyze: 'Videoni tahlil qilish',
    report: 'Video hisoboti',
    idea: "G‘oyani tekshirish",
    plan: 'Kontent-reja',
    competitors: 'Raqobatchilar',
    results: 'Natijalarim',
    insights: 'AI tavsiyalar',
    admin: 'Admin dashboard',
    settings: 'Sozlamalar',
  }), [])

  const toast = (message, type = 'info') => {
    setToastData({ message, type })
    window.clearTimeout(window.__viralToastTimeout)
    window.__viralToastTimeout = window.setTimeout(() => setToastData(null), 3200)
  }

  const navigate = (next) => {
    setPage(next)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const headerDescription = page === 'overview' ? 'Akkauntingizdagi kontent signallari — real vaqtga yaqin' : undefined
  return <div className={`app-shell ${sidebarCollapsed ? 'sidebar-is-collapsed' : ''}`}>
    <Sidebar active={page} onNavigate={navigate} collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} mobileOpen={mobileMenu} onClose={() => setMobileMenu(false)} />
    {mobileMenu && <button className="mobile-backdrop" onClick={() => setMobileMenu(false)} aria-label="Menyuni yopish" />}
    <main className="main-area">
      <Header title={titleMap[page]} description={headerDescription} onMenu={() => setMobileMenu(true)}>
        <button className="header-search" onClick={() => toast('Qidiruv tez orada qo‘shiladi', 'info')}><Search size={17} /><span>Qidirish</span><kbd>⌘ K</kbd></button>
        <button className="icon-button notification-button" onClick={() => toast('Yangi bildirishnomalar yo‘q', 'info')} aria-label="Bildirishnomalar"><Bell size={19} /><i /></button>
        <Avatar small />
      </Header>
      <div className="page-content">
        {page === 'overview' && <Overview goTo={navigate} />}
        {page === 'analyze' && <UploadPage goTo={navigate} toast={toast} />}
        {page === 'report' && <ReportPage toast={toast} />}
        {page === 'idea' && <IdeaPage toast={toast} />}
        {page === 'plan' && <PlanPage toast={toast} />}
        {page === 'competitors' && <CompetitorsPage toast={toast} />}
        {page === 'results' && <ResultsPage toast={toast} />}
        {page === 'insights' && <InsightsPage toast={toast} />}
        {page === 'admin' && <AdminPage />}
        {page === 'settings' && <SettingsPage toast={toast} />}
      </div>
    </main>
    <Toast data={toastData} onClose={() => setToastData(null)} />
  </div>
}

export default App
