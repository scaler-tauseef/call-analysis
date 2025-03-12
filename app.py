import streamlit as st
from utils import transcribe_audio, analyze_transcription, format_analysis
import os
import tempfile
import asyncio
from functools import partial
import aiohttp
from utils import TranscriptionService

# This MUST be the first Streamlit command
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
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save the uploaded file to the temporary directory
            temp_path = os.path.join(temp_dir, audio_file.name)
            with open(temp_path, 'wb') as f:
                f.write(audio_file.getbuffer())
            
            # Process the audio file
            transcription = await transcribe_audio(temp_path)
            if transcription:
                analysis = analyze_transcription(transcription)
                return transcription, analysis
            return None, None
    except Exception as e:
        st.error(f"Error processing audio: {str(e)}")
        return None, None

def main():
    # Add custom CSS for column layout
    st.markdown("""
    <style>
    /* Main content area styling */
    .main-content {
        padding: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)
    
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

if __name__ == "__main__":
    main() 