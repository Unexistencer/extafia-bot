from discord.ext import commands
from discord import app_commands, Interaction
import discord
import asyncio

from constants import Category
from msg_utils import ToggleView, MessageResolver
import service.choose_service
import service.choose_input_service as choose_input

from logger import logger, generate_task_num


class ChooseCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------- /choose --------
    @app_commands.command(name="choose", description="Choose one for you")
    @app_commands.describe(
        options="split options by space: Panda Lumi GAY",
        image="upload an image to OCR choices from",
    )
    async def choose(
        self,
        interaction: Interaction,
        options: str | None = None,
        image: discord.Attachment | None = None
    ):
        task_num = generate_task_num()
        logger.info(
            f"[{task_num}] /choose invoked by {interaction.user} #{interaction.user.id} "
            f"in guild {interaction.guild} #{interaction.guild.id}"
        )

        await interaction.response.defer(ephemeral=False)

        try:
            resolver = MessageResolver(interaction.guild.id, interaction.user.id)
            options_label = await resolver.get(Category.CHOOSE, "ui", "options")
            result_label = await resolver.get(Category.CHOOSE, "ui", "result")
            forbidden_message = await resolver.get(Category.CHOOSE, "ui", "forbidden")

            items = await choose_input.resolve_items_from_interaction(
                guild_id=interaction.guild.id,
                user_id=interaction.user.id,
                options=options,
                image=image,
            )

            embeds = await service.choose_service.choose(
                task_num,
                interaction.guild.id,
                interaction.user.id,
                items
            )

            options_embed = await choose_input.build_options_embed(interaction.guild.id, interaction.user.id, items)

            if isinstance(embeds, list):
                pages = [embeds[1], options_embed]
                view = ToggleView(
                    result_embed=pages[0],
                    choices_embed=pages[1],
                    owner_id=interaction.user.id,
                    options_label=options_label,
                    result_label=result_label,
                    forbidden_message=forbidden_message,
                    timeout=180,
                )

                await interaction.followup.send(embed=embeds[0])
                await asyncio.sleep(5)
                
                msg =  await interaction.followup.send(embed=pages[0], view=view)
                view.message = msg
            else:
                pages = [embeds, options_embed]
                view = ToggleView(
                    result_embed=pages[0],
                    choices_embed=pages[1],
                    owner_id=interaction.user.id,
                    options_label=options_label,
                    result_label=result_label,
                    forbidden_message=forbidden_message,
                    timeout=180,
                )

                msg =  await interaction.followup.send(embed=pages[0], view=view)
                view.message = msg

        except choose_input.ChooseInputError as e:
            resolver = MessageResolver(interaction.guild.id, interaction.user.id)
            error_title = await resolver.get(Category.CHOOSE, "ui", "error_title")
            embed = discord.Embed(title=error_title, description=e.user_message, color=discord.Color.red())
            await interaction.followup.send(embed=embed)

    # -------- .choose (non-slash command) --------
    @commands.command(name="choose")
    async def choose_prefix(self, ctx: commands.Context, *, options: str = ""):
        async with ctx.typing():
            task_num = generate_task_num()
            guild_id = ctx.guild.id if ctx.guild else 0
            user_id = ctx.author.id

            logger.info(
                f"[{task_num}] .choose invoked by {ctx.author} #{user_id} "
                f"in guild {ctx.guild} #{guild_id}"
            )

            try:
                resolver = MessageResolver(guild_id, user_id)
                options_label = await resolver.get(Category.CHOOSE, "ui", "options")
                result_label = await resolver.get(Category.CHOOSE, "ui", "result")
                forbidden_message = await resolver.get(Category.CHOOSE, "ui", "forbidden")

                items = await choose_input.resolve_items_from_message(
                    guild_id=guild_id,
                    user_id=user_id,
                    message=ctx.message,
                    channel=ctx.channel,
                    options=options
                )

                embeds = await service.choose_service.choose(task_num, guild_id, user_id, items)

                options_embed = await choose_input.build_options_embed(guild_id, user_id, items)

                if isinstance(embeds, list):
                    pages = [embeds[1], options_embed]
                    view = ToggleView(
                        result_embed=pages[0],
                        choices_embed=pages[1],
                        owner_id=ctx.author.id,
                        options_label=options_label,
                        result_label=result_label,
                        forbidden_message=forbidden_message,
                        timeout=180,
                    )

                    await ctx.send(embed=embeds[0])
                    await asyncio.sleep(5)
                    
                    msg =  await ctx.send(embed=pages[0], view=view)
                    view.message = msg
                else:
                    pages = [embeds, options_embed]
                    view = ToggleView(
                        result_embed=pages[0],
                        choices_embed=pages[1],
                        owner_id=ctx.author.id,
                        options_label=options_label,
                        result_label=result_label,
                        forbidden_message=forbidden_message,
                        timeout=180,
                    )

                    msg =  await ctx.send(embed=pages[0], view=view)
                    view.message = msg


            except choose_input.ChooseInputError as e:
                resolver = MessageResolver(guild_id, user_id)
                error_title = await resolver.get(Category.CHOOSE, "ui", "error_title")
                embed = discord.Embed(title=error_title, description=e.user_message, color=discord.Color.red())
                await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChooseCog(bot))
