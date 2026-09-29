import type { LiveAlert } from "@/components/video-player"

/** Preview data is stable for a given anchor and never enters production. */
export function fixturesEnabled(search: string): boolean {
  return process.env.NODE_ENV !== "production" && new URLSearchParams(search).get("fixtures") === "1"
}

export function makeUiFixtures(anchor: number): LiveAlert[] {
  const minutes = [2, 4, 7, 9, 12, 17, 23, 29, 35, 43, 51, 57, 64, 73, 83, 96, 108, 118]
  const cameraIds = ["CAM-01", "CAM-02", "CAM-03"]
  return minutes.map((offset, index) => {
    const time = new Date(anchor - offset * 60_000)
    return {
      id: `PREVIEW-${String(index + 1).padStart(3, "0")}`,
      isoTime: time.toISOString(),
      timestamp: time.toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit" }),
      cameraId: cameraIds[index % cameraIds.length],
      location: ["البوابة الشمالية", "الممر الشرقي", "الساحة الرئيسية"][index % 3],
      type: index % 3 === 1 ? "Violence" : "Weapon",
      severity: index === 0 || index === 7 ? "critical" : index % 3 === 0 ? "high" : "medium",
      confidence: [93, 78, 86, 74, 91, 68, 82, 88, 76][index % 9],
      alertLatencyMs: [842, 1120, 970, 1380, 765, 1045][index % 6],
    }
  })
}
