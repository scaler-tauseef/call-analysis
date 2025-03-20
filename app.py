import streamlit as st
from utils import transcribe_audio, analyze_transcription, format_analysis
import os
import tempfile
import asyncio
from functools import partial
import aiohttp
from utils import TranscriptionService
import json

# This MUST be the first Streamlit command
st.set_page_config(
    page_title="Motion Sales Call Analysis",
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
    # Header with left-aligned styling
    st.markdown("""
        <div style="padding: 2rem 0;">
            <h1 style="margin-bottom: 1rem;">🎯 Motion Sales Call Analysis</h1>
            <p style="font-size: 1.2rem; color: #666;">
                Upload a sales call recording to analyze it for potential false promises and concerning patterns.
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    # File upload with clean UI
    audio_file = st.file_uploader(
        "Upload Audio File",
        type=["mp3", "wav", "m4a"],
        help="Upload an audio file to analyze"
    )
    
    if audio_file:
        st.audio(audio_file, format='audio/*')
        
        # Add analyze button with improved styling
        analyze_button = st.button(
            "Analyze Call",
            key='analyze_call_button',
        )
        
        if analyze_button:
            with st.spinner("🎯 Analyzing your sales call... This may take a few minutes."):
                # Run async process_audio in the event loop
                loop = asyncio.new_event_loop()
                transcription, analysis = loop.run_until_complete(process_audio(audio_file))
                loop.close()
                
                if transcription and analysis:
                    st.session_state.transcription = transcription
                    st.session_state.analysis = analysis
                
            if st.session_state.transcription:
                st.success("✨ Analysis completed successfully!")
                
                # Create two columns for the layout
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    # Show transcription in expander
                    with st.expander("📝 View Transcription", expanded=False):
                        st.markdown(st.session_state.transcription)
                    
                    # Download buttons
                    st.download_button(
                        "📥 Download Transcription",
                        st.session_state.transcription,
                        file_name="transcription.txt",
                        mime="text/plain",
                        key='download_transcription_button',
                        use_container_width=True
                    )
                
                with col2:
                    # Download analysis button
                    st.download_button(
                        "📥 Download Analysis",
                        st.session_state.analysis,
                        file_name="analysis.json",
                        mime="application/json",
                        key='download_analysis_button',
                        use_container_width=True
                    )
                
                # Display detailed analysis results
                st.markdown("## 🔍 Detailed Analysis")
                
                try:
                    formatted_sections = format_analysis(st.session_state.analysis)
                    for section in formatted_sections:
                        st.markdown(section, unsafe_allow_html=True)
                except Exception as e:
                    st.error("Error displaying analysis results")

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8501))
    main() 