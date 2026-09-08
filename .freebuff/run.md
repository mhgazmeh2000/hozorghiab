# Freebuff Attendance Manager — dev run doc (Windows)

Reproduces the artifacts a fresh checkout needs, then starts both servers for the live preview.
No `.env` files exist in this project — the backend runs on safe defaults
(`backend/attendance.db` SQLite, seeded users/networks on first boot, uvicorn on
`127.0.0.1:8000`). The frontend dev server runs on `127.0.0.1:5173` and proxies
`/api` and `/health` to the backend.

## 1. Reproduce uncommitted artifacts

Backend — create venv and install Python deps (first time only):

```bash
cd backend
python -m venv .venv                       # already present in this worktree
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

No `.env` is required. Database schema is created automatically at backend startup
(via `init_db()` under the SQLite dev path) and the seeder creates the admin users
and the 10 default scan networks. Default bootstrap logins (change after first login):

- `admin` / `ChangeMe-Admin-2026!`
- `operator` / `ChangeMe-Operator-2026!`
- `viewer` / `ChangeMe-Viewer-2026!`

Frontend — install npm deps (first time only):

```bash
cd frontend
npm install                                # node_modules already present
```

## 2. Run the servers

Start the backend first (detached, Windows):

```powershell
powershell -NoProfile -Command "(Start-Process -FilePath 'C:\Users\m.gazmeh\Desktop\hozorghiab\backend\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory 'C:\Users\m.gazmeh\Desktop\hozorghiab\backend' -RedirectStandardOutput '<log>' -RedirectStandardError '<log>.err' -WindowStyle Hidden -PassThru).Id"
```

Note: uvicorn on Windows spawns a worker child; treat parent+child as one server
(only the child holds the socket). Verify with `curl http://127.0.0.1:8000/health`.

Then start the frontend dev server (detached):

```powershell
powershell -NoProfile -Command "(Start-Process -FilePath 'npm.cmd' -ArgumentList 'run','dev' -RedirectStandardOutput '<log>' -RedirectStandardError '<log>.err' -WindowStyle Hidden -PassThru).Id"
```

Verify with `curl http://127.0.0.1:5173/health` (proxied → backend `{"status":"ok",...}`).

Preview URL: http://127.0.0.1:5173/

Ports: backend 8000 (default), frontend 5173 (default, from `frontend/vite.config.ts`).
Both were free when the preview was registered. If a port is taken, pass
`--port <n>` to uvicorn / set `server.port` via Vite CLI flags and update the proxy target.
