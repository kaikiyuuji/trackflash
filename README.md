# TrackFlash
<img width="1310" height="549" alt="image" src="https://github.com/user-attachments/assets/60202d9c-09af-4daf-b13e-d86e1c5f4272" />

Jogo de adivinhar músicas por trechos curtos. O jogador ouve um clip do início da faixa e tenta acertar o nome. A cada erro o trecho aumenta.

## Regras

- Clipe inicial: **2 segundos**
- Progressão por erro: `2 → 4 → 7 → 11 → 16` segundos
- Máximo de erros: **5**
- Dica libera após **3 erros** — mostra primeira letra, quantidade de letras, palavras e duração
- Album e artista ficam ocultos durante toda a rodada
- Comparação de resposta ignora maiúsculas, acentos e pontuação

## Como rodar

**Frontend:**

```bash
npm run dev
```

URL: `http://127.0.0.1:5173`

**Backend:**

```bash
npm run api
```

URL: `http://127.0.0.1:8000`

**Build:**

```bash
npm run build
```

**Testes Python:**

```bash
python -m unittest backend.tests.test_domain
```

## Stack

**Frontend:** React + TypeScript + Vite

**Backend:** Python puro (stdlib), HTTP server manual, SQLite via `sqlite3`

## Endpoints

```
GET    /health
GET    /albums
POST   /albums
POST   /albums/upload
POST   /albums/{album_id}/tracks
DELETE /albums/{album_id}
DELETE /tracks/{track_id}
DELETE /library
GET    /tracks
GET    /tracks?album_id={id}
POST   /rounds
GET    /rounds/{round_id}
POST   /rounds/{round_id}/guess
GET    /rounds/{round_id}/hint
GET    /media/{arquivo}.mp3
GET    /media/{arquivo}.{jpg|png|webp}
```

## Arquivos principais

```
src/App.tsx              componentes e lógica de jogo
src/api.ts               cliente HTTP tipado
src/styles.css           design system
backend/server.py        roteamento HTTP e multipart
backend/domain.py        regras de negócio e SQLite
backend/tests/           testes unitários do domínio
backend/data/            banco SQLite (não commitado)
backend/uploads/         arquivos de mídia (não commitado)
```

## Funcionalidades

**Biblioteca:**
- Criar álbum com nome, artista, ano e capa opcional (`.jpg/.png/.webp`)
- Upload múltiplo de `.mp3` por álbum
- Adicionar faixas a álbum existente
- Remover álbum individual (remove faixas e arquivos)
- Remover faixa individual
- Limpar biblioteca inteira

**Jogo:**
- Botão play/pause no mesmo botão (sem botão extra)
- Áudio para ao iniciar nova rodada
- Campo de resposta com autocomplete por nome de faixa
- Efeitos sonoros 8-bit via Web Audio API (cliques, acerto, erro)
- Animação de confetti ao acertar

## Observações

- Arquivos `.sqlite3` e `.mp3` de uploads não são commitados (ver `.gitignore`)
- O backend não envia `artist`, `album_title` nem `album_id` na resposta da rodada
- Duração das faixas usa `180s` como fallback — detecção real do MP3 não implementada
