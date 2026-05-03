"use client"

import React, { useState, useEffect, useRef } from "react"
import { 
  Play, 
  Pause, 
  RotateCcw, 
  ShieldAlert, 
  Zap,
  Volume2,
  VolumeX,
  Maximize2,
  ChevronUp,
  ChevronDown,
  Info
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Slider } from "@/components/ui/slider"
import { cn } from "@/lib/utils"

interface IncidentReplayProps {
  clipUrl?: string
  thumbnailUrl?: string
  threatType: "violence" | "weapon"
  confidence: number
  location: string
  timestamp: string
  onClose?: () => void
  className?: string
  autoPlay?: boolean
}

export function IncidentReplay({
  clipUrl,
  thumbnailUrl,
  threatType,
  confidence,
  location,
  timestamp,
  onClose,
  className,
  autoPlay = true
}: IncidentReplayProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isPlaying, setIsPlaying] = useState(autoPlay)
  const [isMuted, setIsMuted] = useState(true)
  const [progress, setProgress] = useState(0)
  const [showOverlay, setShowOverlay] = useState(true)
  const [isLooping, setIsLooping] = useState(true)

  // Update progress bar
  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const handleTimeUpdate = () => {
      const p = (video.currentTime / video.duration) * 100
      setProgress(p || 0)
    }

    video.addEventListener("timeupdate", handleTimeUpdate)
    return () => video.removeEventListener("timeupdate", handleTimeUpdate)
  }, [])

  // Handle autoplay and source changes
  useEffect(() => {
    if (clipUrl && videoRef.current) {
      videoRef.current.src = clipUrl
      if (autoPlay) {
        videoRef.current.play().catch(e => console.warn("[IncidentReplay] Autoplay failed:", e))
        setIsPlaying(true)
      }
    }
  }, [clipUrl, autoPlay])

  const togglePlay = () => {
    if (!videoRef.current) return
    if (isPlaying) {
      videoRef.current.pause()
    } else {
      videoRef.current.play()
    }
    setIsPlaying(!isPlaying)
  }

  const toggleMute = () => {
    if (!videoRef.current) return
    videoRef.current.muted = !isMuted
    setIsMuted(!isMuted)
  }

  const restart = () => {
    if (!videoRef.current) return
    videoRef.current.currentTime = 0
    videoRef.current.play()
    setIsPlaying(true)
  }

  return (
    <div className={cn(
      "relative flex flex-col bg-black overflow-hidden rounded-2xl border border-white/10 shadow-2xl",
      "aspect-[9/16] max-h-[700px] w-full max-w-[400px]",
      className
    )}>
      {/* Video element */}
      <video
        ref={videoRef}
        className="h-full w-full object-cover"
        loop={isLooping}
        muted={isMuted}
        playsInline
        poster={thumbnailUrl}
        onClick={togglePlay}
      />

      {/* Top Overlay: Threat Info */}
      <div className="absolute top-0 left-0 right-0 p-4 bg-gradient-to-b from-black/80 via-black/40 to-transparent z-10">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <Badge variant="destructive" className="animate-pulse bg-red-600 hover:bg-red-700 text-[10px] py-0 px-2 uppercase tracking-widest font-bold">
              <Zap className="h-3 w-3 mr-1 fill-current" />
              Incident Replay
            </Badge>
            <h3 className="text-white font-bold text-lg leading-tight flex items-center gap-2">
              {threatType === "violence" ? "Violence Detected" : "Weapon Identified"}
              <ShieldAlert className="h-4 w-4 text-red-500" />
            </h3>
            <p className="text-white/60 text-[10px] font-medium flex items-center gap-1">
              <span className="text-red-400 font-bold">{confidence}% Confidence</span>
              <span className="text-white/20">•</span>
              {location}
            </p>
          </div>
          
          <div className="flex flex-col items-end gap-2">
            <div className="bg-black/40 backdrop-blur-md rounded-full p-2 border border-white/10">
              <span className="text-white text-[10px] font-mono">{timestamp}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Side Actions (TikTok Style) */}
      <div className="absolute right-3 bottom-24 flex flex-col gap-6 z-20">
        <div className="flex flex-col items-center gap-1 group">
          <div className="w-12 h-12 rounded-full bg-white/10 backdrop-blur-xl border border-white/20 flex items-center justify-center cursor-pointer transition-all hover:bg-white/20 active:scale-90" onClick={toggleMute}>
            {isMuted ? <VolumeX className="text-white h-5 w-5" /> : <Volume2 className="text-white h-5 w-5" />}
          </div>
          <span className="text-white text-[10px] font-medium shadow-sm">Audio</span>
        </div>

        <div className="flex flex-col items-center gap-1 group">
          <div className="w-12 h-12 rounded-full bg-white/10 backdrop-blur-xl border border-white/20 flex items-center justify-center cursor-pointer transition-all hover:bg-white/20 active:scale-90" onClick={restart}>
            <RotateCcw className="text-white h-5 w-5" />
          </div>
          <span className="text-white text-[10px] font-medium shadow-sm">Restart</span>
        </div>

        <div className="flex flex-col items-center gap-1 group">
          <div className="w-12 h-12 rounded-full bg-white/10 backdrop-blur-xl border border-white/20 flex items-center justify-center cursor-pointer transition-all hover:bg-white/20 active:scale-90" onClick={() => videoRef.current?.requestFullscreen()}>
            <Maximize2 className="text-white h-5 w-5" />
          </div>
          <span className="text-white text-[10px] font-medium shadow-sm">Focus</span>
        </div>
      </div>

      {/* Bottom Controls */}
      <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-black/90 via-black/60 to-transparent z-10">
        <div className="flex flex-col gap-3">
          {/* Progress bar */}
          <div className="h-1 w-full bg-white/20 rounded-full overflow-hidden">
            <div 
              className="h-full bg-red-600 transition-all duration-100 ease-linear" 
              style={{ width: `${progress}%` }} 
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-8 w-8 text-white hover:bg-white/10 rounded-full"
                onClick={togglePlay}
              >
                {isPlaying ? <Pause className="h-5 w-5 fill-current" /> : <Play className="h-5 w-5 fill-current" />}
              </Button>
              <div className="text-white/60 text-[10px] font-mono">
                00:0{Math.floor((videoRef.current?.currentTime || 0) % 10)} / 00:05
              </div>
            </div>

            <Button
              variant="outline"
              size="sm"
              className="bg-white/5 border-white/10 text-white hover:bg-white/10 text-[10px] h-7 gap-1"
            >
              <Info className="h-3 w-3" />
              Detailed View
            </Button>
          </div>
        </div>
      </div>

      {/* Centered Play/Pause Button Animation Overlay */}
      {!isPlaying && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-20 h-20 rounded-full bg-black/40 backdrop-blur-sm flex items-center justify-center border border-white/20">
            <Play className="text-white h-10 w-10 ml-1 fill-current" />
          </div>
        </div>
      )}
    </div>
  )
}
