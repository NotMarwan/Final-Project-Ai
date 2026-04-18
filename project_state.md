# Project: AI Sentinel

## Current Objective
تشغيل وربط لوحة التحكم Next.js مع محرك الكشف FastAPI والتدفق الحي للتنبيهات والتقارير.

## Roadmap
- [Done] إعداد واجهة Next.js الأساسية ولوحة المراقبة.
- [Done] إعداد Backend FastAPI والاستدلال وكاميرات المصدر.
- [In-Progress] ربط البث الحي والتنبيهات بين الواجهة والخلفية.
- [Pending] تثبيت وتحسين التقارير الجنائية العربية وموثوقية الأدلة.
- [Pending] اختبار تشغيل end-to-end وتهيئة الإنتاج.

## Immediate Next Step
التحقق من مسار التشغيل الكامل محلياً بين `backend/api.py` و`app/page.tsx` والتأكد من وصول SSE alerts إلى الواجهة.

## Technical Debt / Obstacles
- وجود نصوص عربية أو ترميزات مشوهة في بعض الملفات المعروضة.
- وجود تكرار محتمل في `connectSSE` داخل `app/page.tsx`.
- اعتماد الواجهة على `http://localhost:8000/alerts` بشكل ثابت.
- الحاجة للتحقق من إعدادات Groq والمتغيرات البيئية.

## Context Logs
- 2026-04-17: تم العثور على `PROJECT_DOCUMENTATION.md` كتوثيق عام للمشروع، ولم يكن `project_state.md` موجوداً في الجذر، لذلك تم إنشاء ملف الذاكرة التشغيلية لأول مرة.
- 2026-04-17: تم اعتماد `project_state.md` كمرجع الحالة الرسمي الذي يجب قراءته في بداية أي جلسة وتحديثه عند كل تغيير مهم أو عند طلب "Status Update".
