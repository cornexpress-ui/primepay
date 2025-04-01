# Telegram Video Bot

This is a Telegram bot that can convert files to videos, take screenshots of the video, and add watermarks. 

## Features

- Convert files to videos
- Take screenshots of videos
- Add watermarks to videos (text and PNG, with options for position and opacity)

## Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/<your-username>/telegram-video-bot.git
   cd telegram-video-bot
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Set your Telegram bot token:

   ```bash
   export TELEGRAM_BOT_TOKEN='your-telegram-bot-token'
   ```

4. Run the bot:

   ```bash
   python main.py
   ```

## Deployment to Heroku

1. Log in to Heroku and create a new app:

   ```bash
   heroku login
   heroku create your-app-name
   ```

2. Push the code to Heroku:

   ```bash
   git push heroku main
   ```

3. Set your Telegram bot token on Heroku:

   ```bash
   heroku config:set TELEGRAM_BOT_TOKEN='your-telegram-bot-token'
   ```

4. Start the app:

   ```bash
   heroku ps:scale web=1
   ```

Your bot should now be running on Heroku.

## Usage

1. Start a chat with your bot on Telegram.
2. Send a video file to the bot.
3. Follow the instructions to take screenshots and add watermarks.

Enjoy!
