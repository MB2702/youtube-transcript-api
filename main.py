import os
from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
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

def get_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([entry['text'] for entry in transcript])
    except Exception as e:
        return f"Error fetching transcript: {str(e)}"

def improve_transcript(text):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that improves transcripts by adding proper punctuation and formatting."},
                {"role": "user", "content": f"Please improve this transcript by adding proper punctuation and formatting:\n\n{text}"}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error improving transcript: {str(e)}"

@app.route('/process_youtube', methods=['POST'])
def process_youtube():
    try:
        youtube_url = request.json.get('url')
        if not youtube_url:
            return jsonify({"error": "No YouTube URL provided"}), 400

        video_id = extract_video_id(youtube_url)
        if not video_id:
            return jsonify({"error": "Invalid YouTube URL"}), 400

        transcript = get_transcript(video_id)
        if transcript.startswith("Error"):
            return jsonify({"error": transcript}), 500

        improved_transcript = improve_transcript(transcript)
        if improved_transcript.startswith("Error"):
            return jsonify({"error": improved_transcript}), 500

        return jsonify({"improved_transcript": improved_transcript})

    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/', methods=['GET'])
def home():
    return "YouTube Transcript Processor API is running. Use POST /process_youtube to process a YouTube URL."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)