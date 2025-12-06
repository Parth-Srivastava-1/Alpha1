# single-file: maytapi.py (FastAPI Backend)
import os
import json
import tempfile
import requests
import pytz
import pytesseract
import random as r
from io import BytesIO
from datetime import datetime
from PIL import Image
from dotenv import load_dotenv
from openai import OpenAI
from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
from typing import Optional
import pyperclip
from sqlalchemy import create_engine, Column, Integer, String, Date, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# optional: pinecone import (keep as in your original)
from pinecone import Pinecone, ServerlessSpec

# load env
load_dotenv()

# Create uploads directory for permanent file storage
UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# ------------------- POSTGRES CONFIG -------------------
USERNAME = "postgres"          # change if needed
PASSWORD = "Parth2329"         # change if needed
DB_NAME = "Alpha"              # change if needed
HOST = "localhost"
PORT = "5432"

DATABASE_URL = f"postgresql://{USERNAME}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL, echo=True)   # echo True helps debugging
Base = declarative_base()
Session = sessionmaker(bind=engine)

# ------------------- FASTAPI + STATIC -------------------
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def index():
    return FileResponse("./static/Alpha.html") 

# ------------------- MODELS -------------------
class log_chats(Base):
    __tablename__ = "Chat_Logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String, nullable=False)
    sender_message = Column(Text, nullable=False)
    message_type = Column(String, nullable=False)
    date = Column(Date)
    time = Column(String, nullable=False)

class bot_data(Base):
    __tablename__ = "Bots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    MAYTAPI_PRODUCT_ID = Column(String, nullable=False)
    MAYTAPI_PHONE_ID = Column(String, nullable=False)
    MAYTAPI_TOKEN = Column(String, nullable=False)
    # OPENAI_API_KEY and SUMMARY_FILE_PATH removed from DB as requested
    PINECONE_API_KEY = Column(String, nullable=False)
    PINECONE_INDEX_NAME = Column(String, nullable=False)
    PROMPT = Column(Text, nullable=False)
    CODE = Column(Integer, nullable=False, unique=True)
    
Base.metadata.create_all(engine)

# ------------------- GLOBALS -------------------
config = {}
openai = None
index = None
Prompt = ""
MAYTAPI_BASE_URL = ""
MAYTAPI_TOKEN = ""
blocked_numbers = []

# ------------------- UTILS -------------------

def save_uploaded_file(uploaded_file: UploadFile) -> Optional[str]:
    """Saves the uploaded file to a permanent location and returns the path."""
    if not uploaded_file.filename:
        return None
    try:
        # Read content fully
        contents = uploaded_file.file.read()
        uploaded_file.file.seek(0) # Reset file pointer for later use if needed

        if not contents:
            print("Uploaded file is empty.")
            return None

        # Generate a unique filename and save
        file_path = os.path.join(UPLOAD_DIR, f"{r.randint(1000,9999)}_{uploaded_file.filename}")
        with open(file_path, "wb") as f:
            f.write(contents)
        print(f"File saved successfully to: {file_path}")
        return file_path
    except Exception as e:
        print(f"Error saving uploaded file: {e}")
        return None

# ------------------- SERVICE INIT -------------------

def init_services():
    global openai, index, Prompt, MAYTAPI_BASE_URL, MAYTAPI_TOKEN
    
    if not config:
        raise Exception("Bot configuration not loaded.")

    # OpenAI
    openai_key = config.get("OPENAI_API_KEY")
    if not openai_key:
        # Configuration is now mandatory from the form/config dict
        raise Exception("OPENAI_API_KEY is missing in config. Please load bot or submit form with key.")
    openai = OpenAI(api_key=openai_key)

    # Pinecone
    pinecone_key = config.get("PINECONE_API_KEY")
    index_name = config.get("PINECONE_INDEX_NAME")
    if not pinecone_key or not index_name:
        print("Pinecone configuration is incomplete. Skipping Pinecone initialization.")
        index = None
        return # Allow service to run without Pinecone if keys are missing

    try:
        pc = Pinecone(api_key=pinecone_key)
        # create index if not exists (same logic as before)
        existing = pc.list_indexes().names()
        if index_name not in existing:
            pc.create_index(
                name=index_name,
                dimension=1024,
                metric="euclidean",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
        index = pc.Index(index_name)
    except Exception as e:
        print(f"Pinecone initialization failed: {e}")
        index = None # Set index to None if initialization fails

    Prompt = config.get("PROMPT")
    MAYTAPI_BASE_URL = f"https://api.maytapi.com/api/{config.get('MAYTAPI_PRODUCT_ID')}/{config.get('MAYTAPI_PHONE_ID')}/sendMessage"
    MAYTAPI_TOKEN = config.get("MAYTAPI_TOKEN")

# ------------------- DB HELPERS -------------------
def log_chat(user_number, message, message_type):
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    date_obj = now.date()
    time_str = now.strftime('%H:%M:%S')
    with Session() as session:
        entry = log_chats(
            phone_number=user_number,
            sender_message=message,
            message_type=message_type,
            date=date_obj,
            time=time_str
        )
        session.add(entry)
        session.commit()
        print("Logged chat id:", entry.id)

def get_past_chats_postgres(user_number, limit=30):
    with Session() as session:
        qs = session.query(log_chats).filter_by(phone_number=user_number).order_by(log_chats.id.desc()).limit(limit)
        rows = qs.all()
        records = []
        for r in reversed(rows):
            records.append({
                "phone_number": r.phone_number,
                "sender_message": r.sender_message,
                "message_type": r.message_type,
                "date": r.date.isoformat() if r.date else None,
                "time": r.time
            })
        return records
#----------------------Ngrok forwarding url-------------------
def get_ngrok_url():
    try:
        # Ngrok local API se tunnels fetch karna
        res = requests.get("http://127.0.0.1:4040/api/tunnels")
        data = res.json()

        # Forwarding URL lena (http/https dono ho sakte hain)
        url = data['tunnels'][0]['public_url']

        # Clipboard pe copy karna
        pyperclip.copy(url)

        print(f"Ngrok URL copied to clipboard: {url}")
        return url
    except Exception as e:
        print("Error:", e)
        return "Ngrok URL fetch failed."
# ------------------- OpenAI + Pinecone helpers (Functions remain the same) -------------------
# ... (All OpenAI/Pinecone/Maytapi helper functions like get_openai_embedding, 
# search_pinecone, rag_answers, generate_reply_with_memory, generate_chat_summary, 
# send_whatsapp_message, send_whatsapp_image, transcribe_audio_from_url, 
# extract_text_from_image_url remain unchanged) ...
def get_openai_embedding(text):
    resp = openai.embeddings.create(input=text, model="text-embedding-3-small")
    embedding = resp.data[0].embedding[:1024]
    return embedding

def search_pinecone(query, top_k=5):
    if not index:
        return []
    q_emb = get_openai_embedding(query)
    result = index.query(vector=q_emb, top_k=top_k, include_metadata=True)
    return [(m["metadata"]["text"], m["score"]) for m in result["matches"]]

def rag_answers(context_text, user_question):
    prompt = f"Use the following context to answer the question.\n\nContext:\n{context_text}\n\nQuestion:\n{user_question}\n\nAnswer in a helpful and friendly way."
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        max_tokens=200,
        temperature=0.7
    )
    return resp.choices[0].message.content

def generate_reply_with_memory(user_number, user_input):
    past_chats = get_past_chats_postgres(user_number)
    memory = []
    for chat in past_chats:
        if chat["message_type"] == "user":
            memory.append({"role":"user","content":chat["sender_message"]})
        else:
            memory.append({"role":"assistant","content":chat["sender_message"]})
    memory.append({"role":"user","content":user_input})

    resp = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role":"system","content":Prompt}] + memory,
        max_tokens=150,
        temperature=0.7
    )
    return resp.choices[0].message.content

def generate_chat_summary(user_number):
    past = get_past_chats_postgres(user_number, limit=30)
    if not past:
        return "I couldn't find any past chats to summarize."
    chat_lines = []
    for c in past:
        pref = "User:" if c["message_type"] == "user" else "Bot:"
        chat_lines.append(f"{pref} {c['sender_message']}")
    chat_text = "\n".join(chat_lines)
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"Summarize the following WhatsApp conversation."},
            {"role":"user","content":chat_text}
        ],
        max_tokens=200,
        temperature=0.8
    )
    return resp.choices[0].message.content

def send_whatsapp_message(to_number, message):
    headers = {"Content-Type":"application/json", "x-maytapi-key": MAYTAPI_TOKEN}
    payload = {"to_number": to_number, "type":"text", "message": message}
    if not MAYTAPI_TOKEN or not MAYTAPI_BASE_URL:
        print("Maytapi services not initialized. Cannot send message.")
        return {"status":"error", "message": "Maytapi services not configured or initialized."}

    resp = requests.post(MAYTAPI_BASE_URL, json=payload, headers=headers)
    print("Maytapi send:", resp.status_code, resp.text)
    return resp.json()

def send_whatsapp_image(to_number, image_url):
    headers = {"Content-Type":"application/json", "x-maytapi-key": MAYTAPI_TOKEN}
    payload = {"to_number": to_number, "type":"image", "message": image_url}
    if not MAYTAPI_TOKEN or not MAYTAPI_BASE_URL:
        print("Maytapi services not initialized. Cannot send image.")
        return {"status":"error", "message": "Maytapi services not configured or initialized."}
        
    resp = requests.post(MAYTAPI_BASE_URL, json=payload, headers=headers)
    print("Maytapi image send:", resp.status_code, resp.text)
    return resp.json()

def transcribe_audio_from_url(audio_url: str) -> str:
    r = requests.get(audio_url)
    if r.status_code != 200:
        raise Exception("Failed to download audio")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
        tmp.write(r.content)
        tmp.flush()
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            transcript = openai.audio.transcriptions.create(file=f, model="whisper-1")
        return transcript.text.strip()
    finally:
        os.remove(tmp_path)

def extract_text_from_image_url(image_url):
    try:
        response = requests.get(image_url)
        img = Image.open(BytesIO(response.content))
        text = pytesseract.image_to_string(img)
        return text.strip()
    except Exception as e:
        print("OCR failed:", e)
        return ""

# ------------------- Endpoints: submit_maytapi & load_bot -------------------

@app.post("/submit_maytapi")
async def submit_maytapi(
    MAYTAPI_PRODUCT_ID: str = Form(...),
    MAYTAPI_PHONE_ID: str = Form(...),
    MAYTAPI_TOKEN: str = Form(...),
    # Key is read but NOT saved to DB
    openai_api_key_maytapi: str = Form(..., alias="openai_api_key_maytapi"), 
    PINECONE_API_KEY: str = Form(...),
    Pinecone_Index_name: str = Form(..., alias="Pinecone_Index_name"),
    # File is uploaded and saved to disk
    bulk_sheet: Optional[UploadFile] = File(None),
    Prompt: str = Form(...)
):
    """
    Save new bot's permanent config (Maytapi, Pinecone, Prompt, CODE) to DB.
    Set global config (including temporary API Key/File Path) and initialize services.
    """
    global config
    
    summary_path = None
    if bulk_sheet and bulk_sheet.filename:
        summary_path = save_uploaded_file(bulk_sheet)
    
    if not summary_path:
        # Check if the file is mandatory, for now we allow it to be None/missing
        pass
    
    # 2. Generate a unique code (simple random for now)
    code = r.randint(10000, 99999) # Increased range to reduce collision risk

    # 3. Store permanent config in DB
    try:
        with Session() as session:
            entry = bot_data(
                MAYTAPI_PRODUCT_ID=MAYTAPI_PRODUCT_ID,
                MAYTAPI_PHONE_ID=MAYTAPI_PHONE_ID,
                MAYTAPI_TOKEN=MAYTAPI_TOKEN,
                PINECONE_API_KEY=PINECONE_API_KEY,
                PINECONE_INDEX_NAME=Pinecone_Index_name,
                PROMPT=Prompt,
                CODE=code
            )
            session.add(entry)
            session.commit()
            print("Saved bot config id:", entry.id)

            # 4. Set Global Config (including temporary key/path)
            config = {
                "MAYTAPI_PRODUCT_ID": MAYTAPI_PRODUCT_ID,
                "MAYTAPI_PHONE_ID": MAYTAPI_PHONE_ID,
                "MAYTAPI_TOKEN": MAYTAPI_TOKEN,
                # Temporary fields, taken directly from form data:
                "OPENAI_API_KEY": openai_api_key_maytapi,
                "SUMMARY_FILE_PATH": summary_path, 
                
                # Permanent fields, also in config for init:
                "PINECONE_API_KEY": PINECONE_API_KEY,
                "PINECONE_INDEX_NAME": Pinecone_Index_name,
                "PROMPT": Prompt,
                "CODE": code
            }
        
        # 5. Initialize services (OpenAI + Pinecone)
        init_services()
        url=get_ngrok_url()

    except Exception as e:
        return JSONResponse(status_code=500, content={"message": f"Database save/init failed: {e}"})


    return JSONResponse(content={"message": f"Bot setup successful. Please use the CODE:{code} to load bot. Your webhook URL is {url}/webhook"})

@app.post("/load_bot")
async def load_bot(
    Bot_ID: int = Form(..., alias="Bot_ID"), 
    openai_api_key_load: str = Form(..., alias="openai_api_key_load"),
    bulk_sheet_load: Optional[UploadFile] = File(None) # File field is optional on load
):
    """
    Load bot's permanent config from Postgres by CODE.
    Set global config using permanent data + temporary key/path from form.
    Initialize services.
    """
    global config
    
    summary_path = None
    if bulk_sheet_load and bulk_sheet_load.filename:
        # If new file is uploaded on load, save it and use this new path
        summary_path = save_uploaded_file(bulk_sheet_load)
        if not summary_path:
             return JSONResponse(status_code=400, content={"message": "Uploaded bulk sheet is invalid."})


    with Session() as session:
        # Find the bot
        bot = session.query(bot_data).filter_by(CODE=Bot_ID).first()
        if not bot:
            return JSONResponse(status_code=404, content={"message":"Bot not found for the given ID."})

        # Set config dict (using DB data for permanent fields and form data for temporary ones)
        config = {
            "MAYTAPI_PRODUCT_ID": bot.MAYTAPI_PRODUCT_ID,
            "MAYTAPI_PHONE_ID": bot.MAYTAPI_PHONE_ID,
            "MAYTAPI_TOKEN": bot.MAYTAPI_TOKEN,
            "PINECONE_API_KEY": bot.PINECONE_API_KEY,
            "PINECONE_INDEX_NAME": bot.PINECONE_INDEX_NAME,
            "PROMPT": bot.PROMPT,
            "CODE": bot.CODE,
            
            # Temporary fields, taken directly from form data:
            "OPENAI_API_KEY": openai_api_key_load, # Always use the key from the form
            "SUMMARY_FILE_PATH": summary_path, # Use the path of the newly uploaded file (if any)
        }
        url=get_ngrok_url()
    # initialize services (OpenAI + Pinecone)
    try:
        init_services()
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": f"Init services failed: {e}"})

    return JSONResponse(content={"message": f"Bot loaded successfully. Your webhook URL is {url}/webhook"})

# ------------------- Bulk trigger (reads saved excel path from config) -------------------
def run_bulk_send(custom_message: str, start_row: int, end_row: int):
    """Reads the Excel file, filters by row range, and sends the custom message."""
    file_path = config.get('SUMMARY_FILE_PATH')
    
    if not file_path:
        return {"status": "error", "message": "Bulk sheet not uploaded or bot not configured."}

    try:
        # File read karna
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"Error reading bulk sheet: {e}")
        return {"status": "error", "message": f"Error reading bulk sheet: Bulk sheet read failed."}
    
    # 1-based index (user input) ko 0-based slicing mein convert karna
    # df.iloc[start_row - 1 : end_row] -> This selects rows from (start_row - 1) up to (but not including) end_row + 1.
    # Agar user Start=1, End=10 deta hai, toh yeh row index 0 se 9 tak lega (yaani 10 rows).
    
    try:
        df_filtered = df.iloc[start_row - 1 : end_row] 
    except IndexError:
         return {"status": "error", "message": f"Invalid range: Start={start_row}, End={end_row}. Check if the range is valid for the sheet."}

    # First column (index 0) ko phone numbers ki list mein le rahe hain
    try:
        phone_numbers = df_filtered.iloc[:, 0].astype(str).tolist()
    except Exception as e:
        print(f"Error extracting phone numbers: {e}")
        return {"status": "error", "message": "Error extracting phone numbers from sheet (check first column data type)."}
        
    total_sent = 0
    
    # Message send karna
    for number in phone_numbers:
        number = number.strip() # Cleaning up whitespace
        if not number or number in blocked_numbers:
            continue

        result = send_whatsapp_message("91"+number, custom_message)
        if result.get("status") == "success":
            total_sent += 1

    return JSONResponse(True)
def trigger_bulk():
    """
    Reads excel file path from global config and sends messages.
    """
    if not config.get("SUMMARY_FILE_PATH"):
        return {"status":"error","message":"No excel file path configured for the current session."}

    try:
        file_path = config.get("SUMMARY_FILE_PATH")
        if not os.path.exists(file_path):
             return {"status":"error","message":"Configured excel file not found on disk."}
             
        
    except Exception as e:
        return {"status":"error","message":f"Failed to read excel: {e}"}
    df = pd.read_excel(r"C:\Users\SUN\Documents\Alphaaaa\Dryfruits.xlsx")
    sent = []
    # ... (Rest of bulk messaging logic remains the same) ...
    for idx, row in df.iterrows():
        # Clean and validate phone number
        phone = str(row.get("number", "")).strip()
        if not phone.startswith("91") and len(phone) == 10:
             phone = "91" + phone # Assuming Indian numbers without country code
        
        name = str(row.get("name", "")).strip() if "name" in df.columns else ""
        if not phone or len(phone) < 12: # Basic validation (e.g., 91xxxxxxxxxx)
            continue
            
        # sample message
        message = f"Hello {name or ''}, this is a test message."
        try:
            send_whatsapp_message(phone, message)
            sent.append({"phone": phone, "name": name})
        except Exception as e:
            print("Failed to send to", phone, e)

    return {"status":"done","total_sent": len(sent), "details": sent}

@app.post("/bulk_hi")
async def bulk_hi(message: str = Form(...),
    start: int = Form(...),
    end: int = Form(...)
):
    """
    Triggers the bulk message sending process using the configured sheet and the provided message/range.
    """
    if not config.get('MAYTAPI_TOKEN'):
        return JSONResponse(status_code=400, content={"status": "error", "message": "Bot not initialized. Please load bot first on Alpha.html."})
    
    # Run the core logic
    result = run_bulk_send(message, start, end)
    
    if result["status"] == "done":
        return FileResponse(r"C:\Users\SUN\Documents\Alpha_Final\static\bulk.html")
    else:
        # Return 400 for errors
        return JSONResponse(status_code=400, content=result)
    

# ------------------- Webhook endpoint (main chat flow) -------------------
@app.post("/webhook")
async def webhook(request: Request):
    # Check if services are initialized before processing webhook
    if not config:
        return {"status":"error","message":"Bot not loaded. Please load bot first."}
        
    data = await request.json()
    # ... (Rest of webhook logic remains the same) ...
    raw_body = await request.body()
    print("RAW WEBHOOK DATA:", raw_body)

    print("Incoming:", data)
    try:
        from_number = data["user"]["phone"]
        message_type = data["message"]["type"]
    except KeyError:
        return {"status":"error","message":"Invalid payload"}

    if from_number in blocked_numbers:
        return {"status":"blocked"}

    # parse message content
    if message_type in ["voice","ptt"]:
        try:
            audio_url = data["message"]["url"]
            user_message = transcribe_audio_from_url(audio_url)
        except Exception as e:
            send_whatsapp_message(from_number, "Sorry, couldn't transcribe voice.")
            return {"status":"error","message":"transcription_failed"}
    elif message_type == "image":
        image_url = data["message"]["url"]
        user_message = extract_text_from_image_url(image_url)
        if not user_message:
            send_whatsapp_message(from_number, "Sorry, couldn't read the image.")
            return {"status":"error","message":"ocr_failed"}
    elif message_type == "text":
        user_message = data["message"]["text"].strip()
    else:
        send_whatsapp_message(from_number, "Unsupported message type")
        return {"status":"error","message":"unsupported_type"}

    # log incoming
    log_chat(from_number, user_message, "user")

    # generate reply
    if any(kw in user_message.lower() for kw in ["summary","summarize"]):
        reply = generate_chat_summary(from_number)
    else:
        matches = []
        try:
            if index:
                matches = search_pinecone(user_message)
        except Exception as e:
            print("Pinecone search failed:", e)
            
        if matches:
            best_text, best_score = max(matches, key=lambda x: x[1])
            if best_score >= 1.35:
                ctx = "\n\n".join([t for t,s in matches if s>0.7])
                reply = rag_answers(ctx, user_message)
            else:
                reply = generate_reply_with_memory(from_number, user_message)
        else:
            reply = generate_reply_with_memory(from_number, user_message)

    # log bot reply and send
    log_chat(from_number, reply, "bot")
    send_whatsapp_message(from_number, reply)
    return {"status":"success"}

# ------------------- Utility: simple check endpoint -------------------
@app.post("/check")
def check():
    # quick test - ensure config loaded
    if not config:
        return {"status":"no_config"}
    try:
        # Note: You need to make sure the target number and image URL are valid
        send_whatsapp_image("918756803328", "https://i.ibb.co/gZYzbdJv/service.jpg")
        return {"status":"ok"}
    except Exception as e:
        return {"status":"error","message":str(e)}