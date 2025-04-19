import os
import tempfile
import openai
from dotenv import load_dotenv
import streamlit as st
import asyncio
import aiohttp
import time
import random
from typing import Dict, Any, Optional, List
import os.path
import json
from prompts import FALSE_PROMISE_PROMPT, BAD_CALL_PROMPT

# Load environment variables
load_dotenv()

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

class TranscriptionService:
    def __init__(self):
        self.base_url = "https://fast-transcriber.sales-copilot.scaler.com"
        #self.base_url = "http://motion-transcriber-service.us-west-2.elasticbeanstalk.com"
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
                            status_container.info(f"Processing audio...")
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

        messages = [
            {"role": "system", "content": FALSE_PROMISE_PROMPT},
            {"role": "user", "content": transcription}
        ]

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.1,
            response_format={ "type": "json_object" }
        )

        return response.choices[0].message.content

    except Exception as e:
        st.error(f"Error during analysis: {str(e)}")
        return None

def analyze_bad_phrases(transcription):
    """
    Analyze transcription using OpenAI's GPT model to detect bad and abusive phrases
    """
    try:
        if not transcription:
            raise ValueError("No transcription provided for analysis")

        messages = [
            {"role": "system", "content": BAD_CALL_PROMPT},
            {"role": "user", "content": transcription}
        ]

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.1,
            response_format={ "type": "json_object" }
        )

        return response.choices[0].message.content

    except Exception as e:
        st.error(f"Error during bad phrase analysis: {str(e)}")
        return None

def format_analysis(analysis_text):
    """
    Format the analysis results for display
    """
    try:
        analysis = json.loads(analysis_text)
        formatted_sections = []
        
        if not analysis.get('false_promises'):
            return ["No false promises detected in the conversation."]
            
        # Sort false promises by confidence score
        false_promises = sorted(
            analysis['false_promises'],
            key=lambda x: x['confidence'],
            reverse=True
        )
        
        for promise in false_promises:
            confidence = promise['confidence']
            
            # Determine severity level and styling
            if confidence >= 80:
                severity = "🔴 High Severity"
                color = "red"
            elif confidence >= 50:
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
                        Confidence: {confidence}%
                    </span>
                </div>
                <div style="margin: 1rem 0;">
                    <p style="font-weight: bold;">Statement:</p>
                    <p style="margin-left: 1rem; font-style: italic;">"{promise['statement']}"</p>
                </div>
                <div>
                    <p style="font-weight: bold;">Reason:</p>
                    <p style="margin-left: 1rem;">{promise['reason']}</p>
                </div>
            </div>
            """
            formatted_sections.append(section)
            
        return formatted_sections

    except json.JSONDecodeError:
        return ["Error: Could not parse analysis results."]
    except Exception as e:
        return [f"Error formatting analysis: {str(e)}"]

def format_bad_phrases_analysis(analysis_text):
    """
    Format the bad phrases analysis results for display
    """
    try:
        analysis = json.loads(analysis_text)
        formatted_sections = []
        
        if not analysis.get('bad_phrases'):
            return ["No bad or abusive phrases detected in the conversation."]
            
        # Sort bad phrases by severity or confidence score if available
        bad_phrases = sorted(
            analysis['bad_phrases'],
            key=lambda x: x.get('severity', 0),
            reverse=True
        )
        
        for phrase in bad_phrases:
            severity = phrase.get('severity', 50)
            
            # Determine severity level and styling
            if severity >= 80:
                severity_label = "🔴 High Severity"
                color = "red"
            elif severity >= 50:
                severity_label = "🟡 Medium Severity"
                color = "orange"
            else:
                severity_label = "🟢 Low Severity"
                color = "green"
                
            # Create formatted HTML section
            section = f"""
            <div style="padding: 1rem; margin: 1rem 0; border-radius: 8px; border: 1px solid {color};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <h3 style="margin: 0; color: {color};">{severity_label}</h3>
                    <span style="background-color: {color}; color: white; padding: 0.25rem 0.5rem; border-radius: 4px;">
                        Severity: {severity}%
                    </span>
                </div>
                <div style="margin: 1rem 0;">
                    <p style="font-weight: bold;">Phrase:</p>
                    <p style="margin-left: 1rem; font-style: italic;">"{phrase['phrase']}"</p>
                </div>
                <div>
                    <p style="font-weight: bold;">Reason:</p>
                    <p style="margin-left: 1rem;">{phrase['reason']}</p>
                </div>
            </div>
            """
            formatted_sections.append(section)
            
        return formatted_sections

    except json.JSONDecodeError:
        return ["Error: Could not parse bad phrases analysis results."]
    except Exception as e:
        return [f"Error formatting bad phrases analysis: {str(e)}"] 