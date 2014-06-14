#!/usr/bin/env python2.7

# =============================================================================
# IMPORTS
# =============================================================================

import praw
import re
import MySQLdb
import ConfigParser
import time
from datetime import datetime, timedelta
from requests.exceptions import HTTPError, ConnectionError, Timeout
from praw.errors import ExceptionList, APIException, InvalidCaptcha, InvalidUser, RateLimitExceeded
from socket import timeout
from pytz import timezone

# =============================================================================
# GLOBALS
# =============================================================================

#Reddit info
USER = config.get("Reddit", "username")
PASS = config.get("Reddit", "password")
DB_USER = config.get("SQL", "user")
DB_PASS = config.get("SQL", "passwd")
DB_TABLE = config.get("SQL", "table")
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

    def execute(self, command):
        self.cursor.execute(command)

    def fetchall(self):
        return self.cursor.fetchall()

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()

class Search(object):
	commented = [] # comments already replied to
	subId = [] # reddit threads already replied in

	def __init__(self, comment):
		self.comment = comment # Reddit comment Object
		self._messageInput = '"Hello, I\'m here to remind you to see the parent comment!"'
		self._totalTime = 0

	def parse_comment(self):
		"""
		Parse comment looking for the message and time
		"""
		# Default Times
		timeDayInt = 1
		timeHourInt = 0

		# check for hours
		# regex: 4.0 or 4 "hour | hours" ONLY
		timeHourTemp = re.search("(?:\d+)?\.*(?:\d+ [hH][oO][uU][rR]([sS]|))", self.comment.body)

		if timeHourTemp:
			# regex: ignores ".0" and non numbers
			timeHourTemp = re.search("\d*", timeHourTemp.group(0))
			timeHourInt = int(timeHourTemp.group(0))

		# check for days
		# regex 4.0 or 4 "day | days" ONLY
		timeDayTemp = re.search("(?:\d+)?\.*(?:\d+ [dD][aA][yY]([sS]|))", self.comment.body)
		if timeDayTemp:
			timeDayTemp = re.search("\d*", timeDayTemp.group(0))
			timeDayInt= int(timeDayTemp.group(0))
		# cases where the user inputs hours but not days
		elif not timeDayTemp and timeHourTemp > 0:
			timeDayInt = 0

		# convert into hours
		self._totalTime = (timeDayInt * 24) + timeHourInt

		# check for user message
		# regex: Only text around quotes, avoids long messages
		messageInputTemp = re.search('(["].{0,10000}["])', self.comment.body)
		if messageInputTemp:
			self._messageInput = messageInputTemp.group(0)


	def save_to_db(self):
		"""
		Saves the permalink comment, the time, and the message to the DB
		"""

		# connection
		addToDB = Connect()

		# Converting time
		replyDate = datetime.now(timezone('UTC')) + timedelta(hours=self.hours)
		#9999/12/31 HH/MM/SS
		replyDate = format(replyDate, '%Y-%m-%d %H:%M:%S')

		addToDB.execute("INSERT INTO %s VALUES ('%s', %s, '%s', '%s')" %(
						DB_TABLE, 
						self.comment.permalink, 
						self._messageInput, 
						replyDate, 
						self.comment.author))
		addToDB.commit()
		addToDB.close()
