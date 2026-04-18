# AI Sentinel GitHub Feature Research

This document collects feature ideas from mature open-source surveillance and video analytics projects on GitHub, then translates them into an AI Sentinel roadmap.

Execution and decision updates are tracked in:

- `docs/revolution-update-log.md`

Goal:

- Borrow proven product ideas, not code.
- Keep AI Sentinel local-first and camera-agnostic.
- Build features in a safe order: ingest first, intelligence second, specialization third.

## What I surveyed

| Project | GitHub source | Useful ideas to borrow |
|---|---|---|
| go2rtc | [AlexxIT/go2rtc](https://github.com/AlexxIT/go2rtc) | Multi-protocol restreaming, low-latency live view, ONVIF ingest, two-way audio, browser-friendly output, codec negotiation, FFmpeg transcoding, HomeKit/RTSP/WebRTC bridges. |
| Frigate | [blakeblackshear/frigate](https://github.com/blakeblackshear/frigate) | Local AI detection, motion-gated inference, object-based retention, recordings, WebRTC/MSE, mask and zone editor, multi-camera review workflows, re-streaming to reduce camera connections. |
| Frigate support issues | [Required zones by object type](https://github.com/blakeblackshear/frigate/issues/4254), [Zones and retention examples](https://github.com/blakeblackshear/frigate/issues/7043), [Zone filtering examples](https://github.com/blakeblackshear/frigate/issues/6255) | Per-object required zones, pre/post capture windows, object filters, motion masks, advanced event retention logic. |
| ZoneMinder | [ZoneMinder/zoneminder](https://github.com/ZoneMinder/zoneminder) | Full CCTV suite mindset, support for IP/USB/analog cameras, capture-analysis-record-monitor stack, mature surveillance operations. |
| Scrypted | [koush/scrypted](https://github.com/koush/scrypted) | Plugin-based camera onboarding, smart detections, low-latency streaming, software motion sensor, rebroadcast buffer, codec settings, HomeKit/Google/Alexa style integrations. |
| Scrypted docs | [Software Motion Sensor](https://github.com/koush/scrypted/wiki/Software-Motion-Sensor), [Codec Settings](https://github.com/koush/scrypted/wiki/Codec-Settings) | Motion sensor fallback when a camera does not expose motion events, use of substreams, performance-aware codec choices, stream role separation. |
| motionEye | [motioneye-project/motioneye](https://github.com/motioneye-project/motioneye) | Simple web surveillance UI, motion daemon front end, lightweight multi-camera management, multilingual UX. |
| Kerberos.io | [kerberos-io](https://github.com/kerberos-io) | Small-to-enterprise scalability, bring-your-own-storage, on-prem/hybrid/cloud deployment patterns, RTSP camera compatibility. |
| OpenALPR | [openalpr/openalpr](https://github.com/openalpr/openalpr) | License plate recognition, image/video plate extraction, bindings for Python and other languages, parking and access-control use cases. |
| CompreFace | [exadel-inc/CompreFace](https://github.com/exadel-inc/CompreFace) | Face recognition/verification/detection APIs, mask detection, head pose, age/gender, role management, REST integration. |

## Core feature ideas to adopt

### 1. Stream bridge and camera onboarding

Borrow from go2rtc and Scrypted:

- Add a local restream layer so cameras are connected once and re-served to the backend and browser in the best format.
- Support RTSP, ONVIF, WebRTC, MJPEG, and HLS where useful.
- Prefer substreams for detection and main streams for recording.
- Treat the camera vendor app as setup-only, not as the runtime dependency.
- Keep a software motion fallback for cameras that do not expose motion alarms.

Why this matters for AI Sentinel:

- Less camera load.
- Lower browser latency.
- Cleaner support for mixed camera brands.
- Easier swapping between Tapo, EZVIZ, and future models.

### 2. Detection pipeline discipline

Borrow from Frigate:

- Use motion gating so the model does not run on every single frame.
- Add object-based event logic instead of generic "motion only" alerts.
- Keep object-specific retention rules.
- Split detection, recording, and review concerns.
- Add pre-capture and post-capture buffers around events.

Why this matters for AI Sentinel:

- Cheaper inference.
- Better evidence clips.
- Fewer false alerts.
- More useful forensic reports.

### 3. Zones, masks, and event rules

Borrow from Frigate issue patterns:

- Add per-camera zones such as `gate`, `porch`, `lobby`, `parking`, `cashier`.
- Let each zone require one or more object types before an alert is accepted.
- Add motion masks for sky, roads, timestamps, and irrelevant edges.
- Support object-specific rules per zone.

Why this matters for AI Sentinel:

- Reduces noisy detections.
- Lets the project become site-aware instead of just model-aware.
- Makes the system look like a real security product.

### 4. Review and operator workflow

Borrow from Frigate and motionEye:

- Event timeline.
- Multi-camera scrubbing.
- Snapshot gallery.
- Event queue by severity.
- Review status: new, acknowledged, confirmed, false positive, exported.

Why this matters for AI Sentinel:

- Converts raw detections into a real operator workflow.
- Helps shift the project from demo mode to security operations mode.

### 5. Security and access control

Borrow from ZoneMinder, Scrypted, and CompreFace patterns:

- Role-based access control for viewers, operators, admins.
- Audit trail for camera switches, alert exports, and report downloads.
- Per-camera credentials and secrets management.
- Camera VLAN isolation and VPN-only remote access.
- Optional 2FA for admin actions.

Why this matters for AI Sentinel:

- Prevents the project from looking like a prototype with no controls.
- Makes the system safer for real deployments.

### 6. Specialized analytics modules

Borrow from OpenALPR and CompreFace:

- License plate recognition for parking, gates, and delivery bays.
- Face recognition for whitelist/blacklist use cases where policy allows it.
- Mask detection, head pose, and basic access-control heuristics.

Why this matters for AI Sentinel:

- Adds specialized value beyond "generic camera AI."
- Opens the door for site-specific deployments.
- Makes the platform more defensible as a product.

### 7. Scalability and deployment

Borrow from Kerberos.io and ZoneMinder:

- Support small deployments and multi-site deployments with the same codebase.
- Keep storage pluggable.
- Keep the backend flexible enough for local disk, NAS, or future object storage.
- Make camera profiles portable between sites.

Why this matters for AI Sentinel:

- Lets us start small without painting ourselves into a corner.

## Recommended AI Sentinel roadmap

### Phase 0: Ingest foundation

1. Go2rtc-style camera bridge.
2. ONVIF discovery and profile import.
3. Per-camera health checks.
4. Main stream plus substream mapping.
5. Stable camera profiles and network templates.

### Phase 1: Event intelligence

1. Zone editor and motion masks.
2. Object-based alerts.
3. Required-zone rules.
4. Pre/post capture evidence clips.
5. Snapshot gallery and evidence chain.
6. Event review queue with status labels.

### Phase 2: Operations

1. RBAC.
2. Admin audit trail.
3. VPN-only remote access policy.
4. Camera VLAN and DHCP reservation templates.
5. Backup/export of reports and clips.

### Phase 3: Specialization

1. License plate recognition.
2. Face recognition where policy allows it.
3. Visitor/blacklist workflows.
4. Parking and gate analytics.
5. Audio-risk hooks for distress or shouting.

### Phase 4: Scale and polish

1. Multi-site support.
2. Low-bandwidth mode.
3. Mobile-friendly review view.
4. Plugin architecture for new analytics modules.
5. Advanced operator dashboards.

## Recommended build order

If we want the biggest value with the least risk, the first feature set should be:

1. Stream bridge and camera onboarding.
2. Zones and masks.
3. Required-zone event logic.
4. Pre/post capture evidence clips.
5. Event review queue.
6. RBAC and audit trail.

After that, we can add specialization modules one by one.

## الميزات مع الشرح المبسط

هذا القسم يشرح الميزات بطريقة عملية وبسيطة، حتى تعرف ماذا سنبني بالضبط ولماذا هي مهمة.

### 1. ربط الكاميرات محليًا

المقصود أن الكاميرا لا تعتمد على بث مباشر من الإنترنت، بل ترتبط مباشرة داخل الشبكة المحلية `LAN` عبر `RTSP` أو `ONVIF`.

الفائدة:

- اتصال أسرع وأثبت.
- لا يعتمد على خدمة خارجية قد تتوقف.
- أسهل في الدمج مع النظام.

### 2. جسر بث واحد لكل الكاميرات

بدل ما يفتح البرنامج الكاميرا عدة مرات، نعمل طبقة وسيطة تستقبل البث مرة واحدة ثم تعيد توزيعه للتطبيق والواجهة.

الفائدة:

- تقل الأحمال على الكاميرا.
- يقل التقطيع.
- يسهل دعم أكثر من جهاز أو شاشة في نفس الوقت.

### 3. البث الرئيسي والبث الفرعي

بعض الكاميرات تعطيك أكثر من جودة:

- البث الرئيسي: جودة أعلى للتسجيل والأدلة.
- البث الفرعي: جودة أخف للتحليل السريع أو العرض في الواجهة.

الفائدة:

- نستخدم الجودة المناسبة لكل مهمة بدل ما نستهلك أعلى جودة دائمًا.

### 4. اكتشاف الكاميرات تلقائيًا

النظام يقدر يقرأ الكاميرات الموجودة في الشبكة، ويعرف اسم كل كاميرا وإعداداتها، بدل ما تضيف كل شيء يدويًا كل مرة.

الفائدة:

- أسرع في الإعداد.
- أقل أخطاء.
- مناسب لو زادت الكاميرات لاحقًا.

### 5. المراقبة الذكية بدل التحليل على كل فريم

بدل أن النموذج يحلل كل صورة في كل لحظة، نستخدم حركة أو إشارات مبدئية لتحديد متى نفعّل التحليل العميق.

الفائدة:

- توفير في المعالجة.
- استجابة أفضل.
- تقليل الضغط على المعالج أو الـ GPU.

### 6. المناطق Zones

نقسم الصورة إلى مناطق مثل:

- البوابة
- المدخل
- اللوبي
- المواقف
- الكاشير

ثم نحدد لكل منطقة ما الذي يهمنا.

الفائدة:

- النظام يفهم أين حدثت الحركة، وليس فقط أن هناك حركة.
- يقل الإنذارات غير المهمة.

### 7. أقنعة الحركة Motion Masks

أحيانًا في الصورة أجزاء لا تهمنا مثل السماء أو الشارع أو شاشة ثابتة أو مؤقت الوقت داخل الكاميرا.

نضع لها قناع حتى يتجاهلها النظام.

الفائدة:

- تقليل التنبيهات الكاذبة.
- تركيز أفضل على المنطقة المهمة.

### 8. قواعد إلزامية Required Rules

مثال:

- إذا دخل شخص للمنطقة `gate` فقط لا يكفي.
- إذا دخل شخص ومعه حركة مشبوهة أو سلاح محتمل أو أكثر من شخص في منطقة ممنوعة، عندها يصبح الحدث مهمًا.

الفائدة:

- يجعل التنبيه أذكى.
- يمنع إنذارات غير ضرورية.

### 9. مقاطع الأدلة Evidence Clips

عند حدوث حدث مهم، لا نحفظ فقط صورة واحدة، بل نحفظ مقطعًا قصيرًا قبل وبعد الحدث.

الفائدة:

- يعطي سياق كامل.
- مفيد جدًا في التحقيق.
- أفضل بكثير من لقطة واحدة فقط.

### 10. لقطات Snapshot

يحفظ النظام صورة ثابتة من الحدث مثل "اللقطة الأولى" أو "أفضل لقطة" من المشهد.

الفائدة:

- سريع في التصفح.
- مناسب للمعاينة السريعة.
- يسهل إرسال التنبيه في Telegram أو البريد.

### 11. سجل الأدلة Evidence Chain

هذا سجل يوضح:

- متى حدث التنبيه
- ما هي الكاميرا
- أين مقطع الفيديو
- أين الصورة
- أين التقرير

الفائدة:

- مهم جدًا في التوثيق.
- يجعل المشروع يبدو احترافيًا وموثوقًا.

### 12. تقرير جنائي Forensic Report

بعد الحدث، يمكن للنظام أن يكتب تقريرًا مختصرًا يشرح ما ظهر في الصورة أو الفيديو.

الفائدة:

- يعطي القارئ فهمًا سريعًا لما حدث.
- مفيد لفرق الأمن أو الإدارة.

### 13. قائمة مراجعة الأحداث Event Review Queue

بدل ما تأتي التنبيهات بشكل عشوائي، نجمعها في قائمة يمكن مراجعتها لاحقًا.

الفائدة:

- المراقب يراجع الأحداث واحدة واحدة.
- يمكن تعليم الحدث: صحيح، خطأ، تم اعتماده، تم تجاهله.

### 14. الصلاحيات Roles and Access Control

ليس كل مستخدم له نفس الصلاحيات.

مثال:

- Viewer: يشاهد فقط.
- Operator: يراجع الأحداث.
- Admin: يغير الكاميرات والإعدادات.

الفائدة:

- أمان أعلى.
- منع العبث بالإعدادات.

### 15. سجل التدقيق Audit Log

يسجل من فعل ماذا ومتى.

مثال:

- من غيّر الكاميرا
- من حمّل التقرير
- من فتح الأدلة

الفائدة:

- مهم للأمان والمراجعة.
- يساعدنا عند وجود مشكلة أو خطأ.

### 16. عزل الشبكة VLAN

نفصل شبكة الكاميرات عن شبكة السيرفرات والمستخدمين.

الفائدة:

- أمان أعلى.
- صعوبة وصول غير المصرح لهم.
- شبكة أكثر تنظيمًا.

### 17. دعم أكثر من ماركة كاميرات

النظام لا يقتصر على Tapo فقط، بل يدعم أيضًا EZVIZ وأي كاميرا تدعم `RTSP/ONVIF`.

الفائدة:

- حرية في الشراء.
- لا نربط المشروع بمصنّع واحد.

### 18. التعرف على اللوحات License Plate Recognition

إذا كانت الكاميرا عند البوابة أو المواقف، يمكن إضافة ميزة قراءة لوحة السيارة.

الفائدة:

- مفيد للمواقف والبوابات والتسليم.
- يعطي المشروع تخصصًا أقوى.

### 19. التعرف على الوجوه Face Recognition

النظام يقدر يميّز وجه شخص معروف إذا كان هذا مسموحًا في الموقع والسياسة.

الفائدة:

- مناسب لبعض البيئات الأمنية.
- مفيد للقوائم المسموحة أو المحظورة.

### 20. تحليل الصوت

إذا كانت الكاميرا فيها مايك، يمكن لاحقًا فحص الصوت لاكتشاف صراخ أو ضجيج غير طبيعي.

الفائدة:

- يضيف طبقة ثانية من الفهم.
- مفيد في الأماكن الحساسة.

### 21. دعم عدة مواقع

نفس النظام يمكن تشغيله في موقع واحد أو عدة مواقع.

الفائدة:

- قابل للتوسع.
- مناسب لو صار عندنا فروع مستقبلًا.

### 22. وضع ضعيف الشبكة

إذا كانت الشبكة بطيئة، النظام ينزل الجودة أو يستخدم البث الفرعي.

الفائدة:

- النظام يبقى يعمل بدل ما يتوقف.

### 23. واجهة مراجعة موبايل

واجهة واضحة للهاتف لمراجعة الأحداث والتنبيهات بسرعة.

الفائدة:

- تناسب الاستخدام اليومي.
- عملية جدًا لفرق الأمن أو الإدارة.

### 24. إضافات Plugins

بدل ما نضيف كل شيء داخل قلب النظام، نقدر نضيف ميزات على شكل وحدات مستقلة.

الفائدة:

- أسهل في التطوير.
- أسهل في الصيانة.
- يخلينا نضيف ذكاء جديد بدون كسر القديم.

## What to avoid for now

- Cloud-only camera workflows.
- Vendor apps as the runtime dependency.
- Adding too many AI models before the ingest layer is stable.
- Copying every feature from every project at once.
- Building face or plate recognition before the zone and evidence pipeline is solid.

## Practical recommendation for this repo

The strongest next step is to make AI Sentinel behave like a local NVR first:

- Local camera ingest.
- Clean event logic.
- Evidence clips.
- Review workflow.
- Security controls.

Then we add specialized intelligence on top.
