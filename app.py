import streamlit as st
from utils import transcribe_audio, analyze_transcription, format_analysis, logger
import os
import tempfile
import asyncio
from functools import partial
import aiohttp
from utils import TranscriptionService

# Set page config must be the first Streamlit command
st.set_page_config(
    page_title="Sales Call Analysis",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.transcription = None
    st.session_state.analysis = None

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
    </style>
""", unsafe_allow_html=True)

async def process_audio(audio_file):
    try:
        logger.log_step("Process Started", "info", f"Processing file: {audio_file.name}")
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save the uploaded file to the temporary directory
            temp_path = os.path.join(temp_dir, audio_file.name)
            with open(temp_path, 'wb') as f:
                f.write(audio_file.getbuffer())
            
            # Process the audio file
            transcription = await transcribe_audio(temp_path)
            if transcription:
                logger.log_step("Transcription Success", "success", "Audio transcribed successfully")
                logger.log_step("Starting Analysis", "info", "Analyzing transcription for false promises")
                analysis = analyze_transcription(transcription)
                if analysis:
                    logger.log_step("Analysis Complete", "success", "Transcription analyzed successfully")
                return transcription, analysis
            logger.log_step("Process Failed", "error", "Failed to process audio file")
            return None, None
    except Exception as e:
        logger.log_step("Process Error", "error", str(e))
        st.error(f"Error processing audio: {str(e)}")
        return None, None

def main():
    # Add custom CSS for column layout
    st.markdown("""
    <style>
    /* Custom styling for columns */
    [data-testid="stHorizontalBlock"] {
        gap: 2rem;
    }
    
    /* Main content area styling */
    .main-content {
        padding-right: 1rem;
    }
    
    /* Logs column styling */
    .logs-column {
        background-color: #0E1117;
        border-radius: 5px;
        padding: 1rem;
        height: 100%;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Create two columns with custom widths
    main_col, logs_col = st.columns([0.7, 0.3])
    
    # Main content column
    with main_col:
        # Header
        st.title("🎯 Sales Call Analysis")
        st.markdown("""
        Upload a sales call recording to analyze it for potential false promises and concerning patterns.
        Supported formats: MP3, WAV, M4A
        """)
        
        # File upload
        audio_file = st.file_uploader(
            "Upload Audio File",
            type=["mp3", "wav", "m4a"],
            help="Upload an audio file to analyze"
        )
        
        if audio_file:
            logger.log_step("File Uploaded", "info", f"File name: {audio_file.name}")
            st.audio(audio_file, format='audio/*')
            
            # Add analyze button with unique key
            if st.button("Analyze Call", key='analyze_call_button'):
                with st.spinner("Processing audio... This may take a few minutes."):
                    # Run async process_audio in the event loop
                    loop = asyncio.new_event_loop()
                    transcription, analysis = loop.run_until_complete(process_audio(audio_file))
                    loop.close()
                    
                    if transcription and analysis:
                        st.session_state.transcription = transcription
                        st.session_state.analysis = analysis
                    
                if st.session_state.transcription:
                    st.success("Analysis completed!")
                    logger.log_step("Process Complete", "success", "Analysis completed successfully")
                    
                    # Show transcription in expander
                    with st.expander("View Transcription"):
                        st.markdown(st.session_state.transcription)
                    
                    # Display analysis results
                    st.markdown("## Analysis Results")
                    
                    formatted_sections = format_analysis(st.session_state.analysis)
                    for section in formatted_sections:
                        st.markdown(section)
                        st.markdown("---")
                    
                    # Download buttons with unique keys
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button(
                            "Download Transcription",
                            st.session_state.transcription,
                            file_name="transcription.txt",
                            mime="text/plain",
                            key='download_transcription_button'
                        )
                    with col2:
                        st.download_button(
                            "Download Analysis",
                            st.session_state.analysis,
                            file_name="analysis.txt",
                            mime="text/plain",
                            key='download_analysis_button'
                        )
    
    # Logs column
    with logs_col:
        logger.render_logs()

if __name__ == "__main__":
    main() 