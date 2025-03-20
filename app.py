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

# Load environment variables
load_dotenv()

# Check for required environment variables
if not os.getenv("OPENAI_API_KEY"):
    st.error("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable in .env file.")
    st.stop()

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
    st.session_state.bad_phrases_analysis = None
    st.session_state.api_result = None

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
                # First analyze for false promises
                analysis = analyze_transcription(transcription)
                # Then analyze for bad phrases
                bad_phrases_analysis = analyze_bad_phrases(transcription)
                return transcription, analysis, bad_phrases_analysis
            return None, None, None
    except Exception as e:
        st.error(f"Error processing audio: {str(e)}")
        return None, None, None

async def process_with_s3(audio_file):
    # Process the audio file with S3 upload and API integration
    success, result = await process_audio_file_with_s3(audio_file)
    return success, result

def main():
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
    
    # Create tabs for different analysis methods
    tab1, tab2 = st.tabs(["Local Analysis", "S3 + API Analysis"])
    
    with tab1:
        st.markdown("""
        <h3 style="margin-bottom: 1rem;">Local Analysis</h3>
        <p>Upload an audio file to analyze it locally using our AI models.</p>
        """, unsafe_allow_html=True)
        
        # File upload with clean UI
        audio_file = st.file_uploader(
            "Upload Audio File",
            type=["mp3", "wav", "m4a"],
            help="Upload an audio file to analyze locally",
            key="local_audio_file"
        )
        
        if audio_file:
            st.audio(audio_file, format='audio/*')
            
            # Add analyze button with improved styling
            analyze_button = st.button(
                "Analyze Call Locally",
                key='analyze_call_button',
            )
            
            if analyze_button:
                with st.spinner("🎯 Analyzing your sales call..."):
                    # Run async process_audio in the event loop
                    loop = asyncio.new_event_loop()
                    transcription, analysis, bad_phrases_analysis = loop.run_until_complete(process_audio(audio_file))
                    loop.close()
                    
                    if transcription and analysis:
                        st.session_state.transcription = transcription
                        st.session_state.analysis = analysis
                        st.session_state.bad_phrases_analysis = bad_phrases_analysis
                    
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
                        # Download analysis buttons
                        st.download_button(
                            "📥 Download False Promises Analysis",
                            st.session_state.analysis,
                            file_name="false_promises_analysis.json",
                            mime="application/json",
                            key='download_analysis_button',
                            use_container_width=True
                        )
                        
                        if st.session_state.bad_phrases_analysis:
                            st.download_button(
                                "📥 Download Bad Phrases Analysis",
                                st.session_state.bad_phrases_analysis,
                                file_name="bad_phrases_analysis.json",
                                mime="application/json",
                                key='download_bad_phrases_button',
                                use_container_width=True
                            )
                    
                    # Create tabs for different analyses
                    result_tab1, result_tab2 = st.tabs(["False Promises", "Bad Phrases"])
                    
                    # Tab 1: False Promises Analysis
                    with result_tab1:
                        st.markdown("## 🔍 False Promises Analysis")
                        try:
                            formatted_sections = format_analysis(st.session_state.analysis)
                            for section in formatted_sections:
                                st.markdown(section, unsafe_allow_html=True)
                        except Exception as e:
                            st.error(f"Error displaying false promises analysis results: {str(e)}")
                    
                    # Tab 2: Bad Phrases Analysis
                    with result_tab2:
                        st.markdown("## 🔍 Bad Phrases Analysis")
                        if st.session_state.bad_phrases_analysis:
                            try:
                                formatted_sections = format_bad_phrases_analysis(st.session_state.bad_phrases_analysis)
                                for section in formatted_sections:
                                    st.markdown(section, unsafe_allow_html=True)
                            except Exception as e:
                                st.error(f"Error displaying bad phrases analysis results: {str(e)}")
                        else:
                            st.info("Bad phrases analysis not available.")
    
    with tab2:
        st.markdown("""
        <h3 style="margin-bottom: 1rem;">S3 + API Analysis</h3>
        <p>Upload an audio file to S3 and get analysis from the external API.</p>
        """, unsafe_allow_html=True)
        
        if not os.getenv("AWS_ACCESS_KEY_ID") or not os.getenv("AWS_SECRET_ACCESS_KEY"):
            st.warning("AWS credentials not found. Please set the AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables in .env file.")
        else:
            # File upload for S3 analysis
            s3_audio_file = st.file_uploader(
                "Upload Audio File",
                type=["mp3", "wav", "m4a"],
                help="Upload an audio file to analyze via S3 and API",
                key="s3_audio_file"
            )
            
            if s3_audio_file:
                st.audio(s3_audio_file, format='audio/*')
                
                # Add analyze button
                s3_analyze_button = st.button(
                    "Analyze with S3 + API",
                    key='s3_analyze_button',
                )
                
                if s3_analyze_button:
                    # Run async process with S3
                    loop = asyncio.new_event_loop()
                    success, result = loop.run_until_complete(process_with_s3(s3_audio_file))
                    loop.close()
                    
                    if success and result:
                        st.session_state.api_result = result
                    
                if st.session_state.api_result:
                    # Display results
                    st.success("✨ Analysis completed successfully!")
                    
                    # Create two columns for the layout
                    col1, col2 = st.columns([1, 1])
                    
                    with col1:
                        # Show call details
                        with st.expander("📋 Call Details", expanded=False):
                            st.json(st.session_state.api_result)
                        
                        # Download analysis button
                        st.download_button(
                            "📥 Download Full Analysis",
                            json.dumps(st.session_state.api_result, indent=2),
                            file_name="api_analysis.json",
                            mime="application/json",
                            key='download_api_analysis_button',
                            use_container_width=True
                        )
                    
                    # Create tabs for different analyses from the API
                    api_tab1, api_tab2 = st.tabs(["False Promises", "Bad Call Phrases"])
                    
                    # Tab 1: False Promises Analysis from API
                    with api_tab1:
                        st.markdown("## 🔍 False Promises Analysis")
                        try:
                            meta = st.session_state.api_result.get("meta", {})
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
                    with api_tab2:
                        st.markdown("## 🔍 Bad Call Analysis")
                        try:
                            meta = st.session_state.api_result.get("meta", {})
                            abusive_bad_call_data = meta.get("abusive_bad_call", {})
                            
                            if abusive_bad_call_data:
                                formatted_sections = format_bad_phrases(abusive_bad_call_data)
                                for section in formatted_sections:
                                    st.markdown(section, unsafe_allow_html=True)
                            else:
                                st.info("Bad call analysis not available.")
                        except Exception as e:
                            st.error(f"Error displaying bad call analysis results: {str(e)}")

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8501))
    main() 