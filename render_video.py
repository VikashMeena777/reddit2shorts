#!/usr/bin/env python3
"""
Reddit Shorts Video Renderer - FULLY AUTOMATED (FREE)
======================================================
Uses edge-tts for FREE text-to-speech, no API keys needed!
Uploads to Catbox.moe for FREE file hosting with direct links!

Triggered by GitHub Actions with payload:
- video_url: Pexels video URL
- video_id: Pexels video ID
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
import shutil
import requests
from pathlib import Path

# Edge TTS for FREE voice generation
import edge_tts

# --- Configuration ---
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


def upload_to_catbox(file_path: str) -> str:
    """Upload a file to Catbox.moe and return the direct download URL."""
    print(f"  Uploading to Catbox.moe...")
    
    url = "https://catbox.moe/user/api.php"
    
    with open(file_path, 'rb') as f:
        files = {
            'fileToUpload': (os.path.basename(file_path), f, 'video/mp4')
        }
        data = {
            'reqtype': 'fileupload'
        }
        
        response = requests.post(url, files=files, data=data)
        response.raise_for_status()
        
        # Catbox returns the direct URL as plain text
        download_url = response.text.strip()
        
        if not download_url.startswith('https://'):
            raise RuntimeError(f"Catbox upload failed: {download_url}")
        
        print(f"  Uploaded: {download_url}")
        return download_url


async def generate_tts(script: str, output_path: str) -> str:
    """Generate text-to-speech using Edge TTS (FREE)."""
    print(f"  Using voice: {VOICE}")
    
    communicate = edge_tts.Communicate(script, VOICE)
    await communicate.save(output_path)
    
    size_kb = os.path.getsize(output_path) / 1024
    print(f"  Generated: {output_path} ({size_kb:.1f} KB)")
    return output_path


def download_video(video_url: str, output_path: str) -> str:
    """Download a video from Google Drive (via rclone) or direct URL."""
    print(f"  Downloading: {video_url[:60]}...")
    
    # Check if it's a Google Drive link
    if 'drive.google.com' in video_url:
        # Extract file ID from various Google Drive URL formats
        import re
        
        # Match patterns like /d/FILE_ID/ or id=FILE_ID
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', video_url)
        if not match:
            match = re.search(r'id=([a-zA-Z0-9_-]+)', video_url)
        
        if not match:
            raise RuntimeError(f"Could not extract file ID from Google Drive URL: {video_url}")
        
        file_id = match.group(1)
        print(f"  Google Drive file ID: {file_id}")
        
        # Use rclone to download from Google Drive
        # rclone must be configured with 'gdrive' remote
        rclone_path = f"vk889900:{{{{ id={file_id} }}}}"
        
        cmd = [
            'rclone', 'copyto',
            '--drive-shared-with-me',
            f':drive,team_drive=:{{id={file_id}}}',
            output_path
        ]
        
        # Alternative simpler approach using rclone backend command
        cmd = [
            'rclone', 'copyurl',
            f'https://drive.google.com/uc?export=download&id={file_id}',
            output_path,
            '--auto-filename=false'
        ]
        
        # Best approach: use rclone with Google Drive backend
        cmd = [
            'rclone', 'copy',
            f'vk889900:{{id={file_id}}}',
            os.path.dirname(output_path),
            '--drive-acknowledge-abuse',
            '-v'
        ]
        
        print(f"  Running rclone...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"  rclone error: {result.stderr}")
            # Try alternative: direct download with confirmation bypass
            print("  Trying direct download with gdown...")
            try:
                import gdown
                gdown.download(id=file_id, output=output_path, quiet=False)
            except ImportError:
                # Fall back to requests with cookies
                session = requests.Session()
                response = session.get(f'https://drive.google.com/uc?id={file_id}&export=download')
                
                # Check for confirmation token
                for key, value in response.cookies.items():
                    if key.startswith('download_warning'):
                        response = session.get(
                            f'https://drive.google.com/uc?id={file_id}&export=download&confirm={value}',
                            stream=True
                        )
                        break
                
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
        else:
            # rclone downloads to a file named by the original filename
            # We need to rename it to our expected output path
            downloaded_files = os.listdir(os.path.dirname(output_path))
            for f in downloaded_files:
                if f.endswith('.mp4') and f != os.path.basename(output_path):
                    src = os.path.join(os.path.dirname(output_path), f)
                    shutil.move(src, output_path)
                    break
    else:
        # Direct URL download (Catbox, etc.)
        response = requests.get(video_url, stream=True)
        response.raise_for_status()
        
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
    print("REDDIT SHORTS VIDEO RENDERER (FREE)")
    print("=" * 60)
    print(f"Title: {payload['story_title']}")
    print(f"Video: {payload.get('video_name', 'gameplay')}")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Generate TTS using Edge TTS (FREE!)
        print("\n[1/5] Generating voiceover with Edge TTS (FREE)...")
        audio_path = str(temp_path / "audio.mp3")
        await generate_tts(payload['script'], audio_path)
        
        # Get audio duration
        duration = get_audio_duration(audio_path)
        print(f"  Audio duration: {duration:.1f} seconds")
        
        # Download video from Google Drive or direct URL
        print("\n[2/5] Downloading background video...")
        video_path = str(temp_path / "background.mp4")
        video_path = download_video(payload['video_url'], video_path)
        
        # Generate subtitles from script
        print("\n[3/5] Generating subtitles...")
        script = payload.get('script', 'Story content')
        subtitle_path = generate_subtitles_from_script(script, duration, str(temp_path))
        print(f"  Created: {subtitle_path}")
        
        # Render final video
        print("\n[4/5] Rendering final video...")
        safe_title = ''.join(c for c in payload['story_title'][:30] if c.isalnum() or c == ' ').replace(' ', '_')
        output_filename = f"short_{safe_title}_{payload['timestamp']}.mp4"
        output_path = str(temp_path / output_filename)
        
        render_video(audio_path, video_path, subtitle_path, output_path, duration)
        
        # Upload to Catbox.moe (FREE file hosting!)
        print("\n[5/5] Uploading to Catbox.moe...")
        download_url = upload_to_catbox(output_path)
        
        print("\n" + "=" * 60)
        print("SUCCESS!")
        print("=" * 60)
        print(f"Filename: {output_filename}")
        print(f"Download URL: {download_url}")
        
        # Set GitHub Actions outputs for n8n callback
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                f.write(f"filename={output_filename}\n")
                f.write(f"download_url={download_url}\n")
                f.write(f"title={payload['story_title']}\n")
        
        return download_url


def main():
    parser = argparse.ArgumentParser(description='Render Reddit story as vertical short')
    parser.add_argument('--payload', required=True, help='JSON payload from n8n')
    args = parser.parse_args()
    
    payload = json.loads(args.payload)
    asyncio.run(main_async(payload))


if __name__ == '__main__':
    main()
