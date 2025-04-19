import streamlit as st
from utils import transcribe_audio, analyze_transcription, format_analysis, analyze_bad_phrases, format_bad_phrases_analysis
import os
import tempfile
import asyncio
from functools import partial
import aiohttp
from utils import TranscriptionService
import json
from dotenv import load_dotenv
from s3_utils import process_audio_file_with_s3, format_false_promises, format_bad_phrases
from datetime import datetime
import sqlite3

# Load environment variables
load_dotenv()

# Check for required environment variables
if not os.getenv("OPENAI_API_KEY"):
    st.error("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable in .env file.")
    st.stop()

# Initialize SQLite DB for persistent history
db_path = os.path.join(os.path.dirname(__file__), "history.db")
conn = sqlite3.connect(db_path, check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    transcription TEXT,
    result TEXT
)
""")
conn.commit()

# Ensure `audio_filename` column exists (for upgrades)
cols = [c[1] for c in cursor.execute("PRAGMA table_info(history)").fetchall()]
if 'audio_filename' not in cols:
    cursor.execute("ALTER TABLE history ADD COLUMN audio_filename TEXT")
    conn.commit()

# This MUST be the first Streamlit command
st.set_page_config(
    page_title="Scaler Ai Call Analysis Demo",
    page_icon=os.path.join(os.path.dirname(__file__), "favicon.ico"),
    layout="centered",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.api_result = None
    st.session_state.transcription = None
    # Ensure uploads directory exists
    uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
    if not os.path.exists(uploads_dir):
        os.makedirs(uploads_dir)
    # Load existing history from SQLite DB
    cursor.execute("SELECT id, timestamp, transcription, audio_filename, result FROM history ORDER BY id")
    rows = cursor.fetchall()
    st.session_state.history = [
        {'id': r[0], 'timestamp': r[1], 'transcription': r[2], 'audio_filename': r[3], 'result': json.loads(r[4])}
        for r in rows
    ]
    st.session_state.history_selected = None

# Add custom CSS
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    .stAlert {
        margin-top: 1rem;
    }
    .uploadedFile {
        margin-bottom: 2rem;
    }
    .logo-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        margin-bottom: 2rem;
        text-align: center;
    }
    .logo-container img {
        max-height: 100px;
        margin-bottom: 1.5rem;
    }
    .logo-container h1 {
        margin-bottom: 0.5rem;
    }
    /* History button styling */
    .stButton > button {
        border-radius: 8px !important;
        margin-bottom: 8px !important;
        text-align: left !important;
    }
    </style>
""", unsafe_allow_html=True)

async def process_with_s3(audio_file, status_container=None, progress_bar=None):
    # Process the audio file with S3 upload and API integration
    success, result, transcription, local_filename = await process_audio_file_with_s3(
        audio_file, 
        status_container=status_container,
        progress_bar=progress_bar
    )
    return success, result, transcription, local_filename

def main():
    # Sidebar history section
    with st.sidebar:
        st.header("History")
        
        # New analysis button
        if st.button("➕ New Analysis", key="new_analysis_button", use_container_width=True, type="primary"):
            st.session_state.history_selected = None
            st.session_state.api_result = None
            st.session_state.transcription = None
            st.experimental_rerun()
        
        st.markdown("---")
        
        # Simple history listing
        if st.session_state.history:
            # Reverse the list to show newest entries at the top
            history_to_display = list(reversed(st.session_state.history))
            
            for idx, entry in enumerate(history_to_display):
                # Convert back to original index for selection purposes
                original_idx = len(st.session_state.history) - 1 - idx
                timestamp = entry['timestamp']
                
                # Format a cleaner timestamp
                try:
                    date_obj = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                    formatted_time = date_obj.strftime("%H:%M:%S")
                except:
                    formatted_time = timestamp
                
                # Simple entry display with selection indicator and entry number 
                # Entry numbers stay the same (newest = highest number)
                entry_number = idx + 1  # Start with 1 for the newest
                prefix = "➡️ " if st.session_state.history_selected == original_idx else ""
                label = f"{prefix}Entry #{entry_number} - {formatted_time}"
                
                if st.button(label, key=f"hist_{entry['id']}", use_container_width=True):
                    st.session_state.history_selected = original_idx
                    st.experimental_rerun()
        else:
            st.info("No history yet. Upload an audio file to get started.")

    # Header with logo stacked above text
    st.markdown("""
        <div class="logo-container">
            <img src="https://scaler-blog-prod-wp-content.s3.ap-south-1.amazonaws.com/wp-content/uploads/2022/10/22114541/Scaler_Logo_WhiteBG-860x484.jpg" alt="Scaler Logo">
            <h1>Scaler AI Call Analysis Demo</h1>
            <p style="font-size: 1.2rem; color: #666;">
                Upload a sales call recording to analyze it for potential false promises and concerning patterns.
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    # Main content area
    main_container = st.container()
    with main_container:
        # Split view based on whether we're in history view or new upload mode
        if st.session_state.history_selected is not None:
            # HISTORY VIEW MODE
            entry = st.session_state.history[st.session_state.history_selected]
            display_analysis_results(entry)
        else:
            # NEW UPLOAD MODE
            upload_and_analyze()

def upload_and_analyze():
    """Handle new audio upload and analysis"""
    # Check for AWS credentials
    if not os.getenv("AWS_ACCESS_KEY_ID") or not os.getenv("AWS_SECRET_ACCESS_KEY"):
        st.warning("AWS credentials not found. Please set the AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables in .env file.")
        return
    
    # File uploader
    audio_file = st.file_uploader(
        "Upload Audio File",
        type=["mp3", "wav", "m4a"],
        help="Upload an audio file to analyze via S3 and API",
        key="audio_file"
    )
    
    if not audio_file:
        return
    
    # Show uploaded audio
    st.audio(audio_file, format='audio/*')
    
    # Analyze button
    analyze_button = st.button("Analyze Call", key='analyze_button')
    if not analyze_button:
        return
    
    # Create containers for analysis status
    status_container = st.empty()
    progress_container = st.progress(0)
    result_container = st.container()
    
    # Start analysis
    with status_container:
        st.info("Starting analysis...")
    
    # Run the analysis
    loop = asyncio.new_event_loop()
    success, result, transcription, local_filename = loop.run_until_complete(
        process_with_s3(audio_file, status_container, progress_container)
    )
    loop.close()
    
    # Always save history entry with audio file, even if analysis fails
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    audio_filename = local_filename or ""
    
    # If local_filename is empty but we have successfully processed, create a history-based filename
    if not audio_filename and audio_file:
        # Insert entry first to get an ID
        cursor.execute(
            "INSERT INTO history (timestamp, transcription, audio_filename, result) VALUES (?, ?, ?, ?)",
            (ts, transcription or "", "", json.dumps(result) if result else "{}")
        )
        conn.commit()
        entry_id = cursor.lastrowid
        
        # Save uploaded audio with the entry ID
        audio_bytes = audio_file.getvalue()
        ext = os.path.splitext(audio_file.name)[1]
        audio_filename = f"history_{entry_id}{ext}"
        uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
        audio_path = os.path.join(uploads_dir, audio_filename)
        
        with open(audio_path, 'wb') as f:
            f.write(audio_bytes)
        
        # Update the entry with the filename
        cursor.execute(
            "UPDATE history SET audio_filename = ? WHERE id = ?",
            (audio_filename, entry_id)
        )
        conn.commit()
    else:
        # Insert the history entry with the available data
        cursor.execute(
            "INSERT INTO history (timestamp, transcription, audio_filename, result) VALUES (?, ?, ?, ?)",
            (ts, transcription or "", audio_filename, json.dumps(result) if result else "{}")
        )
        conn.commit()
        entry_id = cursor.lastrowid
    
    # Add to session state history
    history_entry = {
        'id': entry_id,
        'timestamp': ts,
        'transcription': transcription or "",
        'audio_filename': audio_filename,
        'result': result or {}
    }
    st.session_state.history.append(history_entry)
    
    # Update UI based on success/failure
    if success and result:
        status_container.success("✨ Analysis completed successfully!")
        progress_container.empty()
        
        # Switch to history view of the new entry
        st.session_state.api_result = result
        st.session_state.transcription = transcription
        st.session_state.history_selected = len(st.session_state.history) - 1
        
        # Display the results (will be replaced when page reruns)
        with result_container:
            display_analysis_results(history_entry)
        
        # Force a rerun to clean up the UI
        st.experimental_rerun()
    else:
        status_container.warning("Analysis couldn't be completed, but your audio has been saved.")
        progress_container.empty()
        st.session_state.history_selected = len(st.session_state.history) - 1
        st.experimental_rerun()

def display_analysis_results(entry):
    """Display analysis results for a given history entry"""
    # Extract data from entry
    transcription = entry.get('transcription', '')
    result = entry.get('result', {})
    audio_filename = entry.get('audio_filename', '')
    
    # Status indicator
    st.success("Viewing analysis results")
    
    # Display audio if available
    if audio_filename:
        uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
        audio_path = os.path.join(uploads_dir, audio_filename)
        try:
            st.audio(open(audio_path, 'rb'), format='audio/*')
        except FileNotFoundError:
            st.warning(f"Audio file not found in uploads folder. It may have been moved or deleted.")
    else:
        st.info("No audio file available for this analysis.")
    
    # Transcription section
    if transcription:
        col1, col2 = st.columns([3, 1])
        with col1:
            with st.expander("📝 View Transcription", expanded=False):
                st.markdown(transcription)
        with col2:
            st.download_button(
                "📥 Download Transcription",
                transcription,
                file_name="transcription.txt",
                mime="text/plain",
                key='download_transcription_button',
                use_container_width=True
            )
    
    # Show analysis results if available
    if result:
        # Create tabs for different analysis types
        result_tab1, result_tab2 = st.tabs(["False Promises", "Bad Call Phrases"])
        
        # Tab 1: False Promises Analysis
        with result_tab1:
            st.markdown("## 🔍 False Promises Analysis")
            try:
                meta = result.get("meta", {})
                false_promise_data = meta.get("false_promise", {})
                
                if false_promise_data:
                    formatted_sections = format_false_promises(false_promise_data)
                    for section in formatted_sections:
                        st.markdown(section, unsafe_allow_html=True)
                else:
                    st.info("False promises analysis not available.")
            except Exception as e:
                st.error(f"Error displaying false promises analysis results: {str(e)}")
        
        # Tab 2: Bad Call Analysis
        with result_tab2:
            st.markdown("## 🔍 Bad Call Analysis")
            try:
                meta = result.get("meta", {})
                abusive_bad_call_data = meta.get("abusive_bad_call", {})
                
                if abusive_bad_call_data:
                    formatted_sections = format_bad_phrases(abusive_bad_call_data)
                    for section in formatted_sections:
                        st.markdown(section, unsafe_allow_html=True)
                else:
                    st.info("Bad call analysis not available.")
            except Exception as e:
                st.error(f"Error displaying bad call analysis results: {str(e)}")
    else:
        st.warning("No analysis results available for this entry.")

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8501))
    main() 