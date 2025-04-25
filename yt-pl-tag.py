#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube Playlist Downloader with Audio Tagging

This script downloads music from a YouTube playlist, saves it in a specified directory,
and applies a label to all the tracks.

Usage:
    ./yt-pl-tag.py --playlist "PLAYLIST_URL" --label "LABEL" --dir "OUTPUT_DIRECTORY"

Requirements:
    - yt-dlp (for downloading YouTube videos)
    - mutagen (for audio tagging)
    - ffmpeg (for audio conversion)
"""

import argparse
import os
import sys
from pathlib import Path
import subprocess
import shutil
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TXXX, TPE1, TCON, COMM

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='Download YouTube playlist and tag audio files.')
    parser.add_argument('--playlist', required=True, help='YouTube playlist URL')
    parser.add_argument('--label', required=True, help='Label to apply to all tracks')
    parser.add_argument('--dir', required=True, help='Output directory for downloaded files')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing files (default: False)')
    
    return parser.parse_args()

def check_dependencies():
    """Check if required dependencies are installed."""
    dependencies = ['yt-dlp', 'ffmpeg']
    
    for dep in dependencies:
        if shutil.which(dep) is None:
            print(f"Error: {dep} is not installed. Please install it before running this script.")
            sys.exit(1)

def expand_path(path):
    """Expand user home directory in path."""
    return os.path.expanduser(path)

def create_output_directory(directory):
    """Create output directory if it doesn't exist."""
    directory_path = Path(expand_path(directory))
    
    try:
        directory_path.mkdir(parents=True, exist_ok=True)
        return str(directory_path)
    except Exception as e:
        print(f"Error creating directory {directory}: {e}")
        sys.exit(1)

def apply_label_to_file(file_path, label):
    """Apply label to a single MP3 file."""
    try:
        # Load the ID3 tags
        audio = MP3(file_path, ID3=ID3)
        
        # Create ID3 tag if it doesn't exist
        if audio.tags is None:
            audio.add_tags()
        
        # Check if this label already exists in USER_LABEL
        existing_labels = []
        label_already_exists = False
        
        for tag in audio.tags.getall("TXXX"):
            if tag.desc == "USER_LABEL":
                existing_labels.extend(tag.text)
                if label in tag.text:
                    label_already_exists = True
        
        # If label doesn't exist, add it to the list
        if not label_already_exists:
            # Remove existing USER_LABEL tags
            for tag in list(audio.tags.getall("TXXX")):
                if tag.desc == "USER_LABEL":
                    audio.tags.delall("TXXX:USER_LABEL")
                    break
            
            # Add new USER_LABEL tag with all labels
            existing_labels.append(label)
            audio.tags.add(TXXX(encoding=3, desc="USER_LABEL", text=existing_labels))
            
            # Add to Genre field (TCON) - append to existing genres
            genres = []
            if 'TCON' in audio.tags:
                genres = audio.tags['TCON'].text
            if label not in genres:
                genres.append(label)
                audio.tags.add(TCON(encoding=3, text=genres))
            
            # Add as a comment if not already there
            comment_exists = False
            for comm in audio.tags.getall("COMM"):
                if comm.desc == 'Label' and label in comm.text:
                    comment_exists = True
                    break
            
            if not comment_exists:
                audio.tags.add(COMM(encoding=3, lang='eng', desc='Label', text=label))
            
            # Save the changes
            audio.save()
            print(f"Applied label '{label}' to: {os.path.basename(file_path)}")
            return True
        else:
            print(f"Label '{label}' already exists on: {os.path.basename(file_path)}")
            return True
        
    except Exception as e:
        print(f"Error applying label to {file_path}: {e}")
        return False

def get_playlist_video_ids(playlist_url):
    """Get the list of video IDs in a YouTube playlist."""
    print(f"Getting video IDs from playlist: {playlist_url}")
    
    cmd = [
        'yt-dlp',
        '--flat-playlist',
        '--print', 'id',
        playlist_url
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        video_ids = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        
        print(f"Found {len(video_ids)} videos in playlist.")
        return video_ids
    except subprocess.CalledProcessError as e:
        print(f"Error getting playlist information: {e}")
        return []

def download_and_tag_video(video_id, output_dir, label, overwrite=False):
    """Download a single video and apply label immediately."""
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"Processing video: {video_id}")
    
    # Check if file already exists by getting the filename it would have
    cmd_filename = [
        'yt-dlp',
        '--get-filename',
        '-o', f'{output_dir}/%(title)s.mp3',
        '--restrict-filenames',
        video_url
    ]
    
    try:
        result = subprocess.run(cmd_filename, check=True, capture_output=True, text=True)
        expected_filename = result.stdout.strip()
        file_exists = os.path.exists(expected_filename)
        
        if file_exists and not overwrite:
            print(f"File already exists: {os.path.basename(expected_filename)}")
            # Apply label to existing file
            apply_label_to_file(expected_filename, label)
            return True
    except subprocess.CalledProcessError as e:
        print(f"Error getting filename: {e}")
        return False
    
    # Download the file if it doesn't exist or overwrite is True
    cmd_download = [
        'yt-dlp',
        '-x',
        '--audio-format', 'mp3',
        '--audio-quality', '0',  # Best quality
        '-o', f'{output_dir}/%(title)s.%(ext)s',
        '--add-metadata',
        '--embed-thumbnail',
        '--restrict-filenames',
    ]
    
    if not overwrite:
        cmd_download.append('--no-overwrites')
    
    cmd_download.append(video_url)
    
    try:
        subprocess.run(cmd_download, check=True)
        
        # Apply label to the downloaded file
        if os.path.exists(expected_filename):
            apply_label_to_file(expected_filename, label)
            print(f"Downloaded and labeled: {os.path.basename(expected_filename)}")
            return True
        else:
            print(f"File was not downloaded: {video_url}")
            return False
    except subprocess.CalledProcessError as e:
        print(f"Error downloading video: {e}")
        return False

def process_playlist(playlist_url, output_dir, label, overwrite=False):
    """Process each video in the playlist one by one."""
    print(f"Processing playlist: {playlist_url}")
    
    # Get video IDs from playlist
    video_ids = get_playlist_video_ids(playlist_url)
    if not video_ids:
        print("No videos found in playlist.")
        return False
    
    # Process each video one by one
    success_count = 0
    total_count = len(video_ids)
    
    for i, video_id in enumerate(video_ids, 1):
        print(f"\n[{i}/{total_count}] Processing video {video_id}")
        if download_and_tag_video(video_id, output_dir, label, overwrite):
            success_count += 1
    
    print(f"\nSuccessfully processed {success_count} out of {total_count} videos.")
    return success_count > 0

def get_existing_files(directory):
    """Get list of existing MP3 files in the directory."""
    return list(Path(directory).glob('*.mp3'))

def apply_label_to_files(directory, label):
    """Apply label to all MP3 files in directory."""
    print(f"\nApplying label '{label}' to all files in directory...")
    
    mp3_files = list(Path(directory).glob('*.mp3'))
    
    if not mp3_files:
        print("No MP3 files found in the output directory.")
        return False
    
    success_count = 0
    for mp3_file in mp3_files:
        if apply_label_to_file(mp3_file, label):
            success_count += 1
    
    print(f"Applied label to {success_count} out of {len(mp3_files)} files.")
    return success_count > 0

def verify_tags(directory, label):
    """Verify that tags were properly applied to files."""
    print("\nVerifying tags on files...")
    
    mp3_files = list(Path(directory).glob('*.mp3'))
    if not mp3_files:
        print("No MP3 files found to verify.")
        return
    
    for mp3_file in mp3_files:
        try:
            audio = MP3(mp3_file, ID3=ID3)
            if audio.tags is None:
                print(f"Warning: No tags found in {mp3_file.name}")
                continue
                
            # Check for our custom tag
            custom_tag_found = False
            all_labels = []
            
            for tag in audio.tags.getall("TXXX"):
                if tag.desc == "USER_LABEL":
                    all_labels = tag.text
                    if label in all_labels:
                        custom_tag_found = True
                        break
            
            if custom_tag_found:
                print(f"✓ Verified label '{label}' on: {mp3_file.name}")
                if len(all_labels) > 1:
                    print(f"  All labels: {', '.join(all_labels)}")
            else:
                print(f"✗ Label '{label}' not found on: {mp3_file.name}")
                
        except Exception as e:
            print(f"Error verifying tags on {mp3_file}: {e}")

def main():
    """Main function."""
    args = parse_arguments()
    
    # Check dependencies
    check_dependencies()
    
    # Create output directory
    output_dir = create_output_directory(args.dir)
    
    # Process each video in the playlist one by one
    if process_playlist(args.playlist, output_dir, args.label, args.overwrite):
        # Verify tags were applied correctly
        verify_tags(output_dir, args.label)
        print("\nProcess completed successfully!")
    else:
        print("Failed to process playlist. Process aborted.")

if __name__ == "__main__":
    main()
