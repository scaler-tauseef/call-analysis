# Sales Call Analysis

A Streamlit application that analyzes sales call recordings for potential false promises and concerning patterns. The application uses OpenAI's Whisper model for transcription and GPT-4 for analysis.

## Features

- Audio file upload (supports MP3, WAV, M4A)
- Automatic transcription of Hindi audio to English
- Analysis of sales conversations for false promises
- Downloadable transcription and analysis results

## Requirements

- Python 3.8+
- OpenAI API key
- Streamlit
- PyTorch
- Whisper

## Installation

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file and add your OpenAI API key:
   ```
   OPENAI_API_KEY=your_api_key_here
   ```

## Usage

1. Start the Streamlit app:
   ```bash
   streamlit run app.py
   ```
2. Upload an audio file
3. Click "Analyze Call"
4. View the transcription and analysis results
5. Download the results if needed

## Project Structure

- `app.py`: Main Streamlit application
- `utils.py`: Utility functions for transcription and analysis
- `requirements.txt`: Project dependencies
- `.env`: Environment variables (not tracked in git)

## Note

The application is optimized for Hindi to English transcription using Whisper's "medium" model, which provides a good balance of accuracy and performance on systems with 8GB RAM. 