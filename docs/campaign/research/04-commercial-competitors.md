---
authority: scoped
non_authoritative: true
---

# WT-04 — Commercial competitors capability comparison (research catalog)

**Ticket:** WT-04 Commercial competitors (Agent 04) — research only, no runtime code changes.
**Worktree:** `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-04`, branch `codex/sentinel-04-commercial`, baseline `e86d34b5d16abcc133ad3470c8d135d00b2423d4`.
**Research date:** 2026-09-29. **All URLs below were accessed 2026-09-29** (single research session).
**Authority:** scoped campaign artifact. Not a status or design authority (`docs/CURRENT.md` / `docs/DESIGN.md` remain authoritative).
**Purpose:** capability comparison of strong commercial video-security / incident-management products against AI Sentinel's requirements, plus reusable patterns and adopt/integrate/adapt/reject reasoning. No proprietary code or branding is copied anywhere in this catalog; only observable, documented behavior and public claims are recorded.

---

## 1. Method (as executed)

### 1.1 Search categories (kept distinguishable)

- **Category A — VMS with analytics:** Milestone XProtect, Genetec Security Center, Avigilon (Motorola), Verkada, Rhombus, Arcules, Envysion.
- **Category B — AI violence/weapon detection vendors:** Actuate AI, Scylla, ZeroEyes, Ambient.ai, Cawamo, Omnilert, Hive, Plainsight, ("Owltondo" — unidentifiable, see §8).
- **Category C — incident/evidence management:** Axon Evidence (Evidence.com), Omnigo, RapidSOS.
- **Category D — adjacent capabilities (face capture quality, LPR, people counting):** Hikvision analytics pages, Dahua (uncovered), plus LPR/counting/face-blur documentation from Category A vendors (Verkada, Rhombus, Milestone LPR extension).

### 1.2 Evidence levels used per claim

`vendor claim` (marketing page, no test context) · `documented behavior` (official help/docs text describing what the product does) · `inspected implementation` · `published experiment` · `locally reproduced`. The last three levels **never apply** in this catalog: competitor products were not inspected, benchmarked, or reproduced. Independent-test references relayed by vendors (e.g. Scylla's IPVM/DoD statements) are recorded as *vendor-reported third-party claims*, not as published experiments.

### 1.3 Query log (all 2026-09-29; engines: DuckDuckGo HTML, Bing fallback, Mojeek fallback; via local fetch helper)

`Actuate AI gun detection platform official site` · `Scylla AI violence detection weapon detection official` · `ZeroEyes gun detection how it works official` · `Ambient.ai security intelligence platform official` · `Cawamo AI weapon detection video` · `ZeroEyes gun detection official site` · `Ambient.ai security intelligence platform` · `Cawamo weapon detection video AI` · `Owltondo security AI company` · `Hive Vision AI video understanding detection` · `Cawamo AI camera weapon detection startup` · `Owltondo` · `Hive AI visual models weapons detection API` · `Plainsight vision AI platform video` · `Omnilert gun detection active shooter` · `Milestone XProtect LPE video analytics people counting official` · `Genetec Security Center intrusion manager analytics official` · `Avigilon Appearance Search video analytics official` · `Verkada people counting license plate recognition face blur alarms` · `Rhombus AI weapon detection people counting LPR official` · `Axon Evidence digital evidence management chain of custody official` · `Rhombus Systems people counting license plate detection help` · `Hikvision people counting whitepaper accuracy official` · `Dahua people counting IVS heat map official` · `Omnilert gun detection platform official site` · `Hikvision people counting solution official site` · `Dahua people counting technology official`.

Primary evidence was then taken from official pages fetched directly (product pages, help-center markdown, one vendor brochure PDF). Secondary pages encountered in results (reseller pages, news articles, Crunchbase/PitchBook/LinkedIn, Startup Nation Central) are **discovery-only** and marked as such.

### 1.4 Stop rule

Expansion stopped when repeated targeted queries (weapon-detection vendors; people-counting semantics; incident workflow) stopped yielding materially new *categories* of options and only re-surfaced resellers/partners of candidates already registered. **No internet-wide coverage is claimed.** Search engines were rate-limited intermittently (DuckDuckGo HTTP 202 on bursts) and Bing returned polluted results for several obscure queries; remaining gaps are disclosed in §8.

---

## 2. AI Sentinel baseline used for comparison (from blueprint seed inputs)

Sources (read 2026-09-29): `wt-01/docs/blueprint/runtime-map.md`, `ownership-map.md`, `runtime-map-verification.md`; `wt-02/docs/blueprint/design-map.md`, `ui-contract.md`. The **reconciled seed landed mid-compilation** at `wt-03/docs/blueprint/` (branch `codex/sentinel-03-docs-gen`, commit `27c18d2`; `INDEX.md` + `index.json` ID registry read 2026-09-29). Its registered namespaces — `F-01..F-49`, `U-01..U-10`, `SC-1..SC-10`, `S-01..S-22`, `B-1..B-10`, `N-1..N-16`, `R-1..R-8` — were cross-checked against every ID referenced in this catalog and are **consistent; no ID conflicts, no new IDs allocated**. Baseline descriptions below remain derived from the wt-01/wt-02 maps that the seed fingerprints as its inputs.

### 2.1 What AI Sentinel already implements (feature IDs F-01…F-49, U-01…U-10, SC-1…SC-10)

| Capability | AI Sentinel state (verified in runtime map) |
|---|---|
| Weapon detection | F-09: ONNX YOLO, 6 classes {pistol, rifle, shotgun, knife, sword, revolver}, async thread, EMA/decay/TTL signal shaping, independent alert threshold 0.65 |
| Violence detection | F-07/F-08: SlowFast (measured) 32-frame temporal window, window-validity contract, EMA + hysteresis, stride sampling |
| Decision layer | F-14/F-15: N-of-M confirmation + cooldown, runtime-mutable policy (F-01/F-35), rule-based fusion + severity |
| Person counting | F-10: person detect + track overlay; `personCount = len(tracks)` per frame — **occupancy-style, not flow counting** |
| Evidence capture | F-21: alert clip with 5 s pre-window + 5 s post-window, strict H.264/yuv420p MP4 encode + probe verification |
| Chain of custody | F-22: SHA-256 hash-chained JSONL ledger with full-chain verification on every read (`/evidence_chain/{id}`) |
| Incident reporting | F-25 Arabic PDF report; F-28 offline facts-only Arabic report (explicitly no image analysis); F-26 remote LLM report module missing from git (B-1) |
| Multi-camera | F-03/F-06: per-camera capture workers + per-camera inference process (CAM-01/CAM-02 scale), per-camera decision layers |
| Operator UI | U-01…U-10: RTL SOC dashboard, triage queue, incident dossier + replay with overlay projection, clip sidebar, overview charts, command palette |
| Transport / streaming | F-13/F-19 MJPEG + SSE alerts/detections (SC-5); F-37 WebRTC/go2rtc **missing module, disabled** |
| Audit / auth | F-33 API-key auth (**25 of 42 routes never authorize**, R-8); F-34 audit JSONL (no frontend consumer) |
| Camera health | F-38 status enum {STARTING/OK/DEGRADED/FAILED/STOPPED/UNAVAILABLE} only |
| Face capture | F-30 `face_intel.py` fully **disconnected** (no routes); `/face/*` tests target non-existent routes |
| Offline operation | Local-only inference + local reports; file/demo replay (F-20); **no camera device exists in the campaign environment** (live gates unmeasured) |

### 2.2 What AI Sentinel lacks against the commercial bar (gap IDs used below)

- **GAP-1 Incident case workflow:** no case object with lifecycle (open/assign/attach/notes/close), no multi-clip incident timeline, no incident-level export package.
- **GAP-2 Evidence read/audit discipline:** ledger verifies integrity but evidence *views/downloads* are not audit-logged per action; no export manifest; single-process ledger only (documented limitation).
- **GAP-3 Retention & legal hold:** `clips.clip_retention_days` is inert config; nothing prunes clips/thumbnails/reports/ledger; no hold/freeze flag.
- **GAP-4 Counting/statistics semantics:** per-frame `len(tracks)` only; no in/out flow counting, occupancy trends, dwell/queue stats, or heat maps; `/system/metrics` returns zeros (N-3).
- **GAP-5 Camera image-quality health:** no blur/occlusion/tilt/low-light/field-of-view checks; health is a status enum.
- **GAP-6 Human-verification stage:** alerts are `confirmedAlert: true` on emission; no operator-ack lifecycle before dispatch.
- **GAP-7 Escalation contract:** Telegram queue only; no generic signed webhook/outbound event contract for third-party response systems.
- **GAP-8 Scene-unit detection requirements:** weapon/violence claims carry no pixel-height/PPM or camera-placement qualification; `calibrationStatus: "unverified"` everywhere (no calibration artifact).
- **GAP-9 Roles/permissions:** single admin API key; no per-user roles, no search-reason/case-number gate for sensitive searches.
- **GAP-10 Feature-naming discipline:** category API claims "X3D" while runtime loads SlowFast (F-29); `personCount`/`severity` contract mismatch risks silent client drops (R-3).

---

## 3. Candidate register

Per candidate: **ID · official URLs (accessed 2026-09-29) · product version/release context · capabilities + evidence level · weapon/violence/face · camera-quality features · latency/throughput claims with context · multi-camera · offline/degraded · incident workflow · evidence handling · reporting · analytics semantics · security model · UI patterns · hardware/environment · license/pricing · maintenance status (2026)**.

### Category A — video management systems with analytics

#### C-A1 Milestone Systems — XProtect
- **URLs (primary):** https://www.milestonesys.com/products/software/xprotect/ ; documentation portal https://doc.milestonesys.com/en-US/ (index discovered; not deep-read). Pricing page linked from product nav ("XProtect pricing"); product lifecycle page linked from support nav.
- **Version context:** current XProtect family with 4 variants (Express+, Professional+, Expert, Corporate); no single version number published on product page. Evidence level: **vendor claim** (product page).
- **Capabilities:** centralized VMS; real-time alerting combining live video + alarms + events; rules/advanced analytics-driven response automation; investigation: search by time/events/motion, **synchronized multi-camera playback**, evidence export; evidence authenticity via **digital signing of recorded/exported footage**; **Evidence Lock** (protect video/audio/metadata from deletion); **Evidence Manager** (multi-file-type evidence collection/review/sharing); LPR extension; BriefCam Video Synopsis analytics; Smart Client "single pane of glass", Smart Wall for control rooms; geographic maps; Interconnect (remote sites independent + central access) and **Federated Architecture** (hierarchical multi-XProtect); XProtect Remote Manager (central health/config); failover servers; 1,000+ third-party integrations; deployment on Husky appliance / AWS / hybrid.
- **Weapon/violence/face:** none native on the product page; analytics are partner/BriefCam-based (**vendor claim**).
- **Camera-quality features:** "market's widest choice of cameras/sensors/IoT" (device packs) — no shutter/exposure/WDR claims at software level.
- **Latency/throughput claims:** none published on the page; **do not compare**.
- **Multi-camera:** first-class (synchronized playback, Smart Wall, Interconnect/Federated).
- **Offline/degraded:** failover servers minimize downtime; sites under Interconnect run independently if central link drops (**vendor claim**).
- **Incident workflow:** "respond in real time" + "investigate incidents" tooling incl. documentation of incidents (**vendor claim**).
- **Evidence handling:** digital signing, Evidence Lock, Evidence Manager; export & share video evidence.
- **Reporting:** incident documentation/export; advanced reporting exists in variants (see Genetec-style comparison; Milestone reports not deep-read).
- **Analytics semantics:** delegated to BriefCam/partner analytic events.
- **Security model:** "cyber-secure, regular updates", compliance-oriented claims.
- **UI patterns:** Smart Client multi-view, Smart Wall, maps, wall auto-update on alarms.
- **Hardware/environment:** on-prem servers / Husky / AWS; per-camera device support via Device Pack.
- **License/pricing:** variant-based licensing (per-site scale); specific prices not published on page (pricing page exists; not deep-read).
- **Maintenance status (2026):** active — site live, "Product lifecycle" + Device Pack download pages maintained; Arcules now presented as Milestone product.

#### C-A2 Genetec — Security Center
- **URLs (primary):** brochure PDF https://info.genetec.com/rs/752-WRB-240/images/EN.Genetec%20Security%20Center%20Brochure.pdf (read in full; **document vintage © 2019** — feature/edition rows below are from that document); current product page https://www.genetec.com/products/unified-security/security-center (JS-rendered, not retrievable via plain fetch); current release note page https://www.genetec.com/product-releases/intrusion-management-in-security-center-saas (discovery-level); techdocs https://techdocs.genetec.com/r/en-US/Security-Center-Administrator-Guide-5.14/About-Intrusion-Managers (docs pointer; JS-rendered).
- **Evidence levels:** documented behavior (brochure); vendor claim (web pages).
- **Capabilities:** unified platform: Omnicast VMS + Synergis ACS + AutoVu ALPR + intrusion monitoring + SIP communications (Sipelia); centralized alarm management across video/ACS/ALPR/3rd-party; **threat level management** (predefined org threat levels → platform-wide actions incl. door lockdown, PTZ presets, recording changes); Plan Manager dynamic maps (PDF/PNG raster, KML, ArcGIS); Federation (multi-site hierarchy, global cardholder management, centralized reports); consolidated dynamic reporting (graphs/charts/histograms); health monitoring engine with statistics; web/mobile clients; SDK + Web API.
- **Weapon/violence/face:** not native; partner add-ons list includes "intrusion systems, gunshot detection", "video analytics, face recognition, forensics search" (**documented behavior** in brochure's add-ons list).
- **Camera-quality features:** privacy masking; firmware update notifications w/ "firmware vault" (security hygiene, not image quality).
- **Latency/throughput claims:** none published; **do not compare**.
- **Multi-camera/scale:** "hundreds of sites, thousands of cameras, doors, intercom devices, intrusion panels" (**vendor claim**).
- **Offline/degraded:** built-in failover/redundancy (archiver & directory failover in Enterprise/SaaS); hybrid deployment (Synergis/AutoVu in cloud + Omnicast on-prem).
- **Incident workflow:** alarm triage in unified monitoring app; threat-level playbooks.
- **Evidence handling:** "encrypts video in transit or at rest, **and when exporting evidence**" (**documented behavior**, brochure).
- **Reporting:** unified custom reporting across systems/sites.
- **Analytics semantics:** unified video analytics + privacy protection (KiwiVision) as core module.
- **Security model:** encryption end-to-end, claims-based auth + ADFS, system partitioning (what users can see), cybersecurity score widget + hardening checklist, password strength meter, certificate support.
- **UI patterns:** multi-task tabs, interactive maps, live cardholder verification (picture vs live/recorded video), embedded call management, adaptive dashboard.
- **Hardware/environment:** client-server, multi-site, virtualization-friendly; SaaS edition (Omnicast not hosted — brochure note).
- **License/pricing:** **perpetual or subscription**; editions Standard/Pro/Enterprise/SaaS; caps documented: cameras 50/250/unrestricted; readers 64/256/unrestricted; clients 5/10/unrestricted; optional modules (Sipelia, intrusion monitoring, threat levels, AD, Federation, failover) per edition.
- **Maintenance status (2026):** active — 2025/2026 SaaS intrusion-management release page live; brochure itself is 2019 vintage (edition table may have changed; treat as documented-at-time-of-document).

#### C-A3 Avigilon (Motorola Solutions) — Avigilon Alta / Avigilon Unity
- **URLs (primary):** https://www.avigilon.com/ (homepage read; ©/Motorola branding current). **Discovery-only:** Bing results referencing "Appearance Search", alta.avigilon.com, cloud.avigilon.com, docs.avigilon.com.
- **Evidence level:** vendor claim (homepage only).
- **Capabilities (as claimed on homepage):** end-to-end video security + access control suite; AI-powered video security cameras and cloud management; two product families (Alta cloud / Unity); part of Motorola Solutions. Details of Appearance Search / object classification were **not** verified from primary pages in this session (docs.avigilon.com requires login) — recorded as discovery-only.
- **Weapon/violence/face:** not verified from primary source this session. **GAP in coverage.**
- **Camera quality / latency / multi-camera / offline / incident / evidence / reporting / analytics / security / UI / hardware / pricing:** not verified from primary source this session. License model is per-camera subscription + cloud (industry-known but **not verified here** → unverified).
- **Maintenance status (2026):** active (homepage live, software downloads page in Bing index).
- **Adopt note:** treat as reference only until docs access improves (§8).

#### C-A4 Verkada — Verkada Command
- **URLs (primary):** https://www.verkada.com/ ; help center https://help.verkada.com/ and **documentation index** https://help.verkada.com/llms.txt (140 KB doc index, parsed); read in full: `incident-management.md`, `detect-people-count.md`, `license-plate-recognition-overview-faq.md`.
- **Evidence levels:** documented behavior (help docs); vendor claim (marketing pages). "Fall 2026 Product Announcements" banner on homepage (webinar 2026-10-08) — actively releasing.
- **Capabilities:** cloud-managed Command platform over hybrid-cloud cameras + Command Connector (add non-Verkada cameras) + Viewing Station (30 simultaneous feeds); alarms (New + Classic), intercom, access control, air-quality sensors, guest, security trailers; **Incident Management** (see below); people analytics (people count, occupancy trends, people/vehicle search), vehicle analytics (LPR), face blur, Person-of-Interest / License-Plate-of-Interest lists, crowd/tamper/occlusion/camera-status/compound/activity/inactivity alert classes.
- **Weapon/violence/face:** **no weapon or violence detection feature appears in the 2026-09-29 documentation index** (llms.txt grep: alert taxonomy lists POI/LPOI/crowd/tamper/occlusion/compound/activity/inactivity — no gun/weapon/fight entries). "AI-Powered Alerts" (industry alerts) exists but is not a weapon product. Face: **face blur** for live + archived video (privacy); face authentication for doors (marketing); facial-recognition style matching via Person of Interest smart lists (docs describe POI alerts).
- **Camera-quality features:** LPR doc documents real **shutter/exposure trade-offs** (LPR cameras run higher shutter → darker images, earlier night-mode transition; external IR illuminator recommended for low-light/distant plates); "adaptive quality" recording whitepaper referenced; tamper/occlusion/camera-status alerts = image-integrity health surface.
- **Latency/throughput claims:** "find footage in seconds" (search UX claim); LPR capture at up to 80 mph (Gen 2) vs 25 mph (Gen 1) — **hardware-generation-qualified**, Gen 2 adds a CV co-processor; up to 3 lanes (Gen 2) vs 1 (Gen 1). No model-latency numbers published → **do not compare**.
- **Multi-camera:** LPR + context-camera pairing pattern; 30-feed Viewing Station; org-wide alerts.
- **Offline/degraded:** **documented**: on internet outage LPR cameras keep recording plates + video to onboard storage and sync to cloud on reconnect; data stored on device and in cloud.
- **Incident workflow (documented behavior — strongest reference for WT work):** Incident = named case with summary; attach archives ("Copy to Incident"); per-clip notes; **Timeline tab** (clips, durations, notes); **People tab / Vehicles tab** (auto-extracted detections from attached clips); **Activity Log tab = audit of views, edits, downloads**; sharing with Editor vs View-Only roles (external users capped at View-Only); **Download Incident ZIP** = Incident Detail PDF + Videos + Activity Log; state open/closed/reactivate; **incidents and contents retained indefinitely**.
- **Evidence handling:** archives + incident packages; **LPR search requires offense reason and case/incident number for every search** (audit gate — "LPR Search Reason & Audit" doc); Axon Evidence integration doc exists in index (`set-up-the-axon-evidence-integration-in-command.md`) — evidence export to a DEMS is a supported pattern.
- **Reporting:** auto-generated incident reports (Incident Management); access-control reports + roll-call + attendance analytics.
- **Analytics semantics:** "Detect People Count" = per-frame people count shown while scrubbing history + activity-density markers (**occupancy semantics, not flow counting**); Occupancy Trends tracks people and vehicles; LPOI/POI event semantics; LPR = Latin-character plates with ≥4 chars only.
- **Security model:** privacy pillars (purpose limitation, transparency, human-in-the-loop, model quality, data minimization, third-party-validated security); org roles (Site Viewer/Site Admin/Org Admin).
- **UI patterns:** incident dossier w/ timeline/people/vehicles/activity-log tabs; archives + scrub analytics; alerts center; web Command.
- **Hardware/environment:** proprietary cameras (Bullet series required for LPR mode), Bridge/Connector for 3rd-party cameras; cloud + edge storage.
- **License/pricing:** per-device license + cloud plan (pricing page linked; **numeric prices not retrieved**); 30-day trial (1 device + full Command access).
- **Maintenance status (2026):** very active (Fall 2026 announcements; docs updated "1 month ago" per help index).

#### C-A5 Rhombus Systems
- **URLs (primary):** https://www.rhombus.com/ ; https://www.rhombus.com/ai-analytics/ ; API docs https://docs.rhombus.com/ (discovery). **Discovery-only (blocked to fetch: HTTP 403 Zendesk):** https://support.rhombussystems.com/hc/en-us/articles/360002258451-People-and-Vehicle-Counting ; .../360037762212-Managing-License-Plate-Recognition-LPR ; developer docs https://api-docs.rhombus.community/implementations/lpr-vehicle.
- **Evidence levels:** vendor claim (marketing pages); discovery-only (support/API doc titles).
- **Capabilities:** cloud-edge platform ("scale infinitely, **operate offline**, minimize latency"); smart cameras, access control, IoT sensors (audio, environmental, motion, entry, panic), TMA 5-diamond-certified alarm monitoring w/ live-agent verification & dispatch; **AI Video Search** (natural-language retrieval across selected cameras), Face Recognition, LPR (support doc + API endpoints), Audio Analytics; real-time detections & alerts with customizable rules; **audio/visual deterrence triggered by detections**; occupancy & movement insights (people & vehicle counting — support doc title), real-time heat maps; environmental monitoring (temperature, humidity, air quality, smoke, vape); third-party analytics/BI embedding on camera feeds; 100% open API; 50+ integrations.
- **Weapon/violence/face:** face recognition (named product capability); weapon/violence detection **not found** on pages read (audio aggression classes unknown — support docs blocked) → partial gap.
- **Camera-quality features:** not published on pages read (hardware camera line: dome/fisheye/bullet/multisensor).
- **Latency/throughput claims:** "cloud-edge … minimize latency", customer story "search time 2 days → 10 minutes", "40% reduction in security incidents / 30% decrease in review time" (testimonial claims; **no dataset/hardware context**) → **do not compare**.
- **Multi-camera:** multi-site cloud management; AI Search across chosen cameras; case study 11K locations/13K devices.
- **Offline/degraded:** "cloud-edge system … operate offline" (**vendor claim**); edge processing implies continued local operation during WAN loss (mechanism not documented in accessible pages).
- **Incident workflow:** alerts + review workflows; alarm monitoring with live-agent verification and dispatch (human-verification loop as a *service*).
- **Evidence handling:** footage export/share; API-driven license-plate/vehicle data export (developer docs).
- **Reporting:** ROI proof/customer-story based; operational insights; no chain-of-custody documentation found.
- **Analytics semantics:** counting = occupancy & movement insights + heat maps (**vendor claim**; semantics detail locked in 403 support docs).
- **Security model:** "rooted in cybersecurity" (breach protection/compliance claims); open API with token model (API docs).
- **UI patterns:** console w/ event cards ("door left ajar" example), AI search, alerts, mobile apps.
- **Hardware/environment:** Rhombus cameras/controllers + sensors; cloud console.
- **License/pricing:** subscription ("Request Custom Quote"); pricing page exists (not fetched).
- **Maintenance status (2026):** active (AI Agent widget live on site; docs/API ecosystem live).

#### C-A6 Arcules (Milestone Systems — VSaaS)
- **URLs (primary):** https://arcules.com/ → **redirects to** https://www.milestonesys.com/products/software/arcules/ (read; redirect itself is a 2026 brand/ownership signal).
- **Evidence level:** vendor claim.
- **Capabilities:** cloud VSaaS; live/recorded video web+mobile; **real-time AI alerts with adaptive detection models to "reduce false alarms"**, configurable alert thresholds; intelligent search; evidence export/share; AI insights/operational data; multi-site management; system health/user management dashboard; integrations: access control, LPR, IoT; deployment: cloud, gateway, or camera-to-cloud; **hybrid "Arcules plus XProtect"**.
- **Weapon/violence/face:** not claimed.
- **Camera quality:** "enable cloud analytics on existing cameras", extensive device compatibility; no shutter/WDR claims.
- **Latency/throughput:** none published.
- **Multi-camera/multi-site:** core positioning (distributed sites, minimal staff).
- **Offline/degraded:** gateway/camera-to-cloud variants imply edge continuity (mechanism not documented).
- **Incident workflow/evidence:** "export and share evidence easily" (**vendor claim**); no chain-of-custody documentation.
- **Reporting/analytics:** adaptive analytics alerts, activity insights.
- **Security model:** "built-in security, automatic updates, trusted cloud infrastructure" (**vendor claim**).
- **UI patterns:** single dashboard (sites, devices, status); alert review.
- **License/pricing:** "Arcules pricing" page exists (VSaaS subscription; not fetched).
- **Maintenance status (2026):** active, integrated into Milestone portfolio.

#### C-A7 Envysion (Motorola Solutions)
- **URLs (primary):** https://www.envysion.com/ (read).
- **Evidence level:** vendor claim.
- **Capabilities:** cloud-managed video for retail/restaurants/c-stores: incident management, **system health reports**, heatmaps, Image Alert, intelligent search, loss-prevention **audit programs** (POS exception reports + human auditors + machine analytics), Customer Detection AI, Smart Site Protection, Smart Alarm, professional alarm monitoring, panic button, panel alarm integration, HALO smart sensors (vape/environmental), drive-thru performance/line-time/abandonment analytics, visitor insights; POS + third-party data integration.
- **Weapon/violence/face:** "video-verified response" to threats (monitoring service); no weapon AI claimed; Customer Detection AI (person detection in stores).
- **Camera quality:** system health reports + "quality and coverage" onboarding requirement (FAQ); appliances to accommodate existing equipment.
- **Latency/throughput:** none published.
- **Multi-camera:** 30,000+ locations claim; enterprise user/camera management.
- **Offline/degraded:** not documented.
- **Incident workflow:** Incident Management tool receives human-audit results; exception reports → incidents (**process pattern**).
- **Evidence handling:** video-backed proof for theft resolution; no chain-of-custody documentation.
- **Reporting:** POS exception reports, operational audits, dashboard.
- **Analytics semantics:** line time, speed of service, abandonment, occupancy-style visitor insights.
- **Security model:** Motorola-backed cloud; 24/7 support; nothing more published.
- **UI patterns:** dashboard, incident management, image alerts.
- **Hardware/environment:** appliances + existing cameras; 3–6 week onboarding (FAQ).
- **License/pricing:** contract-based (sales; no numbers).
- **Maintenance status (2026):** active (Motorola Solutions company; site current).

### Category B — AI violence/weapon detection vendors

#### C-B1 Actuate (Actuate AI)
- **URLs (primary):** https://actuate.ai/ ; https://actuate.ai/gun-detection/ (both read). Blog "Weapons Detection Technology: Beyond Guns and Firearms" discovered (discovery-only).
- **Evidence level:** vendor claim. © 2026 — active.
- **Capabilities:** cloud AI video analytics on **existing cameras** ("no hardware integrations required"); **gun detection** ("identifying firearms as they appear", alerts "in seconds"); multi-model ensembles for **false-alarm reduction** ("Reduce False Positives By 95%+"); intruder & crowd detection; line-crossing detection; fire detection mention; **camera health monitoring** (real-time checks for **blurriness, tilting, obstructions, offline status**); GSOC/NOC analytics + reporting; integrations with "key video monitoring software platforms" (Salient listed as partner — discovery-only).
- **Weapon/violence/face:** guns/firearms (marketing page); "beyond guns and firearms" blog suggests broader weapon classes but content unverified. Violence/fight detection: **not claimed** on pages read. Face: not claimed.
- **Camera-quality features:** camera-health checks (blur/tilt/obstruction/offline) — directly relevant to GAP-5.
- **Latency/throughput claims:** "alerting security teams in seconds" (**vendor claim**; no dataset/hardware/protocol context) → **not comparable** to Scylla/ZeroEyes numbers.
- **Multi-camera:** cloud platform, "scalable for any size"; monitoring-center positioning (CMS/ARC/GSOC/MSP).
- **Offline/degraded:** cloud-dependent; no offline mode claimed.
- **Incident workflow:** alert management for monitoring centers; no case-management product claimed.
- **Evidence handling:** not published.
- **Reporting:** "detailed analytics and reporting", trends & system performance.
- **Analytics semantics:** false-alarm filtering as headline metric.
- **Security model:** not published on pages read.
- **UI patterns:** "user-friendly interface" for setup/management (marketing).
- **Hardware/environment:** existing cameras + cloud; subscription SaaS.
- **License/pricing:** **Base Subscriptions + Specialty Subscriptions** (menu); camera health "for as little as a bag of chips per month" (marketing); numeric prices not published.
- **Maintenance status (2026):** active (© 2026; case studies/press pages live).

#### C-B2 Scylla (Scylla Technologies Inc.)
- **URLs (primary):** https://www.scylla.ai/gun-detection/ ; https://www.scylla.ai/aggressive-behavior-detection/ ; https://www.scylla.ai/ (all read in full; © 2026).
- **Evidence levels:** vendor claim, incl. **vendor-reported third-party claims** (IPVM testing; US Army field testing) — not independently verified here.
- **Capabilities:** the most *specified* detection vendor in this catalog.
  - **Gun detection:** classes = small firearms (pistols, revolvers) + large firearms (rifles, assault rifles, shotguns; machine guns listed in FAQ); separate **Knife Detection System** product. Detection requires **as little as 100 ms up to 1 s of video input** (algorithm input requirement, not end-to-end latency; stream/network latency excluded per FAQ). **False-positive rate < 0.1 alerts/camera/day** (claim). **Minimum PPM (pixels-per-meter) = 100 for firearms**; effective ≈ **15 m on standard Full HD**, farther with higher resolution. Small firearms optimally detected **held in hand in natural shooting position**; weapons on tables/tucked/flash-shown less likely to trigger; large firearms detectable without a visible person. Handles moving backgrounds, PTZ, drone, bodycam (accuracy caveats for moving/drone). Does **not** distinguish replicas from real firearms (filters unrealistic shapes/colors). Cannot detect concealed weapons. False-alarm suppression via object+handling heuristics, scene-dedup unless significant movement.
  - **Violence (Aggressive Behavior Detection):** detects fights/assaults/arrests/brawling/vandalism; **analyzes 5-second chunks**; first detects person groups then per-region anomalies; **requires direct physical contact lasting at least a few seconds** — explicitly does **not** detect aggressive walking, chasing, or panicked running crowds; stick-armed fights detected if contact occurs; individual + group fights; per-camera configurable max simultaneous fight instances (**recommend 3**; more = more hardware); dedicated vandalism model (vigorous damaging actions; graffiti not detected); claims **up to 96% accuracy, FP ≤ 1/day/camera**; continuous self-learning claim; fine-tunable per environment after deployment.
  - **Camera/environment guidance (documented):** ~45° camera angle, elevated above person height, subjects occupying part of frame, **≥ 20 FPS, 16:9 preferred** (all ratios supported), static cameras trained (PTZ slow moves OK but raise FP risk), drones supported with reduced accuracy.
  - **Face:** **XactID Face Recognition in the Wild** (persons-of-interest identification) + **Face Recognition Auto-Enrollment** (dynamically enroll detected individuals to a visitor database).
  - **Other:** Traffic Flow Analysis; Smoke & Fire; Vehicle Identification/Tracking; Suspicious Shopping Behavior (97.3% claim); Perimeter Intrusion; Slip & Fall; False Alarm Filtering (up to 99.95% filter claim); Access Control Verification; Forensics Pro; Event Raptor; EDI Assist.
- **Latency/throughput claims & context:** detection-from-100 ms-of-video (input duration claim); "analysis and response time < 1 second" for bodycam claim; drone ranges "up to 50 m with 4K, up to 100 m with 8K"; DoD field-test claim "detection of an armed individual from over one mile away, PoD > 96%" (vendor-reported). Hardware: **GPU-powered servers, Ubuntu**; Asteria edge appliance (hardware calculator published). These numbers span different hardware/protocols/datasets → **never rank against ZeroEyes/Omnilert/Actuate numbers**.
- **Multi-camera:** "processes live video from every connected camera simultaneously 24/7"; per-camera FP/latency budgets; VMS integrations (Milestone, Intrado, exacqVision, NovoTrax named).
- **Offline/degraded:** **air-gapped on-prem deployment** via Asteria ("no cloud dependency, no data leaving agency-controlled infrastructure") — strongest offline story in Category B.
- **Incident workflow:** Alarm Hub dashboard + Alarms Panel + mobile app + Command Center; alerts include camera location, timestamp, captured image; delivery via dashboard/mobile/SMS/email/integrated alarm systems; **webhooks** for automatic responses (alarm activation, door lock commands, law-enforcement notification).
- **Evidence handling:** "does not store any video feed data, including recordings or images, **except for alerts containing instances of a person with a firearm**" (privacy-minimizing evidence policy — documented).
- **Reporting:** whitepapers; pilot success metrics defined (drill sensitivity + FP rate monitoring in client environment).
- **Analytics semantics:** see capability definitions above (contact-requiring violence; PPM-gated gun detection) — unusually honest semantics for GAP-10 purposes.
- **Security model:** NDAA §889 compliant; US DoD validated (claims); AICPA/ISO/ASPP certifications claimed; GDPR compliance claimed; air-gap option.
- **UI patterns:** Alarm Hub (alert cards w/ screenshot + location + time), Alarms Panel, hardware calculator, health check page.
- **License/pricing:** quote-based ("Get a Quote"); hardware calculator implies appliance sizing cost model.
- **Maintenance status (2026):** active (© 2026; ASPP PRO 2026 whitepaper; partner program).

#### C-B3 ZeroEyes
- **URLs (primary):** https://zeroeyes.com/products (read). Pricing page exists (linked; not fetched).
- **Evidence level:** vendor claim. © 2026 footer (also "2025" in one variant) — active.
- **Capabilities:** five-product platform on one pipeline: **Visual Firearm Detection** (AI + human verification), **Analytics Suite** (knife detection, intrusion, left-behind objects, **obstructed cameras**), **Public Safety Alerts** (public + licensed signals, AI-detected + analyst-verified), **ZeroLink** (connect cameras/systems/operators/first responders), **3D Mapping** (drone/LiDAR site models), plus **Remote Alerting and Detection**.
- **Weapon/violence/face:** firearms = core (human-verified); knife = Analytics Suite; violence/fight = not claimed; face = not claimed.
- **Camera-quality features:** "obstructed cameras" detection in Analytics Suite; works on **existing IP cameras** ("no new hardware"); training claims "any environment or lighting condition" (**vendor claim**).
- **Latency/throughput claims & context:** "detection in milliseconds", "alerts … often in a matter of seconds" (includes **mandatory human verification in the ZeroEyes Operations Center**, 24/7 analysts, "every alert reviewed, every time"); fleet-scale "300K video frames analyzed per second across all active deployments" (aggregate throughput claim, not per-camera latency); "5M+ training images". None have published dataset/hardware/protocol context → **not comparable**.
- **Multi-camera:** fleet pipeline claim; 40+ US states coverage claim.
- **Offline/degraded:** not documented (cloud/operations-center model implies connectivity requirement).
- **Incident workflow:** human-verification stage = the workflow differentiator; verified alerts route to first responders via ZeroLink/Public Safety Alerts.
- **Evidence handling:** not published on products page.
- **Reporting:** Resource Hub/policy-maker material; no product reporting spec published.
- **Analytics semantics:** "visible firearms" (like Scylla: visual detection only).
- **Security model:** **DHS SAFETY Act Designation** (Qualified Anti-Terrorism Technology) claimed; Data Privacy Framework notice; patents page.
- **UI patterns:** not published (operations-center mediated).
- **Hardware/environment:** existing IP camera infrastructure; ZOC staffed operations center.
- **License/pricing:** quote-based ("Pricing" page exists).
- **Maintenance status (2026):** active.

#### C-B4 Ambient.ai
- **URLs (primary):** https://www.ambient.ai/platform-overview (read). Nav shows product modules + "Gun Detection" use case page.
- **Evidence level:** vendor claim. © 2026 — active (recent "Agentic Video Walls, Case Management" announcement banner).
- **Capabilities:** platform modules: **Ambient Foundation** (detection), **Advanced Forensics** (search), **Access Intelligence** (tailgating/door), **Threat Detection**; threat classes named: **firearms**, fence jumping, sudden egress, tailgating, person fall-down; **auto-validate access-control alarms (claim: 95% reduction in alarm volume)**; **video search "20x faster"**; "address threats 10x faster" claim; insights (tailgating hotspots, camera coverage blindspots, access violations); **Case Management** + agentic video walls (new); retrofit on **existing IP camera streams**; integrations with current tools (VMS/access).
- **Weapon/violence/face:** firearms named; face not claimed; fight/violence not named on page read (fall-down = anomaly class).
- **Camera-quality features:** "camera coverage blindspots" insight (planning-level, not image quality).
- **Latency/throughput claims & context:** model claim "Pulsar outperforms models like GPT-5 in security use cases at **50× better cost efficiency**" (no benchmark protocol published → **unverified vendor claim**); "identify 100s of threats as soon as they emerge"; no per-camera latency figures.
- **Multi-camera:** "all cameras 24/7", multi-site scaling.
- **Offline/degraded:** not documented (SaaS).
- **Incident workflow:** **Case Management** product (new); agentic response workflows (customer story: tailgating behavior change).
- **Evidence handling:** not published.
- **Reporting:** operational insights dashboards.
- **Analytics semantics:** behavior-level events (egress, tailgating, falls) vs object-only analytics ("Legacy video analytics detect objects but lack understanding of behavior").
- **Security model:** not published on page read.
- **UI patterns:** single interface unifying video + sensor data; video walls; case management.
- **Hardware/environment:** IP camera stream access; cloud processing.
- **License/pricing:** quote-based (Book Demo).
- **Maintenance status (2026):** active; product surface expanding (agentic features).

#### C-B5 Cawamo — VisiGuard
- **URLs:** https://cawamo.com/ ; https://www.cawamo.com/visiguard ; https://ai-prod.cawamo.com/ (all JS-rendered SPAs; **no readable content retrieved** — fetch returned 53–58 chars). **Discovery-only:** search results titled "Cawamo VisiGuard — All-in-One AI Security Platform", "CAWAMO | Artificial Intelligence for Security Cameras"; Startup Nation Central company profile (Israeli startup, Aerospace/Defense & HLS); LinkedIn/Crunchbase/PitchBook (discovery-only).
- **Evidence level:** **discovery-only** — no claim recorded beyond the product name/category ("AI for security cameras", security-camera analytics platform).
- **All technical fields:** unverified. **GAP** — see §8.

#### C-B6 Omnilert — Omnilert Gun Detect
- **URLs (primary):** https://www.omnilert.com/ (read). **Discovery-only:** https://www.genetec.com/partners/partner-integration-hub/omnilert/omnilert-gun-detect (Genetec partner listing; page itself JS-rendered), partner reseller pages.
- **Evidence level:** vendor claim. Active (2025 event counters on page).
- **Capabilities:** three-step architecture: (1) **AI Gun Detection** ("patented visual artificial intelligence", DoD/DARPA research lineage claim, "data-centric AI approach"), (2) **Human Verification** — "from our **UL Certified operators** to full integration within your own SOC" (flexible human-in-the-loop), (3) **Automated Notification & Emergency Response** — alert notifications with time/location/photos; automated actions: **lock doors, mobile notifications, alert police, engage displays, sound alarms, custom response**. **AI Camera Health Monitoring: "identify 120+ issues"** — blurry/out-of-focus, obstruction/partial blockage, camera movement/field-of-view changes, poor lighting and exposure issues, reduced clarity, rotation, "AI detection issues", physical degradation.
- **Weapon/violence/face:** guns/active-shooter threats (visual); violence/fight: not claimed; face: not claimed.
- **Camera-quality features:** the most explicit **image-quality health taxonomy** in this catalog (blur, occlusion, FoV change, lighting/exposure, degradation, rotation) — direct reference for GAP-5.
- **Latency/throughput claims & context:** "detect a gun in a **fraction of a second**" (no dataset/hardware/protocol context); case study (EAWR High School): "Threat detected from over **250 feet away**", "monitor 90 cameras all at once", "first responders on scene within 1 minute" (**case claim, not a benchmark**) → **not comparable**.
- **Multi-camera:** 90-camera monitoring case claim; "1,000+ organizations supported", "50+ major integration partners", "3,000+ AI Gun Detection Events in 2025" (**vendor claim**).
- **Offline/degraded:** not documented.
- **Incident workflow:** human verification stage + automated response playbooks + mass notification heritage (Emergency Notification System products).
- **Evidence handling:** not published.
- **Reporting:** alert notifications carry event details + photos; grant/resource material.
- **Analytics semantics:** gun detection + camera-health issues (named taxonomy above).
- **Security model:** **DHS SAFETY Act** claimed; privacy & compliance page; UL-certified verification operators (claim).
- **UI patterns:** not published (SOC/integration mediated).
- **Hardware/environment:** existing cameras; open integration network (Genetec integration hub listing).
- **License/pricing:** quote-based (Request a Demo).
- **Maintenance status (2026):** active.

#### C-B7 Hive (Hive AI — thehive.ai / docs.thehive.ai)
- **URLs (primary):** https://docs.thehive.ai/ (read; agent-friendly index at https://docs.thehive.ai/llms.txt). Products: hivemoderation.com (visual moderation), hivedetect.ai, hive-vision.com (discovery-only).
- **Evidence level:** documented behavior (docs hub text) for product shape; **class coverage UNVERIFIED** (specific API class lists not read this session).
- **Capabilities:** pre-trained model **APIs** across understand/search/generate (21 APIs claimed); content moderation, logo detection, OCR, translation, speech-to-text, visual similarity search, generation. Relevant to AI Sentinel only as a possible **hosted detector/comparator** (visual moderation classically includes violence/gore/weapon-type classes — **unverified here**).
- **Weapon/violence/face:** unverified (see above).
- **Camera/multi-camera/offline/incident/evidence/reporting/UI/hardware:** N/A (API product). Latency/throughput: API SLAs not read.
- **License/pricing:** API usage pricing (not read).
- **Maintenance status (2026):** active (docs live, AI-agent documentation support).

#### C-B8 Plainsight
- **URLs:** https://plainsight.ai/ (JS SPA; fetch returned 65 chars — no content). **Discovery-only:** search titles "Plainsight | Unified Operations Intelligence", "Infrastructure to Build & Scale Your Vision AI", "Vision AI Stack for Developers".
- **Evidence level:** **discovery-only**. Vision-AI platform/tooling category; no capability claims recorded. **GAP** — see §8.

### Category C — incident / evidence management

#### C-C1 Axon — Axon Evidence (Evidence.com)
- **URLs (primary):** https://www.axon.com/products/axon-evidence (read). https://evidence.com/ redirects to login. Help guide: https://www.axon.com/help/axon-evidence/software/axon-evidence/axon-evidence.htm (discovery). Verkada↔Axon Evidence integration doc in Verkada's index (cross-vendor evidence of the export pattern).
- **Evidence level:** vendor claim (mechanisms described plainly).
- **Capabilities:** digital evidence management system (DEMS) "from call to closure": capture from Axon cameras, public submissions, **third-party systems**; auto-tagging for organization; store ("without limits" claim); review; disclosure prep; **Redaction Assistant** (FOIA/public-records automation); transcription.
- **Weapon/violence/face:** N/A (evidence layer).
- **Evidence handling (core reference for GAP-2):** "**Each file … is assigned a unique digital fingerprint** that validates the file's authenticity and confirms it remains unchanged during upload or playback"; "**Every action on a file, whether viewing, editing, or downloading, is automatically recorded in a detailed audit trail**" (chain of custody, court admissibility); **encryption in transit and at rest**; **CJIS compliance** + international privacy/compliance claims; role/user-type permissions.
- **Incident workflow:** case-oriented ("call to closure"); investigator/officer/admin/command-staff personas.
- **Reporting:** disclosure/FOIA workflows; redaction reports.
- **Analytics semantics:** auto-tagging metadata.
- **Security model:** cloud (Azure case study — discovery-only), CJIS, fingerprints, audit trail.
- **UI patterns:** single evidence repository with role dashboards.
- **Hardware/environment:** SaaS (AWS Marketplace listing — discovery-only).
- **License/pricing:** per-seat/agency subscription ("Axon AI Era Plan" bundles — not read in detail).
- **Maintenance status (2026):** active ("Redesigned for today" campaign; live product page).

#### C-C2 Omnigo Software
- **URLs (primary):** https://www.omnigo.com/ (read; © 2026).
- **Evidence level:** vendor claim.
- **Capabilities:** incident management "from call open to case close": proactive planning + dispatch coordination; data capture with **compliance-driven report prompts + auto-populated known fields**; investigation & resolution with **unified evidence/case management and chain of custody**; cross-case connection discovery; trend analytics & searchable data; industry packages (public safety, healthcare, education, gaming, hospitality, courts, corporate, jail management); APIs to third-party apps/devices; FRT integration example (casino self-excluded patrons — customer story).
- **Weapon/violence/face:** N/A at incident layer; FRT integration demonstrated.
- **Evidence handling:** chain of custody named as a design goal of incident management.
- **Incident workflow:** the reference **record model** for GAP-1 (fields: plan/respond, collect/report, investigate/resolve, analyze).
- **Reporting:** regulatory reporting standards, dynamic prompts.
- **Analytics semantics:** incident-based trend analytics (budget justification case).
- **Security model:** not published on page.
- **UI patterns:** configurable case management.
- **License/pricing:** module activation model + **EverSure** (training/consulting/support bundle included with every product).
- **Maintenance status (2026):** active ("New! Jail Management Software System").

#### C-C3 RapidSOS
- **URLs (primary):** https://rapidsos.com/ (read; © 2026). Developer docs/API specs linked ("Platform → Developer Docs / API Specs").
- **Evidence level:** vendor claim.
- **Capabilities:** "Safety Network" bridging consumer/enterprise devices to 911 ECCs; **Emergency Detection / Escalation / Verification** platform functions; **live video streaming to 911**; pre-call/pre-arrival intelligence (telematics, hazmat, sensors); Harmony AI (transcription/translation, non-emergency call automation); products: Unite, Harmony AI, IamResponding, eDispatches, Northern911, Total Response; school solutions bridging "panic buttons, cameras, and alarms" to responders; GIS/mapping; DFR (drone as first responder).
- **Weapon/violence/face:** N/A (escalation layer).
- **Latency/throughput claims:** "faster than CAD" (pre-arrival intelligence claim); "99% of the US" agency coverage claim; no benchmarks published.
- **Multi-camera:** video + sensor data ingest from enterprises (RTCC & data fusion use case).
- **Offline/degraded:** not documented (network service).
- **Incident workflow:** escalation + verification + interoperability patterns; **the reference for GAP-7 outbound escalation**.
- **Evidence handling:** not published.
- **Reporting:** Data Lab / impact reporting.
- **Security model:** Security & Privacy page (linked; not read).
- **UI patterns:** ECC-facing consoles (Unite).
- **Hardware/environment:** API/SDK integration ("Developer Specs").
- **License/pricing:** enterprise agreements (not published).
- **Maintenance status (2026):** active ("Innovation Day 2026").

### Category D — adjacent capabilities (counting, LPR, face capture quality)

#### C-D1 Hikvision — People Counting (See Smarter Technology)
- **URLs (primary):** https://www.hikvision.com/en/core-technologies/see-smarter-technology/people-counting/ (read). Regional mirrors discovered (hsrc.hikvision.com/ca-en/.../people-counting etc. — discovery-only).
- **Evidence level:** vendor claim.
- **Capabilities:** dedicated **deep-learning people-counting cameras** (dual-lens people-counting network cameras; mobile/onboard passenger counting variants) that "automatically and dynamically measure customer flow through a door or within a certain area"; **queue management** (e.g., onboard bus counting to report real-time occupancy); real-time + historical statistics via laptop/mobile software; claim "ultra-high accuracy" distinguishing persons from objects; algorithms "continuously upgradeable"; installation designed to avoid floor obstructions.
- **Counting semantics (important for GAP-4):** "customer **flow** through a door" = directional flow counting (in/out), distinct from per-frame occupancy. **Numeric accuracy is not public** — gated behind Hikvision account login ("sign in to view solution content") → accuracy claim unverified.
- **Camera-quality features:** hardware-based approach (stereo/dual-lens design referenced by product names); no WDR/shutter specs on this page.
- **Weapon/violence/face:** Hikvision AcuSense/face lines exist but were **not** retrieved (§8 gap).
- **License/pricing:** hardware-included analytics (device purchase).
- **Maintenance status (2026):** active; note for procurement: NDAA §889 restrictions apply to Hikvision devices in some jurisdictions (context, not a product claim).

#### C-D2 Dahua — people counting / IVS / SMD
- **Coverage: NOT RETRIEVED.** Searches `Dahua people counting IVS heat map official` and `Dahua people counting technology official` returned engine-polluted results (2026-09-29); official site root fetched but analytics doc URLs not located. **GAP** — see §8. (General market knowledge that Dahua ships IVS people-counting/heat-map/SMD analytics is **not recorded as a claim** here because no primary source was read.)

---

## 4. Cross-cutting capability comparison

Legend: ● documented/claimed feature found (level in §3) · ◐ partial/qualified · ○ not found in accessible sources · n/a not applicable.

| Capability (AI Sentinel requirement) | AI Sentinel (baseline) | C-A1 Milestone | C-A2 Genetec | C-A4 Verkada | C-A5 Rhombus | C-B1 Actuate | C-B2 Scylla | C-B3 ZeroEyes | C-B4 Ambient | C-B6 Omnilert | C-C1 Axon Ev. | C-C2 Omnigo | C-C3 RapidSOS | C-D1 Hikvision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Weapon detection | ● 6-class ONNX | ○ (partner) | ○ (partner add-on) | ○ | ○ | ● guns | ● guns+knife | ● firearms (human-verified) | ● firearms | ● guns | n/a | n/a | n/a | ○ |
| Violence/fight detection | ● SlowFast 32f | ○ | ○ | ○ | ○ | ○ | ● contact-based fights | ○ | ◐ anomalies (egress/fall) | ○ | n/a | n/a | n/a | ○ |
| Face capture / quality | ○ (disconnected F-30) | ○ | ○ (partner) | ● blur+POI | ● recognition | ○ | ● XactID+auto-enroll | ○ | ○ | ○ | n/a | ◐ FRT case | n/a | ○ |
| Counting / statistics | ◐ per-frame tracks | ◐ BriefCam | ○ | ● count+occupancy trends | ● occupancy+heat maps | ◐ crowd detect | ◐ traffic flow | ○ | ◐ insights | ○ | n/a | ● trend analytics | ◐ Data Lab | ● flow+queue |
| LPR | ○ | ● extension | ● AutoVu | ● Gen-qualified | ● (docs blocked) | ○ | ● vehicle tracking | ○ | ○ | ○ | n/a | n/a | n/a | ○ |
| Camera image-quality health | ○ (status enum) | ○ | ◐ firmware vault | ● tamper/occlusion/status | ○ | ● blur/tilt/obstruction | ○ | ● obstructed cameras | ◐ blindspots | ● 120+ issue taxonomy | n/a | n/a | n/a | ○ |
| Incident case workflow | ◐ alert+clip only | ◐ investigation tools | ◐ alarm mgmt+threat levels | ● full case lifecycle | ◐ alerts+alarm agents | ◐ monitoring alerts | ◐ Alarm Hub | ◐ verification stage | ● Case Management | ◐ response playbooks | ● call→closure | ● call→close case | ● escalation/verification | n/a |
| Evidence chain of custody | ● hash-chain ledger | ● signing+lock+manager | ● export encryption | ◐ activity log+ZIP | ○ | ○ | ◐ alert-snapshot-only retention | ○ | ○ | ○ | ● fingerprint+audit | ● named | ◐ | n/a |
| Retention enforcement | ○ (inert config) | ◐ Evidence Lock (hold) | ○ | ● indefinite incidents | ○ | ○ | ◐ alert-only storage | ○ | ○ | ○ | ● managed | ● | n/a | n/a |
| Reporting | ● PDF Arabic + offline | ◐ | ● unified custom | ● incident PDF | ◐ | ● analytics reporting | ◐ pilot metrics | ◐ | ● insights | ◐ notifications | ● redaction/disclosure | ● compliance reports | ● impact | ◐ stats |
| Offline / degraded operation | ● local inference | ◐ failover | ◐ hybrid | ● record-and-sync | ● "operate offline" | ○ (cloud) | ● air-gapped appliance | ○ (ZOC) | ○ (cloud) | ○ | ○ (cloud) | ◐ | n/a | ◐ device |
| Multi-camera / multi-site | ◐ 2 workers/site | ● federated | ● federation | ● org-wide | ● multi-site | ● cloud scale | ● all-cameras 24/7 | ● fleet claims | ● all-cams | ● 90-cam case | n/a | n/a | ◐ | ◐ |
| Human-verification stage | ○ | n/a | n/a | ◐ review roles | ● live-agent alarm | ◐ monitoring stations | ◐ operator-verified alerts | ● mandatory ZOC | ◐ auto-clear+review | ● UL ops/SOC | n/a | ◐ human audits | ● verification fn | n/a |
| Roles / audit on sensitive access | ◐ single API key | ◐ | ● partitioning+ADFS | ● roles+search-reason gate | ◐ API tokens | ○ | ○ | ◐ | ○ | ○ | ● roles+audit | ◐ | ◐ | ○ |
| Escalation/webhooks | ◐ Telegram | ◐ rules+integrations | ● SDK/Web API | ● Webhooks API | ● open API | ◐ integrations | ● webhooks (locks/LE) | ● ZeroLink | ◐ workflows | ● response automation | ◐ disclosure | ◐ APIs | ● API to ECCs | ○ |

**Latency/throughput claims — explicitly NOT ranked.** Each claim has different or missing dataset/hardware/protocol context: Scylla "100 ms–1 s of video input" (algorithm input duration; GPU server Ubuntu; excludes stream/network latency), "≤1 s response" (bodycam), "15 m @1080p, PPM≥100" (geometry-gated); ZeroEyes "milliseconds" detection + "seconds" alert **including mandatory human verification**, "300K fps aggregate fleet" (throughput, not latency); Omnilert "fraction of a second" (no context), case claims (250 ft, 90 cams, 1 min response); Actuate "in seconds" (cloud, multi-model); Ambient "50× cost efficiency vs GPT-5" (no protocol). AI Sentinel's registered bench evidence is pinned to a different revision (B-5) and unmeasured for glass-to-alert latency — no comparison is possible from our side either.

---

## 5. Reusable components/patterns (process/API/policy only — no proprietary code, no branding)

| Pattern | Source candidates | Concrete shape | AI Sentinel target | Expected benefit | Integration effort | Runtime cost | Risks |
|---|---|---|---|---|---|---|---|
| **P-1 Alert verification lifecycle** | C-B3, C-B6, C-B2, C-A5 | alert states `detected → pending_verification → verified → dispatched → closed`, operator ack w/ timestamps | SC-4 / F-14 decision layer + F-42 store | false-dispatch reduction; honest confidence story | medium (state machine + UI ack) | negligible | operators bypassing ack; state desync with cooldown layer |
| **P-2 Fingerprint + read-audit on evidence** | C-C1, C-A4 | every evidence view/download appends audit record; keep SHA-256 chain (already have F-22) | F-22 + F-34 | court-defensible custody; closes GAP-2 | low (audit calls at read sites) | negligible | ledger single-process limit persists |
| **P-3 Incident case object** | C-A4, C-C2 | case = id, status, summary, notes, attached clips, timeline, actors, activity log, export package (PDF + media + hash manifest) | GAP-1; S-11 incidents UI | replaces ad-hoc alert dossier; enables investigations | medium-high (schema + routes + UI) | storage only | schema drift vs SC-2/SC-6; retention entanglement (P-6) |
| **P-4 Search-reason + case-number gate** | C-A4 (LPR audit) | privileged searches (face registry F-30, future LPR/POI) require reason + case id, logged | F-30/F-34, GAP-9 | privacy/abuse controls before face wiring | low | negligible | friction for operators |
| **P-5 Camera image-quality health taxonomy** | C-B6, C-B1, C-A4 | checks: blur (Laplacian variance), occlusion (histogram stability), tilt/FoV (homography drift), low-light (luma), stream liveness; exposed per camera | F-38, F-36 health surface, GAP-5 | turns "DEGRADED" guesses into reasons; honest UI states (U-02) | medium | low (per-frame stats on existing render path) | FP nuisance alerts need thresholds per site |
| **P-6 Retention + legal hold** | C-A1 (Evidence Lock), C-C1 | retention policy per artifact class + `hold` flag that exempts pruning | GAP-3 (inert config today) | disk safety + evidence preservation | medium | cron-level I/O | accidental deletion = integrity incident; needs dry-run |
| **P-7 Scene-unit detection requirements** | C-B2 (PPM ≥100; FPS/angle guidance) | publish min pixels-per-meter / subject-height / FPS requirements for weapon+violence claims; record per-alert geometry | F-07/F-09 outputs, GAP-8 | kills over-claiming; makes accuracy evals meaningful | low (metadata on results) | negligible | none material |
| **P-8 Signed outbound webhook contract** | C-B2 webhooks, C-A4 Webhooks API, C-C3 | event schema (alert id, type, severity, camera, ISO time, evidence links), HMAC signature, retry/backoff, idempotency key | SC-5 parity; GAP-7 | future RapidSOS/lockdown/notification integrations | medium | negligible | secret management (no keys in repo — campaign rule) |
| **P-9 Degraded/offline envelopes per feature** | C-A4 record-and-sync, C-B2 air-gap, C-A5 "operate offline" | document + test: what works offline (detection, clips, reports) vs not (remote LLM report F-26, Telegram F-32) | F-38 health + docs honesty | explicit operator expectations | low (docs + health flags) | none |
| **P-10 Counting semantics naming** | C-D1 (flow), C-A4 (per-frame), C-A5 (occupancy) | rename/qualify `personCount` as per-frame occupancy; flow counting would need line-crossing tracks (not implemented) | F-10/F-17, GAP-4/GAP-10 | prevents false "people counting" claims | low (contract naming, SC-2 notes) | none |

### Adopt / integrate / adapt / reject (per candidate)

| Candidate | Verdict | Reasoning |
|---|---|---|
| C-A1 Milestone | **Integrate (as upstream)** | Our pipeline consumes RTSP from any camera; XProtect is a stream/evidence source. Reuse concepts only (digital signing of exports = P-2 direction; Evidence Lock = P-6). Do not build against Milestone SDK in this campaign. |
| C-A2 Genetec | **Integrate (as upstream)** | Same as C-A1; additionally adopt **threat-level playbook** idea (org-level state changing alert routing) as future policy feature. |
| C-A3 Avigilon | **Reject (for now)** | Primary docs inaccessible (login); nothing verifiable to adopt. Revisit if docs access improves (§8). |
| C-A4 Verkada | **Adapt patterns P-3/P-4/P-9; reject product** | Proprietary cameras/cloud lock-in; but its Incident Management + LPR audit + offline sync docs are the best *documented behavior* references for our incident/evidence workstreams. |
| C-A5 Rhombus | **Adapt (open-API posture, offline envelope); reject product** | Hardware+cloud lock-in; support docs blocked. |
| C-A6 Arcules | **Reject** | VSaaS for remote multi-site; overlaps nothing we must build; adaptive false-alarm models noted as eval inspiration only. |
| C-A7 Envysion | **Reject (product); adapt process** | Retail loss-prevention focus; its **audit-program process** (human audits → incident management) is a good ops pattern for pilot evaluation (E-3). |
| C-B1 Actuate | **Reject product; adapt P-5** | Cloud SaaS duplicates our in-house detectors; camera-health checks (blur/tilt/obstruction/offline) are cheap wins. |
| C-B2 Scylla | **Adapt P-6/P-7/P-8 + benchmark protocol; reject product integration** | Best-documented detection semantics (PPM, contact-based violence, camera guidance) — directly reusable for claims discipline and eval design (E-1/E-2). Product requires GPU servers/appliance + licensing; our models are already local. |
| C-B3 ZeroEyes | **Adapt P-1 (mandatory human verification); reject product** | Managed US-centric service; the *architecture* (detection → verification → dispatch) is exactly GAP-6. |
| C-B4 Ambient.ai | **Adapt (case management, false-alarm auto-clear concept); reject product** | Cloud platform; behavior-level event taxonomy informs our category docs (F-29) and future anomaly classes. |
| C-B5 Cawamo | **Reject (unverifiable)** | No readable primary source; re-check manually via browser if the workstream needs an Israeli vendor comparison. |
| C-B6 Omnilert | **Adapt P-5 + P-1; reject product** | Camera-health taxonomy (120+ issues) + verification/automation steps map onto F-38/F-36 and SC-4. |
| C-B7 Hive | **Integrate (optional, as API comparator only)** | Hosted moderation/vision API could serve as a *second opinion* channel in accuracy evals (E-1) — subject to policy review; class coverage unverified. |
| C-B8 Plainsight | **Reject (unverifiable)** | Platform tooling; no readable primary source. |
| C-C1 Axon Evidence | **Integrate (patterns P-2/P-3; possible export target)** | Fingerprint+audit-trail semantics match our hash-chain; a documented export package makes future Axon-Verkada-style DEMS handoff possible. |
| C-C2 Omnigo | **Adapt (incident record fields, compliance prompts)** | Its case record/report-prompt model is the reference for GAP-1 schema fields. |
| C-C3 RapidSOS | **Integrate (future escalation endpoint via P-8)** | Emergency Detection/Escalation/Verification API shape is the natural consumer of our signed webhooks; not in current scope. |
| C-D1 Hikvision | **Adapt (counting semantics); hardware-agnostic** | Flow-vs-occupancy distinction (P-10); note NDAA procurement constraints for some deployments. |
| C-D2 Dahua | **Reject (uncovered)** | No primary source retrieved. |

### Verification experiments (to run in the appropriate workstreams — none run in this research ticket)

- **E-1 (WT-14):** weapon benchmark at controlled geometry: fixture clips graded by pixels-per-meter (Scylla criterion PPM ≥ 100 ≈ subject pixel scale), report recall + FP/camera-hour for `weapon_yolo.onnx` per class {pistol, rifle, shotgun, knife, sword, revolver}; disclose that classes beyond Scylla's knife product are our added scope.
- **E-2 (WT-14):** violence window ablation: our 32-frame window vs 5-second chunk processing (Scylla-style) on RWF-2000 subset + demo AVIs; measure detection delay vs recall; document contact-requiring vs non-contact events separately (P-7 semantics).
- **E-3 (ops/pilot):** human-verification latency budget study (P-1): operator ack timestamps on synthetic alert stream; target p95 ack ≤ 30 s; measure dispatch correctness.
- **E-4 (WT-25):** evidence export package round-trip (P-2/P-3): export ZIP with manifest of SHA-256s → independent verifier re-hashes → all-match assertion; corrupt one byte → verifier must fail.
- **E-5 (WT-24/26):** camera-health detectors (P-5) on synthetically degraded fixtures (blur kernel, occlusion patch, tilt, darkening); report per-check precision at chosen thresholds.
- **E-6 (WT-14/26):** counting semantics check: compare `len(tracks)` occupancy against ground-truth frame counts; if flow counting is ever claimed, add line-crossing eval (currently unimplemented).

---

## 6. Engineer handoff (≤10 actionable findings for WT-25 / WT-26 / WT-24 / WT-14)

> Workstream remits were not present in the seed inputs available to this agent (§8); items are routed by capability area and carry candidate + feature IDs so the orchestrator can re-map.

1. **WT-25 (incident/evidence):** adopt P-3 incident case model (candidates **C-A4**, **C-C2**): incident record = {id, status open/closed, summary, notes, attached clip refs, timeline, actor log}; schema must extend, not fork, SC-2/SC-6 identities (F-22 alert IDs are the join keys).
2. **WT-25:** implement P-2 read-audit (**C-C1**): every `/clips/{id}`, `/download_evidence/{id}`, `/evidence_chain/{id}` access appends an F-34 audit record (actor, action, artifact hash, ISO time). Cheap; closes GAP-2's weakest point.
3. **WT-25:** add **export package** (ZIP: clips + thumbnails + reports + `manifest.json` of SHA-256s) mirroring **C-A4**'s Download Incident (PDF + videos + activity log) and **C-C1**'s fingerprint semantics; verification experiment E-4.
4. **WT-26 (reporting, S-14):** extend the Arabic PDF report with an evidence-fingerprint section (artifact hashes from F-22 ledger + export manifest); keep the facts-only discipline of F-28 (never assert image analysis in offline reports).
5. **WT-26:** implement retention + legal hold (P-6, **C-A1** Evidence Lock, **C-C1**): activate the inert `clips.clip_retention_days` config with an explicit `hold` flag and dry-run pruning; retention rules must be documented in the report footer.
6. **WT-24 (UI, S-10/S-11):** restructure the incident dossier toward **C-A4**'s tab model (Timeline / People / Vehicles / Activity Log); Activity Log view binds to finding 2's audit records; keep U-04 keyboard triage intact.
7. **WT-24:** camera-health surface (P-5, **C-B6** taxonomy + **C-B1** checks): add blur/occlusion/tilt/low-light checks to F-38's health enum and surface reasons in the existing `SourceVisualState` vocabulary (`unverified`/`stale`); experiment E-5.
8. **WT-14 (detection/accuracy):** adopt P-7 scene-unit reporting (**C-B2**): every weapon/violence result carries subject pixel scale (approx PPM) + window validity (F-08) already present; document minimum camera placement (≈45°, elevated, ≥20 FPS, 16:9 per **C-B2** guidance) in `docs/campaign/` eval protocol; run E-1/E-2.
9. **WT-14 + SC-4 owner:** honesty semantics (**C-B2**): category capability text (F-29) must state what is NOT detected (chasing/panic-running, concealed weapons, replicas) and fix the "X3D" label mismatch; this feeds GAP-10 and the result-to-claim gate.
10. **WT-25/26 shared:** define the signed outbound webhook contract (P-8, **C-B2**/**C-A4**/**C-C3**) as an OPTIONAL disabled-by-default integration: `{alertId, type, severity, cameraId, isoTime, evidenceUrls[], signature}` with idempotency + backoff; no secrets in repo; keeps the door open for RapidSOS-style escalation without committing to it now.

---

## 7. Licensing / support status check (2026)

- **Active and current (verified live pages dated © 2026 or 2026 announcements, all accessed 2026-09-29):** Actuate, Scylla, ZeroEyes, Ambient.ai, Omnilert, Verkada (Fall 2026 release cycle), Rhombus, Milestone XProtect + Arcules, Envysion, Axon Evidence, Omnigo, RapidSOS, Hive docs, Hikvision global.
- **Documented license models:** Genetec = perpetual OR subscription, 4 editions w/ camera/reader/client caps (brochure © 2019 — treat caps as dated); Milestone = variant-based licenses + "Care" support tiers (page linked; specifics not read); Actuate = Base + Specialty subscriptions (usage-tiered); Verkada/Rhombus/Arcules/ZeroEyes/Omnilert/Scylla/Ambient = quote-based; Axon = agency subscription plans; Omnigo = modules + EverSure support bundle; Hikvision = hardware-included analytics.
- **Numeric pricing:** not published by any candidate on pages read; all require sales contact. **No price/perf conclusion is drawn in this catalog.**
- **Procurement caveat:** Hikvision/Dahua devices face NDAA §889 restrictions in some jurisdictions; Scylla advertises NDAA compliance and air-gap as a counter-positioning (vendor claims).

---

## 8. Gaps and limitations (disclosed)

1. **Not internet-wide coverage.** Search engines were rate-limited (DuckDuckGo HTTP 202 bursts) and Bing returned polluted results for several obscure queries (Cawamo, Owltondo, Dahua). Stop rule in §1.4 applied.
2. **"Owltondo" (named in the ticket) is unidentifiable:** queries `Owltondo`, `Owltondo security AI` (2026-09-29) surfaced only an unrelated crypto bridge ("Owlto Finance") and miscellany. No such video-security vendor could be registered. If the intended name was different (e.g. Omnilert, which IS covered as C-B6), the orchestrator should correct it and a follow-up pass can be run.
3. **Unreadable primary sources (JS SPAs / auth walls / bot blocks):** cawamo.com + ai-prod.cawamo.com (C-B5), plainsight.ai (C-B8), genetec.com product + techdocs pages (C-A2 web layer; compensated with brochure PDF + release page), support.rhombussystems.com Zendesk (403; C-A5 semantics locked), evidence.com (login redirect; compensated with axon.com product page), docs.avigilon.com (login; C-A3 largely uncovered), Hikvision solution content (account-gated accuracy numbers).
4. **Dahua (C-D2) entirely uncovered** — no primary analytics doc retrieved. People-counting semantics are covered via C-D1/C-A4/C-A5 instead.
5. **Weapon/violence coverage in Category A:** no Category A vendor markets native weapon/violence detection (they integrate partners: Scylla↔Milestone/exacqVision, Omnilert↔Genetec hub, Verkada↔Axon Evidence). This is itself a finding: the market separates VMS from detection — matching our architecture (F-06 inference process + stream ingest).
6. **Evidence levels are shallow by nature:** everything here is `vendor claim` or `documented behavior`. No `inspected implementation`, `published experiment`, or `locally reproduced` claims exist in this catalog. Vendor-cited third-party tests (Scylla↔IPVM/DoD; ZeroEyes SAFETY Act; Omnilert UL operators) are recorded as vendor-reported only.
7. **Latency/throughput numbers are not comparable** across candidates (different or missing dataset/hardware/protocol contexts) and are never ranked (§4).
8. **WT-25/26/24/14 remits were not defined** in the blueprint seed inputs available to this agent; the handoff (§6) is routed by capability area and can be re-mapped by the orchestrator.
9. **Reconciled seed cross-check (blueprint delta):** the wt-03 seed (commit `27c18d2`) landed during compilation; `INDEX.md`/`index.json` were read and this catalog's ID references were verified against the registry — all consistent. Catalog-local identifier prefixes used here (`C-A*/C-B*/C-C*/C-D*` candidates, `GAP-*`, `P-*`, `E-*`) are **not** blueprint IDs and intentionally sit outside the registered namespaces; no new blueprint IDs were allocated by WT-04.
10. **No pricing/perf conclusion**, no vendor was contacted, no demos were attended, no trials started. All "claims" are page-level.

---

## 9. Source index (all accessed 2026-09-29)

**Primary (evidence-bearing):**
- https://actuate.ai/ ; https://actuate.ai/gun-detection/
- https://www.scylla.ai/ ; https://www.scylla.ai/gun-detection/ ; https://www.scylla.ai/aggressive-behavior-detection/
- https://zeroeyes.com/products
- https://www.ambient.ai/platform-overview
- https://www.omnilert.com/
- https://docs.thehive.ai/
- https://www.milestonesys.com/products/software/xprotect/ ; https://www.milestonesys.com/products/software/arcules/ (arcles.com redirect)
- https://info.genetec.com/rs/752-WRB-240/images/EN.Genetec%20Security%20Center%20Brochure.pdf (PDF, © 2019 document)
- https://www.avigilon.com/
- https://www.verkada.com/ ; https://help.verkada.com/ ; https://help.verkada.com/llms.txt ; https://help.verkada.com/verkada-cameras/video-streaming-and-sharing/incident-management.md ; https://help.verkada.com/verkada-cameras/analytics/people-analytics/detect-people-count.md ; https://help.verkada.com/verkada-cameras/analytics/vehicle-analytics/license-plate-recognition-overview-faq.md
- https://www.rhombus.com/ ; https://www.rhombus.com/ai-analytics/
- https://www.envysion.com/
- https://www.axon.com/products/axon-evidence
- https://www.omnigo.com/
- https://rapidsos.com/
- https://www.hikvision.com/en/core-technologies/see-smarter-technology/people-counting/

**Discovery-only (found via search; not used as evidence for technical claims):** salientsys.com/technology-partners/actuate/ · genetec.com/product-releases/intrusion-management-in-security-center-saas · techdocs.genetec.com (Intrusion Managers guide URL) · genetec.com/partners/partner-integration-hub/omnilert/omnilert-gun-detect · support.rhombussystems.com (People and Vehicle Counting; Managing LPR) · api-docs.rhombus.community/implementations/lpr-vehicle · docs.rhombus.com · docs.verkada.com LPR guide PDF + adaptive-quality whitepaper (linked from help docs) · finder.startupnationcentral.org/company_page/cawamo · linkedin.com/company/cawamo · crunchbase.com/organization/cawamo · pitchbook.com/profiles/company/437595-85 · plainsight.ai / go.plainsight.ai · hive-vision.com/developers/ · hivemoderation.com/visual-moderation · hivedetect.ai · axon.com/help/axon-evidence/... · evidence.com · aws.amazon.com/marketplace (Axon) · partner.microsoft.com (Axon on Azure) · bogen.com Omnilert brochure PDF · secureussolutions.com/omnilert · remicosolutions.com/omnilert · isotecsecurity.com/omnilert · hsrc.hikvision.com regional people-counting pages · securityinfowatch/asmag/copytechnet Scylla↔Konica Minolta coverage · war.gov DoD testing article (relayed by Scylla page).

---

*End of catalog. Compiled by WT-04 (CommercialResearch), 2026-09-29. Research only; no runtime code touched.*
