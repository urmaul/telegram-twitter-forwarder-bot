import logging

import telegram
import tweepy
from pytz import timezone, utc
from telegram import Bot, InputMedia, InputMediaPhoto, InputMediaVideo
from telegram.error import TelegramError

from models import TelegramChat, Tweet, Media
from util import escape_markdown, prepare_tweet_text


class TwitterForwarderBot(Bot):
    MESSAGE_TEMPLATE="""
{link_preview}*{name}* ([@{screen_name}](https://twitter.com/{screen_name}/status/{id})):
{text}
"""

    def __init__(self, token, tweepy_api_object, update_offset=0):
        super().__init__(token=token)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info("Initializing")
        self.update_offset = update_offset
        self.tw = tweepy_api_object

    def reply(self, update, text, *args, **kwargs):
        self.sendMessage(chat_id=update.message.chat.id, text=text, *args, **kwargs)

    def send_tweet(self, chat, tweet: Tweet):
        try:
            self.logger.debug("Sending tweet {} to chat {}...".format(
                tweet.id, chat.chat_id
            ))

            '''
            Use a soft-hyphen to put an invisible link to the first
            image in the tweet, which will then be displayed as preview
            '''
            media_url = ''
            if len(tweet.media_list) == 1:
                media_url = '[\xad](%s)' % tweet.media_list[0].url
            elif tweet.link_url:
                media_url = '[\xad](%s)' % tweet.link_url

            self.sendMessage(
                chat_id=chat.chat_id,
                disable_web_page_preview=not media_url,
                text=self.MESSAGE_TEMPLATE.format(
                    link_preview=media_url,
                    text=prepare_tweet_text(tweet.text),
                    name=escape_markdown(tweet.user_name),
                    screen_name=tweet.user_screen_name,
                    id=tweet.id,
                ),
                parse_mode=telegram.ParseMode.MARKDOWN
            )

            if len(tweet.media_list) > 1:
                self.sendMediaGroup(
                    chat_id=chat.chat_id,
                    media=map(self.create_input_media, tweet.media_list),
                )
            
        except TelegramError as e:
            self.logger.info("Couldn't send tweet {} to chat {}: {}".format(
                tweet.id, chat.chat_id, e.message
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
    
    def create_input_media(self, media: Media) -> InputMedia:
        if media.type == 'video':
            return InputMediaVideo(media.url)
        else:
            return InputMediaPhoto(media.url)
