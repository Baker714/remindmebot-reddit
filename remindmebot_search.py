#!/usr/bin/env python2.7

# =============================================================================
# IMPORTS
# =============================================================================

import praw
import re
import MySQLdb
import ConfigParser
import time
import urllib
import parsedatetime.parsedatetime as pdt
from datetime import datetime, timedelta
from requests.exceptions import HTTPError, ConnectionError, Timeout
from praw.errors import ExceptionList, APIException, InvalidCaptcha, InvalidUser, RateLimitExceeded
from socket import timeout
from pytz import timezone
from threading import Thread

# =============================================================================
# GLOBALS
# =============================================================================

# Reads the config file
config = ConfigParser.ConfigParser()
config.read("remindmebot.cfg")

#Reddit info
user_agent = ("RemindMeBot v2.0 by /u/RemindMeBotWrangler")
reddit = praw.Reddit(user_agent = user_agent)
USER = config.get("Reddit", "username")
PASS = config.get("Reddit", "password")

DB_USER = config.get("SQL", "user")
DB_PASS = config.get("SQL", "passwd")
# =============================================================================
# CLASSES
# =============================================================================

class Connect(object):
    """
    DB connection class
    """
    connection = None
    cursor = None

    def __init__(self):
        self.connection = MySQLdb.connect(
            host="localhost", user=DB_USER, passwd=DB_PASS, db="bot"
        )
        self.cursor = self.connection.cursor()

class Search(object):
    commented = [] # comments already replied to
    subId = [] # reddit threads already replied in

    def __init__(self, comment):
        self._addToDB = Connect()
        self.comment = comment # Reddit comment Object
        self._messageInput = '"Hello, I\'m here to remind you to see the parent comment!"'
        self._storeTime = None
        self._replyMessage = ""
        self._replyDate = None
        self._privateMessage = False

    def run(self, privateMessage=False):
        if privateMessage == True:
            self._privateMessage = True
        self.parse_comment()
        self.save_to_db()
        self.build_message()
        self.reply()

    def parse_comment(self):
        """
        Parse comment looking for the message and time
        """

        if self._privateMessage == True:
            permalinkTemp = re.search('\[(.*?)\]', self.comment.body)
            if permalinkTemp:
                self.comment.permalink = permalinkTemp.group()[1:-1]
                # Makes sure the URL is real
                try:
                    urllib.urlopen(self.comment.permalink)
                except IOError:
                    self.comment.permalink = "http://www.reddit.com/r/RemindMeBot/comments/24duzp/remindmebot_info/"
            else:
                # Defaults when the user doesn't provide a link
                self.comment.permalink = "http://www.reddit.com/r/RemindMeBot/comments/24duzp/remindmebot_info/"

        # remove RemindMe! and everything before
        match = re.search(r'RemindMe!', self.comment.body)
        tempString = self.comment.body[match.start():]

        # Use message default if not found
        messageInputTemp = re.search('(["].{0,9000}["])', tempString)
        if messageInputTemp:
            self._messageInput = messageInputTemp.group()
        # Remove RemindMe!
        self._storeTime = re.sub('(["].{0,9000}["])', '', tempString)[9:]
    def save_to_db(self):
        """
        Saves the permalink comment, the time, and the message to the DB
        """

        cal = pdt.Calendar()
        if cal.parse(self._storeTime)[1] == 0:
            # default time
            holdTime = cal.parse("1 day", datetime.now(timezone('UTC')))
        else:
            holdTime = cal.parse(self._storeTime, datetime.now(timezone('UTC')))
        # Converting time
        #9999/12/31 HH/MM/SS
        self._replyDate = time.strftime('%Y-%m-%d %H:%M:%S', holdTime[0])
        cmd = "INSERT INTO message_date VALUES (%s, %s, %s, %s)"
        self._addToDB.cursor.execute(cmd, (
                        self.comment.permalink, 
                        self._messageInput, 
                        self._replyDate, 
                        self.comment.author))
        self._addToDB.connection.commit()
        self._addToDB.connection.close()
        # Info is added to DB, user won't be bothered a second time
        self.commented.append(self.comment.id)

    def build_message(self):
        """
        Buildng message for user
        """
        self._replyMessage =(
            "I'll message you on [**{0} UTC**](http://www.wolframalpha.com/input/?i={0} UTC To Local Time)"
            " to remind you of this post."
            "{remindMeMessage}"
            "\n\n_____\n ^(I will PM you a message so you don't forget about the comment"
            " or thread later on. Just use the **RemindMe!** command and optional date formats. "
            "Subsequent confirmations in this unique thread will be sent through PM to avoid spam."
            " Default wait is a day.)\n\n"
            "[^([PM Reminder])](http://www.reddit.com/message/compose/?to=RemindMeBot&subject=Reminder&message="
            "[LINK HERE else default to FAQs]%0A%0ANOTE: Don't forget to add time options after RemindMe command!"
            "%0A%0ARemindMe!) ^| "
            "[^([FAQs])](http://www.reddit.com/r/RemindMeBot/comments/24duzp/remindmebot_info/) ^| "
            "[^([Time Options])](http://www.reddit.com/r/RemindMeBot/comments/2862bd/remindmebot_date_options/) ^| "
            "[^([Suggestions])](http://www.reddit.com/message/compose/?to=RemindMeBotWrangler&subject=Suggestion) ^| "
            "[^([Code])](https://github.com/SIlver--/remindmebot-reddit)"
        )
        if self._privateMessage == False:
            remindMeMessage = (
                "\n\n[**Click Here**](http://www.reddit.com/message/compose/?to=RemindMeBot&subject=Reminder&message="
                "[{permalink}]%0ANOTE: MAKE SURE THE TIME OPTIONS ARE CORRECT.%0AEXAMPLE: RemindMe 48"
                " hours/days/weeks/months etc%0A%0ARemindMe! {time}) to also be reminded and to reduce spam.").format(
                    permalink=self.comment.permalink,
                    time=self._storeTime.replace('\n', '')
                )
        else:
            remindMeMessage = ""
        self._replyMessage = self._replyMessage.format(
                self._replyDate,
                remindMeMessage=remindMeMessage)

    def reply(self):
        """
        Messages the user letting as a confirmation
        """
        author = self.comment.author
        try:
            if self._privateMessage == False:
                sub = reddit.get_submission(self.comment.permalink)
                # First message will be a reply in a thread
                # afterwards are PM in the same thread
                if (sub.id not in self.subId):
                    self.comment.reply(self._replyMessage)
                    self.subId.append(sub.id)
                else:
                    reddit.send_message(author, 'RemindMeBot Reminder!', self._replyMessage)
            else:
                reddit.send_message(author, 'RemindMeBot Reminder!', self._replyMessage)
        except (HTTPError, ConnectionError, Timeout, timeout) as err:
            print err
            # PM instead if the banned from the subreddit
            if str(err) == "403 Client Error: Forbidden":
                reddit.send_message(author, 'RemindMeBot Reminder!', self._replyMessage)
        except RateLimitExceeded as err:
            print err
            # PM when I message too much
            reddit.send_message(author, 'RemindMeBot Reminder!', self._replyMessage)
            time.sleep(10)
        except APIException as err: # Catch any less specific API errors
            print err
        else:
            print self._replyMessage
class ReadPM(Thread):
    """
    Allows PMs to also work
    """
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self.start()

    def run(self):
        while True:
            for comment in reddit.get_unread(unset_has_mail=True, update_user=True):
                redditPM = Search(comment)
                if "RemindMe!" in comment.body and str(type(comment)) == "<class 'praw.objects.Message'>":
                    redditPM.run(privateMessage=True)
                    comment.mark_as_read()
            time.sleep(30)

# =============================================================================
# MAIN
# =============================================================================

def main():
    reddit.login(USER, PASS)
    print "start"
    ReadPM()
    while True:
        try:
            # loop through each comment
            for comment in praw.helpers.comment_stream(reddit, 'all', limit=1000, verbosity=0):
                redditCall = Search(comment)
                if ("RemindMe!" in comment.body and 
                    redditCall.comment.id not in redditCall.commented and
                    'RemindMeBot' != str(comment.author)):
                        print "in"
                        t = Thread(target=redditCall.run())
                        t.start()
        except Exception as err:
           print err
# =============================================================================
# RUNNER
# =============================================================================

if __name__ == '__main__':
    main()
