import os
import google.generativeai as genai

# ====== READ API KEY ======
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY","AIzaSyAS91sgGororPlC9LMG2bWDsDXtYFd3O8c")
print("🔍 GEMINI_API_KEY =", GEMINI_API_KEY)

if not GEMINI_API_KEY:
    print("❌ ERROR: GEMINI_API_KEY is not set in environment variables.")
    exit()

# ====== CONFIGURE GEMINI ======
try:
    genai.configure(api_key=GEMINI_API_KEY)
    print("✅ Gemini API configured.")
except Exception as e:
    print("❌ Failed to configure Gemini API:")
    print(e)
    exit()

# ====== LOAD MODEL ======
try:
    model = genai.GenerativeModel("gemini-2.5-flash")
    print("✅ Model loaded: gemini-1.5-flash")
except Exception as e:
    print("❌ Failed to load model:")
    print(e)
    exit()

# ====== TEST GENERATION ======
print("\n=== Sending test prompt ===")
try:
    response = model.generate_content("Say 'Gemini test successful'.")
    print("\n🎉 Response from Gemini:")
    print(response.text)
except Exception as e:
    print("❌ Generation failed:")
    print(e)
