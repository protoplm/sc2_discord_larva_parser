

import discord
from discord.ext import commands
import sc2reader
from plotly.offline import plot
import plotly.graph_objs as go
import parse_larva
import io

# Authorization Key: ##

reaction_contexts = {}

TOKEN = '##'

intents = discord.Intents.default()
intents.messages = True 
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

#Some nonsense to alter the !help command. What a library
class CustomHelpCommand(commands.HelpCommand):
    def get_command_signature(self, command):
        return f'{self.context.clean_prefix}{command.qualified_name} {command.signature}'

    async def send_bot_help(self, mapping):
        embed = discord.Embed(title="Evolution Chamber", description="Here are the available commands:", color=discord.Color.dark_purple())
        for cog, commands in mapping.items():
            filtered = await self.filter_commands(commands, sort=True)
            for command in filtered:
                embed.add_field(name=self.get_command_signature(command), value=command.help, inline=False)

        await self.context.send(embed=embed)

bot.help_command = CustomHelpCommand()



@bot.command(name='analyze', help="Use the analyze command to view metrics from a single replay")
async def analyze_replay(ctx):
    if ctx.message.attachments:
        if len(ctx.message.attachments) == 1:
            attachment = ctx.message.attachments[0]
            if attachment.filename.lower().endswith('.sc2replay'):
                file_path = f'./{attachment.filename}'
                await attachment.save(file_path)
                players = parse_larva.player_info(file_path)
                if parse_larva.is_zvz(players):
                    embed = discord.Embed(
                        title="ZvZ Detected",
                        description="This is a ZvZ, please select which player to analyze by reacting to this message:",
                        color=discord.Color.dark_purple()
                    )
                    for idx, player in enumerate(players, start=1):
                        embed.add_field(name=f"Player {idx}", value=f"React with {idx}️⃣ to analyze {player['name']}.", inline=False)
                    embed.set_footer(text="React below to choose a player")
                    message = await ctx.send(embed=embed)

                    # React with the numbers 1 and 2
                    for idx in range(1, len(players) + 1):
                        await message.add_reaction(f"{idx}️⃣")
                    # Store the context using user.id
                    reaction_contexts[ctx.author.id] = {
                        "message_id": message.id,  # one message id for analyze
                        "replay_file": file_path,
                        "players": players,
                        "type": "analyze"
                    }
                else:
                    image_bytes = parse_larva.all_in(file_path)
                    file = discord.File(fp=io.BytesIO(image_bytes), filename='image.png')
                    await ctx.send(file=file)
            else:
                await ctx.send('Please attach a valid StarCraft II replay file with the .SC2Replay extension.')
        elif len(ctx.message.attachments) == 2:
            await ctx.send('Wrong command, please use !compare')
        elif len(ctx.message.attachments) > 2:
            await ctx.send('Please attach only one replay file for the analyze command.')
    else:
        await ctx.send('Else condition triggered: message has no attachments')       

@bot.event
async def on_reaction_add(reaction, user):
    if user != bot.user and user.id in reaction_contexts:
        context = reaction_contexts[user.id]

@bot.event
async def on_reaction_add(reaction, user):
    if user == bot.user:
        return

    context = reaction_contexts.get(user.id)
    print(reaction_contexts)
    if context["type"] == "compare" and reaction.message.id in context.get("message_ids", []):
        replay_index = context["message_ids"].index(reaction.message.id)
        player_index = int(str(reaction.emoji)[0]) - 1
        context["selections"][replay_index] = player_index

        if None not in context["selections"]:
            comparison_replay, benchmark_replay = context["replay_files"]
            player_selection, benchmark_selection = [
                        (s + 1) if isinstance(s, int) else s for s in context["selections"]] # If value is an integer, add one to adjust for 1 based index of the replay (player 1 vs player2), if it's another value, it keeps its value.

            # Call all_in with the structured data
            image_bytes = parse_larva.all_in(comparison_replay, benchmark_replay, player_selection, benchmark_selection)
            file = discord.File(fp=io.BytesIO(image_bytes), filename='comparison.png')
            await reaction.message.channel.send(file=file)
            del reaction_contexts[user.id]
        
    if context["type"] == "analyze" and reaction.message.id == context['message_id']:
            player_index = int(str(reaction.emoji)[0]) - 1
            selected_player = context["players"][player_index]
            image_bytes = parse_larva.all_in(context["replay_file"], player=selected_player["index"])
            file = discord.File(fp=io.BytesIO(image_bytes), filename='analysis.png')
            await reaction.message.channel.send(file=file)
            del reaction_contexts[user.id]
    else:
        return # Unrelated reaction

@bot.command(name='compare', help="Use the compare command to compare metrics between two replays")
async def compare_replays(ctx):
    if len(ctx.message.attachments) != 2:
        await ctx.send("Please attach exactly two replay files.")
        return

    file_paths = []
    players_list = []

    for attachment in ctx.message.attachments:
        if not attachment.filename.lower().endswith('.sc2replay'):
            await ctx.send('Please ensure both files are valid StarCraft II replay files with the .SC2Replay extension.')
            return
        file_path = f'./{attachment.filename}'
        await attachment.save(file_path)
        file_paths.append(file_path)
        players = parse_larva.player_info(file_path)
        players_list.append(players)

    zvz_checks = [parse_larva.is_zvz(players) for players in players_list]
    message_ids = []

    # Handle ZvZ replays
    for i, (is_zvz, players) in enumerate(zip(zvz_checks, players_list)):
        if is_zvz:
            embed = discord.Embed(
                title=f"ZvZ Detected in Replay {i+1}",
                description=f"Select a player for Replay {i+1} by reacting to this message:",
                color=discord.Color.dark_purple()
            )
            for j, player in enumerate(players):
                embed.add_field(name=f"Player {j+1}", value=f"React with {j+1}️⃣ to analyze {player['name']}.", inline=False)
            embed.set_footer(text="React below to choose a player")
            message = await ctx.send(embed=embed)
            await message.add_reaction("1️⃣")
            await message.add_reaction("2️⃣")
            message_ids.append(message.id)

    # Store context only if there's a ZvZ match
    if message_ids:
        reaction_contexts[ctx.author.id] = {
            "message_ids": message_ids,
            "replay_files": file_paths,
            "players_list": players_list,
            "selections": [None if is_zvz else 'not_zvz' for is_zvz in zvz_checks],  # non zvz games passed to all_in will get assigned to None in that function
            "type": "compare"
        }
    else:
        # Directly process if no ZvZ matches
        image_bytes = parse_larva.all_in(file_paths[0], file_paths[1])
        file = discord.File(fp=io.BytesIO(image_bytes), filename='comparison.png')
        await ctx.send(file=file)

bot.run(TOKEN)

