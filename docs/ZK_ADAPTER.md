# ZK Adapter

## Protocol

Adapter از ZK Standalone TCP protocol استفاده می‌کند و برای دستگاه‌های ZK/OEM روی TCP port `4370` طراحی شده است. تشخیص معتبر از handshake پروتکلی می‌آید، نه صرفاً بازبودن پورت.

## Read operations

پیاده‌سازی فعلی read-only/operational این موارد را پوشش می‌دهد:

- اتصال و تست session
- firmware، serial، platform، device name، OEM vendor و MAC
- device time
- شمارنده کاربران، attendance، fingerprint و face از `GET_FREE_SIZES`
- users و attendance records
- fingerprint/face/card/password evidence در capability matrix
- realtime registration stream در سطح adapter

اطلاعات خام دستگاه در `raw_device_info`/raw data نگهداری می‌شود و مقادیر نامشخص حدس زده نمی‌شوند.

## Synchronization

Attendance ingestion idempotent است و برای هر device یک high-water cursor نگهداری می‌کند. fingerprint دیتابیس همچنان safety net است. در صورت نامعتبرشدن cursor، full sync دستی قابل اجراست.

## Capabilities

وجود یک method به‌تنهایی به معنی `VERIFIED` نیست. `supported` از قرارداد adapter و `verified` از پاسخ واقعی دستگاه تعیین می‌شود. عملیات write مانند delete user، clear logs و set time تا تست پذیرش واقعی `NOT_VERIFIED` باقی می‌مانند.

## Known limitations

- network parameter read/write برای همه firmwareها یکسان نیست و باید با پاسخ واقعی device تکمیل شود.
- communication-key authentication باید قبل از پذیرش دستگاه key-protected به‌صورت جداگانه verify شود.
- Generic/vendor adapters برای MVP جایگزین ZK verified نیستند.
- اگر دستگاه در شبکه قابل دسترسی نباشد، refresh به‌جای تولید داده ساختگی، وضعیت خطا و transport detail برمی‌گرداند.
