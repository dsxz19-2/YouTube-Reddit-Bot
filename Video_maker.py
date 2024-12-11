import os
import json
import praw
import time
import random
import ffmpeg
import pygame
import whisper
import requests
from os import walk
import moviepy.editor as mp
from moviepy.editor import *
from selenium import webdriver
from PIL import Image, ImageDraw
from moviepy.video.fx.resize import resize
from selenium.webdriver.common.by import By

def get_post(limit=5, subreddit="AITAH"):
     # Using praw to get the top 5 posts from a subreddit
     # Fill in your reddit credentials here
     # For information on how to get your own reddit bot visit https://www.youtube.com/watch?v=U9Ogh1OGP-g
     client_secret = ""
     client_id = ""
     password = ""
     username = ""
     user_agent = ""

     reddit_instance = praw.Reddit(
                    client_id = client_id,
                    client_secret = client_secret,
                    username = username,
                    password = password,
                    user_agent = user_agent
               )

     reddit_instance.auth

     subreddit = reddit_instance.subreddit(subreddit)
     top_5 = subreddit.rising(limit=limit)

     story_dict = []
     post_ids = []

     for post in top_5:
          title = post.title
          story = post.selftext
          # Ignore posts with links in the title or story becuase it confuses the text-to-speech AI
          if ("http://" or "https://") in (title or story):
              pass
          else:
              # Append the title and the story of the post to the story_dict list
              # The title and the story will be used to create the video captions
              # The post_ids list will be used to get the video file from the reddit API
              story_dict.append([title, story])
              post_ids.append(post.id)

     return story_dict, post_ids

def add_corners(im, rad):
    # Add rounded corners to the title image
    circle = Image.new('L', (rad * 2, rad * 2), 0)
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, rad * 2 - 1, rad * 2 - 1), fill=255)
    alpha = Image.new('L', im.size, 255)
    w, h = im.size
    alpha.paste(circle.crop((0, 0, rad, rad)), (0, 0))
    alpha.paste(circle.crop((0, rad, rad, rad * 2)), (0, h - rad))
    alpha.paste(circle.crop((rad, 0, rad * 2, rad)), (w - rad, 0))
    alpha.paste(circle.crop((rad, rad, rad * 2, rad * 2)), (w - rad, h - rad))
    im.putalpha(alpha)
    return im

def get_title(subreddit, post_id, image_file):
     # Using selenium to get the title and the credit bar from the reddit post
     driver = webdriver.Chrome() 

     # Go to the reddit post and get the screenshot of the title and the credit bar     
     driver.get(f"https://www.reddit.com/r/{subreddit}/comments/{post_id}")
     print(f"https://www.reddit.com/r/{subreddit}/comments/{post_id}")

     # All the titles and the credit bars have the same atributes in the HTML code
     # It can be found using XPATH
     # Save it to seperate png files
     element = driver.find_element(By.XPATH, ("//h1[@slot='title']"))
     element.screenshot("title.png")
     element = driver.find_element(By.XPATH, ("//div[@slot='credit-bar']"))
     element.screenshot("credit_bar.png")

     # Load the images
     title = pygame.image.load("title.png")
     credit_bar = pygame.image.load("credit_bar.png")

     # Get the height and the width of the title and the credit bar
     title_height = title.get_height()
     title_width = title.get_width()
     credit_bar_height = credit_bar.get_height()
     credit_bar_width = credit_bar.get_width()

     # Create a new blank image with the sum of the heights and whichever image has the largest width
     back_image_height = title_height + credit_bar_height
     back_image_width = max([title_width, credit_bar_width])

     # Add some buffer around the back_image so that when it's rounded it doesn't get cut off any text
     # This is done by adding 15 to the width and height of the back_image
     # Then change the color of the back_image so that when everything is put together it looks like one image
     back_image = Image.new("RGBA", (back_image_width+20, back_image_height+20), (11, 20, 22, 255))
     title = Image.open("title.png")
     credit_bar = Image.open("credit_bar.png")

     # Paste the title and the credit bar onto the back_image away from the corners
     back_image.paste(credit_bar, (10, 0))
     back_image.paste(title, (10, title_height))

     # Add rounded corners to the back_image and save it to the image_file
     back_image = add_corners(back_image, 20)
     back_image.save(image_file)

     # Delete the title and the credit_bar png files
     os.system("del title.png && del credit_bar.png")

     # Close the driver
     driver.close()

     return back_image_height+20, back_image_width+20
    
def voice_over(text, path_to_file="output.mp3"):
    # Select a voice from the website
     headers = {
     "service": "StreamElements",
     "voice": "Matthew",
     "text": text,
     }

     # Make the request to the website
     req = requests.post("https://lazypy.ro/tts/request_tts.php", headers)
     data = req.content.decode()
     data = json.loads(data)["audio_url"]
     data = requests.get(data)

     # Write the audio data to a file and aquire the duration of the audio file
     with open(path_to_file, 'wb') as f:
         f.write(data.content)
     try:
        clip = mp.AudioFileClip(path_to_file)
        duration = clip.duration
        clip.close()
        print("Duration aquired")
        return duration
     except Exception as e:
         print(f"Error getting audio duration: {e}")
         exit(0)

def extract_clip(video_path, clip_length, output_filename):
  clip = mp.VideoFileClip(video_path)

  # If the length of the audio file exceeds the clip of the video return an error message
  if clip_length > clip.duration:
      print(f"Error: Clip length ({clip_length} seconds) cannot exceed video duration ({clip.duration} seconds).")
      exit(0)

  # If the length of the audio file is less than the clip of the video then randomly select a start time
  max_start_time = clip.duration - clip_length
  start_time = round(random.uniform(0, max_start_time), 2)  # Random start time (seconds)
  end_time = start_time + clip_length

  # Extract the clip from the video file and save it to the output_filename
  extracted_clip = clip.subclip(start_time, end_time)
  extracted_clip.write_videofile(output_filename, fps=clip.fps, threads=1, codec="libx264")

  clip.close()

  print(f"Successfully extracted a {clip_length}-second clip and saved as {output_filename}")

def caption(input_video_file, input_audio_file, output_video_file, title_card, font_border_color="black", font_fill_color="white", font_size=100, model_size="tiny", font_file="ARLRDBD.TTF"):
    
    model = whisper.load_model(model_size) 

    text = model.transcribe(audio=input_audio_file, language="en", fp16=False, word_timestamps=True)

    video = VideoFileClip(input_video_file)

    clips = [video]

    for segments in text["segments"]:
        for segment in segments["words"]:
            caption_border = TextClip(segment["word"], font=font_file, fontsize=font_size+5, color=font_border_color).set_position("center").set_start(segment["start"]).set_end(segment["end"])
            caption_fill = TextClip(segment["word"], font=font_file, fontsize=font_size, color=font_fill_color).set_position("center").set_start(segment["start"]).set_end(segment["end"])
            clips.append(caption_border)
            clips.append(caption_fill)

    clips.append(title_card)

    video = CompositeVideoClip(clips)  

    video.write_videofile(output_video_file)

    video.close()

# Define constants
audio_file = "output.mp3"
subreddit = "AITAH"
limit = 5

path_to_videos = "C:/Users/sakth/OneDrive/Documents/python projects/YouTube video maker/Video"

stories, post_ids = get_post(subreddit=subreddit, limit=limit)
useable_stories = []

# Process the text to removed anything the AI might get mispronounc like "r/AITAH" or "r/WIBTA"
# Remove the story if it is too
for i in range(len(stories)):

    full_story = stories[i][0] + "... " + stories[i][1]

    if "r/" or "AITAH" or "WIBTA" in (stories[i][0] or stories[i][0]):
        stories[i][0] = stories[i][0].replace("r/", "")
        stories[i][0] = stories[i][0].replace("AITAH", "Am I a bad person")
        stories[i][0] = stories[i][0].replace("WIBTA", "Would I be the bad person")

        stories[i][1] = stories[i][1].replace("r/", "")
        stories[i][1] = stories[i][1].replace("AITAH", "Am I the bad person")
        stories[i][1] = stories[i][1].replace("WIBTA", "Would I be the bad person")
    
    full_story = full_story.replace("\n", " ")

    if len(full_story) > 3000:
        pass
    else:
        useable_stories.append(full_story) 

    print("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")

# Ittirate through the stories
for i in range(len(useable_stories)):
    vid_id = random.randint(0, 10000)

    # Use the ID of the story to get and image of the title
    height, width = get_title(subreddit="AITAH", post_id=f"{post_ids[i]}", image_file=f"{post_ids[i]}.png")

    # Resize it so it fits
    title_card = ImageClip(f"{post_ids[i]}.png").set_start(0).set_duration(3).set_pos("center")

    if (width > 1080):
        scaling = 962 / width
        height = height * scaling
        title_card = resize(title_card, height=height, width=962)
    else:
        pass

    # Add a little message at the end of the story
    story_for_voice_over = useable_stories[i]    

    # Send it to the voice over website and get the duration of the voice over
    duration = voice_over(text=story_for_voice_over, path_to_file=audio_file)

    # Get a random background gameplay video from the "Background_Gameplay" folder and extract a clip from it 1 second longer than the duration of the voice over
    filenames = next(walk("Background_Gameplay"), (None, None, []))[2]
    background_clip = filenames[random.randint(0, (len(filenames)-1))]
    video_path = os.path.abspath(f"Background_Gameplay/{background_clip}")
    clip_length = duration + 1
    output_filename = "background_clip.mp4"
    extract_clip(video_path, clip_length, output_filename)

    # Combine the background clip with the voice over and save it to the "Video" folder
    video_clip = VideoFileClip(output_filename)
    audio_clip = AudioFileClip(audio_file)
    final_clip = video_clip.set_audio(audio_clip)
    final_clip.write_videofile(f"Video/Video_{vid_id}.mp4")
    video_clip.close()
    audio_clip.close()
    final_clip.close()
    time.sleep(1)

    # Delete the background clip
    os.remove(output_filename)

    # Get first file
    filenames = next(walk(path_to_videos), (None, None, []))[2]
    video = filenames[i]     

    caption(f"Video/Video_{vid_id}.mp4", audio_file, f"Video/Video_{vid_id}_final_.mp4", title_card=title_card)

    # Delete the uncaptioned original video
    # os.remove(f"Video/Video_{vid_id}.mp4")
    os.remove(audio_file)

    time.sleep(10)

    # Create a new folder for the video segments
    os.makedirs(f"{path_to_videos}/Video_{vid_id}")

    # Cut the video into segments of 55 seconds if it's longer than a minute
    if clip_length > 60:
        video_index = 1  
        input_video_path = f'{path_to_videos}/Video_{vid_id}_final_.mp4'
        output_video_path = f'{path_to_videos}/Video_{vid_id}/Video_{vid_id}_final_%03d.mp4'

        # Define segment time
        segment_time = '00:00:55'
        # Build the FFmpeg command
        ffmpeg.input(input_video_path).output(
            output_video_path,
            c='copy',
            map='0',
            f='segment',
            segment_time=segment_time,
            reset_timestamps=1
        ).run(overwrite_output=True)

    # Delete the files
    os.remove(f"{post_ids[i]}.png")
