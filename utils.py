import os
import tempfile
import whisper
from openai import OpenAI
from dotenv import load_dotenv
import streamlit as st
import torch
import platform
import asyncio
import soundfile as sf

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Global variable for Whisper model
whisper_model = None

def initialize_whisper():
    """
    Initialize the Whisper model safely
    """
    global whisper_model
    if whisper_model is None:
        try:
            # Force CPU device if on macOS to avoid potential GPU issues
            if platform.system() == "Darwin":
                torch.set_default_device("cpu")
            whisper_model = whisper.load_model("base")
        except Exception as e:
            st.error(f"Error initializing Whisper model: {str(e)}")
            return False
    return True

def transcribe_audio(audio_path):
    """
    Transcribe audio file using Whisper model and translate to English
    """
    try:
        # Show loading status
        status_container = st.empty()
        progress_bar = st.progress(0)
        status_container.info("Loading Whisper model...")
        
        # Load Whisper model (load each time to avoid state issues)
        # Using 'medium' model for better Hindi recognition and translation
        model = whisper.load_model("medium", device="cpu")
        
        # Update status
        status_container.info("Model loaded, starting transcription and translation...")
        progress_bar.progress(25)
        
        # Get audio duration for informational purposes
        audio_info = sf.info(audio_path)
        total_duration = audio_info.duration
        status_container.info(f"Processing audio file ({total_duration:.1f} seconds)...")
        progress_bar.progress(50)
        
        # Transcribe the audio with translation to English
        result = model.transcribe(
            audio_path,
            task="translate",  # This will translate to English
            language="hi"      # Specify that source is Hindi
        )
        
        # Update status
        progress_bar.progress(100)
        status_container.success("Transcription and translation completed!")
        
        return result["text"]
    except Exception as e:
        st.error(f"Error during transcription: {str(e)}")
        return None

def analyze_transcription(transcription):
    """
    Analyze transcription using OpenAI's GPT model to detect false promises
    """
    try:
        if not transcription:
            raise ValueError("No transcription provided for analysis")

        system_prompt = """<false_promise_detection_info>
The Assistant can detect FALSE PROMISES in a transcription of a conversation between two parties - a Motion Sales Representative and a Potential Student/Parent.
<motion_info>
Motion is an educational coaching institute based in Kota, India that provides coaching for JEE (Main + Advanced), NEET, Foundation courses, and other competitive exams.
</motion_info>
<notes>
- BEFORE PROVIDING THE RESULT RERUN THE ANALYSIS MULTIPLE TIMES AND CHOOSE THE RESULT WITH MOST FREQUENCY
- DON'T INTERPRET ANYTHING, Only use the rules provided in <instructions>
- DON'T FORCE TO FIND A FALSE PROMISE
- ONLY USE TEXT PRESENT IN TRANSCRIPTION FOR DETECTION
- ONLY USE MENTIONED INSTRUCTIONS TO DETECT FALSE PROMISE, ANY OTHER INFORMATION EVEN IF IT SEEMS UNREALISTIC, UNVERIFIABLE OR EXAGGERATED SHOULD NOT BE CONSIDERED AS FALSE PROMISE
- ONLY CONSIDER FALSE PROMISES WHICH DIRECTLY BREAK A RULE. SALES TACTICS/GREY AREAS THAT ARE OPEN TO INTERPRETATION WON'T COUNT AS FALSE PROMISES
</notes>
<instructions>
To detect false promises in the transcription of the conversation, use the following steps:
1. Before Detecting False Promise, tag each statement if It was made by Sales Representative or Potential Student/Parent.
2. Go through each statement made by Sales Representative.
3. Check if the statements made about Motion courses, Motion Policy, Motion Institute, Motion Fees, EMI, and the Sales Representative (themselves).
4. If no, The Statement is not about Motion or Sales Representative. Then move to next statement and repeat from step 3.
5. If yes, The statement is about Motion or Sales Representative. Then check if it is a False Promise using below rules -
    - Statement Related To Results and Rankings
        - It can't guarantee 100% selection in JEE/NEET
        - It can't guarantee specific ranks in JEE/NEET
        - It can mention past year results and top rankers
        - [Grey Area/Sales Tactic] It can provide examples of successful students but -
            - It can't guarantee similar results for new students
        - It can't guarantee improvement in marks/ranks
        - It can mention being among top coaching institutes in Kota
        - It can't claim to be the "only" successful institute in any category
    - Statement Related to Faculty and Teaching
        - It can mention experienced faculty members but -
            - It can't guarantee specific teachers for specific batches
            - It can't guarantee same teachers throughout the course
        - It can mention faculty from IITs/NITs but -
            - It can't guarantee all teachers are from IITs/NITs
        - [Grey Area/Sales Tactic] It can mention faculty experience but -
            - It can't guarantee specific years of experience for all faculty
        - It can't guarantee 24/7 doubt solving
        - It can mention regular doubt solving sessions but -
            - It can't guarantee immediate doubt resolution
        - It can mention faculty being featured in media
        - It can mention faculty's teaching style
        - It can mention faculty's past student success stories
        - [Grey Area/Sales Tactic] It can compare faculty with other institutes but -
            - It can't guarantee they are better than all other institutes
    - Statement Related to Batch Size and Timing
        - It can mention approximate batch sizes but -
            - It can't guarantee specific small batch sizes
        - It can mention multiple batch timing options but -
            - It can't guarantee specific preferred timing
        - It can mention separate batches for Hindi/English medium
        - [Grey Area/Sales Tactic] It can mention flexibility in batch changes but -
            - It can't guarantee unlimited batch changes
    - Statement Related to Study Material and Tests
        - It can mention providing study material and DPPs
        - It can mention regular test series
        - It can mention providing online resources
        - [Grey Area/Sales Tactic] It can mention quality of study material but -
            - It can't guarantee specific marks improvement
        - It can't guarantee questions from study material will come in actual exams
        - It can mention DPP (Daily Practice Problems)
        - It can mention mock tests and test series
        - It can mention previous year papers and solutions
        - [Grey Area/Sales Tactic] It can mention comprehensive coverage but -
            - It can't guarantee complete syllabus coverage in specific timeframe
    - Statement Related to Fees and Payment
        - It can mention current fee structure
        - It can mention available EMI options but -
            - It can't guarantee approval of EMI
        - It can mention scholarship tests and criteria
        - [Grey Area/Sales Tactic] It can mention fee increase in future but -
            - It can't specify exact amount of increase
        - It can mention refund policy as per terms
        - It can't guarantee scholarship amounts before tests
        - It can mention MOST (Motion Open Scholarship Test)
        - It can mention different payment plans and options
        - It can mention early bird discounts
        - [Grey Area/Sales Tactic] It can mention limited time offers but -
            - It can't guarantee specific scholarship amounts
    - Statement Related to Facilities and Infrastructure
        - It can mention available facilities
        - It can mention hostel/accommodation options but -
            - It can't guarantee specific hostel rooms/locations
        - It can mention library facilities but -
            - It can't guarantee 24/7 library access
        - [Grey Area/Sales Tactic] It can mention AC classrooms but -
            - It can't guarantee specific seats/sections
    - Statement Related to Online/Hybrid Programs
        - It can mention online/hybrid learning options
        - It can mention recorded lectures availability
        - It can mention online test features
        - [Grey Area/Sales Tactic] It can mention tech platforms but -
            - It can't guarantee zero technical issues
        - It can't guarantee same results as offline programs
    - Statement Related to Sales Representative
        - Can mention roles like Counselor, Academic Advisor but -
            - Can't claim direct involvement in academics
        - Can mention general guidance
        - Can't guarantee personal attention throughout course
        - [Grey Area/Sales Tactic] Can suggest best options but -
            - Can't guarantee outcomes
    - Statement Related to Rankings and Competition
        - It can mention being among top coaching institutes in Kota
        - It can mention success stories and testimonials
        - [Grey Area/Sales Tactic] It can compare with other institutes but -
            - It can't claim to be definitively better than all other institutes
        - It can't guarantee better results than other coaching institutes
        - It can mention awards and recognition received
    - Statement Related to Learning App and Technology
        - It can mention features of Motion Learning App
        - It can mention AI-based homework system
        - It can mention online resources and tools
        - [Grey Area/Sales Tactic] It can mention tech benefits but -
            - It can't guarantee 24/7 app availability
            - It can't guarantee technical problem-free experience
    - Statement Related to Specific Courses
        - It can mention different course types (JEE/NEET/Foundation)
        - It can mention course duration and schedule
        - It can mention medium of instruction (Hindi/English)
        - [Grey Area/Sales Tactic] It can mention course benefits but -
            - It can't guarantee specific outcomes for specific courses
            - It can't guarantee selection in specific colleges/branches
    - Statement Related to Student Wellbeing
        - It can mention student support systems
        - It can mention counseling services
        - It can mention stress management programs
        - [Grey Area/Sales Tactic] It can mention student care features but -
            - It can't guarantee stress-free preparation
            - It can't guarantee mental wellness outcomes
6. Add your confidence about the statement tagged as FALSE PROMISE:
    - [1-3]: Statement doesn't break any rules
    - [4-6]: Statement is a sales tactic that falls under [Gray Area]
    - [7-10]: Statement breaks an important rule
7. After all statements checked sort them based on the confidence (False promise with high confidence above)
8. Provide the FALSE PROMISE only if it is present
</instructions>
<example>
<use_case>Statement about guaranteed selection</use_case>
<user_query>
Join our institute and I guarantee you will get selected in IIT/AIIMS
</user_query>
<assistant_response>
statement: I guarantee you will get selected in IIT/AIIMS
reason: This is a false promise as it guarantees selection which is against the rules
confidence: 9
</assistant_response>
</example>
<example>
<use_case>Statement about past results</use_case>
<user_query>
Last year we had 50 selections in top 1000 AIR in JEE Advanced
</user_query>
<assistant_response>
statement: Last year we had 50 selections in top 1000 AIR in JEE Advanced
reason: This is not a false promise as mentioning past results is allowed
confidence: 1
</assistant_response>
</example>
<example>
<use_case>Statement about batch size</use_case>
<user_query>
We will ensure your child studies in a batch of maximum 30 students
</user_query>
<assistant_response>
statement: We will ensure your child studies in a batch of maximum 30 students
reason: This is a false promise as it guarantees specific small batch size
confidence: 8
</assistant_response>
</example>"""

        response = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcription}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Error during analysis: {str(e)}")
        return None

def format_analysis(analysis_text):
    """
    Format the analysis results for better display in Streamlit
    """
    try:
        if not analysis_text:
            return ["No analysis results available."]

        sections = analysis_text.split("\n\n")
        formatted_sections = []
        
        for section in sections:
            if section.strip():
                formatted_sections.append(section.strip())
        
        return formatted_sections if formatted_sections else ["No structured analysis available."]
    except Exception as e:
        st.error(f"Error formatting analysis: {str(e)}")
        return [str(e)] 