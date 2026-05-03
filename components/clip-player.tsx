"use client"

import React, { useRef, useEffect } from "react"
import { useClipPlayback } from "@/hooks/use-clip-playback"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { 
  Play, 
  Pause, 
  Repeat, 
  Repeat1, 
  Maximize2 
} from "lucide-react"

interface ClipPlayerProps {
  clipUrl?: string
  clipName?: string
  autoPlay?: boolean
  className?: string
}

export function ClipPlayer({ clipUrl, clipName, autoPlay = true, className }: ClipPlayerProps) {
  const {
    isPlaying,
    isLooping,
    playbackSpeed,
    videoRef,
    togglePlay,
    toggleLoop,
    setSpeed,
    playClip,
  } = useClipPlayback({
    initialLoop: true,
    onLoopComplete: () => {
      console.log(`[ClipPlayer] Loop completed for ${clipName}`)
    },
  })

  // Load clip when URL changes
  useEffect(() => {
    if (clipUrl) {
      if (autoPlay) {
        playClip(clipUrl)
      } else if (videoRef.current && videoRef.current.src !== clipUrl) {
        videoRef.current.src = clipUrl
      }
    }
  }, [clipUrl, autoPlay, playClip, videoRef])

  const handleSpeedChange = (value: number[]) => {
    const newSpeed = value[0]
    setSpeed(newSpeed)
  }

  return (
    <div className={`relative bg-black rounded-lg overflow-hidden ${className}`}>
      <video
        ref={videoRef}
        className="w-full h-full object-contain"
        loop={isLooping}
        playsInline
      />
      
      {/* Clip name overlay */}
      {clipName && (
        <div className="absolute top-2 left-2 bg-black/70 text-white text-xs px-2 py-1 rounded">
          {clipName}
        </div>
      )}
      
      {/* Controls overlay */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-3">
        <div className="flex items-center gap-2">
          {/* Play/Pause */}
          <Button
            variant="ghost"
            size="icon"
            className="text-white hover:bg-white/20 h-8 w-8"
            onClick={togglePlay}
          >
            {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </Button>
          
          {/* Loop toggle */}
          <Button
            variant="ghost"
            size="icon"
            className={`h-8 w-8 ${isLooping ? "text-primary" : "text-white"} hover:bg-white/20`}
            onClick={toggleLoop}
          >
            {isLooping ? <Repeat className="h-4 w-4" /> : <Repeat1 className="h-4 w-4" />}
          </Button>
          
          {/* Speed control */}
          <div className="flex items-center gap-2 flex-1">
            <span className="text-white text-xs">Speed:</span>
            <Slider
              min={0.25}
              max={2.0}
              step={0.25}
              value={[playbackSpeed]}
              onValueChange={handleSpeedChange}
              className="flex-1"
            />
            <span className="text-white text-xs w-8">{playbackSpeed}x</span>
          </div>
          
          {/* Fullscreen */}
          <Button
            variant="ghost"
            size="icon"
            className="text-white hover:bg-white/20 h-8 w-8"
            onClick={() => videoRef.current?.requestFullscreen()}
          >
            <Maximize2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
