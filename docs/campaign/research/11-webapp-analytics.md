---
authority: scoped
non_authoritative: true
---

# WT-11 — Web app & analytics research: operator workflows, statistics patterns, RTL/a11y

**Ticket:** WT-11 (web app and analytics research, research-only).
**Worktree:** `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-11`, branch `codex/sentinel-11-webapp-research`, pinned baseline
`e86d34b5d16abcc133ad3470c8d135d00b2423d4`.
**Access date for every URL in this document: 2026-09-29.** All retrieval was done with static `fetch`/reader extraction from this
machine (no browser session). Anything a JS-only documentation portal refused to serve is marked as such.
**Scope:** this is a scoped research catalog for the UI workstreams (WT-25/26/27). It is **not** status or design authority
(`docs/CURRENT.md` / `docs/DESIGN.md` remain the only authorities). It contains **no** competitor branding, screenshots, or
copy — patterns and information architecture only.

Evidence levels used below:

| Tag | Meaning |
|---|---|
| `[DOC]` | Official vendor documentation/PDF actually fetched and read in this ticket (static text extracted). |
| `[DOC-SPA]` | Official documentation exists at a URL we found, but the portal is JS-rendered; content **not** verified. Used only for URL/IA evidence. |
| `[SNIP]` | Search-result title/snippet only (`duckduckgo.com/html`, fetched 2026-09-29). Not treated as a behavioral claim. |
| `[SRC]` | Our own source/baseline fact, from the WT-01/WT-02 seed documents or from reading this worktree's source. |
| `[INFERENCE]` | Author's synthesis/recommendation, not a documented vendor behavior. |
| `[UNVERIFIED — browser]` | Requires a browser/a11y audit that was **not** run in this ticket. |

---

## 0. Method, and what could not be verified

* **Retrieved and read (`[DOC]`):** Milestone XProtect Smart Client 2025 R2 user manual (PDF, 6 953 extracted lines) and the
  *Export in XProtect* feature brief (PDF); Milestone 2018 R1 static Smart Client help pages (alarm manager tab, keyboard
  shortcuts); Genetec **Security Center SaaS** static help (Acknowledging alarms + index); Verkada Help (incident management,
  alert creation across products, audit logs, camera stats, device stats dashboard, people analytics, people/vehicle history
  search, camera event alerts, camera status alerts, incident-response analytics); Avigilon ACC Client Operator Guide v7.8
  (PDF, 1 374 extracted lines); Eagle Eye Networks developer docs (`events-alerts-notifications-introduction`, `events.md`,
  `video-search.md`); OpenEye knowledge base (Export Video, Video Clips, Clip Sharing in OWS, Alert History, Events/Rules/Alerts/
  Notifications, System Summary Reports, Account Activity); Envysion Learning (Intelligent Search, Saving Video and Data,
  Usage Dashboard); Axon Evidence product guide (Audit trail, Unified Audit Trail, Case share quick start); W3C WCAG 2.2 REC,
  WAI-ARIA APG Alert + Dialog(Modal) patterns, W3C i18n "Structural markup and right-to-left text in HTML", WAI Complex Images
  tutorial; npm registry + GitHub commit feeds for the OSS libraries in §4.
* **Found but not readable (`[DOC-SPA]`):** `techdocs.genetec.com` (Security Center 5.12/5.13/5.14 user guides),
  `doc.milestonesys.com` HTML bundle pages, `docs.avigilon.com` bundle pages, `support.avigilon.com` articles,
  `help.verkada.com/command/getting-started/quick-reference-guide-for-verkada-command` (body not in HTML), `support.een.com`
  portal articles. These are Zoomin/Salesforce/Zendesk-style SPAs; a static fetch returns only the shell. We say so instead of
  quoting search snippets as fact.
* **Deliberate non-goals:** no UI copying, no competitor screenshots, no phone/camera data, no paid services, no source-code
  inspection of third-party products.
* **Missing seed input:** `docs/blueprint/` in `wt-03` (the reconciled seed INDEX) did not exist when this document was written
  (checked 2026-09-29). The `F-01…F-10 → U-01…U-10` renumbering therefore comes from the campaign ticket text and the WT-02
  design map; **verify against the reconciled seed before implementing.**
* **Nothing in §3 is an accessibility certification.** No browser, screen-reader, contrast-measurement, or axe/Lighthouse run
  was performed here (the campaign forbids mid-flight repo-wide tooling). Every a11y item is a *checklist entry to test*, not a
  measured result.

---

## 1. Operator-workflow pattern catalog (real products, official docs)

### 1.1 Investigation flow: alarm/clip → context → decision → close

| Pattern | Product evidence (`[DOC]`) | Details worth copying |
|---|---|---|
| **Alarm lifecycle states** | Milestone SC 2025 R2 user manual, *Alarm states* (p. 147): "Alarms can be in one of the following states: **New**, **In progress**, **On hold**, or **Closed**… you can see the state of each alarm in the **Alarm List**, in the **State Name** column." | Four states, one column, always visible; state is what the operator changes, not a hidden attribute. |
| **Acknowledge vs assign vs purge vs bookmark** | Avigilon ACC Client Operator Guide v7.8, *Reviewing Alarms* (pp. 24–25): views **Active Alarms / Alarms Assigned to Me / Alarms Assigned to Others / Acknowledged Alarms**; per-alarm actions **Acknowledge, Assign Alarm, Unassign Alarm, Purge Alarm, Open In View, Bookmark Alarm**; "the Alarm Triggers box lists each time the alarm was triggered while the alarm was active". | Separate the *list filter* (whose alarm is it) from the *row action* (what do I do with it). Bookmark ≠ acknowledge. |
| **Notes on acknowledgement** | Avigilon, *Acknowledging Alarms*: "Once notified, click **Acknowledge**. If notes are enabled, enter any relevant details." | Acknowledgement can carry a structured free-text note. |
| **Closing requires a reason** | Milestone manual, *Get statistics on alarms* (p. 152) — alarm reports can be filtered by "**Reasons for closing**". | Closing is a first-class, *categorized* event, not a dismissal. |
| **Incident case file** | Verkada Help, *Incident Management*: "organize relevant video footage, append notes, and automatically generate incident reports"; tabs **Timeline** (clips, archive duration, notes), **People**, **Vehicles**, **Activity log**; actions: Share, Download relevant files, Change incident status, Mark active; explicit per-role permission matrix (create / view own / view all / assign owner / share / delete / close). | Case = container of clips + notes + derived entities (people/vehicles) + an **activity log**, with permissions stated in the UI. |
| **Incident assignment + loss amounts** | Envysion Learning, nav & *Saving Video and Data*: "Incident Management — Creating Incidents / Managing Incidents / **Resolving** Incidents / **Assigning** Incidents / Adding **Loss Amounts** to Incidents / Incident Notifications". | Domain-specific incident fields (loss amount) live on the incident, not in the alert. |
| **Investigating & documenting incidents explicitly** | Milestone SC manual TOC: "Investigating and documenting incidents (46) — Scenario: you discover an incident while watching live video / after it happened"; "Gathering and sharing evidence (141)". | Products document the *flow* as a first-class topic; UI copy should mirror the flow’s vocabulary. |

### 1.2 Multi-camera matrix / overview views

| Pattern | Evidence (`[DOC]`) | Details |
|---|---|---|
| **Colour-coded camera overview, red until acknowledged** | Avigilon guide, *Focus of Attention / The Overview* (pp. 16–17): each hexagon = camera; **Red = Alarms**, **Yellow = Face Watch List / People Without Masks / LPR matches / Unusual Activity**, **Teal = Video Analytic or Unusual Motion Detection**, **Blue = Motion Detection**, **Green = camera currently in the Recent Events list**, **Gray = no event**, **Colorless = camera offline**. "active alarms are displayed and cameras are highlighted in red **until the alarm is acknowledged**". | This is the single most transferable pattern for our F-01/F-02: a 1-tile-per-camera state board whose colour is a *state machine* (alarm persists until acknowledged), plus an explicit "offline" (colorless) state distinct from "no event" (gray). |
| **Video-wall / view groups as a saved object** | Milestone SC manual: "XProtect Smart Wall (66)", "Views and view items (28)", "Private and shared views (101)"; Avigilon: *Managing Views* (shared views, cycling, layouts, save/edit/rename/delete). | Matrices are **saved, named, shareable** objects, not an ad-hoc grid. |
| **Adaptive view hides inactive feeds** | Milestone *Export in XProtect* brief (p. 2): "Operators can export video from multiple cameras covering the same event by using **Adaptive View**. It highlights the most relevant camera angles by automatically hiding inactive feeds." | Reduces grid noise automatically; the operator can see *why* a tile is absent. |

### 1.3 Synchronised playback, timelines, scrub-and-jump

| Pattern | Evidence (`[DOC]`) | Details |
|---|---|---|
| **Timeline bands encode provenance** | Avigilon guide, *Playing Recorded Video with the Timeline* (pp. 6–8): coloured bars = recorded video, motion-event video, **bookmarked video**, **protected bookmarked video**, **selected search-result video**, archived video; empty areas = no recording. Zoom "in to a quarter of a second, and out to see years"; jump by day/minute/**camera event**; playback ≤ 8×. | One timeline whose bands answer "what exists here?" before the operator scrubs. Our `minuteHeatBuckets` is a weak cousin; bands should distinguish alert vs clip vs no-data. |
| **Synchronised playback across tabs** | Avigilon, *Synchronizing Recorded Video Playback* (pp. 8–9): per-timeline sync toggle; "Tabs can only be synchronized to one time. You cannot synchronize groups of tabs to separate times." New tabs only, unless individually synced. | Explicit, per-view sync with a *stated limitation* in the doc. |
| **Instant replay presets** | Avigilon, *Using Instant Replay* (p. 9): right-click → **Replay – 30 / 60 / 90 seconds**. | One-click "show me what just happened", with fixed, predictable windows. |
| **Search results are marks on the timeline; playback skips gaps** | Envysion Learning, *Intelligent Search*: "The **orange** [marks] on the timeline shows all results found. Video playback will jump gaps and go to the next segment of video with results"; controls: full screen, snapshot, save clip, copy link, change playback rate, frame-step, pause, jump back 15 s. | Search results and playback are the same surface; a "skip to next hit" toggle is the core review accelerator. |
| **Detection-moment overlay replay** | `[SRC]` our `components/incident-replay.tsx` + `lib/live-visual-state.ts` project detection boxes at the detection moment (±0.7 s). | Already ahead of ACC7 here; the ACC7 gap we should close is *timeline marks for results* and *gap-skipping*. |

### 1.4 Evidence export, chain of custody, and legal packaging

| Pattern | Evidence (`[DOC]`) | Details |
|---|---|---|
| **Export list builder, then settings, then hand-off** | Milestone *Export in XProtect* brief: search → preview (inline/detached/full-screen) → **add to export list** → choose format (native XProtect or MP4), apply privacy masks, enable encryption → download/share; "Building an export list, preview clips, and configure export settings in one place"; export several cameras into **one file** ("a cohesive narrative"). | Evidence packaging is a *staged wizard over a persistent list*, not a single “download” button. |
| **Deletion protection during investigation (Evidence Lock)** | Milestone SC manual, *Evidence locks* (pp. 211–217): protects sequences from manual **and automatic** deletion for a defined duration; add/edit/delete; **Evidence lock list** with sort/filter/search; "Keep evidence lock for"; per-run **status messages** (what went well / what did not); evidence locks can be **added to the export list**; *Video restrictions* vs *Evidence locks* explicitly contrasted (restrict viewing vs prevent deletion). | Two different protections must not be conflated in UI copy: **who may view** ≠ **what may be deleted**. Milestone also reports partial success ("Details") rather than a binary OK. |
| **Immutable, per-item audit with UUID traceability** | Axon Evidence product guide, *Audit trail* (modified 2026-08-10): "chronological record of all interactions with a piece of evidence"; event list includes viewed / downloaded / shared / **bookmarks updated, downloaded, edited, removed** / retention level updated / **evidence flag updated** / deleted; "audit events include unique identifiers (**UUIDs**) for cases and evidence… to support verification and traceability when titles change"; export as PDF with **Audit Period (defaults to 2 weeks)** and an "include confidential activity" checkbox. | Every evidence object needs a stable id *and* a human title, because titles change; the audit must survive renames. |
| **Share-with-expiry and per-recipient telemetry** | OpenEye KB, *Clip Sharing in the OWS Server Software Web Client*: after sharing, the clip shows **Shared To**, **Views** (count), **Downloads** (count), a share checkbox, and an **Expiration** date ("Date that the video clip will no longer be viewable"). | Chain-of-custody *and* least-privilege in one panel: who can see it, how often it was seen, when access dies. |
| **Case share by reference vs copy** | Axon guide, *Case share quick start*: "Share partner access (case share **by reference**) … Recipients can view and download the evidence directly from your Axon Evidence system" vs "Share a **copy** of a case". | Distinguish "link to our master" from "dispatched duplicate" in the UI; they have different custody semantics. |
| **Container format choice + client-side player** | Milestone: native XProtect format vs MP4; the native format is played by *XProtect Smart Client – Player* for external parties ("operators and authorities… outside your organization who receive exported video"). | Decide explicitly whether exports must be playable by a non-authenticated third party. |

### 1.5 Notification handling, ack/mute, and rate discipline

| Pattern | Evidence (`[DOC]`) | Details |
|---|---|---|
| **Schedule → recipients → per-recipient channel → device action** | Verkada Help, *Create Alerts Across Verkada Products*: wizard steps **Events → Notification Schedule** ("specify the days and times… Alerts generate 24/7 by default") **→ Notification** (add users or groups; per-user notification method: push, SMS, messaging) **→ optional Device Action** (horn speaker: text-to-speech ≤ 200 chars or uploaded MP3). | Four independent axes: *when*, *who*, *how*, *physical action*. Muting one axis must not silently disable the others. |
| **Silence ≠ stop generating** | OpenEye KB, *Events, Rules, Alerts, and Notifications*: "Only alerts sent to emails, push, and client notifications will **pause** when a timed restriction is reached… **Alerts in OWS are still generated and are viewable in Alert History**"; mobile app push can be toggled off. | The honest behaviour for our UI: *muting hides the toast, never the count or the list*. |
| **Alert states: Open (Acknowledged) → Closed** | OpenEye KB, *Alert History*: filter fields **Date/Time — Last 24 Hours, Last 7 Days, Last 30 Days, Last 90 Days, Custom**; hover = thumbnail; comments shown inline; detail page has **Acknowledgement State** dropdown + Notes + hyperlinks to Location and Alert Rule; "Open (Acknowledged) alerts retain a checkbox so that a **Closed** state can be applied later. **Closed alerts can no longer be selected**."; CSV export includes the ack state and **the name of the user that changed the status**; "Alert History will retain alerts… forever"; "Closed or expired Active Alerts move to the Alert History list". | Ack is reversible, close is terminal, and the *actor* is recorded. |
| **Event-rate limits are documented** | OpenEye KB (same page): event ingest caps — "Analytics: 10 000 per day, 1 000 per hour, 100 per min; Intrusion (un-armed): 5 000 / 500 / 50". | Real systems must state their rate limits; ours should surface the equivalent (SSE queue `maxsize=128` drops silently today — `[SRC]` runtime-map R-1). |
| **Alert taxonomy is bounded and named** | OpenEye: **ten** alert types (Health, Storage Retention, Point of Sale, Motion, Sensor, Analytics, Analytics Queue, Access, Intrusion, Intrusion Zone). Verkada camera event types: person/vehicle detection, **Person of Interest**, **License Plate of Interest**, **Loitering**, **Crowd**, **Online/Offline**, **Tamper**, **Occlusion**, Helix, line crossing. | A fixed, documented enumeration is what makes filters, mutes and statistics coherent. Ours is `{Violence, Weapon}` (`[SRC]` SC-4) — smaller, but must be enumerated in one place. |
| **Active vs history split with expiry** | OpenEye, *Alert History*: Active Alerts board shows colour-coded groups with lifetime ("Health Alerts – Orange, 72 hours… until manually closed"); closed/expired alerts move to history. | Two lists with an explicit transfer rule, not one growing list. |

### 1.6 Keyboard-first operation

| Pattern | Evidence (`[DOC]`) | Details |
|---|---|---|
| **Position/numbered navigation** | Milestone 2018 R1 Smart Client help, *Keyboard shortcuts (explained)*: "**ENTER** Toggle maximized/regular display of the selected position in the view. **ALT** Select a specific view item. When using ALT, you can navigate to a view item **by typing the numbers displayed on the screen**." Shortcuts apply to the Live and Playback tabs and explicitly *do not* apply to Matrix content or static images. | Number overlays let the operator jump to tile *n* without a mouse; documented exclusions prevent surprise. |
| **A full keyboard command reference** | Avigilon guide TOC (p. 45–52): *Keyboard Commands* split into **Image Panel & Camera**, **View Tab**, **View Layout**, **Playback**, **PTZ**, **Joystick**; Milestone manual: "Default keyboard shortcuts (99)". | Reference tables by *task group*, and joystick support for PTZ. |
| **Command palette / quick search** | Verkada Help pages expose a "⌘ Ctrl k" search affordance in the doc chrome itself (noted on every help page fetched). | `[INFERENCE]` A palette is now table stakes; ours exists (`[SRC]` Ctrl/Cmd+K). |
| **Ours today** | `[SRC]` design-map §3.4: `1–7` sections, `Ctrl/Cmd+K` palette, `j`/`k`/`Enter` in the incidents queue, roving ArrowUp/Down/Home/End in the alert feed, `Escape` closes the palette; shortcuts are ignored while typing. | We have the primitives; we lack a *visible, documented* shortcut list and triage verbs (ack/bookmark/export). |

### 1.7 Audit views

| Pattern | Evidence (`[DOC]`) | Details |
|---|---|---|
| **Unified audit with actor/action/entity filters and freshness stamp** | Axon guide, *Unified Audit Trail* (modified 2026-09-22): one page combining Agency/Aware/CCTV/Evidence/Cases/Devices/Groups/ALPR trails; permission `View Unified Audit Trail`; filters **Actor** (Users, System, **API Client**, Partner, Agency, Other), **Action**, **Traditional Audit Trail**, plus entity search and date/time; all filters AND-combined; page shows "**Audit data current as of**" timestamp; UI shows ≤ **3 months**, older data only via export; export ≤3 months = immediate PDF, >3 months = **asynchronous, delivered by email**; file name pattern `UnifiedAuditTrail_Agency_From_To.pdf`. | Three things to copy: (a) an explicit *data-as-of* freshness label; (b) a documented UI retention window with an export escape hatch; (c) async export with a stated delivery channel. |
| **Audit coverage includes page views and permission-gated visibility** | OpenEye KB, *Account Activity*: "auditing device and feature changes… with precise timestamps and user identification"; categories include device/camera settings updates, **Face Detection Data Deleted**, Video Clips, and **page views** (with the enumerated list of pages: Active Alerts, Alert History, Account Activity, Video Clips, …); End Users must be in a group where Account Activity is enabled. | Audit *reads* as well as writes; and access to the audit log is itself permissioned. |
| **Audit with categories + generated reports** | Verkada Help, *Manage and View Audit Logs*: Org Admins → All Products → Admin → Security & Logs → **Audit Log**; optional **AI Search** to filter events; "default category filters to quickly view common audit log events by category… prioritize relevant data over high-volume system logs"; bulk export for "quarterly audits or long-term investigations". | Default *saved views per category* beat a raw log table. |
| **Ours today** | `[SRC]` runtime-map F-34: `GET /audit/status`, `GET /audit/recent?limit=` exist server-side; **no frontend consumer** (design-map: "all other backend routes have zero frontend callers"). | Highest value-per-effort addition available for the "audit views" requirement. |

---

## 2. Analytics / statistics patterns: what security dashboards actually count

### 2.1 Vocabulary discipline: event ≠ detection ≠ alert ≠ notification ≠ incident

* **Eagle Eye developer docs** (`[DOC]`, *Events, Alerts, and Notifications*): "An **event** could be anything that happens on the system, such as a camera disconnection or motion detection… This event triggers the generation of an **alert**, which is a reaction to the event. Depending on your notification settings, a **notification** is sent in response to this alert." Three layers, three APIs (`/events`, `/alerts`, `/notifications`), with `/notifications` exposing a **read status**.
* **Milestone** (`[DOC]`, manual *Events* p. 154): "An event… is a predefined incident that can be set up to trigger an alarm. Events are either predefined system incidents or user-defined events, for example analytics events… **Events are not necessarily linked to an alarm**."
* **OpenEye** (`[DOC]`): events carry thresholds configured in *rules*; alerts are the rule outputs; alert *types* are a fixed list of ten.
* **Ours** (`[SRC]`): we count **alerts** (SSE `LiveAlert`) and show **detections** (telemetry scores) — two different things already separated in the UI (`ConfidenceBars` vs alert list). **Recommendation:** never label an alert count "detections", and never label a detection score "alerts". Add a one-line legend into the statistics section itself listing exactly what each number counts.

### 2.2 Denominators and coverage (camera-hours)

* **Verkada Device Stats Dashboard** (`[DOC]`): **Uptime** "Shows the percentage of cameras online, offline, or down over time"; cloud-backup retention distribution; "Cameras highlighted in yellow are marked **At risk** if bandwidth limits affect the backup process"; per-camera drill-down from a metric box; **heartbeat rule** in *Camera Status Alerts*: "Verkada changes a camera's status to offline when a heartbeat is not received within **15 minutes**".
* **Verkada Camera Stats** (`[DOC]`): cloud-backup bars are explicitly tri-state — "**Dark blue** bars – data successfully backed up… **Striped** bars – data not available in the cloud (likely due to the camera being **offline & not recording**)… **Red** bars – data **pending upload**".
* **Milestone** (`[DOC]`, manual p. 239): the **System Monitor** tab "displays the health of all your XProtect VMS system components… you can instantly identify if a camera has stopped working… or is overloaded"; client CPU/RAM/GPU loads are shown.
* **OpenEye System Summary Reports** (`[DOC]`): health rules are *thresholds over a window* — "Abnormal Restart: how many unscheduled restarts occur within a **24 hour period**", "Recorder Not Reporting: enter a **threshold time**", "Connection Lost to Camera: threshold time for an offline camera", "No Recorded Video: threshold time since video last recorded"; recommended cadence "weekly or monthly… to audit recorder usage and user activity".
* **Ours today** (`[SRC]`): F-01 "active cameras" is hardcoded **"غير متاح"** and F-07 camera health is hardcoded **"غير متاح"**, honestly sourced; **but** `GET /cameras/status` and `GET /system/status` exist with zero frontend callers (runtime-map V-06, F-38).
* **Recommendation (WT-26):** define coverage explicitly before showing any rate: `coverage = observed camera-time / window time`, and expose it as **unavailable** (not zero) until `/cameras/status` is consumed. A percentage without its denominator and its window is the classic dishonest dashboard. `[INFERENCE]`

### 2.3 Time-window semantics and comparison

* **Milestone alarm statistics** (`[DOC]`, manual p. 152): fixed windows **Last 24 hours / 7 days / 30 days / 6 months / Last year**; **two graphs side by side**, each filtered by *Category / State / Priority / Reasons for closing / Site / **Response time***, each with its own sub-filter (e.g., State = *New* vs *In progress*); the result can be printed to PDF.
* **OpenEye Alert History** (`[DOC]`): **Last 24 Hours / 7 Days / 30 Days / 90 Days / Custom** + "first 300k alerts" export cap.
* **Axon Unified Audit Trail** (`[DOC]`): 3-month UI window + async export for longer ranges + "current as of" stamp.
* **Ours today** (`[SRC]`): `15m | 1h | 24h | all` over a **session buffer capped at 50 alerts** (`sentinel-store.tsx`), with an explicit footnote that statistics are session-scoped; `previousWindowCount` gives a delta against the previous equal window.
* **Recommendations (WT-26):** (a) rename `all` → **"الجلسة (حد أقصى 50)"** so the cap is visible; (b) always render `windowStart–windowEnd` next to a count; (c) keep the previous-window delta, but label it "مقارنة بالنافذة السابقة" and never draw it when the previous window is partially covered by the cap; (d) ban cross-window comparisons other than the explicit delta. `[INFERENCE]`

### 2.4 Drill-down to evidence

* **Envysion** (`[DOC]`): search hits are orange marks on the timeline; playback jumps between hits; the same screen offers snapshot, save clip, and copy link.
* **Avigilon** (`[DOC]`): *Searching → Reviewing Search Results → Saving Results*; a search result class ("selected motion or event search result video") is a distinct **timeline band colour**; bookmarks are separate bands.
* **Milestone** (`[DOC]`): search → **export list** → export; evidence locks can be **added to the export list** directly.
* **Ours today** (`[SRC]`): charts cross-filter the alert list (dimension isolation in `overview.tsx`), and F-04 has a dossier + replay + clip sidebar; but there is **no route** (G-1), so a chart segment cannot be linked/bookmarked.
* **Recommendation (WT-26):** every chart segment click should (1) apply the filter (already), (2) focus the first matching alert in the queue, and (3) expose a "فتح ملف الحادثة" action. Until routes exist (G-1), this stays in-page state. `[INFERENCE]`

### 2.5 False-positive review loops

* **Avigilon "Unusual events"** (`[DOC]`, guide pp. 16–17): filter the timeline to Unusual **Activity** / **Motion** only; choose **Anomaly Type** (All / Speed / Direction / Location); a **Rarity slider** ("Keep the slider towards the right to **reduce noise**"); a **Minimum Duration** 0–59 s (default 2 s); **Skip Play** to jump to the next event; image panels without unusual events are **dimmed**. Unusual events can be bookmarked and exported like any other.
* **Verkada guidance** (`[DOC]`, camera event alerts): "Use line crossing and loitering detection instead of **person detection** when available" — i.e. prefer narrowly-defined triggers over broad class detections to suppress noise; availability is model-gated (CF81 / 3rd-gen+).
* **OpenEye** (`[DOC]`): hard per-type event limits (analytics 100/min) and alert-rule thresholds.
* **Ours today** (`[SRC]`): thresholds/cooldowns are adjustable (`/set_threshold`, `/set_cooldown`) and the decision layer is N-of-M; but the UI has no explicit *review verdict* per alert, and no false-positive ledger.
* **Recommendation (WT-26/25):** add a session-local verdict (`تأكيد` / `إنذار كاذب`) per alert with a visible tally ("مُراجَع: N — مؤكَّد M / كاذب K") and **label it session-only**. Do **not** compute precision/recall from it: the registered evidence has **no accuracy measurement at all** (`[SRC]` runtime-map §6.2 "Accuracy/recall/precision… not demonstrated", calibration artifact absent → `calibrationStatus: "unverified"`). A dashboard that prints "دقة 96%" would be fabrication.

### 2.6 Confidence vs severity labelling discipline

* Ours (`[SRC]`): `confidence` is 0–100 with `calibrationStatus: "unverified"` (F-40: `backend/model_calibration.json` absent → defaults); severity ∈ {critical, high, medium}; the frontend validator silently drops `severity: "none"` (R-3).
* Vendors avoid percentage-only confidence for triage: Milestone/Avigilon/OpenEye all triage on **Priority/State/Alert type** with counts, not model scores; Avigilon maps *system messages* to Red/Yellow/Green with a written legend (guide p. 10).
* **Recommendation:** in UI copy use "درجة (غير معايرة)" and surface `calibrationStatus` verbatim; keep severity as the triage axis; never render a score without its scale and calibration status. `[INFERENCE]`

### 2.7 Chart accessibility beyond colour

* W3C WCAG 2.2 `1.4.1 Use of Color` (verified present in `https://www.w3.org/TR/WCAG22/`, fetched 2026-09-29) — colour must not be the only visual means of conveying information.
* W3C WAI tutorial **Complex Images** (`https://www.w3.org/WAI/tutorials/images/complex/`, fetched 2026-09-29) — provide a long description / structured equivalent for complex visuals.
* Practical patterns to adopt: numeric direct labels on bars/segments; shape or pattern fill as secondary encoding; each chart gets an equivalent **data table** toggle (`<table>` with caption + `scope`s); `aria-describedby` summary sentence ("٣ تنبيهات عنف، ٢ سلاح، في آخر ١٥ دقيقة"); donut/histogram exposed as `role="img"` with text alternative **only if** the table toggle exists. `[INFERENCE]` + `[DOC]`
* Ours today (`[SRC]`): keyboard support exists for bucket selection but **not** for camera-row hover dimming (G-5); hover cross-highlight has no keyboard equivalent for one of four charts.

### 2.8 Empty / loading / stale states

* **Axon** (`[DOC]`): "Audit data **current as of** [timestamp]" — a freshness label on data, not just a spinner.
* **Verkada** (`[DOC]`): the *striped* bar for "data not available (camera offline)" is the visual distinction between **zero** and **missing**.
* **Ours today** (`[SRC]`): `SourceVisualState = live | replay | stale | offline | loading | unverified` with Arabic labels and token colours; AlertFeed distinguishes *filtered-empty* vs *disconnected* vs *no alerts in window*; `telemetryIsStale`/`inferenceIsStale` at 5 s.
* **Recommendation:** extend the three-way distinction (no data / zero / stale) to **every chart**, not only to the feed; add an explicit "آخر تحديث" timestamp near statistics. `[INFERENCE]`

---

## 3. Accessible RTL interfaces (WCAG 2.2 AA, Arabic typography, our tokens)

### 3.1 WCAG 2.2 criteria verified in this ticket

Success-criterion names/numbers below were verified by text search against the W3C Recommendation page `https://www.w3.org/TR/WCAG22/` (fetched 2026-09-29), not from memory.

| SC | Level | Why it matters for this UI | Checklist item for WT-27/25/26 |
|---|---|---|---|
| 1.4.1 Use of Color | A | Severity/state charts and camera tiles | Every colour-coded state also carries a text label and/or icon; verify the confidence histogram legend text. |
| 1.4.3 Contrast (Minimum) | AA | Dense dark dashboard, `text-[10px]` tertiary text | Measure `--text-secondary`/`--text-tertiary` on `--surface-0..3` ≥ 4.5:1 (normal text) — `[UNVERIFIED — browser]`. |
| 1.4.11 Non-text Contrast | AA | Focus rings, chart lines, badge borders | ≥ 3:1 against adjacent colour. |
| 1.4.12 Text Spacing | AA | Arabic line-height/spacing overrides | Override user stylesheet must not clip labels. |
| 2.1.1 Keyboard | A | Incident triage must be fully operable | Extend j/k/Enter to ack/bookmark/export; verify no mouse-only action in the dossier. |
| 2.2.2 Pause, Stop, Hide | A | Sparklines, live counters, glow animations | Provide a pause for auto-updating stats; honour reduced motion. |
| 2.2.3 / 2.3.3 Animation from Interactions | AAA | Motion is optional | Already in `globals.css`; verify with `prefers-reduced-motion: reduce` that no glow/sparkline animates. |
| 2.4.3 Focus Order | A | Palette, dossier, toast | Tab order follows visual order in RTL; verify overlay focus return. |
| 2.4.7 Focus Visible | AA | Existing `focus-visible` ring uses `--signal` | Verify ring visible on `--surface-0..3` (contrast ≥ 3:1). |
| **2.4.11 Focus Not Obscured (Minimum)** | AA (2.2) | **Toasts and sticky bars can cover the focused element** | Ensure the fixed toast does not obscure the focused control; allow dismissal; consider moving it or reserving space. |
| 2.5.7 Dragging Movements | AA (2.2) | Timeline drag-to-brush (`overview-charts` pointer drag) | Provide a keyboard/numeric alternative to the drag-brush time selection. |
| **2.5.8 Target Size (Minimum)** | AA (2.2) | 24×24 px minimum for pointer targets | Check rail items, chart legends, toggle chips, row action icons. |
| 3.2.6 Consistent Help | A (2.2) | Help/system entry points | Keep one consistent location for help/status. |
| 3.3.7 Redundant Entry | A (2.2) | API key / session re-entry | Do not ask the operator to re-enter data already provided in the same process. |
| 3.3.8 Accessible Authentication (Minimum) | AA (2.2) | API-key entry (`AccessNotice`, `ApiAccess`) | No cognitive test; paste must work; no blocking of password managers. |
| 4.1.2 Name, Role, Value | A | Custom camera tiles, chart widgets | Tiles are buttons/links with accessible names, not divs with click handlers. |
| 4.1.3 Status Messages | AA | Alert toasts, connection changes | `role="status"`/`aria-live` exists; ensure *meaningful* messages and no announcement floods. |

### 3.2 Live regions and alert rates (ARIA APG)

* `https://www.w3.org/WAI/ARIA/apg/patterns/alert/` (`[DOC]`, fetched 2026-09-29): "An alert is an element that displays a brief, important message in a way that attracts the user's attention **without interrupting the user's task**. Dynamically rendered alerts are automatically announced by most screen readers."
* `https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/` (`[DOC]`): "Windows under a modal dialog are **inert**" — background must be non-interactive; focus is trapped and must return to the invoking element on close.
* Ours today (`[SRC]`): `AlertToast` uses `role="alert"`/`aria-live` assertive/polite and is suppressed on the incidents tab; palette is `role="dialog" aria-modal="true"` with Escape; critical alerts are announced through an `aria-live="assertive"` `sr-only` region.
* **Checklist (WT-27):** (1) verify focus is *not* moved by the toast (APG: don't steal focus); (2) verify the palette traps focus and **returns focus** to the trigger; (3) cap announcements — e.g. coalesce identical/rapid alerts within N seconds and always expose the count in a polite region (vendor analogue: OpenEye rate limits + "alerts still generated"); (4) never announce on mute. `[INFERENCE]`

### 3.3 Arabic typography and bidirectional layout

* **Font** (`[SRC]` design-map §3.2): `app/layout.tsx` loads `IBM_Plex_Sans_Arabic` via `next/font/google` with subsets `arabic` + `latin`, weights 400/500/600/700, `display: 'swap'`, variable `--font-arabic`; `@theme inline` maps `--font-sans`. **License verified** (`[DOC]`, `https://raw.githubusercontent.com/IBM/plex/master/LICENSE.txt`, fetched 2026-09-29): SIL Open Font License 1.1, "Copyright © 2017 IBM Corp. with Reserved Font Name 'Plex'" — free to use/embed; the reserved font name means we must not redistribute a modified copy under the name "Plex". **No font file may be committed as a weight.**
* **Bidi** (`[DOC]`, W3C i18n *Structural markup and right-to-left text in HTML*, fetched 2026-09-29): the `dir` attribute on the document element sets base direction; explicit `dir` on elements is required when data may carry a different direction.
* Ours today (`[SRC]`): `<html lang="ar" dir="rtl">`; logical properties (`start-*/end-*`, `inset-inline-start`, `ms-*/me-*`) used throughout; LTR islands are explicit (`dir="ltr"` on timeline plot, ribbon lanes, seek slider, IDs, kbd hints); `<bdi>` isolates IDs/timestamps; digits normalized to Latin and formatted `ar-SA-u-ca-gregory-nu-latn`.
* **Checklist (WT-27):** (a) test mixed strings "CAM-01 — 12:34:56" and "تنبيه alert-1738…" render without reordering; (b) keep the **video seek bar LTR** (time axis direction is a data property, not a language property) — already the case, keep it documented in the component; (c) verify timeline x-axis direction for RTL users against the operator's mental model (recommend: keep time LTR, annotate with a visible "الزمن →" label); `[INFERENCE]` (d) verify Arabic numerals render in `InstrumentValue` tabular style without shattering; (e) confirm `font-display: swap` does not cause layout shift (CLS) in the dense grid — `[UNVERIFIED — browser]`.

### 3.4 Token fit for the patterns above (no new palette)

All patterns below are expressed in **existing** tokens from `app/globals.css` (`[SRC]` design-map §3.1 / `docs/DESIGN.md`): `--surface-0..3`, `--border-hairline`, `--text-primary/secondary/tertiary`, `--signal`, `--threat-critical/high/medium`, `--cat-weapon`, `--cat-violence`, `--state-live/replay/stale/offline`, `--radius`, `--shadow-panel`, `--glow-critical`, `--motion-*`, `--ease-instrument`.

| Pattern | Token mapping | Note |
|---|---|---|
| Camera/tile live/replay/stale/offline | `--state-live/replay/stale/offline` | Already used by `ui-monitor-section.tsx`; reuse on any overview tile. |
| Severity critical/high/medium | `--threat-critical/high/medium` | Known collision: `--threat-medium` is numerically close to `--state-stale` (`[SRC]` G-5) — do **not** place them adjacent without a text label. |
| Detection category weapon/violence | `--cat-weapon`, `--cat-violence` | Keep category colour distinct from severity colour. |
| Actions/focus | `--signal` + `--signal-contrast` | Focus ring already `var(--signal)`. |
| Panels/dialogs | `--surface-1..3`, `--radius-panel`, `--shadow-panel` | Use the InstrumentPanel primitives, not new card styles. |
| Motion | `--motion-fast/base/slow`, `--ease-instrument` | Must be disabled under reduced motion. |

---

## 4. Open-source UI references: license + maintenance (measured, not asserted)

| Library / kit | Version + license (npm registry, fetched 2026-09-29) | Latest commit on default branch (GitHub `.atom` feed, fetched 2026-09-29) | Verdict for this codebase |
|---|---|---|---|
| **recharts** | 3.10.1 — **MIT** (npm `time.modified` 2026-09-21) | 2026-09-28 (`recharts/recharts@main`) | Already in use (`overview-charts.tsx` PieChart). Keep. **No new dependency needed** for the charts we plan. |
| **shadcn/ui** (CLI package `shadcn`) | 4.21.0 — **MIT** (modified 2026-09-04) | 2026-09-28 (`shadcn-ui/ui@main`) | Our repo already carries the primitives; the generator is copy-in, so licence risk is minimal. Keep the existing subset. |
| **@tremor/react** | 3.18.7 — **Apache 2.0** (modified 2025-01-13) | repo `tremorlabs/tremor` last commit **2025-10-10**; **`tremor-blocks` LICENCE = MIT** (`LICENSE.md`, fetched 2026-09-29; the repo itself last committed 2025-01-22) | Apache-2.0/MIT are compatible with our usage, but React 19 / Tailwind v4 compatibility is unverified and the npm package has been quiet since Jan 2025 → **do not adopt**; borrow patterns only. `[INFERENCE]` |
| **video.js** | 8.24.1 — **Apache-2.0** (modified 2026-09-17) | 2026-09-16 (`videojs/video.js@main`) | Only relevant if we move off MJPEG/`<video>`; currently we have a bespoke player. Adding a 400 kB-class player is not justified by this ticket → **hold**. |
| **clappr** | 0.3.13 — **BSD-3-Clause** (npm publish 2023-01-18) | repo commits 2026-09-25 (`clappr/clappr@main`) | Release cadence stale vs repository activity (last npm publish 2023) → **avoid**. |
| **vis-timeline** | 8.5.4 — **Apache-2.0 OR MIT** (modified 2026-08-12) | 2026-08-22 (`visjs/vis-timeline@master`; `main` branch does not exist) | Powerful but DOM-heavy and RTL/axis-direction risk; our timeline is small and already token-styled → **avoid**; revisit only if the timeline grows beyond a single session window. |
| **Our own primitives** | `[SRC]` | — | `components/ui/*` (55 modules, 5 imported), `AlertToast`, `InstrumentPanel`, `overview-charts.tsx` are the real design surface. Recommendation: extend these; **add no chart/player/timeline dependency in WT-25/26**. |

**Licence hygiene note:** anything MIT/Apache-2.0/BSD-3-Clause/OFL-1.1 is fine for this project (no copyleft found in the candidates). Tremor’s older npm packages must be re-checked for the "Tremor Commons Clause" if a *later* version is considered — we found **no** Commons Clause text in the artifacts we fetched (`main` repo LICENSE = plain Apache-2.0; `tremor-blocks` LICENSE.md = MIT), and we did **not** find a Commons Clause file at the path we probed (404). Do not state otherwise without a fresh check. `[DOC]` + `[UNVERIFIED]` for that specific clause.

---

## 5. Recommendations for WT-25 — incident workflow (triage states, filtering, replay, severity)

Each item: **pattern → evidence level/source → fit to our tokens/code → verification (how to prove it works)**.

**T25-1 · Four-state triage on top of our alert stream** `[DOC: Milestone alarm states; Avigilon acknowledge/assign/purge]`
Keep backend severity untouched (SC-4). Add a **session-local** triage state per alert: `جديد → قيد المعالجة → مُعلَّق → مُغلق`, plus flags `مُستلَم (acknowledged)`/`مُعيَّن لي`. Fit: a small state map in `lib/sentinel-selectors.ts` (S-12) and a status column in `alert-feed.tsx`/`incident-panel.tsx` (S-11) using `--text-secondary` for state text and `--signal` for the selected row. **Verification:** (a) unit test the reducer transitions; (b) keyboard-only run: `j/k` → `Enter` → `a`(ack) → `c`(close) updates the visible state column; (c) state is lost on reload, and the UI says so ("حالة الجلسة").

**T25-2 · Visible shortcut reference + triage verbs** `[DOC: Milestone keyboard shortcuts; Avigilon Keyboard Commands]`
Add `a` (ack), `b` (bookmark), `e` (export), `/` (focus filter), `?` (shortcut help) alongside existing `1–7`, `Ctrl/Cmd+K`, `j/k/Enter`. Fit: extend the key handler in `app/page.tsx`/`incidents-section.tsx`; render the list in the palette (already a dialog) so it is discoverable in-product. **Verification:** e2e additions mirroring the existing `tests/e2e/test_operator_flows.py` style; assert shortcuts are inert while typing in an input/`contenteditable` (existing rule).

**T25-3 · Group/dedupe and rate-cap visibility** `[DOC: OpenEye Group By + rate limits; Verkada Compound Alerts; Milestone list filters]`
Show a grouped queue: same `cameraId`+`type` within N seconds = one row with a **counter** ("×3") that expands; keep the raw alerts accessible. Fit: derived selector; badge uses `--surface-2` + `--border-hairline`. **Verification:** unit tests on the grouping function (window edges, distinct cameras not merged) and a fixture-mode visual check (`/?fixtures=1`, dev-only).

**T25-4 · Mute that never hides counts** `[DOC: OpenEye "alerts are still generated"; Milestone disable-on-event-type]`
Add a per-type mute with an explicit expiry, a visible `مكتوم` badge, and a persistent count in the section header. Never let muting zero the statistics. Fit: `CrossFilters` already models type filters; add a separate `muted` flag so filtering ≠ muting. **Verification:** with everything muted, the header count stays non-zero in fixture mode; toast suppressed but list intact.

**T25-5 · Replay with pre/post roll, gap-skip, and timeline marks** `[DOC: Avigilon instant replay 30/60/90 + jump-by-event + ¼s zoom; Envysion orange marks + gap-skip; Milestone playback tab time-selection export]`
Upgrade `IncidentReplay`: ±5 s pre/post roll around the alert (configurable), a **marker** on the scrubber at the detection moment (already projected overlays), "تخطَّ الفراغات" toggle, and speed control. Fit: reuse `lib/live-visual-state.ts` projection + `--motion-base`; keep the scrubber `dir="ltr"`. **Verification:** with a fixture clip, assert the marker time equals the alert `isoTime` offset; assert gap-skip does not cross the alert boundary; frame-step works with keyboard only.

**T25-6 · Export dialog that shows custody facts** `[DOC: Milestone export list + encryption + privacy masks; Axon audit events + UUIDs; OpenEye share expiry + view/download counts]`
When `GET /download_evidence/{id}` is invoked (202 → poll, existing), render a custody panel: `alertId` (bdi), clip `sha256`, ledger `prevHash → currentHash`, `prevHash === "GENESIS"` handling, snapshot/report hashes, and a **verification badge** driven by the actual `GET /evidence_chain/{id}` result (SC-4a). Fit: `incident-panel.tsx` `Message`/`InstrumentValue` primitives; `--state-live` for verified, `--state-stale` for unverified, `--threat-critical` for mismatch — always with text. **Verification:** with a stubbed chain that returns a broken link, the badge must read **فشل التحقق** (test with a fixture), not merely "error".

**T25-7 · Case file continuity (notes + status + activity)** `[DOC: Verkada incident tabs + activity log; Envysion incident assign/resolve + notifications]`
Ensure the dossier has: notes, linked clips (`ClipSidebar`), **status**, and an activity feed of the session actions. Fit: all client-side; no new backend. **Verification:** adding a note/status appears in the activity list with the operator's role; **label the whole activity feed as session-scoped** because no persistence endpoint exists (`[SRC]` G-10).

**T25-8 · Camera-state board with non-colour redundancy** `[DOC: Avigilon Focus of Attention colours + "red until acknowledged"; Milestone Smart Wall; Verkada video wall; EEN layouts]`
For the overview/hero, render one tile per source with: state text (from `SourceVisualState`), icon, colour token, and "unacknowledged alert" persistence (tile stays alert-coloured until acknowledged). Fit: existing `STATE_LABEL`/`STATE_COLOR` in `ui-monitor-section.tsx`. **Verification:** tiles remain distinguishable in a greyscale screenshot and with `forced-colors: active` (Windows high contrast) — `[UNVERIFIED — browser]`, to be run by the UI workstream.

**T25-9 · Explicit severity ordering rule** `[DOC: Milestone priority/reasons-for-closing; Avigilon message severity colours]`
Document and implement a single ordering: `critical > high > medium`, tie-break `newest first`, with "unalerted/low" never shown as a severity. Fit: one comparator shared by feed, queue and charts (kills the 5 duplicate severity maps `[SRC]` §2.3). **Verification:** unit test the comparator; UI shows the rule in the help list.

**T25-10 · Audit surface (cheap, high value)** `[DOC: Axon Unified Audit Trail; OpenEye Account Activity; Verkada Audit Log]`
Consume the existing `GET /audit/recent?limit=` and `GET /audit/status` (`[SRC]` F-34, currently uncalled): a table with actor/action/time, a "بيانات حتى [وقت]" freshness stamp, category default views, and export. Fit: System section (U-07), `InstrumentPanel`. **Verification:** the surface shows the same record count as the API for a given `limit`; freshness stamp updates on refresh.

---

## 6. Recommendations for WT-26 — statistics correctness (denominators, windows, camera scope, links to evidence)

**S26-1 · State what each number counts, in the UI.** `[DOC: EEN event→alert→notification; Milestone events≠alarms; OpenEye ten alert types]`
Add a legend under the statistics grid: `تنبيهات (أحداث اجتازت قاعدة الإبلاغ)`, `كشوفات (قراءات النموذج)`, `أشخاص (تتبّع)`. **Verification:** the legend text matches the selector names in code; a test asserts a person-count message does not increment the alert count (`parsePersonCountEnvelope` path).

**S26-2 · Coverage instead of a naked count.** `[DOC: Verkada uptime % + 15-min heartbeat + striped "not available" bars; Milestone System Monitor; OpenEye health thresholds]`
Either (a) consume `GET /cameras/status` (exists, unused) to compute `coverage = observed camera-time / window`, or (b) keep "غير متاح" (current honest state). Never show a rate whose denominator is hidden. **Verification:** with the endpoint returning 0 cameras, the UI shows "غير متاح" (not 0 %); with 2 cameras online for the full window, coverage = 100 % within tolerance.

**S26-3 · Window semantics in the UI.** `[DOC: Milestone 24h/7d/30d/6mo/1yr report; OpenEye 24h/7d/30d/90d/custom; Axon 3-month UI + async export]`
Render `windowStart–windowEnd`; rename `all` → session-capped; keep the previous-window delta labelled; disable the delta when the session cap truncated the previous window. **Verification:** boundary tests on `inTimeWindow`/`windowForBuckets` plus a fixture run at the 50-alert cap showing the "capped" warning.

**S26-4 · Drill-down from every chart to evidence.** `[DOC: Envysion orange marks + jump-to-result; Avigilon search-result timeline band; Milestone export list]`
Clicking a segment applies the filter **and** focuses/opens the matching dossier. **Verification:** click each of the four chart panels in fixture mode and assert the incident list contains exactly the filtered ids and the dossier opens on the first one.

**S26-5 · A review loop, honestly scoped.** `[DOC: Avigilon rarity/min-duration/skip-play; Verkada "prefer line-crossing over person detection"; OpenEye rules/thresholds]`
Add per-alert verdicts with a session tally, plus threshold/cooldown links to the existing controls. **Never** show precision/recall/accuracy: registered evidence contains no accuracy measurement and the calibration artifact is absent (`[SRC]` runtime-map §6.2, F-40). **Verification:** the panel renders "غير مُقاس" for accuracy metrics; unit test that verdict tally excludes unreviewed alerts from the denominator (denominator shown as `مُراجَع من إجمالي`).

**S26-6 · Confidence is not accuracy.** `[DOC]` (vendor triage uses priority/state, not model scores — Avigilon Overview colours, Milestone alarm states) + `[SRC]` (`calibrationStatus: "unverified"`, F-40).
Render confidence as "درجة" with the uncalibrated note; keep severity as the triage axis; never colour-only. **Verification:** grep-style test that no UI string contains "دقة"/"accuracy" next to a score; visual check that the histogram labels each band numerically.

**S26-7 · Accessible charts.** `[DOC: WCAG 1.4.1; WAI Complex Images]`
Data-table toggle per chart, `aria-describedby` summaries, direct labels, keyboard equivalents for the camera-row hover dimming. **Verification:** keyboard-only traversal of all four charts; screen-reader pass (NVDA) reading the summary sentence and the table caption — `[UNVERIFIED — browser]`.

**S26-8 · No-data vs zero vs stale on every chart.** `[DOC: Verkada striped bars; Axon "current as of" stamp]`
Each chart header shows a freshness stamp and a distinct empty state. **Verification:** force the SSE stream offline and assert each chart shows the *offline* copy rather than an empty axis; force a 6-second telemetry gap and assert the *stale* copy.

**S26-9 · Exports carry their own caveats.** `[DOC: Milestone printable alarm report with two filtered graphs + time span; OpenEye CSV with ack state + actor; Envysion CSV usage export; Axon PDF]`
The existing `GET /download_report/{id}` PDF and any statistics export must embed: window, filters, denominators, and the session-scope caveat. **Verification:** open the generated PDF and read the header block; assert the caveat string is present in the PDF text.

---

## 7. A11y/RTL checklist the UI workstreams can test against

Testable, ordered, and tied to evidence above. Items marked `[UNVERIFIED — browser]` require a real browser/AT run that this ticket did not perform.

1. **Keyboard completeness** — every action reachable by keyboard: sections (1–7), palette (Ctrl/Cmd+K), queue (j/k/Enter), triage verbs, chart selection, dossier actions, export. *(2.1.1)*
2. **Focus visibility & obscuring** — `focus-visible` ring on every interactive element; the fixed toast and any sticky bar must not cover the focused element. *(2.4.7, 2.4.11)* `[UNVERIFIED — browser]`
3. **Focus management in overlays** — palette/dialog: background inert, focus trapped, Escape closes, **focus returns** to the trigger. *(APG dialog-modal)* `[UNVERIFIED — browser]`
4. **Live regions** — critical alerts assertive, others polite; coalesce announcements; muting removes the toast but the polite count region still updates; no announcement steals focus. *(4.1.3, APG alert)*
5. **Reduced motion** — with `prefers-reduced-motion: reduce`, no sparkline/glow/marker animation runs; toasts appear without movement. *(2.2.2, 2.3.3)*
6. **Target size** — interactive targets ≥ 24×24 px (rail items, legend chips, icon buttons, row actions). *(2.5.8)*
7. **Dragging alternative** — the drag-to-brush time window has a keyboard/numeric equivalent. *(2.5.7)*
8. **Contrast (dark tokens)** — compute ratios for `--text-primary/secondary/tertiary` on `--surface-0..3`, and for `--threat-*` badges on their backgrounds; fix or re-tone via existing tokens only. *(1.4.3, 1.4.11)* `[UNVERIFIED — browser]`
9. **Colour independence** — every state/severity/chart-series has text/shape redundancy; verify in greyscale. *(1.4.1)*
10. **RTL correctness** — logical properties only (no `left/right` layout), LTR islands declared (`dir="ltr"` on time axes/scrubber/IDs), `<bdi>` around ids/timestamps/mixed strings, Arabic-Indic digits normalized per `components/shell/locale.ts`. `[SRC]` + verify visually. `[UNVERIFIED — browser]`
11. **Arabic font integrity** — Arabic + Latin subsets loaded (`next/font`), no layout shift on swap, tabular numerals in `InstrumentValue`. *(3.1)* `[UNVERIFIED — browser]`
12. **Auth accessibility** — API-key entry: paste allowed, no cognitive puzzle, no blocker for password managers; re-auth does not re-ask for data already entered. *(3.3.7, 3.3.8)*
13. **Status messaging** — connection state changes, export progress (202 polling), and stale-data banners are announced politely with meaningful text, not just colour. *(4.1.3)*
14. **Consistent help** — one predictable location for the shortcut list/help. *(3.2.6)*

---

## 8. Gaps, limitations, and open items

1. **Genetec 5.12/5.13/5.14 Security Center user guides are JS-only portals** (`[DOC-SPA]`): we could not read *Responding to alarms*, *Alarm monitoring task*, or *Generating reports*. The Genetec evidence actually read is the **SaaS** help ("Acknowledging alarms": view and acknowledge active alarms from the **Alarms side panel**; index sections: Tiles, Maps, **Investigation** — "natural language search and filters" —, Front desk, **Reports**). Treat Genetec 5.x workflow claims as **unverified**.
2. **Milestone and Avigilon modern HTML portals are JS-only** (`[DOC-SPA]`). Milestone content came from the **official PDFs** (2025 R2 manual, Export brief) and the **2018 R1 static pages** (shortcuts, alarm manager tab); Avigilon content came from the **ACC 7.8 operator guide PDF (2020)**. **ACC 8/9 may differ**; do not cite ACC7 behaviors as current ACC8 UI without re-checking.
3. **Verkada keyboard-shortcut page body is not in the HTML** (`[DOC-SPA]`) → no Verkada shortcut claims. Verkada alert **severity/priority ranking** was not found in the fetched pages; only notification scheduling/recipients/device actions and event-type taxonomy.
4. **Eagle Eye** evidence is the **developer API documentation** (official) plus marketing pages; the customer help-centre articles are SPA-gated. No EEN video-wall UI details verified.
5. **No browser/a11y measurement in this ticket**: all §3 checklist items and every visual claim are `[UNVERIFIED — browser]`; the campaign assigns browser verification to the UI workstreams (and there is **no camera device**, so live-camera states stay unmeasurable).
6. **No accuracy/calibration data exists** in the registered evidence (`[SRC]`); therefore no statistic in WT-26 may express accuracy/precision/recall. Any such number would be fabricated.
7. **No backend persistence for triage/notes/audit-consumption**: all T25-1/7 recommendations are session-local until SC-1/backend work lands; the UI must say so.
8. **`GET /cameras/status`, `GET /system/status`, `GET /system/metrics`** exist but are unused (runtime-map F-36/F-38, N-3) and `/system/metrics` returns zeros (metrics never recorded) — S26-2 must not consume `/system/metrics` as a denominator source.
9. **Seed reconciliation pending**: `wt-03/docs/blueprint/INDEX` absent at write time; U-## mapping to verify.
10. **No competitor branding/design copying** — patterns and IA only; no screenshots captured (research-only ticket).

---

## 9. Source list (all URLs fetched 2026-09-29)

**Player/UI documentation**
- Milestone XProtect Smart Client 2025 R2 user manual (PDF) — `https://doc.milestonesys.com/sc/pdf/2025r2/en-US/MilestoneXProtectSmartClient_UserManual_en-US.pdf` — alarm states p.147; alarm list/statistics p.152; bookmarks pp.155–160; evidence locks pp.211–217; export p.220; keyboard shortcuts p.99; System Monitor p.239.
- Milestone, *Export in XProtect* feature brief (PDF) — `https://doc-be.milestonesys.com/bundle/Export_in_XProtect/raw/resource/enus/Export_in_XProtect.pdf`.
- Milestone XProtect Smart Client 2018 R1 help (static HTML) — Alarm Manager tab `https://www.milestonesys.com/globalassets/techcomm/2018-r1/sc/english-united-states/56988.htm`; keyboard shortcuts `.../633.htm`.
- Genetec Security Center SaaS Help, *Acknowledging alarms* — `https://help.securitycentersaas.genetec.cloud/en/AcknowledgingAlarms.html` (and `.../en/`).
- Genetec Security Center user guide (5.12) — `https://techdocs.genetec.com/r/en-US/Security-Center-User-Guide-5.12` (`[DOC-SPA]`, JS-only).
- Avigilon Control Center Client Operator Guide v7.8 (PDF) — `https://d8eqw8u9b6kgn.cloudfront.net/file_library/pdf/acc7/avigilon-acc-7-client-operator-guide-en.pdf`.
- Verkada Help — incident management `https://help.verkada.com/verkada-cameras/video-streaming-and-sharing/incident-management`; alert creation `https://help.verkada.com/command/organization-settings/create-alerts-across-verkada-products`; audit logs `https://help.verkada.com/command/organization-settings/manage-your-admin-page-settings/manage-and-view-audit-logs`; camera stats `https://help.verkada.com/verkada-cameras/analytics/camera-stats`; device stats `.../camera-stats/device-stats-dashboard`; people analytics `.../analytics/people-analytics`; people/vehicle history search `.../analytics/people-and-vehicle-history-search`; camera event alerts `.../analytics/create-camera-event-alerts`; camera status alerts `.../analytics/create-camera-event-alerts/camera-status-alerts`; incident-response analytics `https://help.verkada.com/incident-response/analytics/review-responses-from-command`.
- OpenEye Knowledge Base — Export Video `https://answers.openeye.net/Live%2C_Search_and_Export/Export/Export_Video`; Video Clips `.../Cloud_Web_Client/Video_Clips`; Clip Sharing (OWS server web client) `.../Export/Clip_Sharing_in_OWS/Clip_Sharing_in_the_OWS_Server_Software_Web_Client`; Alert History `https://answers.openeye.net/Configure/Alerts/Alert_History`; Events, Rules, Alerts, and Notifications `https://answers.openeye.net/Configure/Alerts/Events%2C_Rules%2C_Alerts%2C_and_Notifications`; System Summary Reports `https://answers.openeye.net/Configure/Reports/System_Summary_Reports`; Account Activity `https://answers.openeye.net/Optimize/Account_Activity`.
- Envysion Learning — Intelligent Search `https://learning.envysion.com/docs/managing-video/wvms/`; Saving Video and Data `https://learning.envysion.com/docs/reports/saving-video-and-data/`; Usage Dashboard `https://learning.envysion.com/docs/administrative-user-setup/usage-dashboard/`.
- Axon Evidence product guide — Audit trail `https://www.axon.com/help/axon-evidence/software/axon-evidence/audit-trail/audit-trail.htm`; Unified Audit Trail `https://www.axon.com/help/admin-and-it/software/admin-and-it/evidence-settings/unified-audit-trail.htm`; Case share quick start `https://www.axon.com/help/axon-evidence/software/axon-evidence/cases/share-cases/case-share-quick-start.htm`.
- Eagle Eye Networks developer docs — `https://developer.eagleeyenetworks.com/docs/events-alerts-notifications-introduction`, `.../docs/events.md`, `.../docs/video-search.md` (markdown variants served by the vendor).

**Standards / accessibility**
- WCAG 2.2 Recommendation — `https://www.w3.org/TR/WCAG22/` (SC names verified by text search).
- WAI-ARIA APG — Alert pattern `https://www.w3.org/WAI/ARIA/apg/patterns/alert/`; Dialog (Modal) `https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/`.
- W3C i18n — `https://www.w3.org/International/questions/qa-html-dir` (*Structural markup and right-to-left text in HTML*).
- WAI Tutorials — Complex Images `https://www.w3.org/WAI/tutorials/images/complex/`.
- IBM Plex licence — `https://raw.githubusercontent.com/IBM/plex/master/LICENSE.txt` (SIL OFL 1.1, RFN "Plex").

**Library licence/activity measurements**
- npm registry (license + version + last-modified): `recharts`, `video.js`, `clappr`, `vis-timeline`, `shadcn`, `@tremor/react`.
- GitHub commit feeds: `recharts/recharts@main`, `videojs/video.js@main`, `clappr/clappr@main`, `visjs/vis-timeline@master`, `shadcn-ui/ui@main`, `tremorlabs/tremor@main`, `tremorlabs/tremor-blocks@main`; tremor-blocks `LICENSE.md` = MIT.

---

## 10. Engineer hand-off (WT-25 / WT-26 / WT-27)

**WT-25 (incident workflow).** Implement T25-1…T25-10 in the S-11/S-12/S-10 file scope only. Start with the cheapest correctness wins: (1) single severity comparator + single state map; (2) session triage state with visible "session-only" labelling; (3) triage keyboard verbs + shortcut list in the existing palette; (4) custody panel driven by the real `/evidence_chain/{id}` verification result; (5) audit surface consuming `/audit/recent`. Do **not** touch SC-3/SC-4 wire formats; do not add dependencies (§4).

**WT-26 (statistics).** Implement S26-1…S26-9 in the S-13 file scope (`components/overview/*`, `lib/detection-types.ts` labels, `lib/sentinel-selectors.ts` via S-12 coordination). Non-negotiables: visible window bounds; a legend that names what each count counts; no accuracy/precision/recall numbers; coverage shown only when a denominator exists (`/cameras/status`), otherwise "غير متاح"; chart data-table toggles; freshness stamps.

**WT-27 (design system / a11y).** Adopt §7 as the test checklist. Priority order: (1) contrast measurement of `--text-*` on `--surface-*` and the `--threat-medium`/`--state-stale` collision; (2) focus-not-obscured for the toast; (3) dialog focus trap + focus return; (4) live-region coalescing; (5) reduced-motion verification; (6) target size sweep; (7) RTL/bidi spot checks; (8) auth accessibility for the API-key flow. All token work must edit `app/globals.css` and then run `npm run docs:sync` (the design snapshot is generated, `[SRC]` SC-9).

**Blueprint delta.** Features/IDs touched by these recommendations: `F-41` (frontend shell/dashboard), `F-42` (alert store/validator), `F-43` (telemetry/overlay freshness), `F-44` (clip/evidence UX), `F-34` (audit log — currently unconsumed), `F-38`/`F-36` (`/cameras/status`, `/system/status` — denominators), `F-40` (calibration status → labelling discipline). UI sections: `U-01` overview, `U-04` incidents & evidence, `U-07` system (audit), `U-08` shell (keyboard/help), `U-09` design system (a11y tokens). Shared contracts respected: `SC-3`, `SC-4`, `SC-8` unchanged; `SC-9` docs policy (`scoped_artifacts` + non-authority marker) as broadcast by DocsSeed/Main.

**Honesty statement for this document.** Every behavioral claim above is tagged with its evidence level; no vendor screenshot, copy, or code was reproduced; no accessibility or performance measurement was made in this ticket, and every such item is explicitly marked `[UNVERIFIED — browser]`. The `wt-03` reconciled seed was absent when writing (§0, §8.9).
