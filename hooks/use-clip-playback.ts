"use client"

import { useState, useCallback, useRef, useEffect } from "react"

export interface UseClipPlaybackOptions {
  initialLoop?: boolean
  initialSpeed?: number
  onLoopComplete?: () => void
}

export interface UseClipPlaybackReturn {
  isPlaying: boolean
  isLooping: boolean
  playbackSpeed: number
  videoRef: React.RefObject<HTMLVideoElement | null>
  togglePlay: () => void
  toggleLoop: () => void
  setSpeed: (speed: number) => void
  seekTo: (time: number) => void
  playClip: (clipUrl: string) => void
}

export function useClipPlayback(options: UseClipPlaybackOptions = {}): UseClipPlaybackReturn {
  const { initialLoop = true, initialSpeed = 1.0, onLoopComplete } = options
  
  const [isPlaying, setIsPlaying] = useState(false)
  const [isLooping, setIsLooping] = useState(initialLoop)
  const [playbackSpeed, setPlaybackSpeed] = useState(initialSpeed)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const currentClipUrl = useRef<string | null>(null)

  const togglePlay = useCallback(() => {
    const video = videoRef.current
    if (!video) return

    if (video.paused) {
      video.play()
      setIsPlaying(true)
    } else {
      video.pause()
      setIsPlaying(false)
    }
  }, [])

  const toggleLoop = useCallback(() => {
    setIsLooping((prev) => !prev)
  }, [])

  const seekTo = useCallback((time: number) => {
    const video = videoRef.current
    if (!video) return
    video.currentTime = time
  }, [])

  const playClip = useCallback(
    (clipUrl: string) => {
      const video = videoRef.current
      if (!video) return

      if (currentClipUrl.current !== clipUrl) {
        video.src = clipUrl
        currentClipUrl.current = clipUrl
      }

      video.playbackRate = playbackSpeed
      video.play()
      setIsPlaying(true)
    },
    [playbackSpeed],
  )

  // Handle loop functionality
  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const handleEnded = () => {
      if (isLooping) {
        video.currentTime = 0
        video.play()
        onLoopComplete?.()
      } else {
        setIsPlaying(false)
      }
    }

    video.addEventListener("ended", handleEnded)
    return () => video.removeEventListener("ended", handleEnded)
  }, [isLooping, onLoopComplete])

  // Update playback speed when it changes
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    video.playbackRate = playbackSpeed
  }, [playbackSpeed])

  return {
    isPlaying,
    isLooping,
    playbackSpeed,
    videoRef,
    togglePlay,
    toggleLoop,
    setSpeed: (speed: number) => setPlaybackSpeed(speed),
    seekTo,
    playClip,
  }
}
