#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import sys
sys.path.insert(0, 'lib')

import logging
import base64
import io
import webapp2
import model
from common import common_request
from webapp2 import uri_for
from oauth.handler import OAUTH_ROUTES
from model import Users, Credentials
from google.appengine.api import urlfetch
from apiclient.http import MediaIoBaseUpload
from oauth2client.appengine import StorageByKeyName
from oauth2client.client import AccessTokenRefreshError
import httplib2
import util

DEBUG = True


class Utilities(object):
    @classmethod
    def _init_handler(cls, rrequest):
        rrequest.add_parameter('title', 'Glass Notifier')
        rrequest.add_breadcrumb('Home', uri_for('home'))
        brand = model.Link('Glass Notifications', uri_for('home'))
        nav_links = list()
        nav_links.append(model.Link('About', '#'))
        nav_links.append(model.Link('Contact', '#'))
        rrequest.add_parameter('brand', brand)
        rrequest.add_parameter('nav_links', nav_links)


class RootHandler(webapp2.RequestHandler):
    @common_request
    def get(self):
        Utilities._init_handler(self)
        self.render('index.html')


class OAuthSetupHandler(webapp2.RequestHandler):
    @util.auth_required
    @common_request
    def get(self):
        Utilities._init_handler(self)
        self.render('oauth-success.html')


class AddToTimelineHandler(webapp2.RequestHandler):

    @common_request
    def get(self):
        Utilities._init_handler(self)
        self.render('add-to-timeline.html')

    @common_request
    def post(self):
        Utilities._init_handler(self)
        if self.empty_query_string('user_email', 'message'):
            self.render('add-to-timeline.html')
        else:
            user_email = self.get_parameter('user_email', None)
            logging.debug('Request Email (%s)' % user_email)
            user_entity = Users.get_by_key_name(key_names=user_email)
            if not user_entity:
                self.add_error('Unknown email address. Have you registered with the service ?')
            else:
                user_id = user_entity.credentials_key
                credentials = StorageByKeyName(Credentials, user_id, 'credentials').get()
                mirror_service = util.create_service('mirror', 'v1', credentials)

                credentials_valid = False
                # make sure credentials are valid
                try:
                    credentials.refresh(httplib2.Http())
                    credentials_valid = True
                except AccessTokenRefreshError:
                    # Access has been revoked.
                    util.store_userdetails(self, '', '')
                    credentials_entity = Credentials.get_by_key_name(self.userid)
                    user_entity_delete = Users.get_by_key_name(key_names=user_email)
                    if credentials_entity:
                        credentials_entity.delete()
                    if user_entity_delete:
                        user_entity_delete.delete()

                if credentials_valid:
                    message = self.get_parameter('message', None)
                    is_html = self.get_parameter('is_html', 'False') == 'True'
                    image_url = self.get_parameter('image_url', None)
                    image = self.get_parameter('image', None)

                    logging.info('Inserting timeline item for (%s)' % user_email)
                    body = {
                        'notification': {'level': 'DEFAULT'},
                        'menuItems': [
                            {'action': 'DELETE'}
                        ]
                    }
                    if is_html:
                        body['html'] = message
                    else:
                        body['text'] = message

                    if image_url:
                        if image_url.startswith('/'):
                            image_url = util.get_full_url(self, image_url)
                        resp = urlfetch.fetch(image_url, deadline=20)
                        media = MediaIoBaseUpload(io.BytesIO(resp.content), mimetype='image/jpeg', resumable=True)
                    elif image:
                        media = MediaIoBaseUpload(io.BytesIO(base64.b64decode(image)), mimetype='image/jpeg')
                    else:
                        media = None

                    # self.mirror_service is initialized in util.auth_required.
                    mirror_service.timeline().insert(body=body, media_body=media).execute()

                    self.add_parameter('success', True)
                    self.add_to_json('success', True)
                    logging.info('Successfully inserted timeline item for (%s)' % user_email)
                else:
                    self.add_error('Revoked Credentials.')

            self.render('add-to-timeline.html')


APP_ROUTES = [
    webapp2.Route('/', handler='main.RootHandler', name='home'),
    webapp2.Route('/oauthSetup', handler='main.OAuthSetupHandler', name='oauth_setup'),
    webapp2.Route('/addToTimeLine', handler='main.AddToTimelineHandler', name='add_to_timeline')
]

ALL_ROUTES = APP_ROUTES + OAUTH_ROUTES

application = webapp2.WSGIApplication(ALL_ROUTES, debug=DEBUG)
