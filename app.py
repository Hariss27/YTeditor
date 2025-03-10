import streamlit as st
import os
import requests
from bs4 import BeautifulSoup
from pytube import YouTube
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
import cv2
from PIL import Image, ImageDraw, ImageFont
from transformers import pipeline
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

# Ensure FFmpeg is available (for Streamlit Cloud)
os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"

# -------------------
# Function Definitions
# -------------------

# A. Scrape Trailer URL
def get_trailer_url(movie_name):
    search_url = f"https://www.imdb.com/find?q={movie_name}"
    response = requests.get(search_url)
    soup = BeautifulSoup(response.text, 'html.parser')

    try:
        movie_link = soup.find('a', href=True)['href']
        movie_page_url = f"https://www.imdb.com{movie_link}"
        movie_page_response = requests.get(movie_page_url)
        movie_page_soup = BeautifulSoup(movie_page_response.text, 'html.parser')

        # Find the trailer URL
        trailer_div = movie_page_soup.find('div', {'class': 'ipc-lockup ipc-lockup--baseAlt ipc-lockup--trailer'})
        if trailer_div:
            trailer_url = trailer_div.find('a')['href']
            return f"https://www.imdb.com{trailer_url}"
    except Exception as e:
        st.error(f"Error fetching trailer for {movie_name}: {e}")
    return None

# B. Download Trailer
def download_trailer(url, output_dir="downloads"):
    yt = YouTube(url)
    stream = yt.streams.filter(file_extension='mp4').first()
    os.makedirs(output_dir, exist_ok=True)
    video_path = stream.download(output_path=output_dir)
    return video_path

# C. Add Subtitles
def add_subtitles(video_path, subtitle_text, output_dir="edited_videos"):
    video = VideoFileClip(video_path)
    txt_clip = TextClip(subtitle_text, fontsize=50, color='white').set_position('bottom').set_duration(video.duration)
    final = CompositeVideoClip([video, txt_clip])
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, os.path.basename(video_path))
    final.write_videofile(output_path, codec="libx264")
    return output_path

# D. Enhance Video Quality
def enhance_video(input_path, output_dir="enhanced_videos"):
    video = cv2.VideoCapture(input_path)
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = video.get(cv2.CAP_PROP_FPS)
    output_path = os.path.join(output_dir, os.path.basename(input_path))
    os.makedirs(output_dir, exist_ok=True)
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    while video.isOpened():
        ret, frame = video.read()
        if not ret:
            break
        enhanced_frame = cv2.convertScaleAbs(frame, alpha=1.5, beta=30)  # Adjust brightness and contrast
        out.write(enhanced_frame)

    video.release()
    out.release()
    return output_path

# E. Generate SEO Content
def generate_seo_content(prompt):
    generator = pipeline('text-generation', model='gpt2')
    result = generator(prompt, max_length=100, num_return_sequences=1)
    return result[0]['generated_text']

# F. Create Thumbnail
def create_thumbnail(video_path, output_dir="thumbnails"):
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    cap.release()

    if ret:
        thumbnail_path = os.path.join(output_dir, os.path.splitext(os.path.basename(video_path))[0] + ".png")
        os.makedirs(output_dir, exist_ok=True)
        cv2.imwrite(thumbnail_path, frame)

        img = Image.open(thumbnail_path)
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype("arial.ttf", 50)
        draw.text((50, 50), "Watch Now!", fill="white", font=font)
        img.save(thumbnail_path)
        return thumbnail_path
    return None

# G. Authenticate YouTube API
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def authenticate_youtube():
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    credentials = flow.run_local_server(port=0)
    return build('youtube', 'v3', credentials=credentials)

# H. Upload to YouTube
def upload_to_youtube(youtube, video_path, title, description, tags):
    request_body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags
        },
        'status': {
            'privacyStatus': 'public'
        }
    }

    media = MediaFileUpload(video_path)
    response = youtube.videos().insert(
        part='snippet,status',
        body=request_body,
        media_body=media
    ).execute()

    return response['id']

# -------------------
# Streamlit Interface
# -------------------

st.title("Movie Trailer Editor & YouTube Uploader")

# Input for movie names
movie_names = st.text_area("Enter movie names (one per line):").splitlines()

if st.button("Process Movies"):
    try:
        youtube = authenticate_youtube()

        for movie_name in movie_names:
            st.write(f"Processing movie: {movie_name}")

            # Step 1: Get trailer URL
            trailer_url = get_trailer_url(movie_name)
            if not trailer_url:
                st.error(f"No trailer found for {movie_name}. Skipping...")
                continue

            st.write(f"Trailer URL: {trailer_url}")

            # Step 2: Download trailer
            st.write("Downloading trailer...")
            downloaded_video = download_trailer(trailer_url)
            st.success(f"Trailer downloaded: {downloaded_video}")

            # Step 3: Add subtitles
            st.write("Adding subtitles...")
            subtitled_video = add_subtitles(downloaded_video, f"{movie_name} Trailer")
            st.success(f"Subtitles added: {subtitled_video}")

            # Step 4: Enhance video quality
            st.write("Enhancing video quality...")
            enhanced_video = enhance_video(subtitled_video)
            st.success(f"Video enhanced: {enhanced_video}")

            # Step 5: Generate SEO content
            st.write("Generating SEO content...")
            seo_prompt = f"Best {movie_name} trailer"
            seo_content = generate_seo_content(seo_prompt)
            title, description = seo_content.split("\n", 1)
            tags = [movie_name, "movie trailer", "new release"]

            # Step 6: Create thumbnail
            st.write("Creating thumbnail...")
            thumbnail_path = create_thumbnail(enhanced_video)
            st.success(f"Thumbnail created: {thumbnail_path}")

            # Step 7: Upload to YouTube
            st.write("Uploading to YouTube...")
            video_id = upload_to_youtube(youtube, enhanced_video, title, description, tags)
            st.success(f"Uploaded to YouTube! Video ID: {video_id}")

    except Exception as e:
        st.error(f"An error occurred: {e}")
