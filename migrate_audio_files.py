import os
import sqlite3
import shutil
import glob

# Connect to the database
conn = sqlite3.connect('history.db')
cursor = conn.cursor()

# Ensure uploads directory exists
uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
if not os.path.exists(uploads_dir):
    os.makedirs(uploads_dir)

# Get all audio filenames from the database
cursor.execute("SELECT id, audio_filename FROM history")
db_entries = cursor.fetchall()

print(f"Found {len(db_entries)} entries in database")

# Move the files to the uploads directory
for entry_id, filename in db_entries:
    if not filename:
        continue
        
    source_path = os.path.join(os.path.dirname(__file__), filename)
    target_path = os.path.join(uploads_dir, filename)
    
    if os.path.exists(source_path):
        print(f"Moving {filename} to uploads folder...")
        shutil.move(source_path, target_path)
        print(f"Moved {filename}")
    else:
        if os.path.exists(target_path):
            print(f"Audio file {filename} already exists in uploads folder")
        else:
            print(f"Warning: Audio file {filename} not found in root or uploads folder")

# Look for any history_*.mp3, history_*.wav, or history_*.m4a files in root and move them
audio_files_moved = []
for ext in ['.mp3', '.wav', '.m4a']:
    for filename in os.listdir(os.path.dirname(__file__)):
        if filename.startswith('history_') and filename.endswith(ext):
            source_path = os.path.join(os.path.dirname(__file__), filename)
            target_path = os.path.join(uploads_dir, filename)
            
            if os.path.exists(source_path) and not os.path.exists(target_path):
                print(f"Moving {filename} to uploads folder...")
                shutil.move(source_path, target_path)
                print(f"Moved {filename}")
                audio_files_moved.append(filename)

# Check for any potential database entries with missing audio_filename
print("\nChecking for database entries with missing audio_filename...")
# Find all audio files in uploads directory
uploaded_files = os.listdir(uploads_dir)
history_audio_files = [f for f in uploaded_files if f.startswith('history_')]

# Find entries with empty audio_filename that might have a corresponding file
cursor.execute("SELECT id FROM history WHERE audio_filename = '' OR audio_filename IS NULL")
empty_audio_entries = cursor.fetchall()

updates_made = 0
for entry_id_tuple in empty_audio_entries:
    entry_id = entry_id_tuple[0]
    # Look for a matching history_{id}.* file
    matching_files = []
    for ext in ['.mp3', '.wav', '.m4a']:
        pattern = f"history_{entry_id}{ext}"
        if pattern in history_audio_files:
            matching_files.append(pattern)
    
    if matching_files:
        # Update the database with the first matching file
        filename = matching_files[0]
        cursor.execute(
            "UPDATE history SET audio_filename = ? WHERE id = ?",
            (filename, entry_id)
        )
        updates_made += 1
        print(f"Updated entry ID {entry_id} with audio file {filename}")

if updates_made > 0:
    conn.commit()
    print(f"Updated {updates_made} database entries with audio filenames")
else:
    print("No database updates needed")

print("\nMigration completed!")
conn.close() 