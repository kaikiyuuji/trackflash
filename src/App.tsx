import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  ApiRequestError,
  addTracksToAlbum,
  deleteAlbum,
  deleteTrack,
  getHealth,
  getHint,
  listAlbums,
  listTracks,
  resolveMediaUrl,
  startRound,
  submitGuess,
  uploadAlbumFiles,
  type ApiAlbum,
  type ApiTrack,
  type GameRound,
  type Hint,
} from './api'

type View = 'home' | 'library' | 'game'

const views: { id: View; label: string }[] = [
  { id: 'home', label: 'Inicio' },
  { id: 'library', label: 'Biblioteca' },
  { id: 'game', label: 'Jogar' },
]

function Card({
  className = '',
  label,
  right,
  children,
}: {
  className?: string
  label: string
  right?: string
  children: React.ReactNode
}) {
  return (
    <section className={`card ${className}`}>
      <span className="shine" />
      <div className="meta-row">
        <span>{label}</span>
        {right && <span>{right}</span>}
      </div>
      {children}
    </section>
  )
}

function Segments({ total, active, tone = 'orange' }: { total: number; active: number; tone?: string }) {
  return (
    <div className={`segments ${tone}`} aria-hidden="true">
      {Array.from({ length: total }, (_, index) => (
        <i key={index} className={index < active ? 'on' : ''} style={{ animationDelay: `${index * 26}ms` }} />
      ))}
    </div>
  )
}


function AlbumArt({ tone, imageUrl }: { tone: string; imageUrl?: string | null }) {
  if (imageUrl) {
    return (
      <div className={`album-art ${safeTone(tone)}`} aria-hidden="true">
        <img src={imageUrl} alt="" className="album-cover-img" />
      </div>
    )
  }
  return (
    <div className={`album-art ${safeTone(tone)}`} aria-hidden="true">
      {Array.from({ length: 36 }, (_, index) => (
        <i key={index} />
      ))}
    </div>
  )
}

function Confetti() {
  const pieces = useMemo(
    () =>
      Array.from({ length: 48 }, (_, i) => ({
        id: i,
        left: Math.random() * 100,
        delay: Math.random() * 0.6,
        duration: 1.1 + Math.random() * 0.9,
        tone: (['orange', 'green', 'blue', 'red'] as const)[i % 4],
        size: 6 + Math.floor(Math.random() * 7),
        rotate: Math.floor(Math.random() * 360),
      })),
    [],
  )
  return (
    <div className="confetti-wrap" aria-hidden="true">
      {pieces.map((p) => (
        <i
          key={p.id}
          className={`confetti-piece ${p.tone}`}
          style={{
            left: `${p.left}%`,
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.duration}s`,
            width: `${p.size}px`,
            height: `${Math.round(p.size * 0.55)}px`,
            '--rotate': `${p.rotate}deg`,
          } as React.CSSProperties}
        />
      ))}
    </div>
  )
}

function WinBurst() {
  return (
    <div className="win-burst" aria-live="polite">
      <Confetti />
      <div className="win-burst-inner">
        <Segments total={18} active={18} tone="orange" />
        <span className="win-burst-label">ACERTOU</span>
        <Segments total={18} active={18} tone="green" />
      </div>
    </div>
  )
}

function App() {
  useButtonSound()
  const [view, setView] = useState<View>('home')
  const [albums, setAlbums] = useState<ApiAlbum[]>([])
  const [tracks, setTracks] = useState<ApiTrack[]>([])
  const [apiOnline, setApiOnline] = useState(false)
  const [loadingLibrary, setLoadingLibrary] = useState(true)
  const [libraryError, setLibraryError] = useState('')
  const [round, setRound] = useState<GameRound | null>(null)
  const [guess, setGuess] = useState('')
  const [hint, setHint] = useState<Hint | null>(null)
  const [gameError, setGameError] = useState('')
  const [roundLoading, setRoundLoading] = useState(false)
  const [guessLoading, setGuessLoading] = useState(false)
  const [hintLoading, setHintLoading] = useState(false)

  async function loadLibrary() {
    setLoadingLibrary(true)
    setLibraryError('')
    try {
      const [health, nextAlbums, nextTracks] = await Promise.all([getHealth(), listAlbums(), listTracks()])
      setApiOnline(health.status === 'ok')
      setAlbums(nextAlbums)
      setTracks(nextTracks)
    } catch (error) {
      setApiOnline(apiReachable(error))
      setLibraryError(errorMessage(error))
    } finally {
      setLoadingLibrary(false)
    }
  }

  useEffect(() => {
    void loadLibrary()
  }, [])

  async function createLibraryAlbum(payload: {
    title: string
    artist: string
    year?: string
    coverTone?: string
    coverFile?: File | null
    files: File[]
  }) {
    try {
      await uploadAlbumFiles(payload)
      setApiOnline(true)
      await loadLibrary()
    } catch (error) {
      setApiOnline(apiReachable(error))
      throw error
    }
  }

  async function removeLibraryAlbum(albumId: string) {
    try {
      await deleteAlbum(albumId)
      setApiOnline(true)
      await loadLibrary()
    } catch (error) {
      setApiOnline(apiReachable(error))
      setLibraryError(errorMessage(error))
    }
  }

  async function addLibraryTracks(albumId: string, files: File[]) {
    try {
      await addTracksToAlbum(albumId, files)
      setApiOnline(true)
      await loadLibrary()
    } catch (error) {
      setApiOnline(apiReachable(error))
      throw error
    }
  }

  async function removeLibraryTrack(trackId: string) {
    try {
      await deleteTrack(trackId)
      setApiOnline(true)
      await loadLibrary()
    } catch (error) {
      setApiOnline(apiReachable(error))
      setLibraryError(errorMessage(error))
    }
  }

  async function startGameRound() {
    setView('game')
    setRoundLoading(true)
    setGameError('')
    setHint(null)
    setGuess('')
    try {
      const nextRound = await startRound()
      setRound(nextRound)
      setApiOnline(true)
    } catch (error) {
      setApiOnline(apiReachable(error))
      setGameError(errorMessage(error))
    } finally {
      setRoundLoading(false)
    }
  }

  async function handleGuessSubmit(event: FormEvent) {
    event.preventDefault()
    if (!round || !guess.trim() || round.status !== 'playing') return

    setGuessLoading(true)
    setGameError('')
    try {
      const nextRound = await submitGuess(round.id, guess)
      setRound(nextRound)
      setGuess('')
      setApiOnline(true)
    } catch (error) {
      setApiOnline(apiReachable(error))
      setGameError(errorMessage(error))
    } finally {
      setGuessLoading(false)
    }
  }

  async function requestHint() {
    if (!round) return

    setHintLoading(true)
    setGameError('')
    try {
      const nextHint = await getHint(round.id)
      setHint(nextHint)
      setApiOnline(true)
    } catch (error) {
      setApiOnline(apiReachable(error))
      setGameError(errorMessage(error))
    } finally {
      setHintLoading(false)
    }
  }

  function handleViewChange(nextView: View) {
    setView(nextView)
    if (nextView === 'game' && !round && tracks.length > 0) {
      void startGameRound()
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <span className="eyebrow">MIX LOCAL . BANCO SQLITE</span>
          <strong>TRACKFLASH</strong>
        </div>
        <nav className="view-tabs" aria-label="Telas">
          {views.map((item) => (
            <button
              key={item.id}
              className={view === item.id ? 'active' : ''}
              type="button"
              onClick={() => handleViewChange(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="top-status">
          <span>{apiOnline ? 'API ATIVA' : 'API INATIVA'}</span>
          <span className={`led ${apiOnline ? '' : 'red'}`} />
        </div>
      </header>

      {view === 'home' && (
        <HomeScreen
          albums={albums}
          tracks={tracks}
          loading={loadingLibrary}
          error={libraryError}
          onStart={() => void startGameRound()}
          onLibrary={() => setView('library')}
        />
      )}
      {view === 'library' && (
        <LibraryScreen
          albums={albums}
          tracks={tracks}
          loading={loadingLibrary}
          error={libraryError}
          onRefresh={() => void loadLibrary()}
          onCreateAlbum={createLibraryAlbum}
          onDeleteAlbum={removeLibraryAlbum}
          onAddTracks={addLibraryTracks}
          onDeleteTrack={removeLibraryTrack}
        />
      )}
      {view === 'game' && (
        <GameScreen
          tracks={tracks}
          round={round}
          guess={guess}
          hint={hint}
          error={gameError}
          roundLoading={roundLoading}
          guessLoading={guessLoading}
          hintLoading={hintLoading}
          onGuessChange={setGuess}
          onStartRound={() => void startGameRound()}
          onSubmitGuess={handleGuessSubmit}
          onHint={() => void requestHint()}
        />
      )}
    </main>
  )
}

function HomeScreen({
  albums,
  tracks,
  loading,
  error,
  onStart,
  onLibrary,
}: {
  albums: ApiAlbum[]
  tracks: ApiTrack[]
  loading: boolean
  error: string
  onStart: () => void
  onLibrary: () => void
}) {
  return (
    <section className="screen home-grid">
      <Card className="hero-card dot-grid" label="Motor do jogo" right={loading ? 'SINCRONIZANDO' : 'PRONTO'}>
        <div className="hero-copy">
          <div className="hero-mark">
            <span className="led" />
            <span>{tracks.length ? `${tracks.length} MUSICAS` : 'AGUARDANDO API'}</span>
          </div>
          <h1>TRACKFLASH</h1>
          <p>Monte uma biblioteca de albuns e dispute cada faixa em tentativas curtas.</p>
          {error && <p className="inline-alert">{error}</p>}
        </div>
        <div className="hero-actions">
          <button className="primary-btn" type="button" onClick={onStart} disabled={loading || tracks.length === 0}>
            Jogar
          </button>
          <button className="ghost-btn" type="button" onClick={onLibrary}>
            Ver biblioteca
          </button>
        </div>
      </Card>

      <Card className="metric-card" label="Álbuns" right="SQL">
        <div className="doto-number">{formatCount(albums.length)}</div>
        <span className="mono-sub">ALBUNS INSERIDOS</span>
        <Segments total={18} active={Math.min(18, albums.length * 4)} tone="green" />
      </Card>

      <Card className="metric-card" label="Músicas" right="BD">
        <div className="doto-number">{formatCount(tracks.length)}</div>
        <span className="mono-sub">MUSICAS INDEXADAS</span>
        <Segments total={18} active={Math.min(18, Math.max(1, tracks.length))} />
      </Card>

      <Card className="feed-card" label="Sessão" right="@API">
        <div className="feed-list">
          <p>
            <strong>fila:</strong> {loading ? 'sincronizando' : `${tracks.length} musicas indexadas`}
          </p>
          <p>
            <strong>modo:</strong> trecho inicial
          </p>
          <p>
            <strong>banco:</strong> sqlite persistente
          </p>
        </div>
      </Card>
    </section>
  )
}

function LibraryScreen({
  albums,
  tracks,
  loading,
  error,
  onRefresh,
  onCreateAlbum,
  onDeleteAlbum,
  onAddTracks,
  onDeleteTrack,
}: {
  albums: ApiAlbum[]
  tracks: ApiTrack[]
  loading: boolean
  error: string
  onRefresh: () => void
  onCreateAlbum: (payload: {
    title: string
    artist: string
    year?: string
    coverTone?: string
    coverFile?: File | null
    files: File[]
  }) => Promise<void>
  onDeleteAlbum: (albumId: string) => void
  onAddTracks: (albumId: string, files: File[]) => Promise<void>
  onDeleteTrack: (trackId: string) => void
}) {
  const [title, setTitle] = useState('')
  const [artist, setArtist] = useState('')
  const [year, setYear] = useState('')
  const [coverFile, setCoverFile] = useState<File | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const coverInputRef = useRef<HTMLInputElement | null>(null)
  const [expandedAlbum, setExpandedAlbum] = useState<string | null>(null)
  const [addFiles, setAddFiles] = useState<File[]>([])
  const [addingTracks, setAddingTracks] = useState(false)
  const [addError, setAddError] = useState('')
  const addFileInputRef = useRef<HTMLInputElement | null>(null)

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    setFormError('')

    if (!title.trim() || !artist.trim()) {
      setFormError('Informe o album e o artista')
      return
    }
    if (files.length === 0) {
      setFormError('Envie pelo menos um arquivo .mp3')
      return
    }
    if (files.some((file) => !file.name.toLowerCase().endsWith('.mp3'))) {
      setFormError('Apenas arquivos .mp3 sao aceitos')
      return
    }

    setSaving(true)
    try {
      await onCreateAlbum({
        title: title.trim(),
        artist: artist.trim(),
        year: year.trim() || undefined,
        coverTone: pickTone(albums.length),
        coverFile,
        files,
      })
      setTitle('')
      setArtist('')
      setYear('')
      setCoverFile(null)
      setFiles([])
      if (fileInputRef.current) fileInputRef.current.value = ''
      if (coverInputRef.current) coverInputRef.current.value = ''
    } catch (createError) {
      setFormError(errorMessage(createError))
    } finally {
      setSaving(false)
    }
  }

  async function handleAddTracks(albumId: string) {
    if (addFiles.length === 0) return
    setAddingTracks(true)
    setAddError('')
    try {
      await onAddTracks(albumId, addFiles)
      setAddFiles([])
      if (addFileInputRef.current) addFileInputRef.current.value = ''
      setExpandedAlbum(null)
    } catch (err) {
      setAddError(errorMessage(err))
    } finally {
      setAddingTracks(false)
    }
  }

  return (
    <section className="screen library-grid">
      <Card className="library-head dot-grid" label="Coleção" right={`${tracks.length} MUSICAS`}>
        <div>
          <h2>Albuns inseridos</h2>
          <p className="screen-note">Dados carregados do SQLite pela API Python.</p>
          {(error || formError) && <p className="inline-alert">{error || formError}</p>}
        </div>
        <div className="library-actions">
          <button className="ghost-btn compact" type="button" onClick={onRefresh} disabled={loading}>
            Atualizar
          </button>
        </div>
      </Card>

      <Card className="album-rack" label="Álbuns" right={`${albums.length} ALBUNS`}>
        <div className="album-grid">
          {albums.map((album) => (
            <article className="album-tile" key={album.id}>
              <AlbumArt tone={album.cover_tone} imageUrl={album.cover_image_url ? resolveMediaUrl(album.cover_image_url) : null} />
              <div>
                <h3>{album.title}</h3>
                <p>{album.artist}</p>
              </div>
              <div className="album-meta">
                <span>{album.year || 'ANO --'}</span>
                <span>{album.track_count} musicas</span>
                <span>{album.id.slice(-4).toUpperCase()}</span>
              </div>
              <div className="album-tile-actions">
                <button
                  className="ghost-btn compact small"
                  type="button"
                  onClick={() => setExpandedAlbum(expandedAlbum === album.id ? null : album.id)}
                >
                  {expandedAlbum === album.id ? 'Fechar' : 'Adicionar faixas'}
                </button>
                <button
                  className="danger-btn compact small"
                  type="button"
                  onClick={() => onDeleteAlbum(album.id)}
                >
                  Remover album
                </button>
              </div>
              {expandedAlbum === album.id && (
                <div className="add-tracks-form">
                  <label className="file-field">
                    <span>{addFiles.length ? `${addFiles.length} MP3 selecionados` : 'Selecionar MP3'}</span>
                    <input
                      ref={addFileInputRef}
                      type="file"
                      accept=".mp3,audio/mpeg"
                      multiple
                      onChange={(e) => setAddFiles(Array.from(e.target.files ?? []))}
                    />
                  </label>
                  {addError && <p className="inline-alert">{addError}</p>}
                  <button
                    className="primary-btn compact small"
                    type="button"
                    onClick={() => void handleAddTracks(album.id)}
                    disabled={addFiles.length === 0 || addingTracks}
                  >
                    {addingTracks ? 'Salvando' : 'Adicionar'}
                  </button>
                </div>
              )}
              <span className={`status-chip ${safeTone(album.cover_tone)}`}>PRONTO</span>
            </article>
          ))}
          {!albums.length && <p className="empty-state">Nenhum album carregado.</p>}
        </div>
      </Card>

      <Card className="track-index" label="Músicas" right={loading ? 'SINCRONIZANDO' : 'PRONTO'}>
        <div className="track-table">
          {tracks.map((track, index) => (
            <div className="track-row" key={track.id}>
              <span className="track-num">{String(index + 1).padStart(2, '0')}</span>
              <div>
                <strong>{track.title}</strong>
                <small>
                  {track.artist} / {track.album_title}
                </small>
              </div>
              <span>{formatDuration(track.duration_seconds)}</span>
              <span className="clip-pill">{track.album_id.slice(-4).toUpperCase()}</span>
              <button
                className="danger-btn compact small icon-btn"
                type="button"
                aria-label={`Remover ${track.title}`}
                onClick={() => onDeleteTrack(track.id)}
              >
                ✕
              </button>
            </div>
          ))}
          {!tracks.length && <p className="empty-state">Nenhuma musica disponivel.</p>}
        </div>
      </Card>

      <Card className="album-form-card" label="Inserir álbum" right="ENVIAR MP3">
        <form className="album-form" onSubmit={handleCreate}>
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Nome do album" />
          <input value={artist} onChange={(event) => setArtist(event.target.value)} placeholder="Artista" />
          <input value={year} onChange={(event) => setYear(event.target.value)} placeholder="Ano" />
          <label className="file-field">
            <span>{coverFile ? coverFile.name : 'Capa do album (opcional)'}</span>
            <input
              ref={coverInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
              onChange={(event) => setCoverFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <label className="file-field">
            <span>{files.length ? `${files.length} MP3 selecionados` : 'Selecionar arquivos MP3'}</span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".mp3,audio/mpeg"
              multiple
              onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
            />
          </label>
          <div className="file-list">
            {files.slice(0, 6).map((file) => (
              <span key={`${file.name}-${file.size}`}>{file.name}</span>
            ))}
            {files.length > 6 && <span>+{files.length - 6} more</span>}
          </div>
          <button className="primary-btn compact" type="submit" disabled={saving || files.length === 0}>
            {saving ? 'Salvando' : 'Salvar album'}
          </button>
        </form>
      </Card>
    </section>
  )
}

function GameScreen({
  tracks,
  round,
  guess,
  hint,
  error,
  roundLoading,
  guessLoading,
  hintLoading,
  onGuessChange,
  onStartRound,
  onSubmitGuess,
  onHint,
}: {
  tracks: ApiTrack[]
  round: GameRound | null
  guess: string
  hint: Hint | null
  error: string
  roundLoading: boolean
  guessLoading: boolean
  hintLoading: boolean
  onGuessChange: (guess: string) => void
  onStartRound: () => void
  onSubmitGuess: (event: FormEvent) => void
  onHint: () => void
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const stopTimerRef = useRef<number | undefined>(undefined)
  const sfxCtxRef = useRef<AudioContext | null>(null)
  const prevAttemptsRef = useRef(0)
  const clipSeconds = round?.clip_seconds ?? 2
  const heardBars = Math.max(6, Math.min(48, Math.round((clipSeconds / 16) * 48)))
  const canAnswer = Boolean(round && round.status === 'playing' && !roundLoading)
  const answerTitle = round?.answer?.title ?? round?.track.title
  const hasAudio = Boolean(round?.track.audio_url)
  const [suggestionsOpen, setSuggestionsOpen] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)
  const suggestions = useMemo(() => getTitleSuggestions(guess, tracks), [guess, tracks])

  useEffect(() => {
    return () => {
      if (stopTimerRef.current) window.clearTimeout(stopTimerRef.current)
      audioRef.current?.pause()
    }
  }, [])

  useEffect(() => {
    if (stopTimerRef.current) window.clearTimeout(stopTimerRef.current)
    audioRef.current?.pause()
    if (audioRef.current) audioRef.current.currentTime = 0
    setIsPlaying(false)
  }, [round?.id])

  function getSfxCtx() {
    const AudioContextCtor =
      window.AudioContext ||
      (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AudioContextCtor) return null
    const ctx = sfxCtxRef.current ?? new AudioContextCtor()
    sfxCtxRef.current = ctx
    if (ctx.state === 'suspended') void ctx.resume()
    return ctx
  }

  useEffect(() => {
    if (round?.status !== 'won') return
    const ctx = getSfxCtx()
    if (!ctx) return
    const now = ctx.currentTime
    const notes = [262, 330, 392, 523, 659]
    notes.forEach((freq, i) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'square'
      osc.frequency.setValueAtTime(freq, now + i * 0.11)
      gain.gain.setValueAtTime(0.0001, now + i * 0.11)
      gain.gain.exponentialRampToValueAtTime(0.045, now + i * 0.11 + 0.012)
      gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.11 + 0.22)
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start(now + i * 0.11)
      osc.stop(now + i * 0.11 + 0.25)
    })
  }, [round?.status === 'won'])

  useEffect(() => {
    if (round?.status !== 'lost') return
    const ctx = getSfxCtx()
    if (!ctx) return
    const now = ctx.currentTime
    const notes = [330, 262, 220, 165]
    notes.forEach((freq, i) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'square'
      osc.frequency.setValueAtTime(freq, now + i * 0.14)
      gain.gain.setValueAtTime(0.0001, now + i * 0.14)
      gain.gain.exponentialRampToValueAtTime(0.05, now + i * 0.14 + 0.012)
      gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.14 + 0.28)
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start(now + i * 0.14)
      osc.stop(now + i * 0.14 + 0.3)
    })
  }, [round?.status === 'lost'])

  useEffect(() => {
    if (!round || round.attempts_used === 0) {
      prevAttemptsRef.current = round?.attempts_used ?? 0
      return
    }
    if (round.attempts_used <= prevAttemptsRef.current) {
      prevAttemptsRef.current = round.attempts_used
      return
    }
    prevAttemptsRef.current = round.attempts_used

    // hit flash
    document.body.classList.remove('hit-flash')
    void document.body.offsetWidth // force reflow to restart animation
    document.body.classList.add('hit-flash')
    const t = window.setTimeout(() => document.body.classList.remove('hit-flash'), 400)

    // error beep
    const ctx = getSfxCtx()
    if (ctx) {
      const now = ctx.currentTime
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'square'
      osc.frequency.setValueAtTime(180, now)
      osc.frequency.setValueAtTime(120, now + 0.06)
      gain.gain.setValueAtTime(0.0001, now)
      gain.gain.exponentialRampToValueAtTime(0.06, now + 0.008)
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.18)
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start(now)
      osc.stop(now + 0.2)
    }

    return () => window.clearTimeout(t)
  }, [round?.attempts_used])

  function toggleClip() {
    if (!round?.track.audio_url) return

    const audio = audioRef.current ?? new Audio()
    audioRef.current = audio

    if (!audio.paused) {
      if (stopTimerRef.current) window.clearTimeout(stopTimerRef.current)
      audio.pause()
      setIsPlaying(false)
      return
    }

    if (audio.currentTime === 0) {
      audio.src = resolveMediaUrl(round.track.audio_url)
    }

    void audio.play()
    setIsPlaying(true)

    const remaining = Math.max(100, (clipSeconds - audio.currentTime) * 1000)
    stopTimerRef.current = window.setTimeout(() => {
      audio.pause()
      audio.currentTime = 0
      setIsPlaying(false)
    }, remaining)
  }

  function selectSuggestion(title: string) {
    onGuessChange(title)
    setSuggestionsOpen(false)
  }

  return (
    <section className="screen game-grid">
      <Card className="player-card dot-grid" label={round ? `Rodada ${round.id.slice(-4).toUpperCase()}` : 'Rodada --'} right={`TRECHO ${formatClip(clipSeconds)}`}>
        <div className="player-toolbar">
          <button className="primary-btn compact" type="button" onClick={onStartRound} disabled={roundLoading || tracks.length === 0}>
            {roundLoading ? 'Sorteando' : 'Nova rodada'}
          </button>
        </div>

        <div className="player-head">
          <AlbumArt tone="orange" />
          <div>
            <span className="mono-sub">ORIGEM OCULTA</span>
            <h2>{round ? 'Trecho pronto' : 'Fila aleatória'}</h2>
            <p>{round ? `Janela de audio ${formatClip(clipSeconds)}` : 'Inicie uma rodada para sortear uma musica.'}</p>
            {answerTitle && round?.status !== 'playing' && <p className="answer-reveal">Resposta: {answerTitle}</p>}
          </div>
        </div>

        <div className="transport">
          <button className={`play-btn${isPlaying ? ' playing' : ''}`} type="button" aria-label={isPlaying ? 'Pausar trecho' : 'Tocar trecho'} onClick={toggleClip} disabled={!hasAudio}>
            <span />
          </button>
          <div className="waveform" aria-hidden="true">
            {Array.from({ length: 48 }, (_, index) => (
              <i
                key={index}
                className={index < heardBars ? 'heard' : ''}
                style={{ height: `${18 + ((index * 13) % 54)}px`, animationDelay: `${index * 18}ms` }}
              />
            ))}
          </div>
          <span className="timecode">{formatClip(clipSeconds)}</span>
        </div>

        <form className="answer-panel" onSubmit={onSubmitGuess}>
          <label htmlFor="answer">Resposta</label>
          <div className="answer-row">
            <div className="suggest-wrap">
              <input
                id="answer"
                type="text"
                value={guess}
                onChange={(event) => {
                  onGuessChange(event.target.value)
                  setSuggestionsOpen(true)
                }}
                onFocus={() => setSuggestionsOpen(true)}
                onBlur={() => window.setTimeout(() => setSuggestionsOpen(false), 120)}
                placeholder={round ? 'Nome da musica' : 'Inicie uma rodada'}
                disabled={!canAnswer || guessLoading}
                autoComplete="off"
              />
              {canAnswer && suggestionsOpen && suggestions.length > 0 && (
                <div className="suggest-menu">
                  {suggestions.map((track) => (
                    <button key={track.id} type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => selectSuggestion(track.title)}>
                      {track.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button className="primary-btn compact" type="submit" disabled={!canAnswer || guessLoading || !guess.trim()}>
              {guessLoading ? 'Enviando' : 'Enviar'}
            </button>
          </div>
          {(round?.message || error) && <p className="inline-alert">{error || round?.message}</p>}
        </form>
      </Card>

      <Card className="attempt-card" label="Tentativas" right={`${round?.max_attempts ?? 5} MAX`}>
        <div className="attempt-stack">
          {[1, 2, 3, 4, 5].map((step) => {
            const used = round?.attempts_used ?? 0
            const current = round?.status === 'playing' && step === used + 1
            const guessText = round?.guesses[step - 1]
            return (
              <div key={step} className={step <= used ? 'missed' : current ? 'current' : ''}>
                <span>{String(step).padStart(2, '0')}</span>
                {guessText ? <span className="guess-text">{guessText}</span> : <i />}
              </div>
            )
          })}
        </div>
        <div className="mono-sub">{round ? `${round.attempts_left} RESTANTES` : 'AGUARDANDO RODADA'}</div>
      </Card>

      <Card className="hint-card simple-hint" label="Dica" right={round?.hint_available ? 'LIBERADA' : 'BLOQUEADA'}>
        {hint ? (
          <div className="hint-readout">
            <strong>{hint.first_letter}</strong>
            <span>{hint.title_length} letras</span>
            <span>{hint.word_count} palavras</span>
            <span>{formatDuration(hint.duration_seconds)}</span>
          </div>
        ) : null}
        <button className="ghost-btn compact" type="button" onClick={onHint} disabled={!round?.hint_available || hintLoading}>
          {hintLoading ? 'Buscando' : 'Pedir dica'}
        </button>
      </Card>

      {round?.status === 'won' && <WinBurst />}
    </section>
  )
}

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

function formatClip(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function formatCount(value: number) {
  return String(value).padStart(2, '0')
}

function getTitleSuggestions(query: string, tracks: ApiTrack[]) {
  const foldedQuery = foldSearch(query)
  const ranked = tracks
    .map((track) => {
      const foldedTitle = foldSearch(track.title)
      let score = 0
      if (!foldedQuery) score = 1
      else if (foldedTitle === foldedQuery) score = 100
      else if (foldedTitle.startsWith(foldedQuery)) score = 80
      else if (foldedTitle.includes(foldedQuery)) score = 55
      else {
        const queryParts = foldedQuery.split(' ').filter(Boolean)
        score = queryParts.reduce((total, part) => total + (foldedTitle.includes(part) ? 12 : 0), 0)
      }
      return { track, score }
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.track.title.localeCompare(b.track.title))

  const seen = new Set<string>()
  return ranked
    .map((item) => item.track)
    .filter((track) => {
      const key = foldSearch(track.title)
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .slice(0, 7)
}

function foldSearch(value: string) {
  return value
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^\w\s]/g, ' ')
    .toLowerCase()
    .trim()
    .replace(/\s+/g, ' ')
}

function useButtonSound() {
  const contextRef = useRef<AudioContext | null>(null)

  useEffect(() => {
    function playSound(event: MouseEvent) {
      const target = event.target as HTMLElement | null
      const button = target?.closest('button')
      if (!button || button.disabled) return

      const AudioContextCtor =
        window.AudioContext ||
        (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!AudioContextCtor) return

      const context = contextRef.current ?? new AudioContextCtor()
      contextRef.current = context
      if (context.state === 'suspended') void context.resume()

      const now = context.currentTime
      const notes = [196, 220, 247, 262, 294, 330, 392, 440]
      const base = notes[Math.floor(Math.random() * notes.length)]
      const osc = context.createOscillator()
      const gain = context.createGain()

      osc.type = 'square'
      osc.frequency.setValueAtTime(base, now)
      osc.frequency.setValueAtTime(base * (Math.random() > 0.5 ? 1.5 : 0.75), now + 0.035)
      gain.gain.setValueAtTime(0.0001, now)
      gain.gain.exponentialRampToValueAtTime(0.055, now + 0.006)
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.09 + Math.random() * 0.04)

      osc.connect(gain)
      gain.connect(context.destination)
      osc.start(now)
      osc.stop(now + 0.14)
    }

    document.addEventListener('click', playSound, true)
    return () => document.removeEventListener('click', playSound, true)
  }, [])
}

function safeTone(value: string) {
  return ['orange', 'green', 'blue', 'red'].includes(value) ? value : 'orange'
}

function pickTone(index: number) {
  return ['orange', 'green', 'blue', 'red'][index % 4]
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Erro inesperado na API'
}

function apiReachable(error: unknown) {
  return error instanceof ApiRequestError
}

export default App
