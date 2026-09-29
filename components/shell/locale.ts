export const ARABIC_LATIN_LOCALE = "ar-SA-u-ca-gregory-nu-latn"

export function normalizeLatinDigits(value: string): string {
  return value.replace(/[\u0660-\u0669\u06f0-\u06f9]/gu, (digit) => {
    const code = digit.charCodeAt(0)
    return String(code - (code >= 0x06f0 ? 0x06f0 : 0x0660))
  })
}

export function formatTime24(value: string | number | Date, seconds = false): string {
  return normalizeLatinDigits(new Date(value).toLocaleTimeString(ARABIC_LATIN_LOCALE, {
    hour: "2-digit", minute: "2-digit", ...(seconds ? { second: "2-digit" } : {}), hourCycle: "h23",
  }))
}

export function formatDateTime24(value: string | number | Date): string {
  return normalizeLatinDigits(new Date(value).toLocaleString(ARABIC_LATIN_LOCALE, {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }))
}
