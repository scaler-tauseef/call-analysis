import boto3
import os
import time
import random
import string
import json
import asyncio
import aiohttp
import tempfile
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class S3Service:
    def __init__(self):
        """Initialize the S3 service with AWS credentials"""
        self.s3_bucket = "external-tenants-call-analysis"
        self.s3_prefix = "call-recordings/development/"
        
        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-west-2')
        )
    
    def upload_file(self, file_path, file_name=None):
        """Upload a file to S3 bucket"""
        if file_name is None:
            # Generate a random file name if none provided
            file_name = f"{int(time.time())}_{self.generate_random_id()}.{file_path.split('.')[-1]}"
        
        # Full S3 key path
        s3_key = f"{self.s3_prefix}{file_name}"
        
        try:
            # Upload file to S3
            self.s3_client.upload_file(file_path, self.s3_bucket, s3_key)
            return s3_key
        except Exception as e:
            st.error(f"Error uploading file: {str(e)}")
            return None
    
    def generate_random_id(self, length=16):
        """Generate a random ID for file naming"""
        return ''.join(random.choice(string.digits) for _ in range(length))

def save_local_audio_copy(audio_file, custom_filename=None):
    """Save a local copy of the uploaded audio file to the uploads folder"""
    try:
        # Ensure uploads directory exists
        uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
        if not os.path.exists(uploads_dir):
            os.makedirs(uploads_dir)
            
        # Generate filename if not provided
        if not custom_filename:
            ext = os.path.splitext(audio_file.name)[1]
            timestamp = int(time.time())
            random_id = ''.join(random.choice(string.digits) for _ in range(8))
            filename = f"audio_{timestamp}_{random_id}{ext}"
        else:
            filename = custom_filename
            
        # Save file
        file_path = os.path.join(uploads_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(audio_file.getvalue())
            
        return filename, file_path
    except Exception as e:
        st.error(f"Error saving local audio copy: {str(e)}")
        return None, None

class APIService:
    def __init__(self):
        """Initialize the API service"""
        self.base_url = "https://11.staging.sclr.ac/external_call_logs/v1/tenant_motion"
        self.create_endpoint = f"{self.base_url}/create"
        self.result_endpoint = f"{self.base_url}/result"
        self.poll_interval = 5  # seconds
        self.max_poll_time = 300  # 5 minutes
    
    async def submit_call_log(self, recording_key):
        """Submit a call log to the API and return the response"""
        # Generate random IDs
        external_id = random.randint(10000000, 99999999)
        agent_id = random.randint(10000, 99999)
        prospect_id = random.randint(10000, 99999)
        
        # Build payload
        payload = {
            "external_call_log": {
                "external_id": external_id,
                "meta": json.dumps({
                    "call_duration": 320, 
                    "call_direction": "inbound", 
                    "call_status": "completed"
                }),
                "agent_id": agent_id,
                "prospect_id": prospect_id,
                "recording_key": recording_key,
                "recording_type": 0,
                "unix_call_timestamp": int(time.time() - 3600)  # 1 hour ago
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.create_endpoint, json=payload) as response:
                    # Check for success status codes (200 OK or 201 Created)
                    if response.status in [200, 201]:
                        result = await response.json()
                        if result.get("success"):
                            return True, result.get("data").get("id")
                        return False, f"API error: {json.dumps(result)}"
                    else:
                        return False, f"HTTP error: {response.status}"
        except Exception as e:
            return False, f"Error submitting call log: {str(e)}"
    
    async def poll_results(self, call_id, status_container=None, progress_bar=None):
        """Poll for results until they're available or timeout"""
        max_attempts = self.max_poll_time // self.poll_interval
        attempt = 0
        
        # Track analysis stages
        analysis_stages = {
            "Started": 20,
            "Transcription": 40,
            "Base Analysis": 60,
            "False Promise Analysis": 80,
            "Abusive/Bad Call Analysis": 100
        }
        
        current_stage = "Started"
        if progress_bar:
            progress_bar.progress(analysis_stages[current_stage])
        
        while attempt < max_attempts:
            status_message = f"Processing call analysis: {current_stage}..."
            if status_container:
                status_container.info(status_message)
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.result_endpoint}/{call_id}") as response:
                        if response.status in [200, 201]:
                            result = await response.json()
                            
                            if result.get("success") and result.get("data"):
                                data = result.get("data")
                                meta = data.get("meta", {})
                                
                                # Update progress based on available data
                                if meta:
                                    if "base_analysis" in meta and current_stage in ["Started", "Transcription"]:
                                        current_stage = "Base Analysis"
                                        if progress_bar:
                                            progress_bar.progress(analysis_stages[current_stage])
                                    
                                    if "false_promise" in meta and current_stage in ["Started", "Transcription", "Base Analysis"]:
                                        current_stage = "False Promise Analysis"
                                        if progress_bar:
                                            progress_bar.progress(analysis_stages[current_stage])
                                    
                                    if "abusive_bad_call" in meta and current_stage != "Abusive/Bad Call Analysis":
                                        current_stage = "Abusive/Bad Call Analysis"
                                        if progress_bar:
                                            progress_bar.progress(analysis_stages[current_stage])
                                    
                                # Check if meta contains all necessary data
                                if meta and meta.get("false_promise") and meta.get("abusive_bad_call"):
                                    # Get transcription if available
                                    transcription = result.get("transcription", "")
                                    return True, data, transcription
                                
                                # If we have partial data, continue polling
                                if meta:
                                    pass  # Continue polling - status message already updated above
                                    
                            elif not result.get("success"):
                                return False, f"API error: {json.dumps(result)}", ""
                        else:
                            pass
                            # if status_container:
                            #     status_container.warning(f"HTTP error: {response.status}, retrying...")
                
                attempt += 1
                await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                return False, f"Error polling results: {str(e)}", ""
        
        return False, "Maximum polling time reached without complete results", ""

async def process_audio_file_with_s3(audio_file, status_container=None, progress_bar=None):
    """Process an audio file by uploading"""
    try:
        # Show loading status
        use_internal_ui = status_container is None
        if use_internal_ui:
            status_container = st.empty()
            progress_bar = st.progress(0)
        
        # Save a local copy first
        local_filename, local_path = save_local_audio_copy(audio_file)
        if not local_filename:
            status_container.error("Failed to save local copy of audio file")
        
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save the uploaded file to the temporary directory
            status_container.info("Preparing audio file...")
            if progress_bar:
                progress_bar.progress(5)
            
            temp_path = os.path.join(temp_dir, audio_file.name)
            with open(temp_path, 'wb') as f:
                f.write(audio_file.getbuffer())
            
            # Upload to S3
            status_container.info("Uploading...")
            if progress_bar:
                progress_bar.progress(10)
            
            s3_service = S3Service()
            s3_key = s3_service.upload_file(temp_path)
            
            if not s3_key:
                status_container.error("Failed to upload file")
                return False, None, "", local_filename
            
            # Submit to API
            status_container.info("Submitting...")
            if progress_bar:
                progress_bar.progress(15)
            
            api_service = APIService()
            success, call_id = await api_service.submit_call_log(s3_key)
            
            if not success:
                status_container.error(f"Failed to submit: {call_id}")
                return False, None, "", local_filename
            
            # Poll for results
            status_container.info("Starting analysis...")
            success, result, transcription = await api_service.poll_results(call_id, status_container, progress_bar)
            
            if success:
                if progress_bar:
                    progress_bar.progress(100)
                # status_container.success(f"Analysis completed successfully!")
                return True, result, transcription, local_filename
            else:
                status_container.error(f"Analysis failed: {result}")
                return False, None, "", local_filename
                
    except Exception as e:
        if status_container:
            status_container.error(f"Error processing audio: {str(e)}")
        return False, None, "", None

def format_false_promises(false_promise_data):
    """Format false promises data for display"""
    if not false_promise_data or not false_promise_data.get("false_promises"):
        return ["No false promises detected in the conversation."]
    
    formatted_sections = []
    false_promises = false_promise_data.get("false_promises", [])
    
    for promise in false_promises:
        phrase = promise.get("phrase", "")
        reason = promise.get("reason", "")
        confidence = promise.get("confidence", 0)
        timestamp = promise.get("timestamp", "00:00:00")
        
        # Determine severity level and styling
        if confidence >= 7:
            severity = "🔴 High Severity"
            color = "red"
        elif confidence >= 4:
            severity = "🟡 Medium Severity"
            color = "orange"
        else:
            severity = "🟢 Low Severity"
            color = "green"
        
        # Create formatted HTML section
        section = f"""
        <div style="padding: 1rem; margin: 1rem 0; border-radius: 8px; border: 1px solid {color};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <h3 style="margin: 0; color: {color};">{severity}</h3>
                <span style="background-color: {color}; color: white; padding: 0.25rem 0.5rem; border-radius: 4px;">
                    Confidence: {confidence}/10
                </span>
            </div>
            <div style="margin: 1rem 0;">
                <p style="font-weight: bold;">Statement:</p>
                <p style="margin-left: 1rem; font-style: italic;">"{phrase}"</p>
            </div>
            <div style="margin: 0.5rem 0;">
                <p style="font-weight: bold;">Timestamp:</p>
                <p style="margin-left: 1rem;">{timestamp}</p>
            </div>
            <div>
                <p style="font-weight: bold;">Reason:</p>
                <p style="margin-left: 1rem;">{reason}</p>
            </div>
        </div>
        """
        formatted_sections.append(section)
    
    return formatted_sections

def format_bad_phrases(abusive_bad_call_data):
    """Format bad phrases data for display"""
    if not abusive_bad_call_data:
        return ["No bad phrases detected in the conversation."]
    
    formatted_sections = []
    
    # Handle abusive phrase if present
    abusive_phrase = abusive_bad_call_data.get("abusive_phrase")
    if abusive_phrase:
        abusive_timestamp = abusive_bad_call_data.get("abusive_timestamp", "00:00:00")
        # Abusive phrases are automatically high severity
        section = f"""
        <div style="padding: 1rem; margin: 1rem 0; border-radius: 8px; border: 1px solid red;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <h3 style="margin: 0; color: red;">🔴 Abusive Language</h3>
                <span style="background-color: red; color: white; padding: 0.25rem 0.5rem; border-radius: 4px;">
                    High Severity
                </span>
            </div>
            <div style="margin: 1rem 0;">
                <p style="font-weight: bold;">Phrase:</p>
                <p style="margin-left: 1rem; font-style: italic;">"{abusive_phrase}"</p>
            </div>
            <div>
                <p style="font-weight: bold;">Timestamp:</p>
                <p style="margin-left: 1rem;">{abusive_timestamp}</p>
            </div>
        </div>
        """
        formatted_sections.append(section)
    
    # Handle bad call phrase if present
    bad_call_phrase = abusive_bad_call_data.get("bad_call_phrase")
    if bad_call_phrase:
        bad_call_reason = abusive_bad_call_data.get("bad_call_reason", "")
        bad_call_timestamp = abusive_bad_call_data.get("bad_call_timestamp", "00:00:00")
        bad_call_confidence = abusive_bad_call_data.get("bad_call_confidence", 0)
        
        # Determine severity based on confidence
        if bad_call_confidence >= 7:
            severity = "🔴 High Severity"
            color = "red"
        elif bad_call_confidence >= 4:
            severity = "🟡 Medium Severity"
            color = "orange"
        else:
            severity = "🟢 Low Severity"
            color = "green"
        
        section = f"""
        <div style="padding: 1rem; margin: 1rem 0; border-radius: 8px; border: 1px solid {color};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <h3 style="margin: 0; color: {color};">{severity}</h3>
                <span style="background-color: {color}; color: white; padding: 0.25rem 0.5rem; border-radius: 4px;">
                    Confidence: {bad_call_confidence}/10
                </span>
            </div>
            <div style="margin: 1rem 0;">
                <p style="font-weight: bold;">Phrase:</p>
                <p style="margin-left: 1rem; font-style: italic;">"{bad_call_phrase}"</p>
            </div>
            <div style="margin: 0.5rem 0;">
                <p style="font-weight: bold;">Timestamp:</p>
                <p style="margin-left: 1rem;">{bad_call_timestamp}</p>
            </div>
            <div>
                <p style="font-weight: bold;">Reason:</p>
                <p style="margin-left: 1rem;">{bad_call_reason}</p>
            </div>
        </div>
        """
        formatted_sections.append(section)
    
    if not formatted_sections:
        return ["No bad phrases or abusive language detected in the conversation."]
    
    return formatted_sections 