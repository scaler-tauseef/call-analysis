import sqlite3
import json
import os
import uuid
from datetime import datetime
import base64

# Database file name
DB_FILE = "call_analysis.db"

def init_db():
    """Initialize the database with required tables"""
    # Create the database directory if it doesn't exist
    os.makedirs(os.path.dirname(DB_FILE) if os.path.dirname(DB_FILE) else '.', exist_ok=True)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create analysis table with audio_data column
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS analyses (
        id TEXT PRIMARY KEY,
        filename TEXT,
        upload_time TIMESTAMP,
        transcription TEXT,
        api_result TEXT,
        file_size INTEGER,
        audio_data BLOB,
        audio_type TEXT
    )
    ''')
    
    conn.commit()
    conn.close()

def save_analysis(filename, transcription, api_result, file_size, audio_data, audio_type):
    """Save an analysis to the database with audio data"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Generate a unique ID
    analysis_id = str(uuid.uuid4())
    
    # Convert API result to JSON string
    api_result_json = json.dumps(api_result)
    
    # Get current timestamp
    timestamp = datetime.now().isoformat()
    
    # Insert the analysis with audio data
    cursor.execute(
        "INSERT INTO analyses (id, filename, upload_time, transcription, api_result, file_size, audio_data, audio_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (analysis_id, filename, timestamp, transcription, api_result_json, file_size, audio_data, audio_type)
    )
    
    conn.commit()
    conn.close()
    
    return analysis_id

def get_all_analyses():
    """Get a list of all analyses (without audio data to save memory)"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # This enables column access by name
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, filename, upload_time, file_size FROM analyses ORDER BY upload_time DESC")
    analyses = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return analyses

def get_analysis_by_id(analysis_id):
    """Get a specific analysis by ID including audio data"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # This enables column access by name
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
    analysis = cursor.fetchone()
    
    conn.close()
    
    if analysis:
        result = dict(analysis)
        # Parse JSON string back to dictionary
        result['api_result'] = json.loads(result['api_result'])
        
        # Convert audio data to base64 for display
        if result['audio_data']:
            audio_base64 = base64.b64encode(result['audio_data']).decode('utf-8')
            result['audio_base64'] = audio_base64
        
        return result
    
    return None

def delete_analysis(analysis_id):
    """Delete an analysis by ID"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
    
    conn.commit()
    conn.close()
    
    return cursor.rowcount > 0  # Returns True if a row was deleted 