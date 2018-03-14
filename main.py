import logging

import tweepy
from envparse import Env
from telegram.ext import CommandHandler, Updater, Filters
from telegram.ext.messagehandler import MessageHandler

from bot import TwitterForwarderBot
from commands import *
from job import FetchAndSendTweetsJob

env = Env(
    TWITTER_CONSUMER_KEY=str,
    TWITTER_CONSUMER_SECRET=str,
    TWITTER_ACCESS_TOKEN=str,
    TWITTER_ACCESS_TOKEN_SECRET=str,
    TELEGRAM_BOT_TOKEN=str,
)


if __name__ == '__main__':

    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.WARNING)

    logging.getLogger(TwitterForwarderBot.__name__).setLevel(logging.DEBUG)
    logging.getLogger(FetchAndSendTweetsJob.__name__).setLevel(logging.DEBUG)

    # initialize Twitter API
    auth = tweepy.OAuthHandler(env('TWITTER_CONSUMER_KEY'), env('TWITTER_CONSUMER_SECRET'))
    twapi = tweepy.API(auth)

    # initialize telegram API
    token = env('TELEGRAM_BOT_TOKEN')
    updater = Updater(bot=TwitterForwarderBot(token, twapi))
    dispatcher = updater.dispatcher

    # set commands
    dispatcher.add_handler(CommandHandler('start', cmd_start))
    dispatcher.add_handler(CommandHandler('help', cmd_help))
    dispatcher.add_handler(CommandHandler('ping', cmd_ping))
    dispatcher.add_handler(CommandHandler('wipe', cmd_wipe))
    dispatcher.add_handler(CommandHandler('source', cmd_source))
    dispatcher.add_handler(CommandHandler('auth', cmd_get_auth_url))
    dispatcher.add_handler(CommandHandler('verify', cmd_verify, pass_args=True))
    dispatcher.add_handler(CommandHandler('set_timezone', cmd_set_timezone, pass_args=True))
    dispatcher.add_handler(MessageHandler(Filters.text, handle_chat))

    # put job
    updater.job_queue.run_repeating(
        lambda bot, job: job.context.run(bot),
        60*3,
        first=0,
        context=FetchAndSendTweetsJob()
    )

    # poll
    updater.start_polling()
