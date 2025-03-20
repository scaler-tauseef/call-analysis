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
import base64
import db_utils
from datetime import datetime
import humanize

# Initialize the database
db_utils.init_db()

# Load environment variables
load_dotenv()

# Check for required environment variables
if not os.getenv("OPENAI_API_KEY"):
    st.error("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable in .env file.")
    st.stop()

# Function to load and encode the favicon
def get_favicon_base64():
    try:
        with open("favicon.ico", "rb") as f:
            favicon_data = f.read()
            favicon_base64 = base64.b64encode(favicon_data).decode("utf-8")
            return favicon_base64
    except Exception as e:
        print(f"Error loading favicon: {e}")
        return None

# Function to format datetime
def format_datetime(datetime_str):
    try:
        dt = datetime.fromisoformat(datetime_str)
        return {
            "date": dt.strftime("%b %d, %Y"),
            "time": dt.strftime("%I:%M %p"),
            "relative": humanize.naturaltime(datetime.now() - dt)
        }
    except:
        return {
            "date": datetime_str,
            "time": "",
            "relative": ""
        }

# Function to format file size
def format_file_size(size_bytes):
    return humanize.naturalsize(size_bytes)

# Get the base64 encoded favicon
favicon_base64 = get_favicon_base64()

# This MUST be the first Streamlit command
st.set_page_config(
    page_title="Motion Sales Call Analysis",
    page_icon=f"data:image/x-icon;base64,{favicon_base64}" if favicon_base64 else "🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.api_result = None
    st.session_state.transcription = None
    st.session_state.analysis = None
    st.session_state.bad_phrases_analysis = None
    st.session_state.current_analysis_id = None
    st.session_state.view_mode = "new_analysis"  # Can be "new_analysis" or "history_item"
    # Add new session state variables for history selection and deletion
    if "history_select" not in st.session_state:
        st.session_state.history_select = None
    if "history_delete" not in st.session_state:
        st.session_state.history_delete = None

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
    /* Style the history item container */
    [data-testid="stVerticalBlock"] > div > [data-testid="stVerticalBlock"] {
        margin-bottom: 12px;
        padding-bottom: 8px;
        border-bottom: 1px solid #eee;
    }
    /* Style the history buttons */
    .stButton button {
        text-align: left !important;
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
        height: auto !important;
        padding: 10px !important;
    }
    /* Style the delete button */
    [data-testid="column"]:nth-child(2) .stButton button {
        background-color: transparent !important;
        color: #d9534f !important;
        border: none !important;
        font-size: 16px !important;
        margin-top: 8px !important;
        padding: 5px !important;
        min-height: 0 !important;
    }
    /* Style confirmation buttons */
    [data-testid="stVerticalBlock"] > div > [data-testid="stHorizontalBlock"] .stButton button {
        font-size: 12px !important;
        padding: 2px 8px !important;
        height: 30px !important;
        margin-top: 0 !important;
        text-align: center !important;
    }
    /* Style Yes button */
    [data-testid="stVerticalBlock"] > div > [data-testid="stHorizontalBlock"] > div:first-child .stButton button {
        background-color: #d9534f !important;
        color: white !important;
    }
    /* Style Cancel button */
    [data-testid="stVerticalBlock"] > div > [data-testid="stHorizontalBlock"] > div:last-child .stButton button {
        background-color: #f0f0f0 !important;
        color: #333 !important;
    }
    </style>
""", unsafe_allow_html=True)

async def process_with_s3(audio_file):
    # Process the audio file with S3 upload and API integration
    success, result, transcription = await process_audio_file_with_s3(audio_file)
    return success, result, transcription

def read_audio_file(file):
    """Read the audio file and return its binary content and type"""
    # Save current position
    position = file.tell()
    # Go to the beginning of the file
    file.seek(0)
    # Read the binary content
    content = file.read()
    # Restore position
    file.seek(position)
    
    # Get the file type (extension)
    file_type = file.name.split('.')[-1].lower()
    if file_type not in ['mp3', 'wav', 'm4a']:
        file_type = 'audio/mpeg'  # Default to MP3 if unknown
    else:
        file_type = f'audio/{file_type}'
    
    return content, file_type

def handle_sidebar_events():
    # Check for messages from JavaScript or direct URL parameters
    if "history_select" in st.session_state:
        analysis_id = st.session_state.history_select
        if analysis_id:
            st.session_state.view_mode = "history_item"
            st.session_state.current_analysis_id = analysis_id
            # Clear the session state
            del st.session_state.history_select
    
    elif "history_delete" in st.session_state:
        analysis_id = st.session_state.history_delete
        if analysis_id:
            db_utils.delete_analysis(analysis_id)
            # Clear the session state
            del st.session_state.history_delete
            # If the deleted item was currently selected, reset view
            if st.session_state.current_analysis_id == analysis_id:
                st.session_state.view_mode = "new_analysis"
                st.session_state.current_analysis_id = None

def render_history_item(item, is_selected=False):
    # Format the datetime
    dt_formatted = format_datetime(item['upload_time'])
    file_size = format_file_size(item['file_size'])
    
    # Create unique keys for each history item button
    select_key = f"select_{item['id']}"
    delete_key = f"delete_{item['id']}"
    
    # Create the history item with Streamlit components
    with st.container():
        # Add visual separation and highlight for selected item
        if is_selected:
            st.markdown(f"<div style='border-left: 3px solid #1f77b4; padding-left: 10px;'>", unsafe_allow_html=True)
        else:
            st.markdown("<div>", unsafe_allow_html=True)
            
        # Format filename to be bold and show date/time and file size
        button_text = f"**{item['filename']}**\n{dt_formatted['date']} • {dt_formatted['time']}\n{file_size}"
        
        col1, col2 = st.columns([5, 1])
        
        # Item container (clickable area)
        with col1:
            if st.button(
                button_text,
                key=select_key,
                use_container_width=True
            ):
                st.session_state.history_select = item['id']
                st.rerun()
        
        # Delete button
        with col2:
            delete_clicked = st.button("🗑️", key=delete_key)
            if delete_clicked:
                # Show confirmation dialog using a separate session state variable
                st.session_state[f"confirm_delete_{item['id']}"] = True
        
        # End div for highlighting
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Handle delete confirmation
        if f"confirm_delete_{item['id']}" in st.session_state and st.session_state[f"confirm_delete_{item['id']}"]:
            confirm_col1, confirm_col2 = st.columns([1, 1])
            with confirm_col1:
                if st.button("Yes, delete", key=f"confirm_yes_{item['id']}"):
                    st.session_state.history_delete = item['id']
                    # Clean up session state
                    del st.session_state[f"confirm_delete_{item['id']}"]
                    st.rerun()
            with confirm_col2:
                if st.button("Cancel", key=f"confirm_no_{item['id']}"):
                    # Just remove confirmation flag
                    del st.session_state[f"confirm_delete_{item['id']}"]
                    st.rerun()

def main():
    # Handle events from sidebar
    handle_sidebar_events()
    
    # Sidebar with history
    with st.sidebar:
        st.title("History")
        
        # New Analysis button
        if st.button("➕ New Analysis", use_container_width=True):
            st.session_state.view_mode = "new_analysis"
            st.session_state.current_analysis_id = None
            st.session_state.api_result = None
            st.session_state.transcription = None
            st.rerun()
        
        st.markdown("---")
        
        # Get history items
        history_items = db_utils.get_all_analyses()
        
        if not history_items:
            st.info("No analysis history yet. Upload an audio file to get started.")
        else:
            # Display each history item using Streamlit components
            for item in history_items:
                is_selected = st.session_state.current_analysis_id == item['id']
                render_history_item(item, is_selected)
    
    # Header with logo stacked above text
    st.markdown("""
        <div class="logo-container">
            <img src="https://digitalclassworld.com/business-listing/storage/app/app_resources/seller/institute/institute_icon/3558/institute-logo1719469843.png" alt="Motion Education Logo">
            <h1>Sales Call Analysis</h1>
            <p style="font-size: 1.2rem; color: #666;">
                Upload a sales call recording to analyze it for potential false promises and concerning patterns.
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    # View history item
    if st.session_state.view_mode == "history_item" and st.session_state.current_analysis_id:
        # Load analysis from database
        analysis_data = db_utils.get_analysis_by_id(st.session_state.current_analysis_id)
        
        if analysis_data:
            # Display file info
            dt_formatted = format_datetime(analysis_data['upload_time'])
            file_size = format_file_size(analysis_data['file_size'])
            
            st.markdown(f"""
            ## 📄 {analysis_data['filename']}
            **Analyzed:** {dt_formatted['date']} at {dt_formatted['time']} ({dt_formatted['relative']})  
            **Size:** {file_size}
            """)
            
            # Display the audio player if audio data is available
            if 'audio_base64' in analysis_data and analysis_data['audio_base64']:
                st.markdown(f"""
                ### 🔊 Recording
                <audio controls style="width: 100%;">
                    <source src="data:{analysis_data['audio_type']};base64,{analysis_data['audio_base64']}" type="{analysis_data['audio_type']}">
                    Your browser does not support the audio element.
                </audio>
                """, unsafe_allow_html=True)
            
            # Create two columns for the layout
            col1, col2 = st.columns([1, 1])
            
            with col1:
                # Show transcript in expander
                if analysis_data['transcription']:
                    with st.expander("📝 View Transcription", expanded=False):
                        st.markdown(analysis_data['transcription'])
                
                # Download buttons for transcript and audio
                if analysis_data['transcription']:
                    st.download_button(
                        "📥 Download Transcription",
                        analysis_data['transcription'],
                        file_name=f"{analysis_data['filename']}_transcription.txt",
                        mime="text/plain",
                        key='download_history_transcription_button',
                        use_container_width=True
                    )
                
                # Download audio button if available
                if 'audio_data' in analysis_data and analysis_data['audio_data']:
                    st.download_button(
                        "📥 Download Audio",
                        analysis_data['audio_data'],
                        file_name=analysis_data['filename'],
                        mime=analysis_data['audio_type'],
                        key='download_history_audio_button',
                        use_container_width=True
                    )
            
            # Create tabs for different analyses from the API
            result_tab1, result_tab2 = st.tabs(["False Promises", "Bad Call Phrases"])
            
            # Tab 1: False Promises Analysis from API
            with result_tab1:
                st.markdown("## 🔍 False Promises Analysis")
                try:
                    meta = analysis_data['api_result'].get("meta", {})
                    false_promise_data = meta.get("false_promise", {})
                    
                    if false_promise_data:
                        formatted_sections = format_false_promises(false_promise_data)
                        for section in formatted_sections:
                            st.markdown(section, unsafe_allow_html=True)
                    else:
                        st.info("False promises analysis not available.")
                except Exception as e:
                    st.error(f"Error displaying false promises analysis results: {str(e)}")
            
            # Tab 2: Bad Call Analysis from API
            with result_tab2:
                st.markdown("## 🔍 Bad Call Analysis")
                try:
                    meta = analysis_data['api_result'].get("meta", {})
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
            st.error("Analysis not found. It may have been deleted.")
            # Reset to new analysis mode
            st.session_state.view_mode = "new_analysis"
            st.session_state.current_analysis_id = None
    
    # New analysis mode
    else:
        # Check for AWS credentials
        if not os.getenv("AWS_ACCESS_KEY_ID") or not os.getenv("AWS_SECRET_ACCESS_KEY"):
            st.warning("AWS credentials not found. Please set the AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables in .env file.")
        else:
            # File upload for analysis
            audio_file = st.file_uploader(
                "Upload Audio File",
                type=["mp3", "wav", "m4a"],
                help="Upload an audio file to analyze",
                key="audio_file"
            )
            
            if audio_file:
                st.audio(audio_file, format='audio/*')
                
                # Add analyze button
                analyze_button = st.button(
                    "Analyze Call",
                    key='analyze_button',
                )
                
                if analyze_button:
                    # Run async process with S3
                    loop = asyncio.new_event_loop()
                    success, result, transcription = loop.run_until_complete(process_with_s3(audio_file))
                    loop.close()
                    
                    if success and result:
                        # Read the audio file content
                        audio_data, audio_type = read_audio_file(audio_file)
                        
                        # Save to database with audio data
                        analysis_id = db_utils.save_analysis(
                            filename=audio_file.name,
                            transcription=transcription,
                            api_result=result,
                            file_size=audio_file.size,
                            audio_data=audio_data,
                            audio_type=audio_type
                        )
                        
                        # Set current analysis
                        st.session_state.view_mode = "history_item"
                        st.session_state.current_analysis_id = analysis_id
                        
                        # Rerun to display the new analysis
                        st.rerun()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8501))
    main() 