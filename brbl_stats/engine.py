import datetime
import json
import logging

from apscheduler.schedulers import blocking
from instaparser import agents
from instaparser import entities
import requests

from brbl_stats import db

log = logging.getLogger(__name__)

sched = blocking.BlockingScheduler()
agent = agents.Agent()


@sched.scheduled_job('interval', minutes=30)
def update_info():
    log.info("Starting update user stats!")
    log.info("Download user list")
    resp = requests.get("https://raw.githubusercontent.com/posox/brbl-stats/master/accounts.json")
    if not resp.ok:
        log.error("Failed to get account list: %s", resp.reason)
        return
    with db.get_session() as session:
        db_users = set(map(lambda x: x[0], session.query(db.User.name)))
        for acc_id in json.loads(resp.content)["accounts"]:
            if acc_id in db_users:
                db_users.remove(acc_id)
            try:
                data = _get_user_data(session, acc_id)
            except Exception as e:
                log.error("Failed to get data for account: %s\n%s", acc_id, e)
                continue
        session.query(db.User) \
            .filter(db.User.name.in_(db_users)) \
            .delete(synchronize_session='fetch')
        session.merge(db.Info(id=1, last_updated=datetime.datetime.utcnow()))
        session.commit()
    log.info("Update stats was finished!")


def _get_user_data(session, account_name):
    account = entities.Account(account_name)
    data, _ = agent.get_media(account)
    rate = 0
    counter = 0
    curr_time = datetime.datetime.utcnow()
    for i in range(min(len(data), 12)):
        post_date = datetime.datetime.fromtimestamp(data[i].date)
        delta = curr_time - post_date
        if delta.days <= 21:
            counter += 1
            rate += data[i].likes_count + data[i].comments_count
    user = db.User(
        name=account_name,
        followers=account.followers_count,
        posts=account.media_count,
        rate=rate / float(counter or 1),
        rate_posts=counter,
        profile_pic_url=account.profile_pic_url,
        er=rate * 100.0 / (counter or 1) / account.followers_count)
    session.merge(user)


if __name__ == "__main__":
    sched.start()
