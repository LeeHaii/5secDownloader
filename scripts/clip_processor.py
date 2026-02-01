import os
import csv
import subprocess
from pathlib import Path
import yt_dlp
from typing import List, Tuple
from urllib.parse import urlparse, parse_qs


def download_youtube_video(url: str, output_path: str) -> str:
    """
    Download a YouTube video from a given URL.
    
    Args:
        url (str): The YouTube video URL
        output_path (str): The directory to save the video
    
    Returns:
        str: The path to the downloaded video file
    
    Raises:
        Exception: If download fails
    """
    os.makedirs(output_path, exist_ok=True)
    
    try:
        print(f"  Downloading video from: {url}")
        
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            output_file = ydl.prepare_filename(info)
        
        print(f"  Download completed: {output_file}")
        return output_file
        
    except Exception as e:
        print(f"  Error downloading video: {str(e)}")
        raise


def cut_clip(input_video: str, start_time: float, duration: float, output_file: str) -> None:
    """
    Cut a clip from a video using ffmpeg.
    
    Args:
        input_video (str): Path to the input video file
        start_time (float): Start time in seconds
        duration (float): Duration of the clip in seconds
        output_file (str): Path to save the output clip
    
    Raises:
        Exception: If ffmpeg fails
    """
    try:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # Use -ss before -i for faster seeking with copy codecs
        cmd = [
            'ffmpeg',
            '-ss', str(start_time),
            '-i', input_video,
            '-t', str(duration),
            '-c:v', 'copy',         # Copy video codec without re-encoding
            '-c:a', 'copy',         # Copy audio codec without re-encoding
            '-fflags', '+genpts',   # Generate presentation timestamps to fix sync issues
            '-y',  # Overwrite output file
            '-hide_banner',
            '-loglevel', 'error',
            output_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            print(f"    FFmpeg error details: {result.stderr[:300]}")
            raise Exception(f"FFmpeg error")
        
        # Verify the output file was created and has content
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            print(f"    Clip created: {output_file} ({os.path.getsize(output_file) / 1024:.1f} KB)")
        else:
            raise Exception(f"Output file was not created or is empty")
        
    except subprocess.TimeoutExpired:
        print(f"    Error: Clip creation timed out")
        raise
    except Exception as e:
        print(f"    Error cutting clip: {str(e)}")
        raise


def parse_input_csv(csv_path: str) -> List[List[Tuple[str, List[float]]]]:
    """
    Parse the input CSV file.
    Expected format: URL1, Timestamps1, URL2, Timestamps2, ...
    Timestamps are semicolon-separated in MM.SS format (e.g., 2.57 = 2 minutes 57 seconds).
    
    Returns:
        List[List[Tuple[str, List[float]]]]: 
            For each row: list of (URL, [timestamps in seconds]) tuples
    """
    rows = []
    
    def convert_timestamp(ts_str: str) -> float:
        """Convert MM.SS format to total seconds."""
        parts = ts_str.split('.')
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
        else:
            return float(ts_str)
    
    def clean_youtube_url(url: str) -> str:
        """Extract just the video ID from YouTube URL, removing playlist/list parameters."""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            
            # Get video ID
            video_id = None
            if 'v' in params:
                video_id = params['v'][0]
            elif 'watch' in parsed.path:
                # Fallback to return original if we can't parse it
                return url
            
            if video_id:
                # Return URL with only video ID (no playlist, no start_radio, etc.)
                return f"https://www.youtube.com/watch?v={video_id}"
        except:
            pass
        
        return url
    
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            # Skip empty rows
            if not any(row) or all(cell.strip() == '' for cell in row):
                rows.append([])
                continue
            
            # Parse URL-timestamp pairs
            url_timestamp_pairs = []
            for i in range(0, len(row), 2):
                if i + 1 < len(row):
                    url = row[i].strip()
                    timestamps_str = row[i + 1].strip()
                    
                    if url:  # Only process if URL is not empty
                        # Clean the URL to remove playlist parameters
                        url = clean_youtube_url(url)
                        
                        # Parse timestamps (remove trailing semicolon if present)
                        timestamps = []
                        if timestamps_str:
                            ts_list = [t.strip() for t in timestamps_str.split(';') if t.strip()]
                            timestamps = [convert_timestamp(t) for t in ts_list]
                        
                        url_timestamp_pairs.append((url, timestamps))
            
            rows.append(url_timestamp_pairs)
    
    return rows


def process_clips(csv_path: str, output_base_dir: str, temp_dir: str) -> None:
    """
    Process all videos and clips from the input CSV.
    
    Args:
        csv_path (str): Path to the input CSV file
        output_base_dir (str): Base output directory for clips
        temp_dir (str): Temporary directory for downloaded videos
    """
    # Parse input CSV
    rows = parse_input_csv(csv_path)
    
    print(f"Processing {len(rows)} rows from {csv_path}\n")
    
    # Print all detected URLs for verification
    all_urls = []
    for row_idx, url_timestamp_pairs in enumerate(rows):
        for url, timestamps in url_timestamp_pairs:
            all_urls.append(url)
    
    print(f"Total unique URLs to process: {len(set(all_urls))}")
    print("URLs detected from CSV:")
    for i, url in enumerate(set(all_urls), 1):
        print(f"  {i}. {url}\n")
    
    for row_idx, url_timestamp_pairs in enumerate(rows):
        if not url_timestamp_pairs:
            print(f"Row {row_idx}: Skipped (empty)")
            continue
        
        print(f"Row {row_idx}:")
        
        clip_count = 1
        
        for url, timestamps in url_timestamp_pairs:
            if not url or not timestamps:
                print(f"  Skipped URL-timestamp pair (missing data)")
                continue
            
            print(f"  Processing URL: {url} with {len(timestamps)} timestamps")
            
            # Download video
            try:
                video_path = download_youtube_video(url, temp_dir)
            except Exception as e:
                print(f"  Skipping this URL due to download error")
                continue
            
            # Create output directory for this row
            row_output_dir = os.path.join(output_base_dir, str(row_idx))
            os.makedirs(row_output_dir, exist_ok=True)
            
            # Cut clips for each timestamp
            for timestamp in timestamps:
                output_clip = os.path.join(row_output_dir, f"{row_idx}.{clip_count}.mp4")
                
                try:
                    cut_clip(video_path, timestamp, duration=5.0, output_file=output_clip)
                    clip_count += 1
                except Exception as e:
                    print(f"    Failed to create clip at {timestamp}s")
            
            # Delete the video after all clips are cut
            try:
                os.remove(video_path)
                print(f"  Deleted video: {video_path}")
            except Exception as e:
                print(f"  Warning: Could not delete video file: {str(e)}")
        
        print(f"Row {row_idx}: Completed\n")


def main():
    # Set up paths relative to script location
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    csv_path = project_root / "input" / "input.csv"
    output_dir = project_root / "output"
    temp_dir = project_root / "temp"
    
    # Ensure paths exist
    csv_path = str(csv_path)
    output_dir = str(output_dir)
    temp_dir = str(temp_dir)
    
    if not os.path.exists(csv_path):
        print(f"Error: Input CSV not found at {csv_path}")
        return
    
    print("=" * 60)
    print("5-Second Clip Processor")
    print("=" * 60)
    print(f"Input CSV: {csv_path}")
    print(f"Output Directory: {output_dir}")
    print(f"Temp Directory: {temp_dir}")
    print("=" * 60 + "\n")
    
    try:
        process_clips(csv_path, output_dir, temp_dir)
        print("\n" + "=" * 60)
        print("Processing completed successfully!")
        print("=" * 60)
    except Exception as e:
        print(f"\nFatal error: {str(e)}")


if __name__ == "__main__":
    main()
