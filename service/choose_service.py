import random
import discord
from constants import *
from msg_utils import MessageResolver
from logger import logger

async def choose(task_num: str, guild_id: int, user_id: int, items: list[str]):
    resolver = MessageResolver(guild_id, user_id)

    if len(items) <= 1:
        logger.info(f"[{task_num}]Not enough choices. items={items}")
        title = await resolver.get(Category.CHOOSE, SubCategory.TITLE, "failed")
        description = await resolver.get(Category.CHOOSE, SubCategory.DESCRIPTION, "failed")
        return discord.Embed(title=title, description=description, color=discord.Color.red())

    num = random.randint(0, len(items) - 1)
    result = str(items[num])

    if len(result) > 1 and not random.randint(0, 99):
        logger.info(f"[{task_num}]Critical Hit!!")

        word1 = items[random.randint(0, len(items) - 1)]
        prefix = str(word1)[:len(str(word1)) // 2]
        items2 = [w for w in items if w is not word1 and str(w)]
        if not items2:
            items2 = items
        word2 = items2[random.randint(0, len(items2) - 1)]
        suffix = str(word2)[len(str(word2)) // 2:]

        fake_result = prefix + suffix  # fake

        title1 = await resolver.get(Category.CHOOSE, SubCategory.TITLE, "success", result=fake_result)
        description1 = await resolver.get(Category.CHOOSE, SubCategory.DESCRIPTION, "success")

        title2 = await resolver.get(Category.CHOOSE, SubCategory.TITLE, "success", result=result)
        description2 = await resolver.get(Category.CHOOSE, SubCategory.DESCRIPTION, "critical")

        embed1 = discord.Embed(title=title1, description=description1, color=discord.Color.green())
        embed2 = discord.Embed(title=title2, description=description2, color=discord.Color.green())
        return [embed1, embed2]
    else:
        logger.info(f"[{task_num}]Normal choose.")

    title = await resolver.get(Category.CHOOSE, SubCategory.TITLE, "success", result=result)
    description = await resolver.get(Category.CHOOSE, SubCategory.DESCRIPTION, "success")
    return discord.Embed(title=title, description=description, color=discord.Color.green())


async def choose_with_result_list(task_num: str, guild_id: int, user_id: int, items: list[str]):
    '''for Image-scan version'''
    resolver = MessageResolver(guild_id, user_id)

    if len(items) <= 1:
        title = await resolver.get(Category.CHOOSE, SubCategory.TITLE, "failed")
        description = await resolver.get(Category.CHOOSE, SubCategory.DESCRIPTION, "failed")
        return {"ok": False, "title": title, "description": description}

    num = random.randint(0, len(items) - 1)
    result = str(items[num])

    # critical
    if len(result) > 1 and random.randint(1, 100) == 100:
        word1 = items[random.randint(0, len(items) - 1)]
        prefix = str(word1)[:len(str(word1)) // 2]
        items2 = [w for w in items if w is not word1 and str(w)]
        if not items2:
            items2 = items
        word2 = items2[random.randint(0, len(items2) - 1)]
        suffix = str(word2)[len(str(word2)) // 2:]
        fake_result = prefix + suffix

        title1 = await resolver.get(Category.CHOOSE, SubCategory.TITLE, "success", result=fake_result)
        description1 = await resolver.get(Category.CHOOSE, SubCategory.DESCRIPTION, "success")
        title2 = await resolver.get(Category.CHOOSE, SubCategory.TITLE, "success", result=result)
        description2 = await resolver.get(Category.CHOOSE, SubCategory.DESCRIPTION, "critical")

        return {
            "ok": True,
            "critical": True,
            "fake": {"title": title1, "description": description1},
            "real": {"title": title2, "description": description2},
        }

    title = await resolver.get(Category.CHOOSE, SubCategory.TITLE, "success", result=result)
    description = await resolver.get(Category.CHOOSE, SubCategory.DESCRIPTION, "success")
    return {
        "ok": True,
        "critical": False,
        "real": {"title": title, "description": description},
    }
