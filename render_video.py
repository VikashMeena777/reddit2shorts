#!/usr/bin/env python3
"""
Reddit Shorts Video Renderer - FULLY AUTOMATED (FREE)
======================================================
Uses edge-tts for FREE text-to-speech, no API keys needed!

Triggered by GitHub Actions with payload:
- youtube_video_id: YouTube video ID for gameplay
- youtube_url: Full YouTube URL  
- story_title: Title for the short
- script: The script text for TTS and subtitles
"""

import os
import sys
import json
import asyncio
import argparse
import subprocess
import tempfile
from pathlib import Path

# Google Drive imports for output upload
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Edge TTS for FREE voice generation
import edge_tts

# --- Configuration ---
OUTPUT_FOLDER_ID = os.environ.get('OUTPUT_FOLDER_ID', 'YOUR_OUTPUT_FOLDER_ID')
SCOPES = ['https://www.googleapis.com/auth/drive']

# Edge TTS Voice - Natural sounding male voice
VOICE = "en-US-ChristopherNeural"  # Deep male voice, great for stories
# Other options:
# "en-US-GuyNeural" - Casual male
# "en-US-JennyNeural" - Female
# "en-GB-RyanNeural" - British male

# Subtitle styling
SUBTITLE_FONT = "Impact"
SUBTITLE_FONTSIZE = 55
SUBTITLE_PRIMARY_COLOR = "&H00FFFFFF"  # White
SUBTITLE_OUTLINE_COLOR = "&H00000000"  # Black
SUBTITLE_OUTLINE_WIDTH = 4


def get_drive_service():
    """Authenticate with Google Drive using service account."""
    creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    
    if creds_json:
        creds_info = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(
            creds_info, scopes=SCOPES
        )
    else:
        credentials = service_account.Credentials.from_service_account_file(
            'service_account.json', scopes=SCOPES
        )
    
    return build('drive', 'v3', credentials=credentials)


async def generate_tts(script: str, output_path: str) -> str:
    """Generate text-to-speech using Edge TTS (FREE)."""
    print(f"  Using voice: {VOICE}")
    
    communicate = edge_tts.Communicate(script, VOICE)
    await communicate.save(output_path)
    
    size_kb = os.path.getsize(output_path) / 1024
    print(f"  Generated: {output_path} ({size_kb:.1f} KB)")
    return output_path


def download_pexels_video(video_url: str, output_path: str) -> str:
    """Download a video from Pexels direct URL - no auth needed!"""
    import requests
    
    print(f"  Downloading: {video_url[:60]}...")
    
    response = requests.get(video_url, stream=True)
    response.raise_for_status()
    
    # Get total size for progress
    total_size = int(response.headers.get('content-length', 0))
    
    with open(output_path, 'wb') as f:
        downloaded = 0
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                percent = (downloaded / total_size) * 100
                print(f"\r  Progress: {percent:.1f}%", end='', flush=True)
    
    print()  # New line after progress
    
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  Downloaded: {output_path} ({size_mb:.1f} MB)")
    return output_path


def upload_to_drive(service, file_path: str, folder_id: str, filename: str) -> dict:
    """Upload a file to Google Drive."""
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)
    
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name, webViewLink'
    ).execute()
    
    return file


def get_audio_duration(audio_path: str) -> float:
    """Get the duration of an audio file using ffprobe."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def get_video_dimensions(video_path: str) -> tuple:
    """Get video width and height."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'csv=p=0',
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    width, height = map(int, result.stdout.strip().split(','))
    return width, height


def generate_subtitles_from_script(script: str, audio_duration: float, output_dir: str) -> str:
    """Generate ASS subtitles from the script text with estimated timing."""
    import re
    
    ass_path = os.path.join(output_dir, "subtitles.ass")
    
    # Split script into sentences
    sentences = re.split(r'(?<=[.!?])\s+', script)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        sentences = [script]
    
    # Calculate time per sentence
    time_per_sentence = audio_duration / len(sentences)
    
    # ASS Header
    ass_content = f"""[Script Info]
Title: Reddit Story Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{SUBTITLE_FONT},{SUBTITLE_FONTSIZE},{SUBTITLE_PRIMARY_COLOR},&H000000FF,{SUBTITLE_OUTLINE_COLOR},&H00000000,-1,0,0,0,100,100,0,0,1,{SUBTITLE_OUTLINE_WIDTH},0,2,50,50,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    current_time = 0.0
    for sentence in sentences:
        # Split long sentences into chunks of 6-8 words
        words = sentence.split()
        chunk_size = 6
        
        sentence_duration = time_per_sentence
        time_per_chunk = sentence_duration / max(1, len(words) / chunk_size)
        
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)
            
            start_str = format_ass_time(current_time)
            end_time = min(current_time + time_per_chunk, audio_duration)
            end_str = format_ass_time(end_time)
            
            # Clean and format text
            clean_text = chunk_text.upper().replace('\\', '').replace('{', '').replace('}', '')
            if clean_text:
                ass_content += f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{clean_text}\n"
            
            current_time = end_time
    
    with open(ass_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)
    
    return ass_path


def format_ass_time(seconds: float) -> str:
    """Format seconds to ASS time format (H:MM:SS.CC)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def render_video(audio_path: str, video_path: str, subtitle_path: str, output_path: str, duration: float):
    """Render the final vertical video using FFmpeg."""
    print("\n  Rendering final video...")
    
    # Get video dimensions for smart cropping
    width, height = get_video_dimensions(video_path)
    print(f"  Source video: {width}x{height}")
    
    # Calculate crop for 9:16 aspect ratio
    target_ratio = 9 / 16
    source_ratio = width / height
    
    if source_ratio > target_ratio:
        new_width = int(height * target_ratio)
        crop_filter = f"crop={new_width}:{height}"
    else:
        new_height = int(width / target_ratio)
        crop_filter = f"crop={width}:{new_height}"
    
    # Escape subtitle path for FFmpeg
    sub_path_escaped = subtitle_path.replace('\\', '/').replace(':', '\\:').replace("'", "\\'")
    
    # FFmpeg command
    cmd = [
        'ffmpeg', '-y',
        '-stream_loop', '-1',
        '-i', video_path,
        '-i', audio_path,
        '-filter_complex',
        f"[0:v]{crop_filter},scale=1080:1920,setsar=1,ass='{sub_path_escaped}'[v]",
        '-map', '[v]',
        '-map', '1:a',
        '-t', str(duration),
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-movflags', '+faststart',
        output_path
    ]
    
    print(f"  Running FFmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"  FFmpeg Error: {result.stderr}")
        raise RuntimeError("FFmpeg failed")
    
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  Output: {output_path} ({size_mb:.1f} MB)")
    
    return output_path


async def main_async(payload):
    """Async main function for edge-tts."""
    print("=" * 60)
    print("REDDIT SHORTS VIDEO RENDERER (FREE TTS)")
    print("=" * 60)
    print(f"Title: {payload['story_title']}")
    print(f"Video: Pexels #{payload.get('video_id', 'N/A')}")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Generate TTS using Edge TTS (FREE!)
        print("\n[1/5] Generating voiceover with Edge TTS (FREE)...")
        audio_path = str(temp_path / "audio.mp3")
        await generate_tts(payload['script'], audio_path)
        
        # Get audio duration
        duration = get_audio_duration(audio_path)
        print(f"  Audio duration: {duration:.1f} seconds")
        
        # Download Pexels video (direct URL - no auth needed!)
        print("\n[2/5] Downloading video from Pexels...")
        video_path = str(temp_path / "background.mp4")
        video_path = download_pexels_video(payload['video_url'], video_path)
        
        # Generate subtitles from script
        print("\n[3/5] Generating subtitles...")
        script = payload.get('script', 'Story content')
        subtitle_path = generate_subtitles_from_script(script, duration, str(temp_path))
        print(f"  Created: {subtitle_path}")
        
        # Render final video
        print("\n[4/5] Rendering final video...")
        safe_title = ''.join(c for c in payload['story_title'][:25] if c.isalnum() or c == ' ').replace(' ', '_')
        output_filename = f"short_{safe_title}_{payload['timestamp']}.mp4"
        output_path = str(temp_path / output_filename)
        
        render_video(audio_path, video_path, subtitle_path, output_path, duration)
        
        # Upload to Drive
        print("\n[5/5] Uploading to Google Drive...")
        service = get_drive_service()
        result = upload_to_drive(service, output_path, OUTPUT_FOLDER_ID, output_filename)
        
        print("\n" + "=" * 60)
        print("SUCCESS!")
        print("=" * 60)
        print(f"File ID: {result['id']}")
        print(f"Filename: {result['name']}")
        print(f"Link: {result.get('webViewLink', 'N/A')}")
        
        # Output for GitHub Actions
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                f.write(f"file_id={result['id']}\n")
                f.write(f"filename={result['name']}\n")
                f.write(f"web_link={result.get('webViewLink', '')}\n")


def main():
    parser = argparse.ArgumentParser(description='Render Reddit story as vertical short')
    parser.add_argument('--payload', required=True, help='JSON payload from n8n')
    args = parser.parse_args()
    
    payload = json.loads(args.payload)
    asyncio.run(main_async(payload))


if __name__ == '__main__':
    main()
