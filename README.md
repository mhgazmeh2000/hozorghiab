# سامانه مدیریت و مانیتورینگ حضور و غیاب ZK

سامانه RTL فارسی برای مدیریت دستگاه‌های حضور و غیاب مبتنی بر ZK TCP. نسخه فعلی روی خواندن واقعی دستگاه، نگهداری داده، گزارش‌گیری، احراز هویت و RBAC تمرکز دارد. اطلاعاتی که از دستگاه خوانده نشده‌اند حدس زده نمی‌شوند.

## وضعیت

**IMPLEMENTED / VERIFIED / NOT_VERIFIED / NOT_SUPPORTED** به صورت صریح در کد
و داکیومنت (`docs/`) مشخص شده‌اند. تا قبل از اجرای تست روی دستگاه واقعی،
هیچ قابلیتی write-side به‌عنوان VERIFIED در نظر گرفته نمی‌شود.

## اجرای توسعه

### پیش‌نیاز
- Python 3.11+
- Node.js 20+
- (تولید) PostgreSQL 16 + Redis 7

### Backend (توسعه)

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate       # Windows
# source venv/bin/activate    # Linux/macOS
pip install -r requirements.txt
$env:DATABASE_URL = "sqlite+aiosqlite:///./attendance.db"
$env:ENVIRONMENT = "development"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

در حالت توسعه (ENVIRONMENT=development) SECRET_KEY و CREDENTIAL_ENCRYPTION_KEY
به‌صورت خودکار تولید می‌شوند و رمزهای عبور اولیه روی مقادیر توسعه تنظیم
می‌شوند (به لاگ مراجعه کنید). در محیط تولید حتماً همه متغیرها را در `.env`
تنظیم کنید.

### Frontend

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

Frontend روی `http://127.0.0.1:5173` و API از طریق پراکسی روی `http://127.0.0.1:8000`
در دسترس است.

## تولید (Docker Compose)

```powershell
copy .env.example .env
# Edit .env: set SECRET_KEY, CREDENTIAL_ENCRYPTION_KEY, POSTGRES_PASSWORD, bootstrap passwords
docker compose up -d --build
```

Compose شامل سرویس‌های PostgreSQL، Redis، API، Celery Worker، Celery Beat و
frontend است. برای migration از `alembic upgrade head` استفاده کنید.

## تست دستگاه واقعی (read-only)

از روی ماشینی که به شبکه دستگاه‌ها دسترسی دارد:

```powershell
cd backend
python test_real_devices.py
python test_real_devices.py --json --out real_device_report.json
```

این اسکریپت فقط عملیات read-only انجام می‌دهد (connect / firmware / serial / users / attendance)
و هیچ‌گونه عملیات write، clear یا restart اجرا نمی‌کند. در صورت عدم دسترسی
شبکه، مراحل به‌صورت `EXECUTION_ENVIRONMENT` گزارش می‌شوند.

## تست و build

```powershell
cd backend
python -m pytest -q
cd ../frontend
npm run build
```

## اصل داده

- `ONLINE_PROTOCOL_VERIFIED` فقط بعد از اتصال موفق پروتکلی ثبت می‌شود.
- `VERIFIED` فقط بعد از تأیید اپراتور یا خواندن کامل اطلاعات دستگاه ثبت می‌گردد.
- `PROBE_UNREACHABLE` به معنی قطعی دستگاه نیست — صرفاً یعنی از محیط اجرای فعلی
  قابل دسترسی نیست.
- `vendor` هرگز از روی پورت یا پروتکل حدس زده نمی‌شود. تا زمانی که دستگاه خودش
  OEMVendor را گزارش نکند، مقدار آن UNKNOWN باقی می‌ماند.
- عملیات write (delete_user, clear_attendance, set_time, restart, ...) تا قبل از
  تست واقعی و تأیید صریح اپراتور، غیرفعال باقی می‌مانند.

## مستندات

- [آمادگی تولید](docs/PRODUCTION_READINESS.md)
- [اتصال دستگاه واقعی](docs/REAL_DEVICE_INTEGRATION.md)
- [گزارش تست دستگاه واقعی](docs/REAL_DEVICE_TEST_REPORT.md)
- [امنیت](docs/SECURITY.md)
- [آداپتور ZK](docs/ZK_ADAPTER.md)
- [سازگاری دستگاه‌ها](docs/DEVICE_COMPATIBILITY.md)
