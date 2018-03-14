import json
from datetime import datetime

from pytz import timezone
from pytz.exceptions import UnknownTimeZoneError
import telegram
import tweepy
from tweepy.auth import OAuthHandler
from tweepy.error import TweepError

#from models import Subscription
from util import with_touched_chat, escape_markdown, markdown_twitter_usernames

TIMEZONE_LIST_URL = "https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"

def cmd_ping(bot, update):
    bot.reply(update, 'Pong!')


@with_touched_chat
def cmd_start(bot, update, chat=None):
    bot.reply(
        update,
        "Hello! This bot lets you subscribe to twitter accounts and receive their tweets here! "
        "Check out /help for more info.")


@with_touched_chat
def cmd_help(bot, update, chat=None):
        bot.reply(update, """
Hello! This bot forwards you updates from twitter streams!
Here's the commands:
- /wipe - remove all the data about you and your subscriptions
- /auth - start Twitter authorization process
- /verify - send Twitter verifier code to complete authorization process
- /set\_timezone - set your [timezone name]({}) (for example Asia/Tokyo)
- /source - info about source code
- /help - view help text
This bot is being worked on, so it may break sometimes. Maker of original bot @franciscod cares, I don't {}
""".format(
            TIMEZONE_LIST_URL,
            u'\U0001F604'),
                  disable_web_page_preview=True,
                  parse_mode=telegram.ParseMode.MARKDOWN)

@with_touched_chat
def cmd_wipe(bot, update, chat=None):
    bot.reply(update, "Okay, I'm forgetting about this chat. " +
                    " Come back to me anytime you want. Goodbye!")
    chat.delete_instance(recursive=True)


@with_touched_chat
def cmd_source(bot, update, chat=None):
    bot.reply(update, "This bot is Free Software under the LGPLv3. "
                    "You can get the code from here: "
                    "https://github.com/urmaul/telegram-twitter-forwarder-bot"
                    "It's a fork of this bot: "
                    "https://github.com/franciscod/telegram-twitter-forwarder-bot")


@with_touched_chat
def cmd_get_auth_url(bot, update, chat):
    auth = OAuthHandler(bot.tw.auth.consumer_key, bot.tw.auth.consumer_secret)
    auth_url = auth.get_authorization_url()
    chat.twitter_request_token = json.dumps(auth.request_token)
    chat.save()
    msg = "go to [this url]({}) and send me your verifier code using /verify code"
    bot.reply(update, msg.format(auth_url),
              parse_mode=telegram.ParseMode.MARKDOWN)


@with_touched_chat
def cmd_verify(bot, update, args, chat):
    if not chat.twitter_request_token:
        bot.reply(update, "Use /auth command first")
        return
    if len(args) < 1:
        bot.reply(update, "No verifier code specified")
        return
    verifier_code = args[0]
    auth = OAuthHandler(bot.tw.auth.consumer_key, bot.tw.auth.consumer_secret)
    auth.request_token = json.loads(chat.twitter_request_token)
    try:
        auth.get_access_token(verifier_code)
    except TweepError:
        bot.reply(update, "Invalid verifier code. Use /auth again")
        return
    chat.twitter_token = auth.access_token
    chat.twitter_secret = auth.access_token_secret
    chat.save()
    bot.reply(update, "Access token setup complete")
    api = tweepy.API(auth)
    settings = api.get_settings()
    tz_name = settings.get("time_zone", {}).get("tzinfo_name")
    cmd_set_timezone(bot, update, [tz_name])


@with_touched_chat
def cmd_set_timezone(bot, update, args, chat):
    if len(args) < 1:
        bot.reply(update,
            "No timezone specified. Find yours [here]({})!".format(TIMEZONE_LIST_URL),
            parse_mode=telegram.ParseMode.MARKDOWN)
        return

    tz_name = args[0]

    try:
        tz = timezone(tz_name)
        chat.timezone_name = tz_name
        chat.save()
        tz_str = datetime.now(tz).strftime('%Z %z')
        bot.reply(update, "Timezone is set to {}".format(tz_str))
    except UnknownTimeZoneError:
        bot.reply(update,
            "Unknown timezone. Find yours [here]({})!".format(TIMEZONE_LIST_URL),
            parse_mode=telegram.ParseMode.MARKDOWN)


@with_touched_chat
def handle_chat(bot, update, chat=None):
    bot.reply(update, "Hey! Use commands to talk with me, please! See /help")
