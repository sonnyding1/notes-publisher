import argparse
from datetime import datetime
import re
from dotenv import load_dotenv
import os
import logging
import logging.config
import json
import tweepy
import discord
import atproto
import openai

# TODO: discord message char limit is at 2000, should I handle that too? I don't think it's easy to reach that limit anyways tho...
# TODO: logging may have queue handler, but right now I can't figure out how to use it
# TODO: add testing


logger = logging.getLogger("a")


def valid_date(value):
    if not re.match(r"\d{4}-\d{2}-\d{2}", value):
        raise argparse.ArgumentTypeError(
            f"Invalid date format. Please enter in the format of YYYY-MM-DD."
        )
    return value


def fetch_content(current_date):
    file_path = f"../diary/{current_date}.md"
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            content = file.read()
            content = content.split("## 生活")[0].strip()
            content = content.split("## 学习")[1].strip()
            logger.info("fetched diary content:\n" + content)
            return content
    else:
        logger.error(f"diary not found for date {current_date}")


def llm_summarize(content: str, char_limit: int):
    threshold = 5
    client = openai.OpenAI()
    while len(content) > char_limit and threshold > 0:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "developer",
                    "content": f"Summarize texts given to you to under {char_limit} characters",
                },
                {"role": "user", "content": content},
            ],
        )
        content = completion.choices[0].message.content
        logger.info(f"summarized text with len {len(content)}:\n{content}")
        threshold -= 1
    return content


def post_on_x(content):

    client = tweepy.Client(
        consumer_key=os.environ.get("consumer_key"),
        consumer_secret=os.environ.get("consumer_secret"),
        access_token=os.environ.get("access_token"),
        access_token_secret=os.environ.get("access_token_secret"),
    )
    topics = content.split("\n\n")
    while topics:
        topic = topics.pop(0)
        if len(topic) > 280:
            post = client.create_tweet(text=llm_summarize(topic, 280))
        else:
            post = client.create_tweet(text=topic)
        logger.info(f"Posted on X: https://twitter.com/user/status/{post.data['id']}")


def post_on_bluesky(content):
    client = atproto.Client()
    client.login(os.environ.get("username"), os.environ.get("password"))
    topics = content.split("\n\n")
    topic = topics.pop(0)
    if len(topic) > 300:
        post = client.send_post(text=llm_summarize(topic, 300))
    else:
        post = client.send_post(text=topic)
    parent = atproto.models.create_strong_ref(post)
    root = atproto.models.create_strong_ref(post)
    for topic in topics:
        if len(topic) > 300:
            post = client.send_post(
                text=llm_summarize(topic, 300),
                reply_to=atproto.models.AppBskyFeedPost.ReplyRef(
                    parent=parent, root=root
                ),
            )
        else:
            post = client.send_post(
                text=topic,
                reply_to=atproto.models.AppBskyFeedPost.ReplyRef(
                    parent=parent, root=root
                ),
            )
        parent = atproto.models.create_strong_ref(post)
    logger.info("Posted on Bluesky")


def post_on_discord(content):
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        # print(f"We have logged in as {client.user}")
        # 938664591435640882
        channel_ids = [960399383088758794]
        for channel_id in channel_ids:
            channel = client.get_channel(channel_id)
            await channel.send(content)
            logger.info("Posted on Discord")
        await client.close()

    client.run(os.environ.get("token"))


def main():
    today = datetime.today().strftime("%Y-%m-%d")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date", type=valid_date, default=today, help="Date in YYYY-MM-DD format"
    )
    args = parser.parse_args()

    load_dotenv()

    with open("logging_configs/config.json") as f:
        logging_config = json.load(f)
    logging.config.dictConfig(config=logging_config)
    logger.info("logger started")

    content = fetch_content(args.date)
    if not content:
        return

    post_on_x(content)
    post_on_bluesky(content)
    post_on_discord(content)


if __name__ == "__main__":
    main()
