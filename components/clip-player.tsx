"use client"

import { useEffect, useState } from "react"
import { Maximize2, Pause, Play, Repeat, Repeat1, VideoOff } from "lucide-react"
import { Slider } from "@/components/ui/slider"
import { useClipPlayback } from "@/hooks/use-clip-playback"

type Props = { clipUrl?: string; clipName?: string; autoPlay?: boolean; className?: string }

export function ClipPlayer({ clipUrl, clipName, autoPlay = true, className = "" }: Props) {
  const { isPlaying, isLooping, playbackSpeed, videoRef, togglePlay, toggleLoop, setSpeed, playClip } = useClipPlayback({ initialLoop: true })
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!clipUrl) return
    if (autoPlay) playClip(clipUrl)
    else if (videoRef.current && videoRef.current.src !== clipUrl) videoRef.current.src = clipUrl
  }, [clipUrl, autoPlay, playClip, videoRef])

  return <div className={`relative flex min-h-[210px] flex-col overflow-hidden rounded-md border border-[var(--border-hairline)] bg-[var(--surface-0)] ${className}`}>
    <div className="relative min-h-[160px] flex-1"><video ref={videoRef} loop={isLooping} playsInline onError={() => setFailed(true)} onLoadedData={() => setFailed(false)} className="size-full object-contain" />{(!clipUrl || failed) && <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-[var(--surface-0)] text-[var(--text-tertiary)]"><VideoOff size={24} /><strong className="text-xs text-[var(--text-primary)]">{failed ? "تعذّر تشغيل المقطع" : "لا يوجد مقطع محدد"}</strong><span className="text-[10px]">{failed ? "تحقق من توفر ملف الدليل وصيغته." : "اختر دليلاً لعرضه هنا."}</span></div>}{clipName && <bdi className="instrument-num absolute start-2 top-2 max-w-[80%] truncate rounded border border-[var(--border-hairline)] bg-[var(--surface-1)]/90 px-2 py-1 text-[10px] text-[var(--text-primary)]" dir="auto">{clipName}</bdi>}</div>
    <div className="flex flex-wrap items-center gap-2 border-t border-[var(--border-hairline)] bg-[var(--surface-1)] px-2 py-2"><button type="button" aria-label={isPlaying ? "إيقاف المقطع مؤقتاً" : "تشغيل المقطع"} disabled={!clipUrl || failed} onClick={togglePlay} className="grid size-8 place-items-center rounded text-[var(--text-secondary)] hover:bg-[var(--surface-2)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40">{isPlaying ? <Pause size={16} /> : <Play size={16} />}</button><button type="button" aria-label={isLooping ? "إيقاف تكرار المقطع" : "تكرار المقطع"} aria-pressed={isLooping} onClick={toggleLoop} className={`grid size-8 place-items-center rounded hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] ${isLooping ? "text-[var(--state-replay)]" : "text-[var(--text-secondary)]"}`}>{isLooping ? <Repeat size={16} /> : <Repeat1 size={16} />}</button><div className="flex min-w-[110px] flex-1 items-center gap-2"><label id="clip-speed" className="whitespace-nowrap text-[10px] text-[var(--text-secondary)]">السرعة</label><Slider aria-labelledby="clip-speed" min={0.25} max={2} step={0.25} value={[playbackSpeed]} onValueChange={([speed]) => setSpeed(speed)} className="flex-1" /><bdi className="instrument-num w-9 text-end text-[10px] text-[var(--text-primary)]" dir="ltr">{playbackSpeed}×</bdi></div><button type="button" aria-label="عرض المقطع بملء الشاشة" disabled={!clipUrl || failed} onClick={() => void videoRef.current?.requestFullscreen()} className="grid size-8 place-items-center rounded text-[var(--text-secondary)] hover:bg-[var(--surface-2)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40"><Maximize2 size={16} /></button></div>
  </div>
}
