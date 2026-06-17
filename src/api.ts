export type ApiAlbum = {
  id: string
  title: string
  artist: string
  year: string | null
  cover_tone: string
  track_count: number
  cover_image_url: string | null
}

export type ApiTrack = {
  id: string
  title: string
  artist: string
  album_id: string
  album_title: string
  duration_seconds: number
  audio_url: string | null
}

export type RoundTrack = {
  id: string
  duration_seconds: number
  audio_url: string | null
  title?: string
}

export type GameRound = {
  id: string
  status: 'playing' | 'won' | 'lost'
  clip_seconds: number
  attempts_used: number
  attempts_left: number
  max_attempts: number
  hint_available: boolean
  guesses: string[]
  track: RoundTrack
  correct?: boolean
  message?: string
  answer?: RoundTrack
}

export type Hint = {
  title_length: number
  first_letter: string
  word_count: number
  duration_seconds: number
}

export type CreateAlbumPayload = {
  title: string
  artist: string
  year?: string
  cover_tone?: string
  tracks: Array<{
    title: string
    duration_seconds?: number
  }>
}

const API_BASE_URL = (import.meta.env.VITE_TRACKFLASH_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

export class ApiRequestError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isFormData = init.body instanceof FormData
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init.body && !isFormData ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
    },
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiRequestError(typeof payload.error === 'string' ? payload.error : 'Falha na API', response.status)
  }
  return payload as T
}

export async function getHealth() {
  return request<{ status: string; service: string }>('/health')
}

export async function listAlbums() {
  const payload = await request<{ albums: ApiAlbum[] }>('/albums')
  return payload.albums
}

export async function listTracks(albumId?: string) {
  const suffix = albumId ? `?album_id=${encodeURIComponent(albumId)}` : ''
  const payload = await request<{ tracks: ApiTrack[] }>(`/tracks${suffix}`)
  return payload.tracks
}

export async function createAlbum(album: CreateAlbumPayload) {
  const payload = await request<{ album: ApiAlbum & { tracks: ApiTrack[] } }>('/albums', {
    method: 'POST',
    body: JSON.stringify(album),
  })
  return payload.album
}

export async function uploadAlbumFiles({
  title,
  artist,
  year,
  coverTone,
  coverFile,
  files,
}: {
  title: string
  artist: string
  year?: string
  coverTone?: string
  coverFile?: File | null
  files: File[]
}) {
  const form = new FormData()
  form.append('title', title)
  form.append('artist', artist)
  if (year) form.append('year', year)
  if (coverTone) form.append('cover_tone', coverTone)
  if (coverFile) form.append('cover', coverFile)
  files.forEach((file) => form.append('files', file))
  const payload = await request<{ album: ApiAlbum & { tracks: ApiTrack[] } }>('/albums/upload', {
    method: 'POST',
    body: form,
  })
  return payload.album
}

export async function deleteAlbum(albumId: string) {
  return request<{ deleted: boolean }>(`/albums/${encodeURIComponent(albumId)}`, {
    method: 'DELETE',
  })
}

export async function addTracksToAlbum(albumId: string, files: File[]) {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  const payload = await request<{ album: ApiAlbum & { tracks: ApiTrack[] } }>(
    `/albums/${encodeURIComponent(albumId)}/tracks`,
    { method: 'POST', body: form },
  )
  return payload.album
}

export async function deleteTrack(trackId: string) {
  return request<{ deleted: boolean }>(`/tracks/${encodeURIComponent(trackId)}`, {
    method: 'DELETE',
  })
}

export async function startRound(albumId?: string) {
  const payload = await request<{ round: GameRound }>('/rounds', {
    method: 'POST',
    body: JSON.stringify(albumId ? { album_id: albumId } : {}),
  })
  return payload.round
}

export async function submitGuess(roundId: string, guess: string) {
  const payload = await request<{ round: GameRound }>(`/rounds/${roundId}/guess`, {
    method: 'POST',
    body: JSON.stringify({ guess }),
  })
  return payload.round
}

export async function getHint(roundId: string) {
  const payload = await request<{ round_id: string; hint: Hint }>(`/rounds/${roundId}/hint`)
  return payload.hint
}

export function resolveMediaUrl(path: string | null | undefined) {
  if (!path) return ''
  if (/^https?:\/\//i.test(path)) return path
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}
