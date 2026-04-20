# Phase 2 (CNET 575) - Judges Checklist (Mid-Term)

هذه ورقة مختصرة (Cheat Sheet) مبنية مباشرة على نماذج التقييم الخاصة بـ Phase 2.

## A) نموذج الميد (First Examiner Assessment Form)

المحكّم عادة يوزع الدرجة على البنود التالية:

1. **Project Design (10%)**
   - المطلوب: شرح تصميم المشروع بوضوح (Architecture + تدفق البيانات).
   - ماذا نعرض: مخطط بسيط للطبقات + تدفق الفيديو والتنبيه + أين يتم حفظ الأدلة.

2. **Project Development (25%)**
   - المطلوب: تطوير فعلي وكود/تجارب (Coding/Experimental work).
   - ماذا نعرض: تشغيل النظام + ملفات الكود + نقاط تنفيذ واضحة (API endpoints, UI components).

3. **Project Demonstration (25%)**
   - المطلوب: تطبيق فعلي/تحقق من النموذج المقترح.
   - ماذا نعرض: بث فيديو، ظهور Alert، فتح تفاصيل الحادث، تنزيل Evidence/Report.

4. **Originality (15%)**
   - المطلوب: فكرة جديدة أو دمج ذكي يحل مشكلة واقعية.
   - ماذا نقول: دورة كاملة "كشف -> تنبيه -> دليل -> تقرير عربي" + دمج Threat Fusion + Evidence Integrity.

5. **Relevance/Scope/Goals/Objectives (15%)**
   - المطلوب: تبرير المشكلة والنطاق والأهداف.
   - ماذا نقول: قصّة واضحة (Problem -> Why now -> Goals -> Scope -> Constraints).

6. **Presentation Skill (5%)**
   - المطلوب: عرض مرتب وواضح (وقت، ترتيب، لغة).
   - ماذا نفعل: 8-10 شرائح، ديمو سريع، توزيع الكلام بين الفريق.

7. **Q&A (5%)**
   - المطلوب: إجابات ثابتة ومقنعة.
   - ماذا نفعل: نحضر 8-10 أسئلة متوقعة (الكاميرا، الدقة، الأداء، الفولس بوزتف، الخصوصية، التوسع).

## B) نموذج النهائي (Final Examiners Assessment Form) وما يهمنا للميد

هذا النموذج يوضح أن **الميد غالبًا من 20** (Mid-Term 20)، ويتضمن محورين مهمين:

### Section A - Project Presentation (20)

- **Implementation (10):** System development + test cases + testing
- **System Demonstration (5):** مهارة عرض المشروع عمليًا
- **Q&A (5):** تبرير وإجابات قوية

### Section B - Documentation (20) (ينفع نستعد له من الآن)

- Structure/Template (5)
- Clarity (5)
- Technical contents (3)
- Diagrams/Tables (2)
- Formatting (3)
- References (2)

## C) تطبيق البنود على AI Sentinel (ماذا نثبت أمام اللجنة)

هذه الأشياء "ممكن نثبتها" مباشرة من النظام الحالي:

- بث فيديو عبر `GET /video_feed`
- تنبيهات لحظية عبر `GET /alerts` (SSE)
- تنزيل تقرير PDF عبر `GET /download_report/{alert_id}`
- تنزيل Evidence clip عبر `GET /download_evidence/{alert_id}`
- تبديل كاميرا/مصدر عبر `POST /switch_camera`
- سجل أدلة `Evidence Ledger` مع `SHA-256` (يوضح سلامة الأدلة)
- وجود اختبارات وحدة (Unit tests) ونجاحها

## D) خطة ديمو 4-6 دقائق (مناسبة للميد)

1. نفتح Dashboard.
2. نظهر الفيديو يعمل.
3. نشغل مشهد فيه عنف (أو ننتقل لمصدر فيديو جاهز).
4. ننتظر Alert يظهر في Alert Feed.
5. نفتح Incident details.
6. ننزل Evidence clip.
7. ننزل PDF report.

## E) نقطة الكاميرا Anker 2K (كيف نجاوب)

- إذا اشتغلت مباشرة (USB/UVC أو RTSP): ممتاز، نخليها جزء من الديمو.
- إذا ما اشتغلت (كاميرا مغلقة بتطبيق): نقول إن النظام يدعم كاميرات قياسية RTSP/ONVIF وUSB، واستخدمنا مصدر ثابت لضمان نجاح العرض، ونكمل دمج الكاميرا كجزء من خطة التطبيق العملي.

