import os
import time
from flask import Flask, request, jsonify, current_app
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from openai import OpenAI
import youtube_transcript_api
import logging
from logging.handlers import RotatingFileHandler

# Chargement des variables d'environnement
load_dotenv()

app = Flask(__name__)

# Configuration du logging
handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=1)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

# Configuration des APIs
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def extract_video_id(url):
    """Extrait l'ID de la vidéo à partir de différents formats d'URL YouTube."""
    parsed_url = urlparse(url)
    if parsed_url.hostname == 'youtu.be':
        return parsed_url.path[1:]
    if parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
        if parsed_url.path == '/watch':
            p = parse_qs(parsed_url.query)
            return p.get('v', [None])[0]
        if parsed_url.path[:7] == '/embed/':
            return parsed_url.path.split('/')[2]
        if parsed_url.path[:3] == '/v/':
            return parsed_url.path.split('/')[2]
    return None

def get_video_transcript(video_id):
    """Récupère la transcription de la vidéo en utilisant l'API YouTube et youtube_transcript_api."""
    try:
        # Essayez d'abord avec youtube_transcript_api
        transcript = youtube_transcript_api.YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([entry['text'] for entry in transcript]), None
    except youtube_transcript_api.NoTranscriptAvailable:
        current_app.logger.warning(f"No transcript available via youtube_transcript_api for video ID: {video_id}")
        # Si ça échoue, essayez avec l'API YouTube officielle
        try:
            captions = youtube.captions().list(part='snippet', videoId=video_id).execute()
            if 'items' not in captions or len(captions['items']) == 0:
                return None, "No captions available for this video"
            
            caption_id = captions['items'][0]['id']
            subtitle = youtube.captions().download(id=caption_id, tfmt='srt').execute()
            return subtitle.decode('utf-8'), None
        except HttpError as e:
            current_app.logger.error(f"YouTube API error: {e}")
            return None, f"An error occurred: {e}"
    except Exception as e:
        current_app.logger.error(f"Unexpected error in get_video_transcript: {e}")
        return None, f"An unexpected error occurred: {e}"

def improve_transcript_with_openai(transcript):
    """Améliore la transcription en utilisant OpenAI."""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that improves transcripts by adding proper punctuation, formatting, and correcting obvious errors."},
                {"role": "user", "content": f"Please improve this transcript:\n\n{transcript}"}
            ],
            max_tokens=4000  # Ajustez selon vos besoins
        )
        return response.choices[0].message.content
    except Exception as e:
        current_app.logger.error(f"OpenAI API error: {e}")
        return transcript  # Retourne la transcription originale en cas d'erreur

@app.route('/process_youtube', methods=['POST'])
def process_youtube():
    try:
        youtube_url = request.json.get('url')
        if not youtube_url:
            return jsonify({"error": "No YouTube URL provided"}), 400

        video_id = extract_video_id(youtube_url)
        if not video_id:
            return jsonify({"error": "Invalid YouTube URL"}), 400
        
        current_app.logger.info(f"Processing video ID: {video_id}")
        
        transcript, error = get_video_transcript(video_id)
        
        if error:
            return jsonify({"error": error}), 400

        if transcript:
            improved_transcript = improve_transcript_with_openai(transcript)
            return jsonify({"transcript": improved_transcript})
        else:
            return jsonify({"error": "Failed to retrieve transcript"}), 500

    except Exception as e:
        current_app.logger.error(f"Unexpected error in process_youtube: {str(e)}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/', methods=['GET'])
def home():
    return "YouTube Transcript Processor API is running. Use POST /process_youtube to process a YouTube URL."

if __name__ == '__main__':
    app.run(debug=True)