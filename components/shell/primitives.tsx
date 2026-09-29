import type { ReactNode } from "react"
import { normalizeLatinDigits } from "./locale"

/** Keeps technical readings tabular while Arabic fallback states use the UI font. */
export function InstrumentValue({ value, className = "" }: { value: string | number; className?: string }) {
  const display = normalizeLatinDigits(String(value))
  const arabic = /[\u0600-\u06ff]/u.test(display)
  return <bdi dir={arabic ? "auto" : "ltr"} className={`${arabic ? "font-sans" : "instrument-num"} ${className}`}>{display}</bdi>
}

/** Shared instrument frame. Surface, hairline, radius, and focus colors live in app/globals.css. */
export function InstrumentPanel({ title, index, children, className = "" }: { title: string; index: string; children: ReactNode; className?: string }) {
  return <section className={`instrument-panel chart-card ${className}`}><div className="chart-heading"><span className="section-index instrument-num">{index}</span><h3>{title}</h3><span className="chart-heading-line" /></div>{children}</section>
}
