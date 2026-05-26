"use client"

import { useState, useEffect } from "react"
import { Card } from "@/components/ui/card"

interface VideoPlayerProps {
  videoUrl: string
}

export default function VideoPlayer({ videoUrl }: VideoPlayerProps) {
  const [videoId, setVideoId] = useState<string | null>(null)

  useEffect(() => {
    // Extract video ID from YouTube URL
    const extractVideoId = (url: string) => {
      const regExp = /^.*((youtu.be\/)|(v\/)|(\/u\/\w\/)|(embed\/)|(watch\?))\??v?=?([^#&?]*).*/
      const match = url.match(regExp)
      return match && match[7].length === 11 ? match[7] : null
    }

    setVideoId(extractVideoId(videoUrl))
  }, [videoUrl])

  if (!videoId) {
    return (
      <Card className="w-full aspect-video flex items-center justify-center bg-muted">
        <p className="text-muted-foreground">Invalid YouTube URL</p>
      </Card>
    )
  }

  return (
    <div className="w-full aspect-video">
      <iframe
        width="100%"
        height="100%"
        src={`https://www.youtube.com/embed/${videoId}`}
        title="YouTube video player"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
        className="rounded-lg"
      ></iframe>
    </div>
  )
}
