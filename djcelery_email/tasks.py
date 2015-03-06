from django.conf import settings
from django.core.mail import get_connection

try:
    from celery import shared_task
except ImportError:
    from celery.decorators import task as shared_task

# Make sure our AppConf is loaded properly.
import djcelery_email.conf  # noqa
from djcelery_email.utils import from_dict, to_dict

# Messages *must* be dicts, not instances of the EmailMessage class
# This is because we expect Celery to use JSON encoding, and we want to prevent
# code assuming otherwise.

TASK_CONFIG = {'name': 'djcelery_email_send_multiple', 'ignore_result': True}
TASK_CONFIG.update(settings.CELERY_EMAIL_TASK_CONFIG)


@shared_task(**TASK_CONFIG)
def send_emails(messages, backend_kwargs):
    # backward compat: catch sending object
    if hasattr(messages, 'from_email'):
        messages = [to_dict(messages)]

    # backward compat: catch send_email (not send_email*s*) case.
    elif isinstance(messages, dict):
        messages = [messages]

    # backward compat: iterable of objects
    elif len(messages) > 0 and hasattr(messages[0], 'from_email'):
        messages = [to_dict(m) for m in messages]

    conn = get_connection(backend=settings.CELERY_EMAIL_BACKEND, **backend_kwargs)
    conn.open()

    for message in messages:
        try:
            conn.send_messages([from_dict(message)])
            logger.debug("Successfully sent email message to %r.", message['to'])
        except Exception as e:
            # Not expecting any specific kind of exception here because it
            # could be any number of things, depending on the backend
            logger.warning("Failed to send email message to %r, retrying. (%r)",
                           message['to'], e)
            send_emails.retry([[message], backend_kwargs], exc=e, throw=False)

    conn.close()


# backwards compatibility
SendEmailTask = send_email = send_emails


try:
    from celery.utils.log import get_task_logger
    logger = get_task_logger(__name__)
except ImportError:
    logger = send_emails.get_logger()
