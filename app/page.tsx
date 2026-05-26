"use client"

import type React from "react"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Loader2, Play } from "lucide-react"
import VideoPlayer from "@/components/video-player"
import VideoSummary from "@/components/video-summary"
import ChatInterface from "@/components/chat-interface"

export default function Home() {
  const [youtubeUrl, setYoutubeUrl] = useState("")
  const [isProcessing, setIsProcessing] = useState(false)
  const [videoData, setVideoData] = useState<any>(null)
  const [error, setError] = useState("")
  const [videoTitle, setVideoTitle] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!youtubeUrl.includes("youtube.com") && !youtubeUrl.includes("youtu.be")) {
      setError("Please enter a valid YouTube URL")
      return
    }

    setError("")
    setIsProcessing(true)
    setVideoData(null)
    setVideoTitle("")

    try {
      console.log("Sending request to process video:", youtubeUrl)
      const response = await fetch("/api/process-video", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ url: youtubeUrl }),
      })

      console.log("Response status:", response.status)

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        console.error("API error response:", errorData)
        throw new Error(`Failed to process video: ${response.status} ${response.statusText}`)
      }

      const data = await response.json()
      console.log("Received data:", data)

      if (!data || !data.transcripts || !data.ocr_text) {
        throw new Error("Invalid data format received from API")
      }

      setVideoData(data)
      console.log("Received video data with transcripts:", videoData?.transcripts?.length || 0, "segments")
      setVideoTitle(data.title || "YouTube Video")
    } catch (err: any) {
      console.error("Error processing video:", err)
      setError(`Error processing video: ${err.message || "Unknown error"}`)
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <main className="container mx-auto py-8 px-4">
      <h1 className="text-3xl font-bold text-center mb-8">YouTube Video Analysis & Q&A</h1>

      <form onSubmit={handleSubmit} className="flex gap-2 mb-8 max-w-2xl mx-auto">
        <Input
          type="text"
          placeholder="Enter YouTube video URL"
          value={youtubeUrl}
          onChange={(e) => setYoutubeUrl(e.target.value)}
          className="flex-1"
          disabled={isProcessing}
        />
        <Button type="submit" disabled={isProcessing}>
          {isProcessing ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Processing
            </>
          ) : (
            <>
              <Play className="mr-2 h-4 w-4" />
              Analyze
            </>
          )}
        </Button>
      </form>

      {error && <p className="text-red-500 text-center mb-4">{error}</p>}

      {isProcessing && (
        <div className="flex flex-col items-center justify-center py-12">
          <Loader2 className="h-12 w-12 animate-spin mb-4" />
          <p className="text-lg">Processing video... This may take a few minutes.</p>
          <p className="text-sm text-muted-foreground mt-2">
            We're extracting audio, transcribing content, and analyzing video frames.
          </p>
        </div>
      )}

      {videoData && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <div className="mb-4">
              <h2 className="text-2xl font-bold">{videoTitle}</h2>
            </div>

            <VideoPlayer videoUrl={youtubeUrl} />

            <Tabs defaultValue="summary" className="mt-6">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="summary">Video Summary</TabsTrigger>
                <TabsTrigger value="chat">Ask Questions</TabsTrigger>
              </TabsList>
              <TabsContent value="summary">
                <Card>
                  <CardHeader>
                    <CardTitle>Video Summary</CardTitle>
                    <CardDescription>Generated from video transcription and visual content</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <VideoSummary videoData={videoData} />
                  </CardContent>
                </Card>
              </TabsContent>
              <TabsContent value="chat">
                <Card>
                  <CardHeader>
                    <CardTitle>Video Q&A</CardTitle>
                    <CardDescription>Ask questions about the video content</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ChatInterface videoData={videoData} videoUrl={youtubeUrl} />
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </div>

          <div className="lg:col-span-1">
            <Card>
              <CardHeader>
                <CardTitle>Extracted Data</CardTitle>
                <CardDescription>Raw data extracted from the video</CardDescription>
              </CardHeader>
              <CardContent className="max-h-[600px] overflow-y-auto">
                <div className="space-y-4">
                  <div>
                    <h3 className="font-medium mb-2">Transcripts</h3>
                    <div className="bg-muted p-3 rounded-md text-sm max-h-[300px] overflow-y-auto">
                      {videoData.transcripts && videoData.transcripts.length > 0 ? (
                        videoData.transcripts.map((t: any, i: number) => (
                          <div key={i} className="mb-2 pb-2 border-b border-border last:border-0">
                            <span className="text-xs text-muted-foreground block mb-1">
                              [{t.start} - {t.end}]
                            </span>
                            <p>{t.text}</p>
                          </div>
                        ))
                      ) : (
                        <p className="text-muted-foreground">No transcript data available</p>
                      )}
                    </div>
                  </div>

                  <div>
                    <h3 className="font-medium mb-2">OCR Text</h3>
                    <div className="bg-muted p-3 rounded-md text-sm">
                      {videoData.ocr_text.map((o: any, i: number) => (
                        <div key={i} className="mb-2">
                          <span className="text-xs text-muted-foreground">[{o.timestamp}]</span>
                          <p>{o.ocr_text}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </main>
  )
}
