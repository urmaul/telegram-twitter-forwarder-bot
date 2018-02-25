import html
import logging
import math
import re
from datetime import datetime
from threading import Event

import tweepy
from telegram.error import TelegramError
from telegram.ext import Job

from models import Tweet, db, TelegramChat

INFO_CLEANUP = {
    'NOTFOUND': "Your subscription to @{} was removed because that profile doesn't exist anymore. Maybe the account's name changed?",
    'PROTECTED': "Your subscription to @{} was removed because that profile is protected and can't be fetched.",
}

class FetchAndSendTweetsJob(Job):
    # Twitter API rate limit parameters
    LIMIT_WINDOW = 15 * 60
    LIMIT_COUNT = 300
    MIN_INTERVAL = 60
    TWEET_BATCH_INSERT_COUNT = 100

    @property
    def interval(self):
        # tw_count = (TwitterUser.select()
        #             .join(Subscription)
        #             .group_by(TwitterUser)
        #             .count())
        # if tw_count >= self.LIMIT_COUNT:
        #     return self.LIMIT_WINDOW
        tw_count = 0
        res = math.ceil(tw_count * self.LIMIT_WINDOW / self.LIMIT_COUNT)
        return max(self.MIN_INTERVAL, res)

    def __init__(self, context=None):
        self.repeat = True
        self.context = context
        self.name = self.__class__.__name__
        self._remove = Event()
        self._enabled = Event()
        self._enabled.set()
        self.logger = logging.getLogger(self.name)

    def run(self, bot):
        self.logger.debug("Fetching tweets...")
        tweet_rows = []
        # fetch the tg users' home timelines
        tg_chats = list(TelegramChat.select().where(TelegramChat.twitter_secret != None))

        for tg_chat in tg_chats:
            bot_auth = bot.tw.auth
            tw_api = tg_chat.tw_api(bot_auth.consumer_key, bot_auth.consumer_secret)
            try:
                if tg_chat.last_tweet_id == 0:
                    # get just the 5 latest tweets
                    self.logger.debug(
                        "Fetching 5 latest tweets for {}".format(tg_chat.chat_id))
                    tweets = tw_api.home_timeline(count=5, tweet_mode='extended')
                else:
                    # get the fresh tweets
                    self.logger.debug(
                        "Fetching new tweets from {}".format(tg_chat.last_tweet_id))
                    tweets = tw_api.home_timeline(since_id=tg_chat.last_tweet_id, tweet_mode='extended')
            except tweepy.error.TweepError as e:
                sc = e.response.status_code
                if sc == 429:
                    self.logger.debug("- Hit ratelimit, breaking.")
                    break

                self.logger.debug(
                    "- Unknown exception, Status code {}".format(sc))
                continue

            sorted_tweets = sorted(tweets, key=lambda tweet: tweet.id)

            for tweet in sorted_tweets:
                self.logger.debug("- Got tweet #{}: {}".format(tweet.id, tweet.full_text))

                # Check if tweet contains media, else check if it contains a link to an image
                extensions = ('.jpg', '.jpeg', '.png', '.gif')
                pattern = '[(%s)]$' % ')('.join(extensions)
                video_url = ''
                photo_url = ''
                link_url = ''
                tweet_text = html.unescape(tweet.full_text)

                if hasattr(tweet, 'retweeted_status'):
                    tweet_text = u'\U0001F501' + ' @' + tweet.retweeted_status.user.screen_name + ': ' + html.unescape(tweet.retweeted_status.full_text)

                if hasattr(tweet, 'quoted_status'):
                    tweet_text += "\n" + u'\U0001F501' + ' @' + tweet.quoted_status['user']['screen_name'] + ': ' + html.unescape(tweet.quoted_status['full_text'])
                    tweet.entities['urls'] = []

                if hasattr(tweet, 'extended_entities') and 'media' in tweet.extended_entities:
                    first_media = tweet.extended_entities['media'][0]                    
                    tweet_text = tweet_text.replace(first_media['url'], '')
                    if 'video_info' in first_media:
                        video_urls = first_media['video_info']['variants']
                        video_url = max([video for video in video_urls if ('bitrate') in d ],key=lambda x:x['bitrate'])['url']
                    else:
                        photo_url = first_media['media_url_https']
                elif tweet.entities['urls']:
                    link_url = tweet.entities['urls'][0]['expanded_url']
            
                if video_url:
                    self.logger.debug("- - Found video URL in tweet: " + video_url)
                if photo_url:
                    self.logger.debug("- - Found photo URL in tweet: " + photo_url)
                
                for url_entity in tweet.entities['urls']:
                    expanded_url = url_entity['expanded_url']
                    indices = url_entity['indices']
                    display_url = tweet.full_text[indices[0]:indices[1]]
                    tweet_text = tweet_text.replace(display_url, expanded_url)

                t = Tweet(
                    tw_id=tweet.id,
                    text=tweet_text,
                    created_at=tweet.created_at,
                    # twitter_user=tweet.id,
                    twitter_user_name=tweet.author.name,
                    twitter_user_screen_name=tweet.author.screen_name,
                    photo_url=photo_url,
                    video_url=video_url,
                    link_url=link_url
                )

                # save the latest tweet sent to chat
                self.logger.debug("- Setting id: {}".format(tweet.id))
                tg_chat.last_tweet_id = tweet.id

                bot.send_tweet(tg_chat, t)

            tg_chat.save()

        self.logger.debug("Cleaning up TelegramChats marked for deletion")
        for chat in TelegramChat.select().where(TelegramChat.delete_soon == True):
            chat.delete_instance(recursive=True)
            self.logger.debug("Deleting chat {}".format(chat.chat_id))
