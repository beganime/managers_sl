# SL System — handoff for the next AI agent

Updated: 2026-10-30. This file is the short entry point; do not treat it as a replacement for the project map or production inspection.

## Start here

1. Read `AGENTS.md` from `C:\Users\ThinkPad\OneDrive\Документы\SL_system`.
2. Read `PROJECT_MAP.md`, then the relevant chapter in `docs/project-map/` and resolve the canonical checkout through `docs/project-map/sources.json`.
3. Run `git status`, record the branch and HEAD, and preserve unrelated dirty work.
4. Before a server change compare every touched file with production. Production may contain uncommitted patches that are not represented by Git HEAD.
5. Never commit `.env`, credentials, SSH/Firebase/Google/S3 keys, customer databases, media, backups or generated store artifacts.

## GitHub layout

| Component | Repository | Working branch containing the latest prepared code |
|---|---|---|
| ManagerSL web / ERP core | `beganime/managers_sl` | `rebuild-erp-core` |
| Client backend + Expo app | `beganime/clients_students_life` | `main` |
| Akyl Cheshmesi chat | `beganime/akyk-cheshmesi` | `codex/deployment-foundation` |
| TranslateSL | `beganime/translate_sl` | `codex/translate-deployment-foundation` |
| ExamSL | `beganime/exam-sl` | `codex/deployment-foundation` |
| SMTP_SL | `beganime/smtp_sl` | `codex/deployment-foundation` |
| TMmail / Mailu deployment | `beganime/tmmail.ru` | `codex/deployment-foundation` |
| Manager mobile app | `beganime/Managers_sl_Mobile` | `rebuild-mobile-v2` |

Do not merge the service branches to `main` merely to make the branch list shorter. They intentionally preserve deployment work that was not verified as a clean production replacement.

## Last completed local work

### ManagerSL

- Client workspace and card: app account provisioning/reveal, avatar, uploaded documents, Disk link, motivation profile, client direction summaries and status.
- Client app content workspace: universities/programs, news, polls and external form surveys with permissions and tests.
- Staff engagement: dashboard motivation, suggestions, staff metrics, mood support, personal Telegram notification outbox and responsive sidebar.
- Client-ready push path and Expo token support are present in the current patch.
- The malformed duplicate university directories in the local checkout were deliberately not committed.

### Client app and backend

- Mobile release is `1.0.13`.
- Compact guest and signed-in home screens, five-item bottom navigation and a four-step express application flow modeled on the public WSEC structure, but using Students Life colors/assets.
- Offline university cache/favorites, required-document packages, application status, polls/forms, news and Expo push integration.
- Backend supports secure onboarding activation, application status, news/polls/forms management and Expo notifications.
- Release notes: `RELEASE_1_0_11.md`, `RELEASE_1_0_12.md`, `RELEASE_1_0_13.md`, `IOS_RELEASE_CHECKLIST.md`.

### TranslateSL

- Canonical ManagerSL client/application links, manager identity, sync state and migration `studio.0004`.
- Manager Core integration service and dashboard updates.

### SMTP_SL

- Canonical SL-ID/application fields for mailboxes/messages and ManagerSL registry sync.
- Background sync calls the registry without storing a raw ManagerSL password.

### Manager mobile

- Finance API and screens were simplified around the unified income/expense flow.
- The old admin payments route now redirects to the consolidated finance tab.
- Dashboard, CRM, profile, workday and navigation use the current ManagerSL endpoints/configuration.

### Akyl, ExamSL and TMmail

- No new uncommitted patch existed on 2026-10-30. Their deployment branches above already existed on GitHub.

## Verification recorded before publication

- ManagerSL: 66 selected Django tests passed; `check` and migration dry-run passed under `insights_test_settings`.
- Client backend: 29 selected Django tests passed. Mobile `tsc --noEmit` passed; Android and iOS Expo exports for 1.0.13 had passed during the preceding client-app stage.
- TranslateSL: 20 tests and Django check passed; migration dry-run reported no changes.
- Manager mobile: TypeScript passed; Expo lint had zero errors and one existing axios import warning.
- SMTP_SL: Django check and the two new Manager registry tests passed. The full 78-test suite had three attachment-API failures under local Django 5.1, while the repository declares Django 6; rerun the full suite in an isolated environment created from `requirements.txt` before deployment.

## Not yet proven

- This publication is source control only. Do not infer that every commit is deployed.
- Client app 1.0.13 still needs a signed EAS Android/iOS build and real-device checks for login, document upload, chat, push, favorites/offline cache and application submission.
- SMTP_SL production runtime and ManagerSL email-registry delivery need an isolated staging test.
- Do not replace production ManagerSL, DiskSL, TranslateSL or mail services with a blind checkout. Compare live files/config and create a backup first.
- Do not disable the VPN/Xray service on `85.209.9.20`.

## Recommended next step

Build and test the client app 1.0.13 on one Android and one iPhone test account, then run a single synthetic end-to-end flow: express request → account creation → full questionnaire → document upload/review → application status → push. After that, reconcile the exact published commits against production and deploy one service at a time with rollback snapshots.
