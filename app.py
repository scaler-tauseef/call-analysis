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
    page_title="Scaler Ai Call Analysis Demo",
    page_icon=os.path.join(os.path.dirname(__file__), "favicon.ico"),
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.api_result = None
    st.session_state.transcription = None

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

async def process_with_s3(audio_file):
    # Process the audio file with S3 upload and API integration
    success, result, transcription = await process_audio_file_with_s3(audio_file)
    return success, result, transcription

def main():
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
    
    # Check for AWS credentials
    if not os.getenv("AWS_ACCESS_KEY_ID") or not os.getenv("AWS_SECRET_ACCESS_KEY"):
        st.warning("AWS credentials not found. Please set the AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables in .env file.")
    else:
        # File upload for analysis
        audio_file = st.file_uploader(
            "Upload Audio File",
            type=["mp3", "wav", "m4a"],
            help="Upload an audio file to analyze via S3 and API",
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
                    st.session_state.api_result = result
                    st.session_state.transcription = transcription
                
            if st.session_state.api_result:
                # Display results
                st.success("✨ Analysis completed successfully!")
                
                # Create two columns for the layout
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    # Show transcript in expander
                    if st.session_state.transcription:
                        with st.expander("📝 View Transcription", expanded=False):
                            st.markdown(st.session_state.transcription)
                    
                    # Download transcript button if available
                    if st.session_state.transcription:
                        st.download_button(
                            "📥 Download Transcription",
                            st.session_state.transcription,
                            file_name="transcription.txt",
                            mime="text/plain",
                            key='download_transcription_button',
                            use_container_width=True
                        )
                
                # with col2:
                #     # Download analysis button
                #     st.download_button(
                #         "📥 Download Full Analysis",
                #         json.dumps(st.session_state.api_result, indent=2),
                #         file_name="api_analysis.json",
                #         mime="application/json",
                #         key='download_api_analysis_button',
                #         use_container_width=True
                #     )
                
                # Create tabs for different analyses from the API
                result_tab1, result_tab2 = st.tabs(["False Promises", "Bad Call Phrases"])
                
                # Tab 1: False Promises Analysis from API
                with result_tab1:
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
                with result_tab2:
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