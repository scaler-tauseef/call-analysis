# Motion Sales Call Analysis

This application provides a web interface for analyzing sales calls to detect false promises and problematic language. It offers two modes of analysis:

1. **Local Analysis**: Processes audio files locally using OpenAI GPT models
2. **S3 + API Analysis**: Uploads audio to S3 and uses an external API for analysis

## Features

- Upload audio files in various formats (MP3, WAV, M4A)
- Detect false promises made during sales calls
- Identify abusive language and bad call practices
- Display results with severity ratings and detailed explanations
- Download analysis results as JSON files

## Setup

### Prerequisites

- Python 3.8 or higher
- AWS account with S3 access (for S3 + API mode)
- OpenAI API key

### Installation

1. Clone this repository:
   ```
   git clone <repository-url>
   cd call-analysis
   ```

2. Create a virtual environment and activate it:
   ```
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file based on the `.env.sample` template:
   ```
   cp .env.sample .env
   ```

5. Edit the `.env` file and add your credentials:
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `AWS_ACCESS_KEY_ID`: Your AWS access key ID
   - `AWS_SECRET_ACCESS_KEY`: Your AWS secret access key
   - `AWS_REGION`: AWS region (default: us-west-2)

### Running the Application

Start the Streamlit server:
```
streamlit run app.py
```

The application will be available at http://localhost:8501

## Usage

### Local Analysis Mode

1. Select the "Local Analysis" tab
2. Upload an audio file using the file uploader
3. Click "Analyze Call Locally"
4. View the analysis results in the "False Promises" and "Bad Phrases" tabs
5. Download the transcription or analysis results using the download buttons

### S3 + API Analysis Mode

1. Select the "S3 + API Analysis" tab
2. Upload an audio file using the file uploader
3. Click "Analyze with S3 + API"
4. The application will:
   - Upload the file to S3 in the `external-tenants-call-analysis/call-recordings/development/` bucket
   - Send the S3 file path to the external API for analysis
   - Poll for results until analysis is complete
5. View the analysis results in the "False Promises" and "Bad Call Phrases" tabs
6. Download the complete analysis using the download button

## Data Flow (S3 + API Mode)

1. Audio file is uploaded to the application
2. File is saved to a temporary location
3. File is uploaded to S3 bucket
4. API request is sent with the S3 file path
5. Application polls the API until results are available
6. Results are displayed in the interface

## API Reference

The external API uses the following endpoints:

- Create log: `https://11.staging.sclr.ac/external_call_logs/v1/tenant_motion/create`
- Get results: `https://11.staging.sclr.ac/external_call_logs/v1/tenant_motion/result/<id>`

## Troubleshooting

- If the application fails to connect to S3, check your AWS credentials in the `.env` file
- If you get OpenAI API errors, check your API key and ensure you have sufficient credits
- For audio processing issues, ensure your audio files are in a compatible format 