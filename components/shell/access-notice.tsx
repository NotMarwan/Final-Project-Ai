"use client"

import { LockKeyhole } from "lucide-react"
import { useApiAccess } from "@/hooks/use-api-access"

/** Shell-wide reminder that operator actions need the API key, which is entered in the System section. */
export function AccessNotice({ onOpenSystem }: { onOpenSystem: () => void }) {
  const { state } = useApiAccess()
  if (state !== "required") return null
  return <div className="access-notice" role="status">
    <LockKeyhole size={13} />
    <span>إجراءات المشغّل تتطلب مفتاح واجهة البرمجة.</span>
    <button type="button" onClick={onOpenSystem}>إدخال المفتاح من قسم النظام</button>
  </div>
}
