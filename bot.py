import discord
from discord.ext import commands
from yt_dlp import YoutubeDL
from collections import deque

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True  # Щоб бачити голосові стани
bot = commands.Bot(command_prefix='!', intents=intents)

# Черга пісень
song_queue = deque()

# yt-dlp налаштування
ytdl_format_options = {
    'format': 'bestaudio[ext=webm][acodec=opus]/bestaudio/best',
    'quiet': True,
    'default_search': 'ytsearch',
    'noplaylist': True,
    'youtube_include_dash_manifest': False,
    'geo_bypass': True,
}
ffmpeg_options = {
    'options': '-vn'
}
ytdl = YoutubeDL(ytdl_format_options)


# Кнопки керування
class MusicControlButtons(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="⏸ Пауза / ▶️ Відновити", style=discord.ButtonStyle.gray)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        try:
            if vc:
                if vc.is_playing():
                    vc.pause()
                    await interaction.response.defer()  # Без повідомлення
                elif vc.is_paused():
                    vc.resume()
                    await interaction.response.defer()  # Без повідомлення
                else:
                    await interaction.response.send_message("⛔ Нічого не відтворюється.", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ Бот не підключений до голосового каналу.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Помилка: {str(e)}", ephemeral=True)

    @discord.ui.button(label="⏭ Пропустити", style=discord.ButtonStyle.blurple)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        try:
            if vc and vc.is_playing():
                vc.stop()
                await interaction.response.defer()  # Без повідомлення
            else:
                await interaction.response.send_message("⚠️ Нічого не грає, бот залишився в голосовому каналі.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Помилка: {str(e)}", ephemeral=True)

    @discord.ui.button(label="🛑 Вийти", style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        try:
            if vc:
                song_queue.clear()
                await vc.disconnect()
                help_msg = (
                    "🛑 Бот вийшов з голосового каналу.\n\n"
                    "**Основні команди:**\n"
                    "`!play <назва або посилання>` — додати пісню до черги\n"
                    "`!queue` — переглянути чергу\n"
                    "`🛑` — вийти з голосового каналу і очистити чергу\n"
                    "`⏭` — пропустити пісню\n"
                    "`⏸ / ▶️` — пауза/відновлення відтворення\n"
                )
                await interaction.response.send_message(help_msg, ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ Я не в голосовому каналі.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Помилка: {str(e)}", ephemeral=True)


# Перевірка кількості користувачів (окрім бота) в голосовому каналі
def members_count(vc: discord.VoiceClient):
    if not vc or not vc.channel:
        return 0
    return sum(1 for m in vc.channel.members if not m.bot)


# Основна команда play
@bot.command()
async def play(ctx, *, search: str):
    if not ctx.author.voice:
        await ctx.send("🔇 Спочатку підключись до голосового каналу!")
        return

    try:
        info = ytdl.extract_info(search, download=False)
        if 'entries' in info:
            info = info['entries'][0]
        url = info.get('url')
        title = info.get('title', 'пісню')
        if not url:
            await ctx.send("❌ Не вдалося отримати аудіо. Спробуй інше.")
            return
        song_queue.append((title, url, ctx))
        await ctx.send(f"📥 Додано до черги: **{title}**")

        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await play_next_song(ctx)

    except Exception as e:
        err_msg = str(e).lower()
        if "unable to extract" in err_msg:
            await ctx.send("❌ Не вдалося знайти пісню за цим запитом. Спробуйте інший пошук.")
        elif "unsupported url" in err_msg:
            await ctx.send("❌ Непідтримуване посилання. Спробуйте іншу URL або ключові слова.")
        else:
            await ctx.send(f"❌ Сталася помилка: {str(e)}")


# Відтворення наступної пісні
async def play_next_song(ctx):
    if song_queue:
        title, url, original_ctx = song_queue.popleft()
        vc = ctx.voice_client
        try:
            if not vc:
                vc = await ctx.author.voice.channel.connect()
        except Exception as e:
            await ctx.send(f"❌ Помилка підключення до голосового каналу: {str(e)}")
            return

        def after_playing(error):
            if error:
                print(f"🎵 Помилка відтворення: {error}")
            fut = play_next_song(ctx)
            bot.loop.call_soon_threadsafe(lambda: bot.loop.create_task(fut))

        try:
            source = discord.FFmpegPCMAudio(url, **ffmpeg_options)
            vc.play(source, after=after_playing)
            view = MusicControlButtons(ctx)
            try:
                bot.loop.create_task(ctx.send(f"🎶 Зараз грає: **{title}**", view=view))
            except:
                pass
        except Exception as e:
            await ctx.send(f"❌ Помилка при відтворенні: {str(e)}")
    else:
        vc = ctx.voice_client
        if vc:
            if members_count(vc) == 0:
                await vc.disconnect()
                await ctx.send("📭 Черга завершена. В голосовому каналі нікого нема, бот вийшов.")
            else:
                await ctx.send("📭 Черга завершена. Бот залишився в голосовому каналі.")


# Команда для перегляду черги
@bot.command()
async def queue(ctx):
    if song_queue:
        msg = "\n".join([f"{i+1}. {title}" for i, (title, _, _) in enumerate(song_queue)])
        await ctx.send(f"📃 Черга:\n{msg}")
    else:
        await ctx.send("📭 Черга пуста.")


@bot.event
async def on_ready():
    print(f'✅ Бот запущено як {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Синхронізовано {len(synced)} команд.")
    except Exception as e:
        print(f"❌ Помилка sync: {e}")


# 🔐 Встав свій токен сюди
bot.run("MTI5MTgyODU3MDMxMzg1MDk2Mg.Gj0z5Y.bj8_jkXc9Rcd7crf0DRoeTJZmEdIfuteYhWoI4")
