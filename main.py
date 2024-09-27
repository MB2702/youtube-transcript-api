import os
import time
from flask import Flask, request, jsonify, current_app
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
import re
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Set up OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

def extract_video_id(url):
    # Extract video ID from YouTube URL
    video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if video_id_match:
        return video_id_match.group(1)
    return None

def get_transcript_with_retry(video_id, max_retries=3):
    for attempt in range(max_retries):
        try:
            current_app.logger.info(f"Attempt {attempt + 1} to fetch transcript for video {video_id}")
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            return " ".join([entry['text'] for entry in transcript])
        except TranscriptsDisabled:
            current_app.logger.error(f"Transcripts are disabled for video {video_id}")
            raise Exception("Transcripts are disabled for this video")
        except Exception as e:
            current_app.logger.error(f"Error fetching transcript on attempt {attempt + 1}: {str(e)}")
            if attempt == max_retries - 1:
                raise Exception(f"Error fetching transcript after {max_retries} attempts: {str(e)}")
            time.sleep(1)  # Court délai entre les tentatives
    raise Exception("Max retries reached")

def improve_transcript(text):
    try:
        current_app.logger.info("Starting transcript improvement with OpenAI")
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that improves transcripts by adding proper punctuation and formatting."},
                {"role": "user", "content": f"Please improve this transcript by adding proper punctuation and formatting:\n\n{text}"}
            ]
        )
        current_app.logger.info("Transcript improvement completed successfully")
        return response.choices[0].message.content
    except openai.error.RateLimitError:
        current_app.logger.error("OpenAI API rate limit reached")
        raise Exception("OpenAI API rate limit reached. Please try again later.")
    except Exception as e:
        current_app.logger.error(f"Error improving transcript: {str(e)}")
        raise Exception(f"Error improving transcript: {str(e)}")

@app.route('/process_youtube', methods=['POST'])
def process_youtube():
    try:
        current_app.logger.info("Received request")
        youtube_url = request.json.get('url')
        current_app.logger.info(f"Processing URL: {youtube_url}")
        
        if not youtube_url:
            current_app.logger.warning("No YouTube URL provided")
            return jsonify({"error": "No YouTube URL provided"}), 400

        video_id = extract_video_id(youtube_url)
        current_app.logger.info(f"Extracted video ID: {video_id}")
        
        if not video_id:
            current_app.logger.warning("Invalid YouTube URL")
            return jsonify({"error": "Invalid YouTube URL"}), 400

        current_app.logger.info("Fetching transcript")
        transcript = get_transcript_with_retry(video_id)
        current_app.logger.info("Transcript fetched successfully")

        current_app.logger.info("Improving transcript")
        improved_transcript = improve_transcript(transcript)
        current_app.logger.info("Transcript improved successfully")

        return jsonify({"improved_transcript": improved_transcript})

    except Exception as e:
        current_app.logger.error(f"An error occurred: {str(e)}")
        error_message = str(e)
        if "Too Many Requests" in error_message or "rate limit" in error_message.lower():
            return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
        elif "transcripts are disabled" in error_message.lower():
            return jsonify({"error": "Transcripts are not available for this video"}), 400
        else:
            return jsonify({"error": f"An unexpected error occurred: {error_message}"}), 500

@app.route('/', methods=['GET'])
def home():
    return "YouTube Transcript Processor API is running. Use POST /process_youtube to process a YouTube URL."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)