import { NextResponse } from "next/server"

const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || "http://localhost:5000"

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const { url } = body

    console.log("Forwarding request to process video:", url)

    if (!url) {
      console.error("Missing URL in request")
      return NextResponse.json({ error: "YouTube URL is required" }, { status: 400 })
    }

    // Forward the request to the Python backend
    const response = await fetch(`${PYTHON_BACKEND_URL}/api/process-video`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ url }),
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

    // Log the received data structure
    console.log("Received video data from backend:", {
      title: data.title,
      transcriptCount: data.transcripts?.length || 0,
      ocrCount: data.ocr_text?.length || 0,
      ragEnabled: data.rag_enabled,
    })

    // Validate the data structure
    if (!data.transcripts) {
      console.warn("Warning: No transcripts in response data")
      data.transcripts = []
    }

    if (!data.ocr_text) {
      console.warn("Warning: No OCR text in response data")
      data.ocr_text = []
    }

    return NextResponse.json(data)
  } catch (error: any) {
    console.error("Error processing video:", error)
    return NextResponse.json({ error: `Failed to process video: ${error.message}` }, { status: 500 })
  }
}
