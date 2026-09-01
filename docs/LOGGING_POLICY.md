# Ra7al Application Logging & PII Protection Policy

## 1. Objectives & Scope

This policy governs the handling, filtering, and retention of application log data for the Ra7al University Bus Management System to prevent the accidental exposure of Personally Identifiable Information (PII), authentication credentials, cryptographic tokens, and system secrets.

---

## 2. Classification of Log Data

### A. ALLOWED in Logs
* Request IDs / Correlation IDs
* HTTP Method, Request Path, and Response Status Code
* Response duration / latency metrics
* Numeric Database Primary Keys (`user_id`, `trip_id`, `reservation_id`, `subscription_id`)
* Non-sensitive business event descriptions (e.g. `"Starting University Bus Management System"`, `"Subscription activated"`)
* Anonymized error categories

### B. STRICTLY FORBIDDEN in Logs
* **Plaintext Passwords & Password Hashes**
* **Dynamic OTP Codes & Verification Tokens**
* **JWT Access & Refresh Tokens** (`Bearer eyJ...`)
* **Raw QR Tokens** (`ra7al://subscription/...`)
* **Authorization Headers & Cookie Values**
* **Database & Redis Connection URLs with Credentials** (`postgresql://user:pass@host`)
* **Payment Card Data / Wallet PINs / Full Transaction Reference Tokens**
* **Complete Unfiltered Request Bodies**

---

## 3. Automated Redaction Controls

Application logs pass through [`SensitiveDataRedactionFilter`](file:///D:/M7moud/Work/Ra7al/backend/app/core/logging.py) before being emitted to `stdout` or persistent log aggregators.

The filter enforces automated regex-based scrubbing:
* `Bearer eyJ...` -> `Bearer [REDACTED_JWT]`
* `"password": "..."` -> `"password": "[REDACTED]"`
* `"otp": "..."` -> `"otp": "[REDACTED_OTP]"`
* `ra7al://subscription/...` -> `ra7al://subscription/[REDACTED_QR]`
* `postgresql://user:password@host` -> `postgresql://user:[REDACTED]@host`


---

## 4. Log Storage & Retention Standards

* **Centralization:** In production, logs are shipped via TLS to a centralized log management platform (e.g., AWS CloudWatch, Datadog, Grafana Loki).
* **Retention Period:** Maximum 90 days for operational logs; audit trail logs archived for 1 year with restricted security access.
* **Access Control:** Access to production log streams is restricted to authorized DevOps and Security leads under Role-Based Access Control (RBAC).
