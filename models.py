import datetime

import tweepy
from peewee import (Model, DateTimeField, ForeignKeyField, BigIntegerField, CharField,
                    IntegerField, TextField, OperationalError, BooleanField)
from playhouse.migrate import migrate, SqliteMigrator, SqliteDatabase
from tweepy.auth import OAuthHandler


class TelegramChat(Model):
    chat_id = IntegerField(unique=True)
    known_at = DateTimeField(default=datetime.datetime.now)
    tg_type = CharField()
    last_contact = DateTimeField(default=datetime.datetime.now)
    twitter_request_token = CharField(null=True)
    twitter_token = CharField(null=True)
    twitter_secret = CharField(null=True)
    last_tweet_id = BigIntegerField(default=0)
    timezone_name = CharField(null=True)
    delete_soon = BooleanField(default=False)

    @property
    def is_group(self):
        return self.chat_id < 0

    def touch_contact(self):
        self.last_contact = datetime.datetime.now()
        self.save()

    @property
    def is_authorized(self):
        return self.twitter_token is not None and self.twitter_secret is not None

    def tw_api(self, consumer_key, consumer_secret):
        auth = OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(self.twitter_token, self.twitter_secret)
        return tweepy.API(auth)


class Media:
    def __init__(self, type, url):
        self.type = type
        self.url = url

class Tweet:
    def __init__(self, *args, **kwargs):
        self.id = None
        self.text = None
        self.created_at = None
        self.user_name = None
        self.user_screen_name = None
        self.link_url = ''
        self.media_list = []

        for k in kwargs:
            setattr(self, k, kwargs[k])

# Create tables
TelegramChat.create_table(fail_silently=True)

# Migrate new fields. TODO: think of some better migration mechanism
db = SqliteDatabase('peewee.db', timeout=10)
migrator = SqliteMigrator(db)
operations = [
    migrator.add_column('telegramchat', 'twitter_request_token', TelegramChat.twitter_request_token),
    migrator.add_column('telegramchat', 'twitter_token', TelegramChat.twitter_token),
    migrator.add_column('telegramchat', 'twitter_secret', TelegramChat.twitter_secret),
    migrator.add_column('telegramchat', 'timezone_name', TelegramChat.timezone_name),
    migrator.add_column('telegramchat', 'delete_soon', TelegramChat.delete_soon),
    migrator.add_column('telegramchat', 'last_tweet_id', TelegramChat.last_tweet_id),
]
for op in operations:
    try:
        migrate(op)
    except OperationalError:
        pass
