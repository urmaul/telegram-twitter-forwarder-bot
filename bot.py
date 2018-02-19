import logging

import telegram
import tweepy
from pytz import timezone, utc
from telegram import Bot
from telegram.error import TelegramError

from models import TelegramChat
from util import escape_markdown, prepare_tweet_text


class TwitterForwarderBot(Bot):

    def __init__(self, token, tweepy_api_object, update_offset=0):
        super().__init__(token=token)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info("Initializing")
        self.update_offset = update_offset
        self.tw = tweepy_api_object

    def reply(self, update, text, *args, **kwargs):
        self.sendMessage(chat_id=update.message.chat.id, text=text, *args, **kwargs)

    def send_tweet(self, chat, tweet):
        try:
            self.logger.debug("Sending tweet {} to chat {}...".format(
                tweet.tw_id, chat.chat_id
            ))

            '''
            Use a soft-hyphen to put an invisible link to the first
            image in the tweet, which will then be displayed as preview
            '''
            media_url = ''
            if tweet.video_url:
                media_url = '[\xad](%s)' % tweet.video_url
            if tweet.photo_url:
                media_url = '[\xad](%s)' % tweet.photo_url

            created_dt = utc.localize(tweet.created_at)
            if chat.timezone_name is not None:
                tz = timezone(chat.timezone_name)
                created_dt = created_dt.astimezone(tz)
            created_at = created_dt.strftime('%Y-%m-%d %H:%M:%S %Z')
            self.sendMessage(
                chat_id=chat.chat_id,
                disable_web_page_preview=not media_url,
                text="""
{link_preview}*{name}* ([@{screen_name}](https://twitter.com/{screen_name}/status/{tw_id})):
{text}
"""
                    .format(
                    link_preview=media_url,
                    text=prepare_tweet_text(tweet.text),
                    name=escape_markdown(tweet.name),
                    screen_name=tweet.screen_name,
                    created_at=created_at,
                    tw_id=tweet.tw_id,
                ),
                parse_mode=telegram.ParseMode.MARKDOWN)
            
        except TelegramError as e:
            self.logger.info("Couldn't send tweet {} to chat {}: {}".format(
                tweet.tw_id, chat.chat_id, e.message
            ))

            delet_this = None

            if e.message == 'Bad Request: group chat was migrated to a supergroup chat':
                delet_this = True

            if e.message == "Unauthorized":
                delet_this = True

            if delet_this:
                self.logger.info("Marking chat for deletion")
                chat.delete_soon = True
                chat.save()

    def get_chat(self, tg_chat):
        db_chat, _created = TelegramChat.get_or_create(
            chat_id=tg_chat.id,
            tg_type=tg_chat.type,
        )
        return db_chat
