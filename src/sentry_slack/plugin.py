"""
sentry_slack.plugin
~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2014 by Sentry Team, see AUTHORS for more details.
:license: BSD, see LICENSE for more details.
"""
import sentry_slack

from django import forms

from sentry.plugins.bases import notify
from sentry.utils import json

import urllib
import urllib2
import logging
from cgi import escape

logger = logging.getLogger('sentry.plugins.slack')

LEVEL_TO_COLOR = {
    'debug': 'cfd3da',
    'info': '2788ce',
    'warning': 'f18500',
    'error': 'f43f20',
    'fatal': 'd20f2a',
}


class SlackOptionsForm(notify.NotificationConfigurationForm):
    webhook = forms.CharField(
        help_text='Your custom Slack webhook URL',
        widget=forms.TextInput(attrs={'class': 'span8'}))
    new_only = forms.BooleanField(
        help_text='Only notify on new events or regressions',
        required=False)


class SlackPlugin(notify.NotificationPlugin):
    author = 'Augustus'
    author_url = 'https://github.com/augiwan/sentry-slack'
    description = 'Post every single new exception to a Slack channel.'
    resource_links = (
        ('Bug Tracker', 'https://github.com/getsentry/sentry-slack/issues'),
        ('Source', 'https://github.com/getsentry/sentry-slack'),
    )

    title = 'Slack by augiwan'
    slug = 'slack'
    conf_key = 'slack'
    description = 'Send errors to Slack'
    version = sentry_slack.VERSION
    project_conf_form = SlackOptionsForm

    def is_configured(self, project):
        return all((self.get_option(k, project) for k in ('webhook',)))

    def color_for_group(self, group):
        return '#' + LEVEL_TO_COLOR.get(group.get_level_display(), 'error')

    def notify_users(self, group, event, fail_silently=False):
        webhook = self.get_option('webhook', event.project)
        project = event.project
        team = event.team

        title = '%s on <%s|%s %s>' % (
            'New event' if group.times_seen == 1 else 'Regression',
            group.get_absolute_url(),
            escape(team.name.encode('utf-8')),
            escape(project.name.encode('utf-8')),
        )

        message = getattr(group, 'message_short', group.message).encode('utf-8')
        culprit = getattr(group, 'title', group.culprit).encode('utf-8')
        user_email = getattr(group, 'user', group.user['email']).encode('utf-8')

        # They can be the same if there is no culprit
        # So we set culprit to an empty string instead of duplicating the text
        if message == culprit:
            culprit = ''
            
        message = ''.join([message, ' by ', user_email])

        payload = {
            'parse': 'none',
            'text': title,
            'attachments': [{
                'color': self.color_for_group(group),
                'fields': [{
                    'title': escape(message),
                    'value': escape(culprit),
                    'short': False,
                }]
            }]
        }

        values = {'payload': json.dumps(payload)}

        data = urllib.urlencode(values)
        request = urllib2.Request(webhook, data)
        try:
            return urllib2.urlopen(request).read()
        except urllib2.URLError:
            logger.error('Could not connect to Slack.', exc_info=True)
            raise
        except urllib2.HTTPError as e:
            logger.error('Error posting to Slack: %s', e.read(), exc_info=True)
            raise
        
    def post_process(self, group, event, is_new, is_sample, **kwargs):
        new_only = self.get_option('new_only', event.project)
        
        if new_only and not is_new:
            return

        if not self.should_notify(group, event):
            return

        self.notify_users(group, event)
