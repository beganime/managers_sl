# ManagerSL document disk

The disk uses SFTPGo WebClient with a private S3-compatible bucket. User
credentials are verified by ManagerSL through the internal service endpoint;
S3 credentials remain only on the services server.

Public exposure is intentionally limited to the WebClient. The SFTP and admin
interfaces are disabled. Uploads through the web interface are limited to
50 MB per file. Active sessions are refreshed for up to 12 hours, so a short
work pause does not sign the employee out.

Filesystem actions are written to a private SQLite audit log. The WebClient
shows the employee, action, virtual path and time for uploads, downloads,
renames, copies, folder changes and deletions. The audit hook uses its own
`DISK_ACTIVITY_HOOK_TOKEN`; do not reuse another integration token.

Production files:

- compose directory: `/opt/sl-services/apps/disk`
- local web port: `127.0.0.1:8110`
- local auth/provisioning bridge: `127.0.0.1:8111`
- public hostname: `disk.manager-sl.ru`
- S3 prefix: `disk/`
- Nginx HTTP config: `/etc/nginx/conf.d/disk-manager-sl.conf`

Do not commit `.env`. It contains the S3 key and the ManagerSL integration
token.

After a full applicant questionnaire is approved, ManagerSL calls the private
folder endpoint. It idempotently prepares:

`academic year / category / Full name (SL-ID) / originals | translations | contracts | universities | invitations`

The four categories are `Бюджет`, `Контракт`, `Гослиния`, and `Магистры`.
Master's applicants are categorized by their education level; all other
applicants use the funding type stored in ManagerSL.

The public endpoint requires `DISK_PROVISION_SERVICE_TOKEN`. It must be
different from `DISK_AUTH_SERVICE_TOKEN` used by SFTPGo authentication.
