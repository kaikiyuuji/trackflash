# TrackFlash Backend

Backend Python inicial, sem dependencias externas, com persistencia em SQLite.

## Rodar

```bash
npm run api
```

API local:

```text
http://127.0.0.1:8000
```

Variaveis opcionais:

```bash
TRACKFLASH_API_HOST=127.0.0.1
TRACKFLASH_API_PORT=8000
TRACKFLASH_DB_PATH=backend/data/trackflash.sqlite3
```

## Endpoints

- `GET /health`
- `GET /albums`
- `POST /albums`
- `POST /albums/upload` (`multipart/form-data`, campo `files` com varios `.mp3`)
- `DELETE /library`
- `GET /tracks`
- `POST /rounds`
- `GET /rounds/{round_id}`
- `POST /rounds/{round_id}/guess`
- `GET /rounds/{round_id}/hint`

## Regras implementadas

- Cada rodada sorteia uma faixa aleatoria.
- Albuns, faixas, rodadas e palpites ficam salvos em SQLite.
- Uploads `.mp3` ficam em `backend/uploads` e sao servidos por `/media/{arquivo}.mp3`.
- A rodada nao retorna album nem artista, apenas o audio e a resposta quando termina.
- A resposta fica oculta ate vencer ou perder.
- O clipe aumenta a cada erro: `2, 4, 7, 11, 16` segundos.
- O jogador perde com 5 erros.
- A dica desbloqueia depois de 3 erros.
- Comparacao de resposta ignora maiusculas, acentos e pontuacao.
