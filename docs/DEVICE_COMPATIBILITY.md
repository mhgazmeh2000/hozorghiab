# Device Compatibility

این سند وضعیت پذیرش read-only دستگاه‌های واقعی ارائه‌شده برای نسخه اول را ثبت می‌کند. مقادیر زیر بر اساس گزارش تست واقعی با `pyzk 0.9` هستند و از داده ساختگی تولید نشده‌اند.

## 172.16.0.20

| مورد | وضعیت | مقدار مشاهده‌شده |
|---|---|---|
| ZK TCP / port 4370 | VERIFIED | ZK TCP |
| Firmware | VERIFIED | Ver 6.60 Apr 27 2017 |
| Serial | VERIFIED | ADWC175060007 |
| Platform | VERIFIED | ZMM220_TFT |
| MAC | VERIFIED | 00:17:61:12:c9:b4 |
| Device time | VERIFIED | قابل دریافت |
| Users | VERIFIED | 167 / 2000 |
| Attendance | VERIFIED | 12799 / 80000, free 67201 |
| Fingerprints | VERIFIED | 168 / 2000 |
| Faces | VERIFIED | 160 / 1500 |
| Cards | VERIFIED | 9 |
| Write operations | NOT_VERIFIED | نیازمند تست جداگانه و confirmation |

Gateway `172.16.0.1` و subnet `255.255.255.0` طبق مشخصات ارائه‌شده هستند؛ تا زمانی که از خود دستگاه در runtime خوانده نشوند، source آن‌ها `USER_PROVIDED` محسوب می‌شود.

## 172.16.32.21

| مورد | وضعیت | مقدار مشاهده‌شده |
|---|---|---|
| ZK TCP / port 4370 | VERIFIED | ZK TCP |
| Firmware | VERIFIED | Ver 6.60 May 3 2016 |
| Serial | VERIFIED | 2623320414184 |
| Platform | VERIFIED | ZLM60_TFT |
| Device name | VERIFIED | MB20 |
| MAC | VERIFIED | 00:17:61:10:51:1f |
| Device time | VERIFIED | قابل دریافت |
| Users | VERIFIED | 90 / 200 |
| Attendance | VERIFIED | 38025 / 50000, free 11975 |
| Fingerprints | VERIFIED | 108 / 400 |
| Faces | VERIFIED | 83 / 200 |
| Cards | VERIFIED | 4 |
| Write operations | NOT_VERIFIED | نیازمند تست جداگانه و confirmation |

Gateway `172.16.32.1` و subnet `255.255.255.0` طبق مشخصات ارائه‌شده هستند؛ تا زمانی که از خود دستگاه در runtime خوانده نشوند، source آن‌ها `USER_PROVIDED` محسوب می‌شود.

## وضعیت فعلی محیط

این دو IP باید با adapter `zkteco` و port `4370` ثبت شوند. اگر دستگاه از محیط اجرا reachable نباشد، سیستم باید `OFFLINE`/`ERROR` و پیام transport را نشان دهد؛ اطلاعات بالا نباید به‌صورت خودکار جایگزین پاسخ runtime شوند.
