import html
import logging
import math
import re
from datetime import datetime
from threading import Event

import tweepy

from models import Tweet, Media, db, TelegramChat

class FetchAndSendTweetsJob():
    def __init__(self, context=None):
        self.logger = logging.getLogger(self.__class__.__name__)

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
                self.logger.debug("- Got tweet #{} @{}: {}".format(tweet.id, tweet.author.screen_name, tweet.full_text))

                t = self.parse_tweet(tweet)

                # save the latest tweet sent to chat
                self.logger.debug("- Setting id: {}".format(tweet.id))
                tg_chat.last_tweet_id = tweet.id

                bot.send_tweet(tg_chat, t)

            tg_chat.save()

        self.logger.debug("Cleaning up TelegramChats marked for deletion")
        for chat in TelegramChat.select().where(TelegramChat.delete_soon == True):
            chat.delete_instance(recursive=True)
            self.logger.debug("Deleting chat {}".format(chat.chat_id))
    
    def parse_tweet(self, tweet) -> Tweet:
        t = Tweet(
            id=tweet.id,
            text=html.unescape(tweet.full_text),
            created_at=tweet.created_at,
            user_name=tweet.author.name,
            user_screen_name=tweet.author.screen_name,
       )

        if hasattr(tweet, 'retweeted_status'):
            t.text = u'\u267B' + ' @' + tweet.retweeted_status.user.screen_name + ': ' + html.unescape(tweet.retweeted_status.full_text)

        if hasattr(tweet, 'quoted_status'):
            t.text = re.sub(r' https://t\.co/[1-9a-zA-Z]+$', r'', t.text) + "\n"
            t.text += u'\u267B' + ' @' + tweet.quoted_status['user']['screen_name'] + ': ' + html.unescape(tweet.quoted_status['full_text'])
            tweet.entities['urls'] = []
            if 'extended_entities' in tweet.quoted_status:
                self.parse_tweet_media(t, tweet.quoted_status['extended_entities'])

        if hasattr(tweet, 'extended_entities'):
            self.parse_tweet_media(t, tweet.extended_entities)
        elif tweet.entities['urls']:
            t.link_url = tweet.entities['urls'][0]['expanded_url']
        
        for url_entity in tweet.entities['urls']:
            expanded_url = url_entity['expanded_url']
            indices = url_entity['indices']
            display_url = tweet.full_text[indices[0]:indices[1]]
            t.text = t.text.replace(display_url, expanded_url)

        return t

    def parse_tweet_media(self, tweet: Tweet, extended_entities: list):
        for entity in extended_entities['media']:
            tweet.text = tweet.text.replace(entity['url'], '')
            if 'video_info' in entity:
                video_urls = entity['video_info']['variants']
                video_url = max([video for video in video_urls if ('bitrate') in video],key=lambda x:x['bitrate'])['url']
                tweet.media_list.append(Media('video', video_url))
                self.logger.debug("- - Found video URL in tweet: " + video_url)
            else:
                photo_url = entity['media_url_https']
                tweet.media_list.append(Media('photo', photo_url))
                self.logger.debug("- - Found photo URL in tweet: " + photo_url)
