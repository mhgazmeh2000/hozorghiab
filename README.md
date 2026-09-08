# سامانه مدیریت و مانیتورینگ حضور و غیاب ZK

سامانه RTL فارسی برای مدیریت دستگاه‌های حضور و غیاب مبتنی بر ZK TCP. نسخه فعلی روی خواندن واقعی دستگاه، نگهداری داده، گزارش‌گیری، احراز هویت و RBAC تمرکز دارد. اطلاعاتی که از دستگاه خوانده نشده‌اند حدس زده نمی‌شوند.

## اجرای توسعه

### Backend

```powershell
cd backend
python -m pip install -r requirements.txt
$env:DATABASE_URL = "sqlite+aiosqlite:///./attendance.db"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

Frontend روی `http://127.0.0.1:5173` و API روی `http://127.0.0.1:8000` اجرا می‌شوند.

## ورود پیش‌فرض توسعه

- `admin` / `ChangeMe-Admin-2026!`
- `operator` / `ChangeMe-Operator-2026!`
- `viewer` / `ChangeMe-Viewer-2026!`

در محیط واقعی حتماً `SECRET_KEY` و رمزهای bootstrap را از طریق environment تغییر دهید.

## تست و build

```powershell
cd backend
python -m pytest -q
cd ../frontend
npm run build
```

## Docker Compose

```powershell
copy .env.example .env
docker compose up -d --build
```

Compose سرویس‌های PostgreSQL، Redis، API، worker، scheduler و frontend را تعریف می‌کند. برای production از secret manager و migration صریح Alembic استفاده کنید.

## مستندات

- [سازگاری دستگاه‌ها](docs/DEVICE_COMPATIBILITY.md)
- [راهنمای ZK Adapter](docs/ZK_ADAPTER.md)

## اصل داده

`ONLINE` فقط بعد از اتصال پروتکلی موفق ثبت می‌شود. `UNKNOWN` و `NOT_VERIFIED` به‌جای حدس‌زدن استفاده می‌شوند. عملیات write روی دستگاه تا زمان تست و تأیید واقعی، verified تلقی نمی‌شوند.
