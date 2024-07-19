import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import random
import json
from dotenv import load_dotenv
import os


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents)

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

queues = {}
current_song = {}
user_history = {}
loop_mode = {}


def save_user_history():
    with open("user_history.json", "w") as f:
        json.dump(user_history, f)


def load_user_history():
    global user_history
    try:
        with open("user_history.json", "r") as f:
            user_history = json.load(f)
    except FileNotFoundError:
        user_history = {}


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    load_user_history()  # Load history on bot startup


@bot.command(name="join", help="Tells the bot to join the voice channel")
async def join(ctx):
    if not ctx.message.author.voice:
        await ctx.send(f"{ctx.message.author.name} is not connected to a voice channel")
        return
    else:
        channel = ctx.message.author.voice.channel
    await channel.connect()


@bot.command(name="leave", help="To make the bot leave the voice channel")
async def leave(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_connected():
        await voice_client.disconnect()
    else:
        await ctx.send("The bot is not connected to a voice channel.")


@bot.command(name="play", help="To play song or playlist from a YouTube URL")
async def play(ctx, url):
    guild_id = ctx.guild.id
    user_id = ctx.author.id
    if guild_id not in queues:
        queues[guild_id] = []

    if user_id not in user_history:
        user_history[user_id] = []

    if url not in user_history[user_id]:
        user_history[user_id].append(url)
        save_user_history()

    async with ctx.typing():
        ydl_opts = {
            "format": "bestaudio/best",
            "noplaylist": False,
            "default_search": "auto",
            "quiet": True,
        }

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")
                return

            if "entries" in info:
                for entry in info["entries"]:
                    queues[guild_id].append(entry["url"])
                await ctx.send(f'Added {len(info["entries"])} songs to the queue.')
            else:
                queues[guild_id].append(info["url"])
                await ctx.send(f'Added {info["title"]} to the queue.')

    if not ctx.voice_client.is_playing():
        await play_next_song(ctx)


async def play_next_song(ctx):
    guild_id = ctx.guild.id
    if guild_id not in loop_mode:
        loop_mode[guild_id] = None

    if queues[guild_id]:
        url = queues[guild_id].pop(0)
        try:
            ctx.voice_client.play(
                discord.FFmpegPCMAudio(url),
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    play_next_song(ctx), bot.loop
                ).result(),
            )
            current_song[guild_id] = url
        except Exception as e:
            await ctx.send(f"An error occurred while playing the song: {e}")
    elif loop_mode[guild_id] == "queue":
        # Loop the queue if set to "queue"
        await ctx.send("Looping the queue.")
        await play_next_song(ctx)
    elif loop_mode[guild_id] == "song" and current_song.get(guild_id):
        # Loop the current song if set to "song"
        queues[guild_id].insert(0, current_song[guild_id])
        await ctx.send("Looping the current song.")
        await play_next_song(ctx)
    else:
        await ctx.send("Queue is empty, add more songs to keep the party going!")


@bot.command(name="recommend", help="Recommends a song based on your history")
async def recommend(ctx):
    user_id = ctx.author.id
    if user_id not in user_history or not user_history[user_id]:
        await ctx.send("You have no song history to base recommendations on.")
        return

    user_history_list = list(user_history[user_id])
    last_song = user_history_list[-1]
    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            search_query = f"ytsearch:{last_song} music"
            info = ydl.extract_info(search_query, download=False)
            related_videos = info.get("entries", [])

            music_videos = [
                video
                for video in related_videos
                if "music" in video.get("title", "").lower()
            ]

            if music_videos:
                recommended_video = random.choice(music_videos)
                await ctx.send(
                    f"How about this one? {recommended_video['webpage_url']}"
                )
            else:
                await ctx.send("No suitable music recommendations found.")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")


@bot.command(name="next", help="To play next song in queue")
async def next(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        voice_client.stop()
    guild_id = ctx.guild.id
    if queues[guild_id]:
        url = queues[guild_id].pop(0)
        current_song[guild_id] = url
        await play_next_song(ctx)
    else:
        await ctx.send("Queue is empty now, add more songs to keep the party going!")


@bot.command(name="pause", help="This command pauses the song")
async def pause(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        voice_client.pause()
    else:
        await ctx.send("The bot is not playing anything at the moment.")


@bot.command(
    name="loop",
    help="Toggle loop mode. Use `!loop` to loop the current song, `!loop queue` to loop the entire queue, and `!loop off` to turn off looping.",
)
async def loop(ctx, mode: str = None):
    guild_id = ctx.guild.id
    if mode == "off":
        loop_mode[guild_id] = None
        await ctx.send("Looping is now turned off.")
    elif mode == "queue":
        loop_mode[guild_id] = "queue"
        await ctx.send("The queue will now be looped.")
    elif mode == "song":
        loop_mode[guild_id] = "song"
        await ctx.send("The current song will now be looped.")
    else:
        await ctx.send(
            "Invalid loop mode. Use `!loop off`, `!loop song`, or `!loop queue`."
        )


@bot.command(name="resume", help="Resumes the song")
async def resume(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_paused():
        voice_client.resume()
    else:
        await ctx.send("The bot is not playing anything at the moment.")


@bot.command(name="queue", help="Shows the current song queue")
async def queue(ctx):
    guild_id = ctx.guild.id
    if guild_id in queues and queues[guild_id]:
        queue_list = "\n".join(
            [f"{i+1}. {url}" for i, url in enumerate(queues[guild_id])]
        )
        await ctx.send(f"Current queue:\n{queue_list}")
    else:
        await ctx.send("The queue is empty haha...so is my heart...")


@bot.command(name="remove", help="removes the 'nth' song from queue")
async def remove(ctx, n: int):
    guild_id = ctx.guild.id
    if guild_id in queues and queues[guild_id]:
        if 0 <= n < len(queues[guild_id]):
            queues[guild_id].pop(n)
            await ctx.send(f"Removed song successfully!")
        else:
            await ctx.send("Invalid song number.")
    else:
        await ctx.send("The queue is empty haha...so is my heart...")


@bot.command(name="vol", help="Sets the volume of the audio playback (0-100)")
async def volume(ctx, volume: int):
    if 0 <= volume <= 100:
        ctx.voice_client.source.volume = volume / 100.0
        await ctx.send(f"Volume set to {volume}%.")
    else:
        await ctx.send("C'mon volume must be between 0 and 100.")


@bot.command(name="clrqueue", help="clears the entire queue")
async def clrqueue(ctx):
    guild_id = ctx.guild.id
    if guild_id in queues and queues[guild_id]:
        queues[guild_id] = []
        await ctx.send(f"Cleared queue successfully!")
    else:
        await ctx.send("Some problem occurred with the queue, try again perhaps")


@bot.command(name="current", help="Displays the current playing song")
async def current(ctx):
    guild_id = ctx.guild.id
    if guild_id in current_song:
        await ctx.send(f"Now playing: {current_song[guild_id]}")
    else:
        await ctx.send("No song is currently playing.")


@bot.command(name="stop", help="Stops the song and clears the queue")
async def stop(ctx):
    voice_client = ctx.message.guild.voice_client
    queues[ctx.guild.id] = []
    if voice_client.is_playing():
        voice_client.stop()
    else:
        await ctx.send("I'm not playing anything for you at the moment.")


@bot.command(name="search", help="Search for a song on YouTube")
async def search(ctx, *, query):
    guild_id = ctx.guild.id
    user_id = ctx.author.id
    if guild_id not in queues:
        queues[guild_id] = []

    if user_id not in user_history:
        user_history[user_id] = []

    async with ctx.typing():
        ydl_opts = {
            "format": "bestaudio/best",
            "noplaylist": False,
            "default_search": "ytsearch",
            "quiet": True,
        }

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")
                return

            if "entries" in info:
                for entry in info["entries"]:
                    url = entry["url"]
                    if url not in user_history[user_id]:
                        user_history[user_id].append(url)
                        save_user_history()
                    queues[guild_id].append(url)
                await ctx.send(f'Added {len(info["entries"])} songs to the queue.')
            else:
                url = info["url"]
                if url not in user_history[user_id]:
                    user_history[user_id].append(url)
                    save_user_history()
                queues[guild_id].append(url)
                await ctx.send(f'Added {info["title"]} to the queue.')

    if not ctx.voice_client.is_playing():
        await play_next_song(ctx)


bot.run(DISCORD_TOKEN)
