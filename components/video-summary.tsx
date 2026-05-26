"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Volume2, VolumeX, Loader2 } from "lucide-react"

interface VideoSummaryProps {
  videoData: any
}

export default function VideoSummary({ videoData }: VideoSummaryProps) {
  const [summary, setSummary] = useState<string>("")
  const [isLoading, setIsLoading] = useState(true)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [speechSynthesis, setSpeechSynthesis] = useState<SpeechSynthesis | null>(null)
  const [utterance, setUtterance] = useState<SpeechSynthesisUtterance | null>(null)

  useEffect(() => {
    // Initialize speech synthesis
    if (typeof window !== "undefined") {
      setSpeechSynthesis(window.speechSynthesis)
    }
  }, [])

  useEffect(() => {
    const generateSummary = async () => {
      setIsLoading(true)
      try {
        // Log the transcript and OCR data counts
        console.log("Generating summary for video data:", {
          hasTranscripts: Boolean(videoData?.transcripts),
          transcriptCount: videoData?.transcripts?.length || 0,
          hasOCR: Boolean(videoData?.ocr_text),
          ocrCount: videoData?.ocr_text?.length || 0,
        })

        const response = await fetch("/api/generate-summary", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ videoData }),
        })

        console.log("Summary response status:", response.status)

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          console.error("Summary API error:", errorData)
          throw new Error(`Failed to generate summary: ${response.status}`)
        }

        const data = await response.json()
        console.log("Summary data received:", data)

        if (!data || !data.summary) {
          throw new Error("Invalid summary data format")
        }

        setSummary(data.summary)
      } catch (err: any) {
        console.error("Error generating summary:", err)
        setSummary(`Failed to generate summary: ${err.message || "Unknown error"}. Please try again.`)
      } finally {
        setIsLoading(false)
      }
    }

    if (videoData) {
      generateSummary()
    }
  }, [videoData])

  const toggleSpeech = () => {
    if (!speechSynthesis) return

    if (isSpeaking) {
      speechSynthesis.cancel()
      setIsSpeaking(false)
      return
    }

    const newUtterance = new SpeechSynthesisUtterance(summary)
    setUtterance(newUtterance)

    newUtterance.onend = () => {
      setIsSpeaking(false)
    }

    speechSynthesis.speak(newUtterance)
    setIsSpeaking(true)
  }

  useEffect(() => {
    return () => {
      if (speechSynthesis && isSpeaking) {
        speechSynthesis.cancel()
      }
    }
  }, [speechSynthesis, isSpeaking])

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-8">
        <Loader2 className="h-8 w-8 animate-spin mb-4" />
        <p>Generating summary...</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium">Summary</h3>
        <Button variant="outline" size="sm" onClick={toggleSpeech} disabled={!summary || summary.includes("Failed")}>
          {isSpeaking ? <VolumeX className="h-4 w-4 mr-2" /> : <Volume2 className="h-4 w-4 mr-2" />}
          {isSpeaking ? "Stop" : "Read Aloud"}
        </Button>
      </div>
      <div className="bg-muted p-4 rounded-lg">
        <p className="whitespace-pre-line">{summary}</p>
      </div>
    </div>
  )
}
