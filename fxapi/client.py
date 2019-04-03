import hashlib
import requests
import re
import time
import random
from lxml import html, etree
from urllib.parse import urlparse, parse_qsl


class Client:
	BASE_URL = 'https://www.fxp.co.il'

	def __init__(self):
		self._events = {}

		self.sess = requests.Session()
		self.sess.headers.update({
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.98 Safari/537.36'
		})

		self._is_logged_in = False

		self.username = None
		self.userid = None
		self.securitytoken = 'guest'
		self.uienfxp = None

	def login(self, username, password):
		if self._is_logged_in:
			return False

		md5pass = hashlib.md5(password.encode()).hexdigest()
		login_req = self.sess.post(f'{self.BASE_URL}/login.php', params={
			'do': 'login',
			'web_fast_fxp': 1
		}, data={
			'vb_login_username': username,
			'vb_login_password': '',
			's': '',
			'securitytoken': self.securitytoken,
			'do': 'login',
			'cookieuser': 1,
			'vb_login_md5password': md5pass,
			'vb_login_md5password_utf': md5pass
		})

		self.userid = login_req.cookies.get('bb_userid')

		if not self.userid:
			return False

		self.username = username

		home_req = self.sess.get(self.BASE_URL, params={
			'web_fast_fxp': 1
		})

		self.securitytoken = re.search(r'SECURITYTOKEN = "(.+?)";', home_req.text).group(1)
		self.uienfxp = re.search(r'uienfxp = "(.+?)";', home_req.text).group(1)

		self._is_logged_in = True

		return True

	def create(self):
		if self._is_logged_in:
			return False

		onesignal_uuid = self.sess.post('https://onesignal.com/api/v1/players', data={
			'device_type': 5,
			'app_id': '56dedbbf-a266-4d9d-9334-dd05d918a530',
			'identifier': random.randrange(1, 10**10),
		}).json().get('id')

		create_req_data = self.sess.post(f'{self.BASE_URL}/ajax.php', data={
			'do': 'fast_question_1',
			'securitytoken': self.securitytoken,
			'uuid': onesignal_uuid,
			'time': int(time.time())
		}).json()

		self.userid = create_req_data.get('userid')
		if not self.userid:
			return False

		self.securitytoken = create_req_data.get('securitytoken')
		self.username = self.get_username_by_id(self.userid)

		self.uienfxp = re.search(r'uienfxp = "(.+?)";', self.sess.get(self.BASE_URL, params={
			'web_fast_fxp': 1
		}).text).group(1)

		self._is_logged_in = True

		return True

	def refresh_securitytoken(self):
		r = self.sess.post(f'{self.BASE_URL}/ajax.php', data={
			'do': 'securitytoken_uienfxp',
			'uienfxp': self.uienfxp,
			'securitytoken': self.securitytoken,
			't': self.securitytoken
		})

		if r.text == 'error':
			return False

		self.securitytoken = r.text
		return True

	def create_thread(self, forum_id, title, content, prefix=None):
		r = self.sess.post(f'{self.BASE_URL}/newthread.php', params={
			'do': 'newthread',
			'f': forum_id
		}, data={
			'prefixid': prefix,
			'subject': title,
			'message_backup': content,
			'message': content,
			'wysiwyg': 1,
			's': '',
			'securitytoken': self.securitytoken,
			'f': forum_id,
			'do': 'postthread',
			'posthash': '',
			'poststarttime': int(time.time()),
			'loggedinuser': self.userid,
			'signature': 1,
			'parseurl': 1
		})
		return dict(parse_qsl(urlparse(r.url).query)).get('t', False)

	def post_comment(self, thread_id, content, spam_prevention=False):
		if spam_prevention:
			content += f' [COLOR=#fafafa]{random.randrange(1, 10**4)}[/COLOR]'

		r = self.sess.post(f'{self.BASE_URL}/newreply.php', params={
			'do': 'postreply',
			't': thread_id
		}, data={
			'securitytoken': self.securitytoken,
			'ajax': 1,
			'message_backup': content,
			'message': content,
			'wysiwyg': 1,
			'signature': 1,
			'fromquickreply': 1,
			's': '',
			'do': 'postreply',
			't': thread_id,
			'specifiedpost': 1,
			'parseurl': 1,
			'loggedinuser': self.userid,
			'poststarttime': int(time.time())
		})

		comment_id = etree.fromstring(r.content).xpath('//postbits/newpostid/text()')

		return comment_id[0] if len(comment_id) > 0 else False

	def report_comment(self, comment_id, reason):
		r = self.sess.post(f'{self.BASE_URL}/report.php', params={
			'do': 'sendemail'
		}, data={
			'reason': reason,
			'postid': comment_id,
			's': '',
			'securitytoken': self.securitytoken,
			'do': 'sendemail'
		})
		return not r.url == f'{self.BASE_URL}/report.php?do=sendemail'

	def like_comment(self, comment_id):
		self.sess.post(f'{self.BASE_URL}/ajax.php', data={
			'do': 'add_like',
			'postid': comment_id,
			'securitytoken': self.securitytoken
		})

		# check if user liked the comment
		r = self.sess.post(f'{self.BASE_URL}/ajax.php', data={
			'do': 'wholikepost',
			'postid': comment_id,
			'securitytoken': self.securitytoken
		})
		return str(self.userid) in re.findall(r'php\?u=(.*?)"', r.text)

	def create_private_chat(self, title, content, to):
		r = self.sess.post(f'{self.BASE_URL}/private_chat.php', data={
			'securitytoken': self.securitytoken,
			'do': 'insertpm',
			'recipients': to,
			'title': title,
			'message': content,
			'savecopy': 1,
			'signature': 1,
			'parseurl': 1,
			'frompage': 1
		})
		if 'parentpmid' in r.text:
			return r.json().get('parentpmid')
		else:
			return False

	def send_private_chat(self, to, pmid, content):
		r = self.sess.post(f'{self.BASE_URL}/private_chat.php', data={
			'message': content,
			'fromquickreply': 1,
			'securitytoken': self.securitytoken,
			'do': 'insertpm',
			'pmid': pmid,
			'loggedinuser': self.userid,
			'parseurl': 1,
			'signature': 1,
			'title': 'תגובה להודעה: ',
			'recipients': to,
			'forward': 0,
			'savecopy': 1,
			'fastchatpm': 1,
			'wysiwyg': 1
		})
		return 'pmid' in r.text

	@classmethod
	def get_username_by_id(self, userid):
		r = requests.get(f'{self.BASE_URL}/member.php', params={
			'u': userid
		}).text
		return html.fromstring(r.content).xpath('//span[@class="member_username"]/span/text()')[0]

	@classmethod
	def get_id_by_username(self, username):
		r = requests.get(f'{self.BASE_URL}/member.php', params={
			'username': username
		})
		return html.fromstring(r.content).xpath('//div[@class="follow-btn noselectea"]/@data-followid')[0]

	@classmethod
	def verify_username(self, username):
		r = requests.post(f'{self.BASE_URL}/ajax.php', params={
			'do': 'verifyusername'
		}, data={
			'securitytoken': 'guest',
			'do': 'verifyusername',
			'username': username
		})
		return etree.fromstring(r.content).xpath('//response/status/text()')[0] != 'invalid'