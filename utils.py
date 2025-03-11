import os
import tempfile
from openai import OpenAI
from dotenv import load_dotenv
import streamlit as st
import asyncio
import aiohttp
import time
import random
from typing import Dict, Any, Optional, List
import os.path
import json
from datetime import datetime

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class StepLogger:
    """Utility class to manage step logs in the application"""
    
    def __init__(self):
        if 'step_logs' not in st.session_state:
            st.session_state.step_logs = []
        if 'log_container' not in st.session_state:
            st.session_state.log_container = None
    
    def log_step(self, step_name: str, status: str = "info", details: Optional[str] = None):
        """
        Log a step with timestamp, name, status, and optional details
        status can be: "info", "success", "error", "warning"
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = {
            "timestamp": timestamp,
            "step": step_name,
            "status": status,
            "details": details
        }
        st.session_state.step_logs.append(log_entry)
        
        # If logs are being displayed, update them immediately
        if st.session_state.log_container is not None:
            self._update_logs()
    
    def clear_logs(self):
        """Clear all logs"""
        st.session_state.step_logs = []
        if st.session_state.log_container is not None:
            self._update_logs()
    
    def get_logs(self) -> List[Dict[str, Any]]:
        """Get all logs"""
        return st.session_state.step_logs

    def _update_logs(self):
        """Update only the logs content"""
        if st.session_state.log_container is not None:
            logs_html = '<div class="logs-container">'
            for log in st.session_state.step_logs:
                logs_html += f"""
                <div class="log-entry log-{log['status']}">
                    <div class="log-timestamp">{log['timestamp']}</div>
                    <div class="log-step">{log['step']}</div>
                """
                if log.get('details'):
                    logs_html += f'<div class="log-details">{log["details"]}</div>'
                logs_html += "</div>"
            logs_html += '</div>'
            st.session_state.log_container.markdown(logs_html, unsafe_allow_html=True)

    def render_logs(self):
        """Render logs with proper styling"""
        # Add styles
        st.markdown("""
        <style>
        .logs-container {
            background-color: #0E1117;
            border-radius: 5px;
            padding: 10px;
            max-height: calc(100vh - 150px);
            overflow-y: auto;
            margin: 0;
        }
        
        .log-entry {
            padding: 8px;
            margin: 5px 0;
            border-radius: 4px;
            font-size: 14px;
            background-color: #1E1E1E;
        }
        .log-info { border-left: 4px solid #0096FF; }
        .log-success { border-left: 4px solid #00FF00; }
        .log-error { border-left: 4px solid #FF0000; }
        .log-warning { border-left: 4px solid #FFA500; }
        .log-timestamp {
            color: #666;
            font-size: 12px;
        }
        .log-step {
            color: #FFF;
            font-weight: bold;
        }
        .log-details {
            color: #CCC;
            font-size: 13px;
            margin-top: 5px;
        }
        
        .logs-container::-webkit-scrollbar {
            width: 6px;
        }
        .logs-container::-webkit-scrollbar-track {
            background: #1E1E1E;
        }
        .logs-container::-webkit-scrollbar-thumb {
            background: #333;
            border-radius: 3px;
        }
        
        div[data-testid="stMarkdown"] {
            margin: 0 !important;
        }
        div.stButton > button {
            margin: 0 0 0.5rem 0;
            width: 100%;
        }
        </style>
        """, unsafe_allow_html=True)

        # Header
        st.markdown("### Process Logs")
        
        # Clear button
        if st.button("Clear Logs", key=f"clear_logs_{int(time.time())}"):
            self.clear_logs()
            st.rerun()

        # Initialize or get the container
        if st.session_state.log_container is None:
            st.session_state.log_container = st.empty()
        
        # Initial render of logs
        self._update_logs()

# Initialize the logger
logger = StepLogger()

class TranscriptionService:
    def __init__(self):
        self.base_url = "https://fast-transcriber.sales-copilot.scaler.com"
        self.metrics = {"success": 0, "failed": 0}
        self.max_poll_time = 300  # 5 minutes maximum polling time
        self.poll_interval = 5  # 5 seconds between polls
        logger.log_step("Transcription Service Initialized", "info")
        
    def _create_result(self, test_id: int, filename: str, success: bool, 
                      text: Optional[str], error: Optional[str] = None, task_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "test_id": test_id,
            "task_id": task_id,
            "filename": filename,
            "success": success,
            "text": text,
            "error": error
        }
    
    async def _poll_result(self, session: aiohttp.ClientSession, task_id: str, 
                          start_time: float, filename: str, test_id: int,
                          status_container: Any, progress_bar: Any) -> Dict[str, Any]:
        max_attempts = self.max_poll_time // self.poll_interval
        attempt = 0
        
        while attempt < max_attempts:
            try:
                elapsed_time = time.time() - start_time
                if elapsed_time >= self.max_poll_time:
                    self.metrics["failed"] += 1
                    logger.log_step("Polling Timeout", "error", f"Maximum polling time exceeded for task {task_id}")
                    st.experimental_rerun()
                    return self._create_result(test_id, filename, False, None, "Maximum polling time exceeded", task_id)

                async with session.get(f"{self.base_url}/transcribe/{task_id}/result") as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get("success") and data.get("status") == "COMPLETED" and data.get("result"):
                            try:
                                result_data = json.loads(data["result"])
                                
                                if result_data.get("text"):
                                    self.metrics["success"] += 1
                                    logger.log_step("Transcription Complete", "success", f"Task {task_id} completed successfully")
                                    return self._create_result(test_id, filename, True, result_data["text"], task_id=task_id)
                            except json.JSONDecodeError as e:
                                logger.log_step("Parse Error", "error", f"Failed to parse result for task {task_id}")
                                return self._create_result(test_id, filename, False, None, f"Failed to parse result: {str(e)}", task_id)
                        elif data.get("status") == "RUNNING" or data.get("status") == "QUEUED":
                            status_container.info(f"Processing audio... (Task ID: {task_id}, Attempt {attempt + 1}/{max_attempts})")
                            progress = min(75 + (attempt / max_attempts * 20), 95)
                            progress_bar.progress(int(progress))
                            logger.log_step("Processing", "info", f"Task {task_id} still processing (Attempt {attempt + 1}/{max_attempts})")
                        else:
                            logger.log_step("Invalid Response", "error", f"Unexpected response structure for task {task_id}")
                            return self._create_result(test_id, filename, False, None, "Invalid response format", task_id)
                    elif response.status != 200:
                        error_msg = f"HTTP {response.status}"
                        try:
                            error_data = await response.json()
                            if error_data.get("error"):
                                error_msg = f"HTTP {response.status}: {error_data['error']}"
                        except Exception:
                            error_msg = f"HTTP {response.status} - Could not parse error response"
                        self.metrics["failed"] += 1
                        logger.log_step("HTTP Error", "error", error_msg)
                        return self._create_result(test_id, filename, False, None, error_msg, task_id)
                
                attempt += 1
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                self.metrics["failed"] += 1
                logger.log_step("Polling Error", "error", str(e))
                return self._create_result(test_id, filename, False, None, f"Polling error: {str(e)}", task_id)
        
        self.metrics["failed"] += 1
        logger.log_step("Polling Timeout", "error", "Maximum attempts reached")
        st.experimental_rerun()
        return self._create_result(test_id, filename, False, None, "Polling timeout: Maximum attempts reached", task_id)
    
    async def process_audio(self, session: aiohttp.ClientSession, audio_file: str,
                          status_container: Any, progress_bar: Any) -> Dict[str, Any]:
        test_id = random.randint(10000, 99999)
        start_time = time.time()
        
        try:
            status_container.info("Reading audio file...")
            progress_bar.progress(25)
            logger.log_step("Reading File", "info", f"Processing {os.path.basename(audio_file)}")
            
            with open(audio_file, 'rb') as f:
                file_content = f.read()

            status_container.info("Preparing upload...")
            progress_bar.progress(50)
            logger.log_step("Preparing Upload", "info")

            mpwriter = aiohttp.MultipartWriter('form-data')
            part = mpwriter.append(file_content, {
                'Content-Type': 'audio/mpeg'
            })
            part.set_content_disposition('form-data', name='audio', filename=os.path.basename(audio_file))

            headers = {
                'Accept': 'application/json',
            }

            status_container.info("Uploading audio file...")
            progress_bar.progress(75)
            logger.log_step("Uploading", "info", "Starting file upload")

            async with session.post(
                f"{self.base_url}/transcribe", 
                data=mpwriter,
                headers=headers
            ) as response:
                if response.status != 200:
                    error_msg = f"Upload failed: HTTP {response.status}"
                    try:
                        error_data = await response.json()
                        if error_data.get("error"):
                            error_msg = f"Upload failed: {error_data['error']}"
                    except Exception:
                        error_msg = f"Upload failed: HTTP {response.status} - Could not parse error response"
                    self.metrics["failed"] += 1
                    logger.log_step("Upload Failed", "error", error_msg)
                    return self._create_result(test_id, audio_file, False, None, error_msg)

                try:
                    data = await response.json()
                    task_id = data.get('task_id')
                    
                    if not task_id:
                        self.metrics["failed"] += 1
                        logger.log_step("Task ID Missing", "error", "No task ID received in response")
                        return self._create_result(test_id, audio_file, False, None, "No task ID received in response")
                except Exception as e:
                    self.metrics["failed"] += 1
                    logger.log_step("Parse Error", "error", "Failed to parse upload response")
                    return self._create_result(test_id, audio_file, False, None, "Failed to parse response")

                status_container.info(f"Starting transcription... (Task ID: {task_id})")
                logger.log_step("Starting Transcription", "info", f"Task ID: {task_id}")
                result = await self._poll_result(session, task_id, start_time, audio_file, test_id,
                                               status_container, progress_bar)
                return result

        except Exception as e:
            self.metrics["failed"] += 1
            logger.log_step("Process Error", "error", str(e))
            return self._create_result(test_id, str(audio_file), False, None, f"Process error: {str(e)}")

async def transcribe_audio(audio_path: str) -> Optional[str]:
    """
    Transcribe audio file using external transcription service
    """
    try:
        # Show loading status
        status_container = st.empty()
        progress_bar = st.progress(0)
        status_container.info("Initializing transcription service...")
        
        service = TranscriptionService()
        progress_bar.progress(25)
        
        async with aiohttp.ClientSession() as session:
            result = await service.process_audio(session, audio_path, status_container, progress_bar)
            
            if result["success"]:
                progress_bar.progress(100)
                status_container.success(f"Transcription completed! (Task ID: {result.get('task_id')})")
                return result["text"]
            else:
                status_container.error(f"Transcription failed: {result['error']} (Task ID: {result.get('task_id')})")
                return None
                
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

def main():
    # Create two columns with specific widths
    col1, col2 = st.columns([0.7, 0.3])

    # Main content in the left column
    with col1:
        st.title("🎯 Sales Call Analysis")
        st.markdown("""
        Upload a sales call recording to analyze it for potential false promises and concerning patterns.
        Supported formats: MP3, WAV, M4A
        """)

        # File uploader
        uploaded_file = st.file_uploader("Choose an audio file", type=["mp3", "wav", "m4a"])

        if uploaded_file is not None:
            # Create a temporary file to store the uploaded audio
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                audio_path = tmp_file.name

            # Add analyze button
            analyze_clicked = st.button("Analyze Call")
            
            if analyze_clicked:
                with st.spinner("Processing audio..."):
                    # Transcribe audio
                    transcription = asyncio.run(transcribe_audio(audio_path))
                    
                    if transcription:
                        st.session_state.transcription = transcription
                        st.session_state.analysis = analyze_transcription(transcription)
                    
                    # Clean up the temporary file
                    os.unlink(audio_path)

            # Display results if available
            if 'transcription' in st.session_state and st.session_state.transcription:
                st.subheader("Transcription")
                st.write(st.session_state.transcription)
                
                if 'analysis' in st.session_state and st.session_state.analysis:
                    st.subheader("Analysis Results")
                    analysis_sections = format_analysis(st.session_state.analysis)
                    for section in analysis_sections:
                        st.write(section)
                
                # Download buttons in a single row
                st.write("")  # Add some spacing
                dl_col1, dl_col2 = st.columns(2)
                with dl_col1:
                    st.download_button(
                        "Download Transcription",
                        st.session_state.transcription,
                        "transcription.txt",
                        "text/plain",
                        key="download_transcription"
                    )
                
                with dl_col2:
                    st.download_button(
                        "Download Analysis",
                        "\n\n".join(format_analysis(st.session_state.analysis)),
                        "analysis.txt",
                        "text/plain",
                        key="download_analysis"
                    )

    # Logs in the right column
    with col2:
        logger.render_logs() 