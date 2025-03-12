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

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class TranscriptionService:
    def __init__(self):
        # self.base_url = "https://fast-transcriber.sales-copilot.scaler.com"
        self.base_url = "http://motion-transcriber-service.us-west-2.elasticbeanstalk.com"
        self.metrics = {"success": 0, "failed": 0}
        self.max_poll_time = 300  # 5 minutes maximum polling time
        self.poll_interval = 5  # 5 seconds between polls
        
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
                                    return self._create_result(test_id, filename, True, result_data["text"], task_id=task_id)
                            except json.JSONDecodeError as e:
                                return self._create_result(test_id, filename, False, None, f"Failed to parse result: {str(e)}", task_id)
                        elif data.get("status") == "RUNNING" or data.get("status") == "QUEUED":
                            status_container.info(f"Processing audio... (Task ID: {task_id}, Attempt {attempt + 1}/{max_attempts})")
                            progress = min(75 + (attempt / max_attempts * 20), 95)
                            progress_bar.progress(int(progress))
                        else:
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
                        return self._create_result(test_id, filename, False, None, error_msg, task_id)
                
                attempt += 1
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                self.metrics["failed"] += 1
                return self._create_result(test_id, filename, False, None, f"Polling error: {str(e)}", task_id)
        
        self.metrics["failed"] += 1
        st.experimental_rerun()
        return self._create_result(test_id, filename, False, None, "Polling timeout: Maximum attempts reached", task_id)
    
    async def process_audio(self, session: aiohttp.ClientSession, audio_file: str,
                          status_container: Any, progress_bar: Any) -> Dict[str, Any]:
        test_id = random.randint(10000, 99999)
        start_time = time.time()
        
        try:
            status_container.info("Reading audio file...")
            progress_bar.progress(25)
            
            with open(audio_file, 'rb') as f:
                file_content = f.read()

            status_container.info("Preparing upload...")
            progress_bar.progress(50)

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
                    return self._create_result(test_id, audio_file, False, None, error_msg)

                try:
                    data = await response.json()
                    task_id = data.get('task_id')
                    
                    if not task_id:
                        self.metrics["failed"] += 1
                        return self._create_result(test_id, audio_file, False, None, "No task ID received in response")
                except Exception as e:
                    self.metrics["failed"] += 1
                    return self._create_result(test_id, audio_file, False, None, "Failed to parse response")

                status_container.info(f"Starting transcription... (Task ID: {task_id})")
                result = await self._poll_result(session, task_id, start_time, audio_file, test_id,
                                               status_container, progress_bar)
                return result

        except Exception as e:
            self.metrics["failed"] += 1
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
Motion is an educational coaching institute based in Kota India, that provides coaching for JEE (Main + Advanced), NEET, Foundation courses, and other competitive exams.
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
            model="o3-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcription}
            ],
            # temperature=0.7,
            # max_tokens=2000
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