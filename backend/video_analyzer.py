import os
import cv2
import json
import whisper
import pytesseract
import easyocr
import numpy as np
import yt_dlp
import tempfile
from google import generativeai as genai

import concurrent.futures
import threading
from datetime import timedelta
from difflib import SequenceMatcher
from flask import Flask, request, jsonify
from flask_cors import CORS
from sentence_transformers import SentenceTransformer
import faiss
import re
import nltk
from nltk.tokenize import sent_tokenize

# ========== CONFIGURATION ==========
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
app = Flask(__name__)
CORS(app)

# ========== Shared Data ==========
class SharedData:
    def _init_(self):
        self.processed_timestamps = set()
        self.transcript_store = {}
        self.lock = threading.Lock()

shared_data = SharedData()

# ========== Gemini API ==========
gemini_model = None
try:
    if not GEMINI_API_KEY:
        print("Gemini API Key is missing. Set GEMINI_API_KEY environment variable.")
    else:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel('gemini-2.5-flash')
        print("Gemini API configured.")
except Exception as e:
    print(f"Error configuring Gemini API: {e}")

# ========== RAG Components ==========

# Initialize sentence transformer model for embeddings
try:
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    print("Embedding model loaded.")
    
    # Download nltk data if needed
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt')
        print("NLTK punkt tokenizer downloaded.")
except Exception as e:
    print(f"Error loading embedding model: {e}")
    embedding_model = None

class RAGPipeline:
    def __init__(self, embedding_dim=384):  # default dim for all-MiniLM-L6-v2
        self.embedding_dim = embedding_dim
        self.chunk_index = None
        self.chunks = []
        self.video_id = None
        
    def reset(self):
        """Reset the RAG pipeline for a new video."""
        self.chunk_index = None
        self.chunks = []
        self.video_id = None
        
    def extract_youtube_id(self, url):
        """Extract YouTube video ID from URL."""
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'(?:embed\/)([0-9A-Za-z_-]{11})',
            r'(?:watch\?v=)([0-9A-Za-z_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
        
    def chunk_text(self, transcripts, ocr_data, chunk_size=3, overlap=1):
        """
        Chunk the transcript and OCR text into smaller pieces.
        
        Args:
            transcripts: List of transcript segments
            ocr_data: List of OCR segments
            chunk_size: Number of segments to include in each chunk
            overlap: Number of segments to overlap between chunks
        
        Returns:
            List of chunks with metadata
        """
        chunks = []
        
        # Process transcripts
        for i in range(0, len(transcripts), chunk_size - overlap):
            end_idx = min(i + chunk_size, len(transcripts))
            segment_texts = [t['text'] for t in transcripts[i:end_idx]]
            if not segment_texts:
                continue
                
            chunk_text = " ".join(segment_texts)
            
            # Get start and end timestamps
            start_time = transcripts[i]['start']
            end_time = transcripts[end_idx - 1]['end']
            
            chunks.append({
                "text": chunk_text,
                "start_time": start_time,
                "end_time": end_time,
                "source_type": "transcript",
                "segment_ids": list(range(i, end_idx))
            })
        
        # Process OCR data - chunk by individual timestamps
        for ocr_item in ocr_data:
            if ocr_item['ocr_text'].strip():
                chunks.append({
                    "text": ocr_item['ocr_text'],
                    "timestamp": ocr_item['timestamp'],
                    "source_type": "ocr"
                })
        
        # Add further chunking for long text segments using sentence tokenization
        additional_chunks = []
        for chunk in chunks:
            if len(chunk["text"].split()) > 100:  # If chunk is very long
                sentences = sent_tokenize(chunk["text"])
                # Group sentences into smaller chunks
                for j in range(0, len(sentences), 3):
                    sentence_group = " ".join(sentences[j:j+3])
                    new_chunk = chunk.copy()
                    new_chunk["text"] = sentence_group
                    new_chunk["sub_chunk"] = True
                    additional_chunks.append(new_chunk)
            
        # Replace original long chunks with sentence-based chunks
        chunks.extend(additional_chunks)
        chunks = [c for c in chunks if not (len(c["text"].split()) > 100 and not c.get("sub_chunk", False))]
        
        return chunks
    
    def generate_embeddings(self, chunks):
        """Generate embeddings for each chunk."""
        if not embedding_model:
            print("Embedding model not available.")
            return None
            
        texts = [chunk["text"] for chunk in chunks]
        embeddings = embedding_model.encode(texts)
        return embeddings
    
    def build_index(self, embeddings):
        """Build a FAISS index for fast similarity search."""
        if embeddings is None or len(embeddings) == 0:
            return None
            
        # Create a new index
        index = faiss.IndexFlatL2(self.embedding_dim)
        # Add the embeddings to the index
        faiss.normalize_L2(embeddings)  # Normalize for cosine similarity
        index = faiss.IndexFlatIP(self.embedding_dim)  # Inner product = cosine similarity for normalized vectors
        index.add(embeddings)
        return index
    
    def process_video_content(self, transcripts, ocr_data, video_url):
        """Process video content to build RAG index."""
        self.video_id = self.extract_youtube_id(video_url)
        
        # Chunk the transcripts and OCR data
        self.chunks = self.chunk_text(transcripts, ocr_data)
        
        # Generate embeddings for each chunk
        embeddings = self.generate_embeddings(self.chunks)
        
        # Build the index
        if embeddings is not None:
            self.chunk_index = self.build_index(embeddings)
            print(f" Built RAG index with {len(self.chunks)} chunks.")
            return True
        else:
            print(" Failed to build RAG index.")
            return False
    
    def retrieve_relevant_chunks(self, query, top_k=5):
        """Retrieve the most relevant chunks for a given query."""
        if not embedding_model or self.chunk_index is None:
            print(" RAG system not initialized.")
            return []
            
        # Generate query embedding
        query_embedding = embedding_model.encode([query])
        faiss.normalize_L2(query_embedding)
        
        # Search the index
        scores, indices = self.chunk_index.search(query_embedding, top_k)
        
        # Return the chunks
        results = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < len(self.chunks) and score > 0:  # Ensure valid index and positive score
                chunk = self.chunks[idx].copy()
                chunk["score"] = float(score)
                results.append(chunk)
                
        return results
    
    def format_rag_context(self, relevant_chunks):
        """Format the retrieved chunks for LLM input."""
        context = "--- Relevant Video Content ---\n"
        
        # Sort chunks by score
        sorted_chunks = sorted(relevant_chunks, key=lambda x: x["score"], reverse=True)
        
        for i, chunk in enumerate(sorted_chunks):
            if chunk["source_type"] == "transcript":
                context += f"[TRANSCRIPT {i+1}] [{chunk['start_time']} - {chunk['end_time']}] {chunk['text']}\n\n"
            else:
                context += f"[ON-SCREEN TEXT {i+1}] [at {chunk['timestamp']}] {chunk['text']}\n\n"
                
        return context.strip()
    
    def load_index(self, video_url, directory="./rag_indices"):
        """Load a previously saved RAG index and chunks."""
        video_id = self.extract_youtube_id(video_url)
        if not video_id:
            return False
            
        index_path = os.path.join(directory, f"{video_id}.index")
        chunks_path = os.path.join(directory, f"{video_id}.json")
        
        if os.path.exists(index_path) and os.path.exists(chunks_path):
            try:
                # Load the index
                self.chunk_index = faiss.read_index(index_path)
                
                # Load the chunks
                with open(chunks_path, "r") as f:
                    self.chunks = json.load(f)
                    
                self.video_id = video_id
                print(f"Loaded existing RAG index for video {video_id}.")
                return True
            except Exception as e:
                print(f"Error loading RAG index: {e}")
                
        return False

# Initialize the RAG pipeline
rag_pipeline = RAGPipeline()

# ========== YT-DLP Functions ==========
def get_video_stream_url(youtube_url):
    
    
    ydl_opts = {
        "format": "bestvideo*+bestaudio/best",

        # Must spoof mobile client to bypass rate-limit & 403
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios"],  # <-- BEST FIX
                "player_skip": ["configs"],           # <-- prevents config API errors
            }
        },

        # Required headers
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 10; SM-G975F) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Mobile Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },

        "force-ipv4": True,
        "nocheckcertificate": True,

        "outtmpl": "video.%(ext)s",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        return info['url'], info.get('title', 'YouTube Video')

def download_audio_temp(youtube_url):
    # Step 1: Use yt-dlp to download full proper audio
    tmp_dir = tempfile.mkdtemp()
    output_template = os.path.join(tmp_dir, "audio.%(ext)s")
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])

    # Find the downloaded wav file
    for file in os.listdir(tmp_dir):
        if file.endswith(".wav"):
            return os.path.join(tmp_dir, file)

    raise FileNotFoundError("Could not find downloaded audio file.")

# ========== Helper Functions ==========
def text_similarity(text1, text2):
    return SequenceMatcher(None, text1, text2).ratio()

def calculate_frame_difference(frame1, frame2, threshold=30):
    if frame1 is None or frame2 is None:
        return 0.0
    try:
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(gray1, gray2)
        _, thresholded = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
        changed_pixels = np.count_nonzero(thresholded)
        total_pixels = thresholded.size
        if total_pixels == 0:
            return 0.0
        return (changed_pixels / total_pixels) * 100
    except:
        return 0.0

# ========== Processing Functions ==========
def extract_audio_whisper(audio_path):
    if not os.path.exists(audio_path):
        print("Audio file not found.")
        return []
    try:
        print(f"Transcribing audio file: {audio_path}")
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, fp16=False)
        output = []
        
        if not result or "segments" not in result:
            print("Whisper returned no segments")
            return []
            
        print(f"Extracted {len(result['segments'])} transcript segments")
        
        for seg in result.get("segments", []):
            start = timedelta(seconds=seg["start"])
            end = timedelta(seconds=seg["end"])
            text = seg["text"].strip()
            output.append({"start": str(start), "end": str(end), "text": text})
            
        print(f"Processed {len(output)} transcript segments")
        return output
    except Exception as e:
        print(f"Whisper transcription error: {e}")
        import traceback
        traceback.print_exc()
        return []

def optimized_ocr_extraction(video_url, frame_interval=30, diff_threshold=2.0, similarity_threshold=0.7, max_duration_sec=None):
    print(f"Opening video stream for OCR: {video_url}")
    cap = cv2.VideoCapture(video_url)
    if not cap.isOpened():
        print(f"Cannot open video stream: {video_url}")
        return []

    reader = easyocr.Reader(['en'], gpu=False)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_count = 0
    previous_frame = None
    results = []

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_time = frame_count / fps
        if max_duration_sec and frame_time > max_duration_sec:
            break

        if frame_count % frame_interval == 0:
            if previous_frame is None or calculate_frame_difference(previous_frame, frame) > diff_threshold:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                text_easyocr = " ".join(reader.readtext(gray, detail=0, paragraph=True))
                text_tesseract = pytesseract.image_to_string(gray)
                combined_text = (text_easyocr + " " + text_tesseract).strip()

                # Check for text similarity with existing results
                if combined_text:
                    similar = False
                    for result in results:
                        if text_similarity(result['ocr_text'], combined_text) > similarity_threshold:
                            similar = True
                            break
                    
                    if not similar:
                        results.append({
                            "timestamp": str(timedelta(seconds=frame_time)),
                            "ocr_text": combined_text
                        })
            previous_frame = frame
        frame_count += 1

    cap.release()
    return results

def process_video_youtube(youtube_url, max_duration_sec=None, frame_interval=30, diff_threshold=2.0, similarity_threshold=0.7):
    try:
        # First check if we have a cached RAG index for this video
        if rag_pipeline.load_index(youtube_url):
            # We still need to get the video title
            _, title = get_video_stream_url(youtube_url)
            return {"rag_enabled": True, "title": title}
    
        audio_tempfile = download_audio_temp(youtube_url)
        print("Audio downloaded and converted to WAV.")

        video_stream_url, title = get_video_stream_url(youtube_url)
        print(f"Video stream ready: {title}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_transcript = executor.submit(extract_audio_whisper, audio_tempfile)
            future_ocr = executor.submit(optimized_ocr_extraction, video_stream_url, frame_interval, diff_threshold, similarity_threshold, max_duration_sec)

            transcripts = future_transcript.result()
            ocr_text = future_ocr.result()

        os.remove(audio_tempfile)
        print("Deleted temporary audio file.")

        # Process for RAG
        rag_success = rag_pipeline.process_video_content(transcripts, ocr_text, youtube_url)
            
        # Ensure transcripts are not empty
        if not transcripts or len(transcripts) == 0:
            print("Warning: No transcript data was extracted")
            
        # Log the data being returned
        print(f"Returning data with {len(transcripts)} transcript segments and {len(ocr_text)} OCR segments")
            
        return {
            "transcripts": transcripts, 
            "ocr_text": ocr_text, 
            "title": title,
            "rag_enabled": rag_success
        }
    except Exception as e:
        print(f"Error processing video: {e}")
        return {"error": str(e)}

def format_context_for_llm(transcripts, ocr_data):
    context = "--- Transcripts ---\n"
    
    if not transcripts or len(transcripts) == 0:
        context += "No transcript data available.\n"
    else:
        for t in transcripts:
            context += f"[{t['start']} - {t['end']}] {t['text']}\n"
    
    context += "\n--- OCR Text ---\n"
    
    if not ocr_data or len(ocr_data) == 0:
        context += "No OCR data available.\n"
    else:
        for o in ocr_data:
            context += f"[{o['timestamp']}] {o['ocr_text']}\n"
            
    print(f"Generated context with {len(transcripts)} transcript segments and {len(ocr_data)} OCR segments")
    return context

def ask_gemini(context, question, use_rag=True):
    if not gemini_model:
        return "Gemini not configured."
    
    # If RAG is enabled and configured, use it
    if use_rag and rag_pipeline.chunk_index is not None:
        # Retrieve relevant chunks
        relevant_chunks = rag_pipeline.retrieve_relevant_chunks(question, top_k=5)
        # Format the context
        context = rag_pipeline.format_rag_context(relevant_chunks)
    
    prompt = f"""Context:
{context}

Question: {question}
Based only on the information provided in the Context above, please answer the question.
- If the answer is found, provide a clear and concise answer.
- If specific timestamps or time ranges are mentioned in the relevant context, try to include them in your answer (e.g., "[0:01:23 - 0:01:45]" or "[at ~0:05:10]").
- If the answer cannot be determined from the Context, explicitly state that the information is not available in the provided text.
- Do not add any information not present in the Context.
Present the output in a good format.
Answer:"""
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini error: {e}"

def generate_summary(context, use_rag=True):
    if not gemini_model:
        return "Gemini not configured."
    
    # For summaries, we want broader coverage, so use more chunks if using RAG
    if use_rag and rag_pipeline.chunk_index is not None:
        # For summary, use a generic query to get representative chunks
        summary_queries = [
            "What is this video about?",
            "What are the main points in this video?",
            "Summarize this video content"
        ]
        all_chunks = []
        for query in summary_queries:
            chunks = rag_pipeline.retrieve_relevant_chunks(query, top_k=5)
            all_chunks.extend(chunks)
        
        # Remove duplicates based on chunk text
        unique_chunks = []
        seen_texts = set()
        for chunk in all_chunks:
            if chunk["text"] not in seen_texts:
                seen_texts.add(chunk["text"])
                unique_chunks.append(chunk)
        
        # Format the context
        context = rag_pipeline.format_rag_context(unique_chunks)
    
    prompt = f"""Context:
{context}
Task: Please generate a concise summary of the provided video content based only on the Context above.
Instructions:
- Focus on the main topics, key arguments, and significant information presented.
- Aim for 2-3 paragraphs.
- Do not include information not found in the Context.
- Structure the summary logically.
Summary:"""
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini error: {e}"

# ========== API Routes ==========
@app.route('/api/process-video', methods=['POST'])
def api_process_video():
    data = request.json
    if not data or 'url' not in data:
        return jsonify({"error": "YouTube URL is required"}), 400
    
    youtube_url = data['url']
    max_duration_sec = data.get('max_duration_sec')
    frame_interval = int(data.get('frame_interval', 30))
    diff_threshold = float(data.get('diff_threshold', 2.0))
    similarity_threshold = float(data.get('similarity_threshold', 0.7))
    
    # Reset RAG pipeline for new video
    rag_pipeline.reset()
    
    result = process_video_youtube(
        youtube_url,
        max_duration_sec=max_duration_sec,
        frame_interval=frame_interval,
        diff_threshold=diff_threshold,
        similarity_threshold=similarity_threshold
    )
    
    if "error" in result:
        return jsonify({"error": result["error"]}), 500
        
    return jsonify(result)

@app.route('/api/generate-summary', methods=['POST'])
def api_generate_summary():
    data = request.json
    if not data:
        return jsonify({"error": "Request data is required"}), 400
    
    use_rag = data.get('use_rag', True)
    
    # If RAG is already loaded (from cached index)
    if use_rag and data.get('rag_enabled', False) and not data.get('videoData'):
        if rag_pipeline.chunk_index is None:
            return jsonify({"error": "RAG system not initialized"}), 400
        
        summary = generate_summary("", use_rag=True)
        return jsonify({"summary": summary})
    
    # Traditional approach with full context
    if 'videoData' not in data:
        return jsonify({"error": "Video data is required"}), 400
        
    video_data = data['videoData']
    context = format_context_for_llm(video_data.get('transcripts', []), video_data.get('ocr_text', []))
    summary = generate_summary(context, use_rag=use_rag)
    
    return jsonify({"summary": summary})

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"error": "Message is required"}), 400
    
    message = data['message']
    use_rag = data.get('use_rag', True)
    
    # If RAG is already loaded (from cached index)
    if use_rag and data.get('rag_enabled', False) and not data.get('videoData'):
        if rag_pipeline.chunk_index is None:
            return jsonify({"error": "RAG system not initialized"}), 400
        
        answer = ask_gemini("", message, use_rag=True)
        
        # Extract timestamp if present in the AI response
        timestamp = None
        timestamp_regex = r'\[(\d{2}:\d{2}:\d{2})\]'
        match = re.search(timestamp_regex, answer)
        if match:
            timestamp = match.group(1)
        
        return jsonify({"text": answer, "timestamp": timestamp})
    
    # Traditional approach with full context
    if 'videoData' not in data:
        return jsonify({"error": "Video data is required"}), 400
        
    video_data = data['videoData']
    context = format_context_for_llm(video_data.get('transcripts', ["not available"]), video_data.get('ocr_text', ["not available"]))
    answer = ask_gemini(context, message, use_rag=use_rag)
    
    # Extract timestamp if present in the AI response
    timestamp = None
    timestamp_regex = r'\[(\d{2}:\d{2}:\d{2})\]'
    match = re.search(timestamp_regex, answer)
    if match:
        timestamp = match.group(1)
    
    return jsonify({"text": answer, "timestamp": timestamp})

@app.route('/api/toggle-rag', methods=['POST'])
def api_toggle_rag():
    """API endpoint to toggle RAG functionality on/off."""
    data = request.json
    if not data or 'enabled' not in data:
        return jsonify({"error": "Enabled flag is required"}), 400
    
    enabled = data['enabled']
    
    if enabled and rag_pipeline.chunk_index is None and 'url' in data:
        # Try to load existing RAG index
        success = rag_pipeline.load_index(data['url'])
        if not success:
            return jsonify({"error": "No RAG index available for this video"}), 404
    
    return jsonify({"rag_enabled": enabled})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
