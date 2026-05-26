import { NextResponse } from "next/server"

const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || "http://localhost:5000"

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const { videoData } = body

    // Log the transcript and OCR data counts
    console.log("Forwarding request to generate summary:", {
      hasTranscripts: Boolean(videoData?.transcripts),
      transcriptCount: videoData?.transcripts?.length || 0,
      hasOCR: Boolean(videoData?.ocr_text),
      ocrCount: videoData?.ocr_text?.length || 0,
    })

    if (!videoData) {
      console.error("Invalid video data format")
      return NextResponse.json({ error: "Valid video data is required" }, { status: 400 })
    }

    // Ensure transcripts and OCR data are arrays
    if (!Array.isArray(videoData.transcripts)) {
      console.warn("Transcripts is not an array, initializing as empty array")
      videoData.transcripts = []
    }

    if (!Array.isArray(videoData.ocr_text)) {
      console.warn("OCR text is not an array, initializing as empty array")
      videoData.ocr_text = []
    }

    // Forward the request to the Python backend
    const response = await fetch(`${PYTHON_BACKEND_URL}/api/generate-summary`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ videoData }),
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      console.error("Python backend error:", errorData)
      return NextResponse.json(
        { error: `Backend error: ${response.status} ${response.statusText}` },
        { status: response.status },
      )
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch (error: any) {
    console.error("Error generating summary:", error)
    return NextResponse.json(
      {
        error: `Failed to generate summary: ${error.message}`,
        summary: "Failed to generate a summary for this video. Please try again.",
      },
      { status: 500 },
    )
  }
}
